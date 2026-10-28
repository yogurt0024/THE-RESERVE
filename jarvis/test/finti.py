"""Finti Ollama, Claude e internet per i test: rispondono come quelli veri, ma senza rete e senza costi."""

import base64
import json
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def avvia(gestore):
    """Avvia un server su una porta libera. Restituisce (server, indirizzo)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), gestore)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _testo(messaggio):
    c = messaggio["content"]
    return c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict))


class FintoOllama(BaseHTTPRequestHandler):
    """qwen3.5:4b è il modello veloce, qwen3.6:35b-a3b quello grande; qwen3:4b ragiona sempre e con
    think=false scrive il ragionamento nel testo."""

    richieste = []
    CAPACITA = {"qwen3.5:4b": ["completion", "tools", "thinking", "vision"],
                "qwen3.6:35b-a3b": ["completion", "tools", "thinking", "vision"],
                "qwen3:4b": ["completion", "tools", "thinking"]}

    def log_message(self, *argomenti):
        pass

    def _json(self, dati, codice=200):
        corpo = json.dumps(dati).encode()
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        self._json({"models": [{"name": nome} for nome in self.CAPACITA]})

    def do_POST(self):
        dati = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FintoOllama.richieste.append({"percorso": self.path, **dati})
        modello = dati["model"]
        if self.path == "/api/show":
            return self._json({"capabilities": self.CAPACITA[modello]})
        if not dati["messages"]:
            return self._json({"done": True})
        if dati.get("stream") is False and "format" not in dati:  # diario, occhi: una risposta sola
            ultimo = dati["messages"][-1]
            contenuto = "Vedo un errore di Minecraft" if ultimo.get("images") else f"Riassunto di {modello}"
            return self._json({"message": {"role": "assistant", "content": contenuto}, "done": True})
        if "format" in dati:  # il modulo di attenzione: decide se una frase senza nome era per Jarvis
            frase = dati["messages"][-1]["content"].rpartition("Frase appena sentita:")[2].lower()
            decisione = "ignora" if "arrivo" in frase else "bisogno" if "quanto fa" in frase else "rivolta"
            return self._json({"message": {"role": "assistant", "content": json.dumps({"decisione": decisione})},
                               "done": True})
        ultimo = dati["messages"][-1]
        strumenti = [s["function"]["name"] for s in dati.get("tools", [])]
        parti = []
        if dati.get("think"):
            parti.append({"message": {"content": "", "thinking": "ragiono"}})
        elif modello == "qwen3:4b":
            parti += [{"message": {"content": c}} for c in ["Okay, the user ", "asks something.", "</think>", "\n\n"]]
        domanda = _testo(ultimo).lower() if ultimo["role"] == "user" else ""
        if "relatività" in domanda and "chiedi_al_cervello_avanzato" in strumenti:
            parti.append({"message": {"content": "", "tool_calls": [
                {"function": {"name": "chiedi_al_cervello_avanzato", "arguments": {"motivo": "difficile"}}}]}})
        elif "tempo" in domanda and "meteo" in strumenti:
            parti.append({"message": {"content": "", "tool_calls": [
                {"function": {"name": "meteo", "arguments": {"citta": "Cagliari"}}}]}})
        elif ultimo["role"] == "tool":
            parti += [{"message": {"content": c}} for c in ["Adesso a Cagliari ", "fa **22°C**."]]
        else:
            parti += [{"message": {"content": c}} for c in [f"Risposta di {modello}: ", _testo(ultimo)]]
        parti.append({"message": {"content": ""}, "done": True})
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            for parte in parti:
                self.wfile.write((json.dumps(parte) + "\n").encode())
                self.wfile.flush()
                if "lento" in domanda:  # per provare ad annullare un compito mentre è in corso
                    time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Jarvis ha smesso di leggere: il compito è stato annullato


class FintoClaude(BaseHTTPRequestHandler):
    """Risponde in streaming (SSE) come l'API di Anthropic. La ricerca web non è attiva sull'account."""

    protocol_version = "HTTP/1.1"
    richieste = []

    def log_message(self, *argomenti):
        pass

    def _errore(self, codice, tipo, messaggio):
        corpo = json.dumps({"type": "error", "error": {"type": tipo, "message": messaggio}}).encode()
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _flusso(self, blocchi, fine, modello):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()

        def evento(tipo, dati):
            self.wfile.write(f"event: {tipo}\ndata: {json.dumps(dati)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.002)

        evento("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": modello, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 1}}})
        for i, blocco in enumerate(blocchi):
            if blocco[0] == "pensiero":
                evento("content_block_start", {"type": "content_block_start", "index": i,
                                               "content_block": {"type": "thinking", "thinking": "", "signature": ""}})
                evento("content_block_delta", {"type": "content_block_delta", "index": i,
                                               "delta": {"type": "signature_delta", "signature": "firma"}})
            elif blocco[0] == "testo":
                evento("content_block_start", {"type": "content_block_start", "index": i,
                                               "content_block": {"type": "text", "text": ""}})
                for pezzo in blocco[1]:
                    evento("content_block_delta", {"type": "content_block_delta", "index": i,
                                                   "delta": {"type": "text_delta", "text": pezzo}})
            else:
                _, identificativo, nome, argomenti = blocco
                evento("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                    "type": "tool_use", "id": identificativo, "name": nome, "input": {}}})
                evento("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {
                    "type": "input_json_delta", "partial_json": json.dumps(argomenti)}})
            evento("content_block_stop", {"type": "content_block_stop", "index": i})
        evento("message_delta", {"type": "message_delta", "delta": {"stop_reason": fine, "stop_sequence": None},
                                 "usage": {"output_tokens": 200}})
        evento("message_stop", {"type": "message_stop"})

    def do_POST(self):
        dati = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FintoClaude.richieste.append(dati)
        ultimo, modello = dati["messages"][-1], dati["model"]
        domanda = _testo(ultimo).lower()
        strumenti = [s.get("name") for s in dati.get("tools", [])]
        if "web_search" in strumenti:
            return self._errore(400, "invalid_request_error", "web_search is not enabled for this organization")
        if "credito" in domanda:
            return self._errore(400, "invalid_request_error",
                                "Your credit balance is too low to access the Anthropic API.")
        risultati = [b for b in ultimo["content"] if b.get("type") == "tool_result"] \
            if isinstance(ultimo["content"], list) else []
        if risultati:
            return self._flusso([("pensiero",), ("testo", ["**A Cagliari** fa bello ", "😊, signore."])],
                                "end_turn", modello)
        if "rifiuta" in domanda:
            return self._flusso([("pensiero",)], "refusal", modello)
        if "tempo" in domanda:
            return self._flusso([("pensiero",), ("testo", ["Controllo."]),
                                 ("strumento", "toolu_1", "meteo", {"citta": "Cagliari"})], "tool_use", modello)
        if "argomenti sbagliati" in domanda:
            return self._flusso([("strumento", "toolu_2", "timer", {"minuti": "cinque"})], "tool_use", modello)
        self._flusso([("pensiero",), ("testo", ["Risposta di Claude: ", _testo(ultimo)])], "end_turn", modello)


def internet_finto(url, parametri=None):
    """Sostituisce strumenti._scarica: dati meteo inventati per Cagliari e due notizie."""
    if "news.google" in url:
        return ("<rss><channel><item><title>Esce il nuovo aggiornamento di Minecraft</title></item>"
                "<item><title>Sole in tutta la Sardegna</title></item></channel></rss>").encode()
    if "geocoding" in url:
        return json.dumps({"results": [{"name": "Cagliari", "latitude": 39.2, "longitude": 9.1,
                                        "admin1": "Sardegna", "country": "Italia"}]}).encode()
    return json.dumps({
        "current": {"temperature_2m": 21.4, "apparent_temperature": 20.1, "relative_humidity_2m": 63,
                    "weather_code": 2, "wind_speed_10m": 14.8},
        "daily": {"time": ["2026-10-28", "2026-10-29", "2026-10-30"], "weather_code": [2, 61, 0],
                  "temperature_2m_max": [22.1, 19.0, 20.3], "temperature_2m_min": [15.2, 14.0, 13.1],
                  "precipitation_probability_max": [10, 80, None]},
    }).encode()


class FintoElevenLabs(BaseHTTPRequestHandler):
    """Risponde come l'API di ElevenLabs. "chiave-buona" è di un piano a pagamento, "chiave-gratis" del piano
    gratuito, che non può creare voci; la voce "esaurita" ha finito i crediti."""

    CHIAVI = {"chiave-buona": "creator", "chiave-gratis": "free"}
    VOCI = [{"voice_id": "anna", "name": "Anna", "category": "premade", "labels": {"gender": "female"}},
            {"voice_id": "bruno", "name": "Bruno", "category": "premade", "labels": {"gender": "male", "accent": "american"}},
            {"voice_id": "giorgio", "name": "Giorgio", "category": "premade",
             "labels": {"gender": "male", "accent": "british", "description": "warm"}}]

    richieste = []

    def log_message(self, *argomenti):
        pass

    def _rispondi(self, codice, corpo, tipo="application/json"):
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo).encode()
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _errore(self, codice, stato):
        self._rispondi(codice, {"detail": {"status": stato, "message": stato}})

    def do_GET(self):
        FintoElevenLabs.richieste.append({"percorso": self.path})
        piano = self.CHIAVI.get(self.headers.get("xi-api-key"))
        if piano is None:
            return self._errore(401, "invalid_api_key")
        if self.path == "/v1/voices":
            return self._rispondi(200, {"voices": self.VOCI})
        self._rispondi(200, {"tier": piano, "character_count": 1200, "character_limit": 10000})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FintoElevenLabs.richieste.append({"percorso": self.path, **corpo})
        piano = self.CHIAVI.get(self.headers.get("xi-api-key"))
        if piano is None:
            return self._errore(401, "invalid_api_key")
        percorso = self.path.split("?")[0]
        if percorso.startswith("/v1/text-to-voice") and piano == "free":
            return self._rispondi(403, {"detail": {"status": "payment_required", "message": (
                "Creating a voice through the API is only available on a paid plan.")}})
        if percorso == "/v1/text-to-voice/design":
            anteprime = [{"generated_voice_id": f"provvisoria-{n}", "media_type": "audio/pcm", "duration_secs": 1.0,
                          "audio_base_64": base64.b64encode(struct.pack("<2400h", *[n * 1000] * 2400)).decode()}
                         for n in (1, 2, 3)]
            return self._rispondi(200, {"previews": anteprime, "text": corpo["text"]})
        if percorso == "/v1/text-to-voice":
            return self._rispondi(200, {"voice_id": "voce-jarvis", "name": corpo["voice_name"]})
        if percorso == "/v1/text-to-speech/esaurita":
            return self._errore(401, "quota_exceeded")
        if percorso.split("/")[-1] in ("voce-jarvis", "giorgio", "bruno", "anna"):
            campioni = 10 * len(corpo["text"])
            return self._rispondi(200, struct.pack(f"<{campioni}h", *[3000] * campioni), "audio/pcm")
        self._errore(404, "voice_not_found")


class FintoGitHub(BaseHTTPRequestHandler):
    """Risponde come GitHub: l'ultima versione (sha) e il pacchetto ZIP del ramo."""

    sha = "abc123"
    archivio = b""

    def log_message(self, *argomenti):
        pass

    def do_GET(self):
        if "/commits/" in self.path:
            corpo, tipo = json.dumps({"sha": FintoGitHub.sha}).encode(), "application/json"
        elif "/zip/refs/heads/" in self.path:
            corpo, tipo = FintoGitHub.archivio, "application/zip"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)
