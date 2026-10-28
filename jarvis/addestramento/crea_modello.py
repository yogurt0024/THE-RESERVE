"""Crea il modello "jarvis" in Ollama dal file .gguf addestrato su Google Colab.

Uso: metti il file scaricato (jarvis-qwen3.5.gguf oppure jarvis-qwen3.gguf) in questa cartella e scrivi
    python crea_modello.py
Il formato della chat (compreso l'uso degli strumenti) viene copiato dal modello di partenza in Ollama.
"""

import subprocess
import sys
from pathlib import Path

NOME = "jarvis"
CARTELLA = Path(__file__).resolve().parent
# Il modello di partenza in Ollama, a seconda della base scelta nel notebook.
BASI = {"qwen3.5": "qwen3.5:4b", "qwen3": "qwen3:4b-instruct"}


def ollama(*argomenti):
    try:
        return subprocess.run(["ollama", *argomenti], capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
    except FileNotFoundError:
        raise SystemExit("Non trovo Ollama: installalo da https://ollama.com/download e riprova.") from None


def trova_gguf():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    trovati = sorted(CARTELLA.glob("jarvis*.gguf"))
    if not trovati:
        raise SystemExit("Non trovo il file del modello. Scaricalo dalla cartella Jarvis del tuo Google Drive "
                         "e mettilo in questa cartella.")
    return trovati[-1]


def main():
    gguf = trova_gguf()
    if not gguf.exists():
        raise SystemExit(f"Non trovo {gguf}.")
    base = BASI["qwen3.5"] if "qwen3.5" in gguf.name else BASI["qwen3"]

    modelfile_base = ollama("show", "--modelfile", base)
    if modelfile_base.returncode != 0:
        raise SystemExit(f"Serve il modello di partenza. Scrivi:  ollama pull {base}")
    # Stesso Modelfile del modello di partenza, con i "pesi" addestrati al posto dei suoi. Solo il primo
    # FROM è il modello del testo: un eventuale secondo FROM (la parte che vede le immagini) resta com'è.
    righe, sostituito = [], False
    for riga in modelfile_base.stdout.splitlines():
        if riga.startswith("FROM ") and not sostituito:
            riga, sostituito = f"FROM ./{gguf.name}", True
        righe.append(riga)
    modelfile = gguf.parent / "Modelfile"
    modelfile.write_text("\n".join(righe) + "\n", encoding="utf-8")

    print(f"Creo il modello {NOME} partendo da {base} (può volerci qualche minuto)...")
    creato = subprocess.run(["ollama", "create", NOME, "-f", str(modelfile)], cwd=gguf.parent)
    if creato.returncode != 0:
        raise SystemExit("Ollama non è riuscito a creare il modello: guarda il messaggio qui sopra.")
    print(f'\nFatto! Ora in config.json scrivi:  "modello": "{NOME}"')


if __name__ == "__main__":
    main()
