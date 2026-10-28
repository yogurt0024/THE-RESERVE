"""Finti Ollama, Claude e internet per i test: rispondono come quelli veri, ma senza rete e senza costi."""

import json
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
        for parte in parti:
            self.wfile.write((json.dumps(parte) + "\n").encode())
            self.wfile.flush()


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
    """Sostituisce strumenti._scarica: dati meteo inventati per Cagliari."""
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
