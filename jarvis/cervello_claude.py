"""Il cervello avanzato di Jarvis: Claude, tramite l'API di Anthropic.

Si usa per il ragionamento profondo, quando il modello locale chiede aiuto, oppure sempre
(impostazione "cervello" in config.json). Servono la libreria ufficiale
(python -m pip install anthropic) e una chiave API, che Jarvis salva in dati/chiave_claude.txt.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import strumenti

try:
    import anthropic
except ImportError:  # non installata, oppure bloccata dal Controllo intelligente delle app
    anthropic = None

CARTELLA_DATI = Path(__file__).resolve().parent / "dati"
FILE_CHIAVE = CARTELLA_DATI / "chiave_claude.txt"
FILE_COSTI = CARTELLA_DATI / "costi.json"

# Dollari per milione di token: (ingresso, uscita).
PREZZI = {
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5": (5.0, 25.0), "claude-opus-4-8": (5.0, 25.0),
}
PREZZO_RICERCA = 0.01  # dollari per ogni ricerca sul web
GIRI = 6  # quante volte di fila Claude può usare strumenti in una risposta
RICERCA_WEB = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}
# Se i filtri di sicurezza rifiutano per errore, la richiesta viene ripetuta su un altro modello.
BETA_FALLBACK = "server-side-fallback-2026-07-01"


class ErroreClaude(Exception):
    pass


class Interrotto(Exception):
    pass


class _RicercaNonDisponibile(Exception):
    pass


class CervelloClaude:
    def __init__(self, config):
        self.modello = config["modello_claude"]
        self.sforzo = config["sforzo_claude"]
        self.ricerca_web = bool(config["internet"])
        self.client = None
        self.problema = ""
        self.costo_ultima_risposta = 0.0
        self.collega()

    @property
    def pronto(self):
        return self.client is not None

    def collega(self):
        if anthropic is None:
            self.problema = "manca la libreria di Claude: scrivi  python -m pip install anthropic"
            self.client = None
            return
        try:
            chiave = FILE_CHIAVE.read_text(encoding="utf-8-sig").strip()
        except OSError:
            chiave = ""
        chiave = chiave or os.environ.get("ANTHROPIC_API_KEY", "")
        if not chiave:
            self.problema = "manca la chiave API: usa il comando /chiave"
            self.client = None
            return
        self.client = anthropic.Anthropic(api_key=chiave)
        self.problema = ""

    def salva_chiave(self, chiave):
        chiave = chiave.strip()
        if not chiave.startswith("sk-ant-"):
            return "Questa non sembra una chiave API di Anthropic: deve iniziare con sk-ant-."
        FILE_CHIAVE.parent.mkdir(exist_ok=True)
        FILE_CHIAVE.write_text(chiave + "\n", encoding="utf-8")
        self.collega()
        return "Chiave salvata sul PC: il cervello avanzato è pronto." if self.pronto else self.problema

    # --- Costi ---

    def _registra_costo(self, risposta):
        prezzo_in, prezzo_out = PREZZI.get(risposta.model, PREZZI.get(self.modello, (0.0, 0.0)))
        uso = risposta.usage
        ingresso = (uso.input_tokens or 0) + (getattr(uso, "cache_creation_input_tokens", 0) or 0) * 1.25 \
            + (getattr(uso, "cache_read_input_tokens", 0) or 0) * 0.05
        ricerche = getattr(getattr(uso, "server_tool_use", None), "web_search_requests", 0) or 0
        costo = ingresso * prezzo_in / 1e6 + (uso.output_tokens or 0) * prezzo_out / 1e6 + ricerche * PREZZO_RICERCA
        self.costo_ultima_risposta += costo
        dati = leggi_costi()
        mese = f"{datetime.now():%Y-%m}"
        dati["mesi"][mese] = dati["mesi"].get(mese, 0.0) + costo
        dati["totale"] = dati.get("totale", 0.0) + costo
        try:
            FILE_COSTI.parent.mkdir(exist_ok=True)
            FILE_COSTI.write_text(json.dumps(dati, indent=2), encoding="utf-8")
        except OSError:
            pass

    # --- Risposte ---

    def rispondi(self, sistema, cronologia, schemi, esegui, stop=None):
        """Risponde alla conversazione (solo testi) producendo eventi per Jarvis:

        ("grezzo", testo)   un pezzo di risposta, ancora da ripulire
        ("pensiero",)       Claude sta ragionando
        ("info", messaggio) uno strumento in uso o un avviso
        `schemi` sono gli strumenti di Jarvis (None = nessuno strumento); `esegui(nome, argomenti)` li esegue.
        """
        self.costo_ultima_risposta = 0.0
        messaggi = []
        for m in cronologia:
            if messaggi and messaggi[-1]["role"] == m["role"]:  # per esempio il resoconto di un compito finito
                messaggi[-1]["content"] += "\n\n" + m["content"]
            else:
                messaggi.append({"role": m["role"], "content": m["content"]})
        while messaggi and messaggi[0]["role"] != "user":  # la conversazione deve iniziare dall'utente
            messaggi.pop(0)
        errori_json = 0
        for _ in range(GIRI):
            strumenti_claude = []
            if schemi is not None:
                strumenti_claude = [{"name": s["function"]["name"], "description": s["function"]["description"],
                                     "input_schema": s["function"]["parameters"], "eager_input_streaming": True}
                                    for s in schemi]
                if self.ricerca_web:
                    strumenti_claude.append(RICERCA_WEB)
            try:
                risposta = yield from self._flusso(sistema, messaggi, strumenti_claude, stop)
            except _RicercaNonDisponibile:
                self.ricerca_web = False  # la ricerca sul web non è attiva su questo account: si fa senza
                continue
            except ValueError:
                # JSON di uno strumento così rotto che la libreria non riesce a leggerlo: si riprova.
                errori_json += 1
                if errori_json > 2:
                    raise ErroreClaude("Claude ha risposto in un formato illeggibile: riprova.") from None
                continue

            if risposta.stop_reason == "pause_turn":  # la ricerca sul web va avanti: si rimanda tutto
                messaggi.append({"role": "assistant", "content": risposta.content})
                continue
            if risposta.stop_reason == "refusal":
                yield ("info", "Claude ha preferito non rispondere a questa richiesta.")
                return
            usi = [b for b in risposta.content if b.type == "tool_use"]
            if not usi:
                return
            if risposta.stop_reason == "max_tokens":
                yield ("info", "La risposta era troppo lunga ed è stata interrotta.")
                return

            risultati = []
            for blocco in usi:
                problema = strumenti.valida(blocco.name, blocco.input, schemi)
                if problema:
                    risultati.append({"type": "tool_result", "tool_use_id": blocco.id, "is_error": True,
                                      "content": f"Argomenti non validi ({problema}): "
                                                 f"{json.dumps(blocco.input, ensure_ascii=False)}"})
                    continue
                yield ("info", strumenti.descrivi(blocco.name, blocco.input))
                testo = esegui(blocco.name, blocco.input)
                risultati.append({"type": "tool_result", "tool_use_id": blocco.id, "content": testo,
                                  "is_error": testo.startswith("Errore:")})
            # I blocchi di ragionamento vanno rimandati identici, insieme a tutto il resto.
            messaggi.append({"role": "assistant", "content": risposta.content})
            messaggi.append({"role": "user", "content": risultati})
        yield ("info", "Ho usato troppi strumenti di fila: mi fermo qui.")

    def _flusso(self, sistema, messaggi, strumenti_claude, stop):
        richiesta = dict(model=self.modello, max_tokens=64000, system=sistema, messages=messaggi,
                         output_config={"effort": self.sforzo},
                         extra_headers={"anthropic-beta": BETA_FALLBACK}, extra_body={"fallbacks": "default"})
        if strumenti_claude:
            richiesta["tools"] = strumenti_claude
        try:
            with self.client.messages.stream(**richiesta) as flusso:
                for evento in flusso:
                    if stop is not None and stop.is_set():
                        raise Interrotto
                    if evento.type == "content_block_start" and evento.content_block.type in (
                            "thinking", "redacted_thinking"):
                        yield ("pensiero",)
                    elif evento.type == "content_block_delta" and evento.delta.type == "text_delta":
                        yield ("grezzo", evento.delta.text)
                risposta = flusso.get_final_message()
        except anthropic.AuthenticationError:
            raise ErroreClaude("La chiave API di Claude non è valida: inseriscine una nuova con /chiave.") from None
        except anthropic.PermissionDeniedError:
            raise ErroreClaude("La chiave API non ha il permesso di usare questo modello di Claude.") from None
        except anthropic.NotFoundError:
            raise ErroreClaude(f'Il modello "{self.modello}" non esiste: controlla modello_claude in config.json.') from None
        except anthropic.RateLimitError:
            raise ErroreClaude("Troppe richieste a Claude in poco tempo: riprova tra un minuto.") from None
        except anthropic.BadRequestError as e:
            messaggio = str(e)
            if "web_search" in messaggio and self.ricerca_web:
                raise _RicercaNonDisponibile from None
            if "credit balance" in messaggio.lower():
                raise ErroreClaude("Il credito del tuo account Anthropic è finito: ricaricalo su "
                                   "console.anthropic.com.") from None
            raise ErroreClaude(f"Claude non ha accettato la richiesta: {e.message}") from None
        except anthropic.APIStatusError as e:
            raise ErroreClaude(f"Claude non è disponibile in questo momento (errore {e.status_code}).") from None
        except anthropic.APIConnectionError:
            raise ErroreClaude("Non riesco a collegarmi a Claude: controlla la connessione a internet.") from None
        self._registra_costo(risposta)
        return risposta


def leggi_costi():
    try:
        dati = json.loads(FILE_COSTI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dati = {}
    dati.setdefault("mesi", {})
    return dati


def dollari(valore):
    if valore == 0:
        return "$0,00"
    return f"${valore:.4f}".replace(".", ",") if valore < 0.01 else f"${valore:.2f}".replace(".", ",")
