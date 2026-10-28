"""Scarica i modelli della voce e dell'ascolto la prima volta che servono (solo libreria standard di Python).

I file finiscono in dati/modelli: se un download si interrompe, alla volta dopo riparte da capo.
"""

import fnmatch
import json
import urllib.request
from pathlib import Path

CARTELLA_MODELLI = Path(__file__).resolve().parent / "dati" / "modelli"
HUGGINGFACE = "https://huggingface.co"


class ErroreDownload(Exception):
    pass


def da_huggingface(repo, file):
    return f"{HUGGINGFACE}/{repo}/resolve/main/{file}"


def file_su_huggingface(repo, schemi):
    """I file di un modello su Hugging Face che corrispondono agli schemi (per esempio "*encoder*int8.onnx")."""
    try:
        with _apri(f"{HUGGINGFACE}/api/models/{repo}") as risposta:
            tutti = [f["rfilename"] for f in json.load(risposta).get("siblings", [])]
    except (OSError, ValueError) as e:
        raise ErroreDownload(f"Non riesco a leggere l'elenco dei file di {repo}: {e}") from None
    for schema in schemi:
        if not any(fnmatch.fnmatch(f, schema) for f in tutti):
            raise ErroreDownload(f"Su Hugging Face non trovo il file {schema} del modello {repo}.")
    return [f for f in tutti if any(fnmatch.fnmatch(f, s) for s in schemi)]


def scarica(indirizzi, destinazione, avanzamento=None):
    """Scarica il file in `destinazione`, se non c'è già, provando gli indirizzi uno dopo l'altro.

    `avanzamento(nome, scaricati, totale)` viene chiamata durante il download (totale è 0 se non si conosce).
    """
    destinazione = Path(destinazione)
    if destinazione.exists():
        return destinazione
    if isinstance(indirizzi, str):
        indirizzi = [indirizzi]
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    parziale = destinazione.with_name(destinazione.name + ".parziale")
    errore = None
    for indirizzo in indirizzi:
        try:
            with _apri(indirizzo) as risposta, open(parziale, "wb") as file:
                totale = int(risposta.headers.get("Content-Length") or 0)
                scaricati = 0
                while blocco := risposta.read(1 << 20):
                    file.write(blocco)
                    scaricati += len(blocco)
                    if avanzamento:
                        avanzamento(destinazione.name, scaricati, totale)
            parziale.replace(destinazione)
            return destinazione
        except OSError as e:
            errore = e
            parziale.unlink(missing_ok=True)
    raise ErroreDownload(f"Non riesco a scaricare {destinazione.name}: {errore}")


def descrivi_avanzamento(nome, scaricati, totale):
    mb = scaricati / 1e6
    if totale:
        return f"Scarico {nome}: {mb:.0f} di {totale / 1e6:.0f} MB ({scaricati * 100 // totale}%)"
    return f"Scarico {nome}: {mb:.0f} MB"


def _apri(indirizzo):
    richiesta = urllib.request.Request(indirizzo, headers={"User-Agent": "Jarvis"})
    return urllib.request.urlopen(richiesta, timeout=60)
