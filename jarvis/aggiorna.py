"""Aggiorna Jarvis all'ultima versione senza toccare i tuoi dati né le tue scelte.

Uso:  py -3.12 aggiorna.py     (oppure in Jarvis: "Jarvis, aggiornati" o /aggiorna)
Scarica da GitHub la versione nuova e sostituisce i file del programma. La cartella dati (memoria, chiavi,
voci, modelli) non viene toccata; in config.json restano le tue impostazioni e si aggiungono solo quelle nuove.
"""

import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
REPOSITORY = "yogurt0024/THE-RESERVE"
RAMO = "claude/beautiful-gauss-ld6wqw"


class ErroreAggiornamento(Exception):
    pass


def _file_versione():
    return CARTELLA / "dati" / "versione.txt"


def _scarica(indirizzo, timeout=60):
    richiesta = urllib.request.Request(indirizzo, headers={"User-Agent": "Jarvis", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
            return risposta.read()
    except urllib.error.HTTPError as e:
        privato = " Se il repository è privato, scarica lo ZIP a mano." if e.code == 404 else ""
        raise ErroreAggiornamento(f"GitHub ha risposto con l'errore {e.code}.{privato}") from None
    except OSError as e:
        raise ErroreAggiornamento(f"non riesco a collegarmi a GitHub (serve internet): {e}") from None


def _api():
    return os.environ.get("JARVIS_GITHUB_API", "https://api.github.com").rstrip("/")


def _zip():
    return os.environ.get("JARVIS_GITHUB_ZIP", "https://codeload.github.com").rstrip("/")


def ultima_versione():
    """L'identificativo (sha) dell'ultima versione pubblicata su GitHub."""
    dati = json.loads(_scarica(f"{_api()}/repos/{REPOSITORY}/commits/{RAMO}", timeout=15))
    return dati["sha"]


def versione_installata():
    try:
        return _file_versione().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def c_e_un_aggiornamento():
    """True se su GitHub c'è una versione nuova, False se no, None se non si può sapere."""
    installata = versione_installata()
    if not installata:
        return None
    try:
        return ultima_versione() != installata
    except (ErroreAggiornamento, ValueError, KeyError):
        return None


def aggiorna():
    """Scarica e installa l'ultima versione. Restituisce (quanti file sono cambiati, messaggio)."""
    try:
        versione = ultima_versione()
    except (ErroreAggiornamento, ValueError, KeyError):
        versione = ""  # si aggiorna lo stesso, ma senza ricordare quale versione è installata
    archivio = zipfile.ZipFile(io.BytesIO(_scarica(f"{_zip()}/{REPOSITORY}/zip/refs/heads/{RAMO}", timeout=300)))
    nomi = archivio.namelist()
    cervello = next((n for n in nomi if n.endswith("jarvis/cervello.py")), None)
    if cervello is None:
        raise ErroreAggiornamento("nel pacchetto scaricato non trovo Jarvis")
    radice = cervello[:-len("cervello.py")]
    cambiati = 0
    for nome in nomi:
        relativo = nome[len(radice):]
        if not nome.startswith(radice) or nome.endswith("/") or not relativo:
            continue
        parti = Path(relativo).parts
        if parti[0] == "dati" or ".." in parti:  # i dati dell'utente non si toccano mai
            continue
        nuovo = archivio.read(nome)
        destinazione = CARTELLA / relativo
        if relativo == "config.json":
            nuovo = _unisci_config(destinazione, nuovo)
            if nuovo is None:
                continue
        elif destinazione.exists() and destinazione.read_bytes() == nuovo:
            continue
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        destinazione.write_bytes(nuovo)
        cambiati += 1
    if versione:
        _file_versione().parent.mkdir(exist_ok=True)
        _file_versione().write_text(versione + "\n", encoding="utf-8")
    if not cambiati:
        return 0, "Jarvis era già aggiornato."
    return cambiati, f"Aggiornamento installato: {cambiati} {'file cambiato' if cambiati == 1 else 'file cambiati'}."


def _unisci_config(destinazione, nuovo):
    """Tiene le scelte dell'utente e aggiunge solo le impostazioni che prima non c'erano. None se non cambia nulla."""
    try:
        attuale = json.loads(destinazione.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return nuovo  # config.json mancante o rovinato: si prende quello nuovo
    aggiunte = {k: v for k, v in json.loads(nuovo).items() if k not in attuale}
    if not aggiunte:
        return None
    attuale.update(aggiunte)
    return (json.dumps(attuale, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("Scarico l'ultima versione di Jarvis...")
    try:
        _, messaggio = aggiorna()
    except (ErroreAggiornamento, zipfile.BadZipFile) as e:
        raise SystemExit(f"Aggiornamento non riuscito: {e}")
    print(messaggio + " La cartella dati e le tue impostazioni sono rimaste come prima.")


if __name__ == "__main__":
    main()
