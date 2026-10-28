"""Jarvis: assistente personale che gira interamente sul tuo PC grazie a Ollama.

Avvio: doppio clic su avvia.bat, oppure `python jarvis.py`.
Le impostazioni (nome, modello, ...) sono in config.json.
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

FILE_CONFIG = Path(__file__).resolve().parent / "config.json"

CONFIG_PREDEFINITA = {
    "nome": "Jarvis",
    "come_chiamarmi": "",
    "modello": "gemma3:4b",
    "ollama_url": "http://localhost:11434",
    "messaggi_da_ricordare": 20,
}

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

AIUTO = """Comandi:
  /nuova   dimentica la conversazione e ricomincia
  /aiuto   mostra questo messaggio
  /esci    chiude Jarvis (oppure Ctrl+C)"""

# Ollama gira sullo stesso PC: niente proxy di sistema in mezzo.
_connessione = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ErroreOllama(Exception):
    pass


def carica_config():
    config = dict(CONFIG_PREDEFINITA)
    if FILE_CONFIG.exists():
        try:
            # utf-8-sig: il Blocco note di Windows a volte salva con il BOM.
            config.update(json.loads(FILE_CONFIG.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError as e:
            raise SystemExit(f"config.json non è valido (riga {e.lineno}): {e.msg}")
    return config


def prompt_di_sistema(config):
    adesso = datetime.now()
    data = f"{GIORNI[adesso.weekday()]} {adesso.day} {MESI[adesso.month - 1]} {adesso.year}"
    testo = (
        f"Sei {config['nome']}, un assistente personale ispirato al J.A.R.V.I.S. di Iron Man: "
        "cortese, preciso e con un pizzico di ironia. "
        "Rispondi sempre in italiano, in modo chiaro e conciso, "
        "a meno che non ti venga chiesto di approfondire. "
        "Scrivi testo semplice, senza formattazione Markdown (niente asterischi o #), "
        "perché le risposte vengono mostrate in una finestra di testo. "
        "Se non conosci una risposta o non sei sicuro, dillo invece di inventare. "
        "Non hai accesso a internet: le tue conoscenze si fermano al tuo addestramento. "
        f"Oggi è {data} e sono le {adesso:%H:%M}."
    )
    if config["come_chiamarmi"]:
        testo += f' Chiama l\'utente "{config["come_chiamarmi"]}".'
    return testo


def richiesta(config, percorso, dati=None, timeout=300):
    url = config["ollama_url"].rstrip("/") + percorso
    corpo = None if dati is None else json.dumps(dati).encode("utf-8")
    req = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/json"})
    try:
        return _connessione.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            messaggio = json.loads(e.read()).get("error", "")
        except ValueError:
            messaggio = ""
        raise ErroreOllama(messaggio or f"Ollama ha risposto con l'errore {e.code}.") from None
    except OSError:
        raise ErroreOllama(
            "Non riesco a contattare Ollama. Controlla che sia installato e avviato "
            "(l'icona del lama vicino all'orologio di Windows)."
        ) from None


def controlla_modello(config):
    with richiesta(config, "/api/tags", timeout=5) as risposta:
        installati = {m["name"] for m in json.load(risposta).get("models", [])}
    modello = config["modello"]
    if modello not in installati and f"{modello}:latest" not in installati:
        raise ErroreOllama(
            f'Il modello "{modello}" non è installato. '
            f"Apri il Prompt dei comandi e scrivi:\n    ollama pull {modello}"
        )


def carica_modello(config, tieni_in_memoria=None):
    """Senza messaggi, Ollama si limita a caricare il modello (o a scaricarlo con keep_alive 0)."""
    dati = {"model": config["modello"], "messages": [], "stream": False}
    if tieni_in_memoria is not None:
        dati["keep_alive"] = tieni_in_memoria
    richiesta(config, "/api/chat", dati).close()


def chiedi(config, cronologia):
    """Manda la conversazione a Ollama e stampa la risposta man mano che arriva."""
    messaggi = [{"role": "system", "content": prompt_di_sistema(config)}] + cronologia
    dati = {"model": config["modello"], "messages": messaggi, "stream": True}
    pezzi = []
    sta_pensando = False
    try:
        with richiesta(config, "/api/chat", dati) as risposta:
            for riga in risposta:
                if not riga.strip():
                    continue
                parte = json.loads(riga)
                if "error" in parte:
                    raise ErroreOllama(parte["error"])
                messaggio = parte.get("message", {})
                if messaggio.get("thinking") and not pezzi and not sta_pensando:
                    print("(sto pensando...) ", end="", flush=True)
                    sta_pensando = True
                testo = messaggio.get("content", "")
                if not pezzi:
                    testo = testo.lstrip()
                if testo:
                    pezzi.append(testo)
                    print(testo, end="", flush=True)
                if parte.get("done"):
                    break
    except KeyboardInterrupt:
        print(" [interrotto]", end="")
    except OSError:
        raise ErroreOllama("La connessione con Ollama si è interrotta.") from None
    print()
    return "".join(pezzi)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config = carica_config()
    nome = config["nome"]
    limite = max(2, int(config["messaggi_da_ricordare"]))

    print(f"Avvio di {nome} con il modello {config['modello']}...")
    try:
        controlla_modello(config)
        carica_modello(config)
    except ErroreOllama as e:
        raise SystemExit(f"Errore: {e}")
    print(f"{nome} è pronto. Scrivi una domanda, oppure /aiuto per i comandi.\n")

    cronologia = []
    while True:
        try:
            domanda = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not domanda:
            continue
        comando = domanda.lower()
        if comando in ("/esci", "esci"):
            break
        if comando == "/aiuto":
            print(AIUTO + "\n")
            continue
        if comando == "/nuova":
            cronologia.clear()
            print(f"{nome}: Ho dimenticato la conversazione, ricominciamo.\n")
            continue

        cronologia.append({"role": "user", "content": domanda})
        print(f"{nome}: ", end="", flush=True)
        try:
            risposta = chiedi(config, cronologia)
        except ErroreOllama as e:
            print(f"\n[Errore] {e}\n")
            cronologia.pop()
            continue
        if risposta:
            cronologia.append({"role": "assistant", "content": risposta})
        else:
            cronologia.pop()
        del cronologia[:-limite]
        print()

    print(f"{nome}: Arrivederci!")
    try:
        # Libera la memoria della scheda video, così resta tutta per i giochi.
        carica_modello(config, tieni_in_memoria=0)
    except ErroreOllama:
        pass


if __name__ == "__main__":
    main()
