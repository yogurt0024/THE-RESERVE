"""Fa ascoltare le voci di Jarvis e salva in config.json quella scelta.

Uso:  py -3.12 prova_voci.py
La voce espressiva si sente con tre livelli di emozione; le altre così come sono e con l'effetto in stile film.
La prima volta installa le librerie che mancano e scarica le voci. Gli esempi restano in dati/voci_di_prova.
"""

import importlib
import json
import subprocess
import sys
import time
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
    import scarica
    import voce

    config = leggi_config()
    titolo = config.get("come_chiamarmi", "signore")
    t = f", {titolo}" if titolo else ""
    lei = config.get("dai_del", "lei") != "tu"
    nome = config.get("nome", "Jarvis")
    frase = (f"Buonasera{t}! Sono {nome}, {'il suo' if lei else 'il tuo'} assistente personale. Ho una buona notizia: "
             "tutti i sistemi sono operativi, e a Cagliari ci sono ventidue gradi. Mi permetta un consiglio, però: "
             "domani pioverà, non dimentichi l'ombrello.")

    print("La voce espressiva recita con emozione: è quella più simile a Jarvis, ma pesa circa 1,5 GB e ha bisogno")
    print("di un processore veloce. Le altre le hai già sentite.")
    tutte = domanda("Provo solo la voce espressiva (e) oppure tutte le voci (t)? ", ("e", "t")) == "t"
    online = tutte and domanda("Provo anche le voci di Microsoft, via internet? (s/n) ", ("s", "n")) == "s"
    CARTELLA_ESEMPI.mkdir(parents=True, exist_ok=True)

    def avanzamento(file, scaricati, totale):
        print(f"\r  {scarica.descrivi_avanzamento(file, scaricati, totale)}   ", end="", flush=True)

    esempi = {}  # numero → (voce, emozione, effetto, audio, frequenza)
    for nome_voce, info in voce.VOCI.items():
        if (nome_voce != "espressiva" and not tutte) or (info["motore"] == "edge" and not online):
            continue
        print(f"\n{info['descrizione']}")
        motore = None
        for tentativo in range(2):
            try:
                motore = voce.carica_motore(nome_voce, avanzamento=avanzamento, config=config)
                break
            except voce.ErroreVoce as e:
                if tentativo == 0 and "manca la libreria" in str(e) and installa(voce.PACCHETTI[info["motore"]]):
                    continue
                print(f"\n  NON FUNZIONA: {e}")
                break
        if motore is None:
            continue
        if info["motore"] == "chatterbox":
            varianti = [("emozione bassa", 0.3, 0), ("emozione media", 0.6, 0), ("emozione alta", 0.9, 0),
                        ("emozione media con l'effetto Jarvis", 0.6, 0.6)]
        else:
            varianti = [("così com'è", None, 0), ("con l'effetto Jarvis", None, 0.6)]
        for descrizione, emozione, effetto in varianti:
            if emozione is not None:
                motore.emozione = emozione
            inizio = time.perf_counter()
            try:
                audio, frequenza = motore.sintetizza(frase)
            except Exception as e:  # ogni libreria ha i suoi errori
                print(f"\n  NON FUNZIONA: {e}")
                break
            tempo = time.perf_counter() - inizio
            audio = voce.effetto_jarvis(audio, frequenza, effetto)
            numero = str(len(esempi) + 1)
            esempi[numero] = (nome_voce, emozione, effetto, audio, frequenza)
            voce.salva_wav(CARTELLA_ESEMPI / f"{numero}-{nome_voce}.wav", audio, frequenza)
            durata = len(audio) / frequenza
            lenta = "  (più lenta del parlato: ci saranno pause tra le frasi)" if tempo > durata else ""
            print(f"\n  {numero}. {descrizione}: pronta in {tempo:.1f} s per {durata:.1f} s di voce{lenta}", flush=True)
            ascolta(audio, frequenza)

    if not esempi:
        raise SystemExit("\nNessuna voce funziona: manda questi messaggi a chi ti aiuta con Jarvis.")
    print(f"\nGli esempi sono anche in {CARTELLA_ESEMPI}.")
    while True:
        scelta = domanda(f"\nQuale preferisci? Scrivi il numero (da 1 a {len(esempi)}), oppure r e il numero per "
                         "riascoltarla (per esempio r1): ", tuple(esempi) + tuple(f"r{n}" for n in esempi))
        if not scelta.startswith("r"):
            break
        *_, audio, frequenza = esempi[scelta[1:]]
        ascolta(audio, frequenza)
    nome_voce, emozione, effetto, *_ = esempi[scelta]
    config = leggi_config()  # riletta adesso, nel caso sia cambiata intanto
    config.update(voce=nome_voce, effetto_voce=effetto)
    if emozione is not None:
        config["emozione_voce"] = emozione
    if config.get("parla") == "mai":
        config["parla"] = "sempre"
    FILE_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nFatto! {nome} userà la voce {nome_voce}. Puoi cambiarla quando vuoi rilanciando questo programma, "
          "oppure in Jarvis con /voce.")


if __name__ == "__main__":
    main()
