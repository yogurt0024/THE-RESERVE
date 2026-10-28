"""Crea il modello "jarvis" in Ollama dal file jarvis.gguf addestrato su Google Colab.

Uso: metti jarvis.gguf in questa cartella e scrivi  python crea_modello.py
Il formato della chat (compreso l'uso degli strumenti) viene copiato da qwen3:4b-instruct,
il modello da cui Jarvis è stato addestrato.
"""

import subprocess
import sys
from pathlib import Path

BASE = "qwen3:4b-instruct"
NOME = "jarvis"
CARTELLA = Path(__file__).resolve().parent


def ollama(*argomenti):
    try:
        return subprocess.run(["ollama", *argomenti], capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
    except FileNotFoundError:
        raise SystemExit("Non trovo Ollama: installalo da https://ollama.com/download e riprova.") from None


def main():
    gguf = Path(sys.argv[1]) if len(sys.argv) > 1 else CARTELLA / "jarvis.gguf"
    if not gguf.exists():
        raise SystemExit(f"Non trovo {gguf}. Scaricalo dalla cartella Jarvis del tuo Google Drive e mettilo qui.")

    base = ollama("show", "--modelfile", BASE)
    if base.returncode != 0:
        raise SystemExit(f"Serve il modello di partenza. Scrivi:  ollama pull {BASE}")
    # Stesso Modelfile del modello di partenza, ma con i "pesi" addestrati al posto dei suoi.
    righe = [f"FROM ./{gguf.name}" if riga.startswith("FROM ") else riga for riga in base.stdout.splitlines()]
    modelfile = gguf.parent / "Modelfile"
    modelfile.write_text("\n".join(righe) + "\n", encoding="utf-8")

    print(f"Creo il modello {NOME} (può volerci qualche minuto)...")
    creato = subprocess.run(["ollama", "create", NOME, "-f", str(modelfile)], cwd=gguf.parent)
    if creato.returncode != 0:
        raise SystemExit("Ollama non è riuscito a creare il modello: guarda il messaggio qui sopra.")
    print(f'\nFatto! Ora in config.json scrivi:  "modello": "{NOME}"')


if __name__ == "__main__":
    main()
