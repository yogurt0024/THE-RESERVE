"""Prova l'orecchio di Jarvis: scrive tutto quello che sente dal microfono e quali frasi sono comandi.

Uso:  py -3.12 prova_ascolto.py   (Ctrl+C per finire)
La prima volta installa le librerie che mancano e scarica i modelli (circa 700 MB). L'audio non viene salvato.
"""

import importlib
import subprocess
import sys
import time
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent


def main():
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.version_info >= (3, 13):
        print("Attenzione: le librerie dell'ascolto funzionano con Python 3.12. Avvia così:  py -3.12 prova_ascolto.py\n")
    try:
        import numpy  # noqa: F401
        import onnx_asr  # noqa: F401
        import sounddevice  # noqa: F401
    except ImportError:
        print("Installo le librerie della voce (solo la prima volta)...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(CARTELLA / "requisiti_voce.txt")])
        importlib.invalidate_caches()
    except OSError as e:  # sounddevice c'è, ma non trova la sua libreria audio
        raise SystemExit(f"Non riesco a usare l'audio del PC: {e}")
    import ascolto
    import scarica
    import sounddevice
    from cervello import carica_config

    config = carica_config()
    nome = config["nome"]
    try:
        print(f"Microfono: {sounddevice.query_devices(kind='input')['name']}")
    except (OSError, ValueError, sounddevice.PortAudioError) as e:
        raise SystemExit(f"Non trovo nessun microfono: {e}")

    def avanzamento(file, scaricati, totale):
        print(f"\r{scarica.descrivi_avanzamento(file, scaricati, totale)}   ", end="", flush=True)

    modello = config.get("modello_ascolto") or ascolto.MODELLO_PREDEFINITO
    print(f"Preparo il modello che trascrive la voce ({ascolto.MODELLI_ASCOLTO[modello]['descrizione']})...")
    try:
        rilevatore = ascolto.carica_rilevatore(avanzamento)
        trascrivi = ascolto.carica_trascrittore(modello, avanzamento)
    except Exception as e:  # download, librerie o modello: qualunque cosa sia, va mostrata
        raise SystemExit(f"\nL'ascolto non funziona: {e}")

    def trascrivi_cronometrato(audio):
        inizio = time.perf_counter()
        testo = trascrivi(audio)
        durata = len(audio) / ascolto.FREQUENZA
        print(f"\nHo sentito ({durata:.1f} s di voce, trascritti in {time.perf_counter() - inizio:.1f} s): {testo}")
        return testo

    def al_comando(testo):
        print(f"  → è un comando per {nome}: {testo}" if testo else
              f"  → mi hai chiamato: {nome} risponderebbe \"Sì?\" e aspetterebbe la richiesta")

    orecchio = ascolto.Ascolto(config, al_comando=al_comando, rilevatore=rilevatore,
                               trascrittore=trascrivi_cronometrato,
                               al_stato=lambda testo: print(f"[{testo}]") if "ascolto" not in testo else None)
    orecchio.avvia()
    print(f"\nPronto! Parla normalmente, poi prova con \"{nome}, che ore sono?\". Ctrl+C per finire.")
    try:
        while orecchio.errore == "":
            time.sleep(0.3)
        print(f"Problema: {orecchio.errore}")
    except KeyboardInterrupt:
        print("\nFine della prova.")
    orecchio.chiudi()


if __name__ == "__main__":
    main()
