"""Fa ascoltare le voci di Jarvis, con e senza l'effetto in stile film, e salva in config.json quella scelta.

Uso:  py -3.12 prova_voci.py
La prima volta installa le librerie che mancano e scarica le voci (da qualche decina a qualche centinaio di MB).
Gli esempi restano anche in dati/voci_di_prova, per riascoltarli quando vuoi.
"""

import importlib
import json
import subprocess
import sys
import wave
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
FILE_CONFIG = CARTELLA / "config.json"
CARTELLA_ESEMPI = CARTELLA / "dati" / "voci_di_prova"


def installa(pacchetti):
    print(f"  Installo {pacchetti} (solo la prima volta)...", flush=True)
    risultato = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", *pacchetti.split()],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    if risultato.returncode != 0:
        righe = [r for r in (risultato.stderr or risultato.stdout).splitlines() if r.strip()]
        print(f"  Non si installa: {righe[-1] if righe else 'errore sconosciuto'}")
        return False
    importlib.invalidate_caches()  # così le librerie appena installate si possono usare subito
    return True


def leggi_config():
    try:
        return json.loads(FILE_CONFIG.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def salva_wav(file, audio, frequenza):
    import numpy as np

    dati = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(file), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(frequenza))
        w.writeframes(dati)


def ascolta(audio, frequenza):
    import sounddevice

    sounddevice.play(audio, frequenza)
    sounddevice.wait()


def domanda(testo, scelte):
    while True:
        risposta = input(testo).strip().lower()
        if risposta in scelte:
            return risposta
        print(f"  Scrivi una di queste: {', '.join(scelte)}")


def main():
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.version_info >= (3, 13):
        print("Attenzione: le librerie della voce funzionano con Python 3.12. Avvia così:  py -3.12 prova_voci.py\n")
    try:
        import numpy  # noqa: F401
        import sounddevice  # noqa: F401
    except ImportError:
        if not installa("numpy sounddevice"):
            raise SystemExit("Senza numpy e sounddevice non posso far sentire le voci.")
    except OSError as e:  # sounddevice c'è, ma non trova la sua libreria audio
        raise SystemExit(f"Non riesco a usare l'audio del PC: {e}")
    import voce

    config = leggi_config()
    titolo = config.get("come_chiamarmi", "signore")
    t = f", {titolo}" if titolo else ""
    lei = config.get("dai_del", "lei") != "tu"
    nome = config.get("nome", "Jarvis")
    frase = (f"Buonasera{t}. Sono {nome}, {'il suo' if lei else 'il tuo'} assistente personale. Tutti i sistemi "
             "sono operativi: a Cagliari ci sono 22 gradi e il cielo è sereno.")

    print("Ti faccio sentire le voci di Jarvis: ognuna prima così com'è, poi con l'effetto in stile film.")
    print("Le voci di Microsoft (Diego e Giuseppe) sono le più naturali, ma il testo da leggere passa da internet.")
    online = domanda("Provo anche quelle? (s/n) ", ("s", "n")) == "s"
    kokoro = domanda("Provo anche Nicola? Va scaricata una sola volta, circa 340 MB (s/n) ", ("s", "n")) == "s"
    CARTELLA_ESEMPI.mkdir(parents=True, exist_ok=True)

    def avanzamento(file, scaricati, totale):
        from scarica import descrivi_avanzamento

        print(f"\r  {descrivi_avanzamento(file, scaricati, totale)}   ", end="", flush=True)

    funzionano = {}
    for numero, (nome_voce, info) in enumerate(voce.VOCI.items(), 1):
        if (info["motore"] == "edge" and not online) or (info["motore"] == "kokoro" and not kokoro):
            continue
        print(f"\n{numero}. {info['descrizione']}")
        try:
            motore = voce.carica_motore(nome_voce, avanzamento=avanzamento)
        except voce.ErroreVoce as e:
            if "manca la libreria" in str(e) and installa(voce.PACCHETTI[info["motore"]]):
                try:
                    motore = voce.carica_motore(nome_voce, avanzamento=avanzamento)
                except voce.ErroreVoce as e2:
                    print(f"\n  NON FUNZIONA: {e2}")
                    continue
            else:
                print(f"\n  NON FUNZIONA: {e}")
                continue
        try:
            audio, frequenza = motore.sintetizza(frase)
        except Exception as e:  # ogni libreria ha i suoi errori
            print(f"\n  NON FUNZIONA: {e}")
            continue
        normale = voce.effetto_jarvis(audio, frequenza, 0)
        jarvis = voce.effetto_jarvis(audio, frequenza, 0.6)
        salva_wav(CARTELLA_ESEMPI / f"{nome_voce}.wav", normale, frequenza)
        salva_wav(CARTELLA_ESEMPI / f"{nome_voce}-jarvis.wav", jarvis, frequenza)
        funzionano[str(numero)] = (nome_voce, normale, jarvis, frequenza)
        print("\n  Così com'è...", flush=True)
        ascolta(normale, frequenza)
        print("  Con l'effetto Jarvis...", flush=True)
        ascolta(jarvis, frequenza)

    if not funzionano:
        raise SystemExit("\nNessuna voce funziona: manda questi messaggi a chi ti aiuta con Jarvis.")
    print(f"\nGli esempi sono anche in {CARTELLA_ESEMPI}.")
    while True:
        scelta = domanda(f"\nQuale voce vuoi? Scrivi il numero ({', '.join(funzionano)}), oppure r e il numero per "
                         "riascoltarla (per esempio r1): ",
                         tuple(funzionano) + tuple(f"r{n}" for n in funzionano))
        if not scelta.startswith("r"):
            break
        _, normale, jarvis, frequenza = funzionano[scelta[1:]]
        ascolta(normale, frequenza)
        ascolta(jarvis, frequenza)
    nome_voce = funzionano[scelta][0]
    effetto = domanda("Con l'effetto Jarvis? (s/n) ", ("s", "n")) == "s"
    config = leggi_config()  # rilette adesso, nel caso siano cambiate intanto
    config.update(voce=nome_voce, effetto_voce=0.6 if effetto else 0.0)
    if config.get("parla") == "mai":
        config["parla"] = "sempre"
    FILE_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nFatto! {nome} userà la voce {nome_voce}{' con' if effetto else ' senza'} l'effetto. "
          "Puoi cambiarla quando vuoi rilanciando questo programma, oppure in Jarvis con /voce.")


if __name__ == "__main__":
    main()
