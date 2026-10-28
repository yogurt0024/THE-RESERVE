"""Prova di compatibilità: controlla se le librerie che servono a Jarvis funzionano su questo PC.

Il Controllo intelligente delle app di Windows può bloccare alcune librerie. Questo programma
le installa una alla volta, prova a usarle e scrive un riepilogo in dati/compatibilita.txt.

Uso:  py -3.12 prova_compatibilita.py   (ci vogliono 5-15 minuti e circa 1 GB di download)
"""

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
FILE_RISULTATO = CARTELLA / "dati" / "compatibilita.txt"
FILE_CHIAVE = CARTELLA / "dati" / "chiave_claude.txt"

# (pacchetto da installare, codice di prova, a cosa serve)
PROVE = [
    ("anthropic", "import anthropic; print(anthropic.__version__)", "cervello avanzato (Claude)"),
    ("sounddevice", "import sounddevice as s; print('microfono:', s.query_devices(kind='input')['name'])",
     "microfono e altoparlanti"),
    ("onnx-asr[cpu]", "import onnx_asr, onnxruntime; print('onnxruntime', onnxruntime.__version__)",
     "capire la voce"),
    ("piper-tts", "from piper.phonemize_espeak import EspeakPhonemizer as E; print(E().phonemize('it', 'ciao')[0])",
     "voce Riccardo (sul PC)"),
    ("kokoro-onnx", "import ctypes, espeakng_loader, kokoro_onnx; "
                    "ctypes.cdll.LoadLibrary(espeakng_loader.get_library_path()); print('ok')", "voce Nicola (sul PC)"),
    ("edge-tts soundfile", "import edge_tts, soundfile; print('libsndfile', soundfile.__libsndfile_version__)",
     "voci Diego e Giuseppe (via internet)"),
    ("opencv-python", "import cv2; print(cv2.__version__)", "webcam"),
]
# Come si presenta un blocco del Controllo intelligente delle app (WinError 4551).
SEGNI_DI_BLOCCO = ("4551", "controllo applicazioni", "controllo delle applicazioni",
                   "controllo dell'applicazione", "criterio di controllo", "application control")


def comando(argomenti, secondi):
    try:
        return subprocess.run(argomenti, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=secondi)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argomenti, 1, "", "tempo scaduto")
    except OSError as e:  # per esempio nvidia-smi non installato
        return subprocess.CompletedProcess(argomenti, 1, "", str(e))


def ultima_riga(testo):
    righe = [r for r in testo.strip().splitlines() if r.strip()]
    return righe[-1][:200] if righe else ""


def prova(pacchetto, codice):
    installa = comando([sys.executable, "-m", "pip", "install", "--upgrade", *pacchetto.split()], 1800)
    if installa.returncode != 0:
        return "NON INSTALLABILE", ultima_riga(installa.stderr or installa.stdout)
    uso = comando([sys.executable, "-c", codice], 300)
    if uso.returncode == 0:
        return "OK", ultima_riga(uso.stdout)
    if any(segno in uso.stderr.lower() for segno in SEGNI_DI_BLOCCO):
        return "BLOCCATO DA WINDOWS", ultima_riga(uso.stderr)
    return "ERRORE", ultima_riga(uso.stderr)


def stato_controllo_intelligente():
    if sys.platform != "win32":
        return "non è Windows"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as chiave:
            valore = winreg.QueryValueEx(chiave, "VerifiedAndReputablePolicyState")[0]
    except OSError:
        return "sconosciuto"
    return {0: "disattivato", 1: "attivo", 2: "in valutazione"}.get(valore, f"sconosciuto ({valore})")


def scheda_video():
    risultato = comando(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                         "--format=csv,noheader"], 20)
    return ultima_riga(risultato.stdout) if risultato.returncode == 0 else "nessuna scheda NVIDIA trovata"


def prova_chiave_claude():
    if not FILE_CHIAVE.exists():
        return "nessuna chiave salvata (in Jarvis usa il comando /chiave)"
    try:
        modello = json.loads((CARTELLA / "config.json").read_text(encoding="utf-8-sig")).get(
            "modello_claude", "claude-opus-5-5")
    except (OSError, ValueError):
        modello = "claude-opus-5-5"
    codice = (
        "import anthropic, pathlib\n"
        f"c = anthropic.Anthropic(api_key=pathlib.Path(r'{FILE_CHIAVE}').read_text(encoding='utf-8-sig').strip())\n"
        f"r = c.messages.create(model='{modello}', max_tokens=2000, output_config={{'effort': 'low'}},\n"
        "    messages=[{'role': 'user', 'content': 'Rispondi solo con la parola OK.'}])\n"
        "print(next((b.text for b in r.content if b.type == 'text'), r.stop_reason))\n"
    )
    risultato = comando([sys.executable, "-c", codice], 120)
    if risultato.returncode == 0:
        return f"funziona ({modello} ha risposto: {ultima_riga(risultato.stdout)})"
    return f"NON funziona: {ultima_riga(risultato.stderr)}"


def main():
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    righe = [
        f"Prova di compatibilità di Jarvis ({datetime.now():%d/%m/%Y %H:%M})",
        f"Python {platform.python_version()} su {platform.system()} {platform.release()} ({platform.version()})",
        f"Controllo intelligente delle app: {stato_controllo_intelligente()}",
        f"Scheda video: {scheda_video()}",
        "",
    ]
    print("\n".join(righe))
    print("Installo e provo le librerie una alla volta: può volerci qualche minuto per ognuna.\n")
    for pacchetto, codice, scopo in PROVE:
        print(f"- {pacchetto} ({scopo})...", flush=True)
        esito, dettaglio = prova(pacchetto, codice)
        riga = f"{esito:20} {pacchetto:15} {scopo}" + (f"\n{'':20} {dettaglio}" if dettaglio else "")
        print(riga + "\n", flush=True)
        righe.append(riga)
    righe += ["", f"Chiave Claude: {prova_chiave_claude()}"]
    print(righe[-1])
    FILE_RISULTATO.parent.mkdir(exist_ok=True)
    FILE_RISULTATO.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"\nFatto! Il riepilogo è anche in {FILE_RISULTATO}: copialo e mandalo a chi ti aiuta con Jarvis.")
    print("Attenzione: il riepilogo non contiene la tua chiave API, e la chiave non va mai condivisa.")


if __name__ == "__main__":
    main()
