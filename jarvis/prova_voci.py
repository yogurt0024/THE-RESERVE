"""Crea la voce di Jarvis su ElevenLabs, oppure fa ascoltare le voci sul PC, e salva in config.json la scelta.

Uso:  py -3.12 prova_voci.py
La prima volta installa le librerie che mancano e scarica le voci. Gli esempi restano in dati/voci_di_prova.
"""

import getpass
import importlib
import json
import random
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


def salva_scelta(**impostazioni):
    config = leggi_config()  # riletta adesso, nel caso sia cambiata intanto
    config.update(impostazioni)
    if config.get("parla") == "mai":
        config["parla"] = "sempre"
    FILE_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepara_chiave_elevenlabs():
    """Controlla (o chiede) la chiave di ElevenLabs. Restituisce il piano ("free", "starter"...), "" se non si sa,
    oppure None se la chiave non c'è o non funziona."""
    import voce_elevenlabs as el

    nuova = not el.leggi_chiave()
    if nuova:
        print("\nServe una chiave API di ElevenLabs (il piano gratuito va bene per cominciare):")
        print("  1. Crea un account su https://elevenlabs.io")
        print("  2. Apri la sezione API Keys (di solito sotto Developers, nel menu a sinistra) e crea una chiave.")
        print("     Lascia attivi i permessi: servono almeno Text to Speech, Voices e Text to Voice.")
        print("  3. Copiala e incollala qui sotto: mentre la incolli non si vede. Non mandarla mai a nessuno.")
        print(el.salva_chiave(getpass.getpass("Chiave: ")))
        if not el.leggi_chiave():
            return None
    try:
        abbonamento = el.richiesta("/v1/user/subscription")
    except el.ErroreElevenLabs as e:
        if e.stato == "missing_permissions":
            return ""
        print(f"Problema con ElevenLabs: {e}")
        return None
    if not nuova:  # con una chiave appena salvata, il piano l'ha già scritto salva_chiave()
        print(el.descrivi_abbonamento(abbonamento))
    return abbonamento.get("tier", "")


def salva_voce_elevenlabs(id_voce, nome, t, descrizione):
    """Fa dire una frase alla voce scelta e la salva come voce di Jarvis."""
    import voce_elevenlabs as el

    try:
        audio = el.sintetizza(f"Eccomi{t}. {el.FRASE_DI_CONFERMA}", id_voce)
    except el.ErroreElevenLabs as e:
        print(f"Questa voce non funziona: {e}")
        return False
    salva_scelta(voce="elevenlabs", voce_elevenlabs=id_voce, effetto_voce=0.0)
    ascolta(audio, el.FREQUENZA)
    print(f"\nFatto! {nome} ora parla con {descrizione}.")
    return True


def progetta_voce(nome, t):
    """Fa creare a ElevenLabs voci nuove dalla descrizione (solo piani a pagamento). True, False o "a pagamento"."""
    import voce
    import voce_elevenlabs as el

    descrizione, seme = el.DESCRIZIONE_JARVIS, None
    while True:
        print("\nElevenLabs crea alcune voci nuove dalla descrizione (qualche secondo)...")
        try:
            voci = el.progetta_voci(descrizione, seme=seme)
        except el.ErroreElevenLabs as e:
            if e.stato == "solo_a_pagamento":
                return "a pagamento"
            print(f"Non ci sono riuscito: {e}")
            return False
        for numero, (_, audio, frequenza) in enumerate(voci, 1):
            voce.salva_wav(CARTELLA_ESEMPI / f"elevenlabs-{numero}.wav", audio, frequenza)
            print(f"  Voce {numero}...", flush=True)
            ascolta(audio, frequenza)
        numeri = tuple(str(n) for n in range(1, len(voci) + 1))
        while True:
            scelta = domanda(f"\nQuale tieni? Il numero ({', '.join(numeri)}); r per riascoltarle; n per crearne "
                             "altre; d per scrivere tu la descrizione; x per lasciar perdere: ",
                             numeri + ("r", "n", "d", "x"))
            if scelta != "r":
                break
            for _, audio, frequenza in voci:
                ascolta(audio, frequenza)
        if scelta == "x":
            return False
        if scelta == "n":
            seme = random.randint(1, 10 ** 6)
            continue
        if scelta == "d":
            print("Descrivi la voce (meglio in inglese, almeno 20 caratteri), per esempio età, tono, accento e")
            print("carattere. Non usare il nome di persone reali: la voce deve essere nuova.")
            nuova = input("> ").strip()
            descrizione = nuova if 20 <= len(nuova) <= 1000 else descrizione
            seme = None
            continue
        try:
            id_voce = el.crea_voce(voci[int(scelta) - 1][0], nome=nome, descrizione=descrizione)
        except el.ErroreElevenLabs as e:
            print(f"Non sono riuscito a salvarla: {e}")
            return False
        return salva_voce_elevenlabs(id_voce, nome, t, f"la voce {scelta} (la trovi anche nel tuo account ElevenLabs)")


def scegli_voce_pronta(nome, t):
    """Fa sentire in italiano le voci maschili già pronte nel tuo account ElevenLabs (vanno bene anche gratis)."""
    import voce
    import voce_elevenlabs as el

    try:
        voci = [v for v in el.voci_disponibili() if (v.get("labels") or {}).get("gender", "male") == "male"]
    except el.ErroreElevenLabs as e:
        print(f"Non riesco a leggere le voci: {e}")
        return False
    # Prima le voci tue, poi quelle britanniche (le più vicine allo stile di Jarvis), poi le altre.
    voci.sort(key=lambda v: (v.get("category") == "premade",
                             "brit" not in str((v.get("labels") or {}).get("accent", "")).lower()))
    voci = voci[:8]
    if not voci:
        print("Nel tuo account non trovo voci maschili.")
        return False
    frase = f"Buonasera{t}. Sono {nome}, e tutti i sistemi sono operativi."
    print(f"\nTi faccio sentire {len(voci)} voci in italiano (ogni prova usa circa {len(frase)} dei tuoi caratteri).")
    esempi = {}
    for v in voci:
        etichette = v.get("labels") or {}
        dettagli = ", ".join(x for x in (etichette.get("accent"), etichette.get("age"), etichette.get("description"))
                             if x)
        numero = str(len(esempi) + 1)
        print(f"\n{numero}. {v.get('name', '?')}" + (f" ({dettagli})" if dettagli else ""), flush=True)
        try:
            audio = el.sintetizza(frase, v["voice_id"])
        except el.ErroreElevenLabs as e:
            print(f"   non disponibile: {e}")
            continue
        esempi[numero] = (v, audio)
        voce.salva_wav(CARTELLA_ESEMPI / f"elevenlabs-{numero}.wav", audio, el.FREQUENZA)
        ascolta(audio, el.FREQUENZA)
    if not esempi:
        return False
    while True:
        scelta = domanda(f"\nQuale tieni? Il numero ({', '.join(esempi)}), r e il numero per riascoltarla "
                         "(per esempio r1), x per lasciar perdere: ",
                         tuple(esempi) + tuple(f"r{n}" for n in esempi) + ("x",))
        if scelta == "x":
            return False
        if not scelta.startswith("r"):
            break
        ascolta(esempi[scelta[1:]][1], el.FREQUENZA)
    v = esempi[scelta][0]
    return salva_voce_elevenlabs(v["voice_id"], nome, t, f"la voce {v.get('name', '')} di ElevenLabs")


def incolla_id_voce(nome, t):
    print("\nSul sito di ElevenLabs apri Voices e scegli o crea la voce che vuoi (per esempio con Voice Design,")
    print("se il tuo piano lo permette, o dalla Voice Library aggiungendola alle tue voci). Poi aprila e copia il")
    print("suo ID (di solito c'è il pulsante \"Copy voice ID\"). È una sequenza di lettere e numeri.")
    id_voce = input("ID della voce: ").strip()
    if not id_voce.isalnum():
        print("Non sembra un ID di ElevenLabs.")
        return False
    return salva_voce_elevenlabs(id_voce, nome, t, "la voce che hai scelto sul sito")


def crea_voce_elevenlabs(nome, t):
    """La voce di Jarvis su ElevenLabs: creata apposta (piani a pagamento) o scelta tra quelle pronte."""
    piano = prepara_chiave_elevenlabs()
    if piano is None:
        return False
    if piano != "free":
        esito = progetta_voce(nome, t)
        if esito != "a pagamento":
            return esito
    print("\nCol piano gratuito ElevenLabs non lascia creare voci nuove dalle API. Ci sono due alternative:")
    print("  p. scegli tra le voci già pronte di ElevenLabs: fluide e naturali, ti faccio sentire le maschili")
    print("  i. incolla l'ID di una voce che hai scelto o creato sul sito di ElevenLabs")
    scelta = domanda("Cosa preferisci? (p, i, oppure x per lasciar perdere) ", ("p", "i", "x"))
    if scelta == "p":
        return scegli_voce_pronta(nome, t)
    if scelta == "i":
        return incolla_id_voce(nome, t)
    return False


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

    CARTELLA_ESEMPI.mkdir(parents=True, exist_ok=True)
    print("La voce più fluida e naturale si crea su ElevenLabs: una voce nuova, fatta apposta per Jarvis.")
    print("Funziona via internet; il piano gratuito basta per circa 10 minuti di parlato al mese.")
    if domanda("Creo la voce di Jarvis con ElevenLabs? (s/n) ", ("s", "n")) == "s" and crea_voce_elevenlabs(nome, t):
        return
    print("\nAllora ecco le voci sul PC. La voce espressiva recita con emozione, ma pesa circa 1,5 GB e ha")
    print("bisogno di un processore veloce.")
    tutte = domanda("Provo solo la voce espressiva (e) oppure tutte le voci (t)? ", ("e", "t")) == "t"
    online = tutte and domanda("Provo anche le voci di Microsoft, via internet? (s/n) ", ("s", "n")) == "s"

    def avanzamento(file, scaricati, totale):
        print(f"\r  {scarica.descrivi_avanzamento(file, scaricati, totale)}   ", end="", flush=True)

    esempi = {}  # numero → (voce, emozione, effetto, audio, frequenza)
    for nome_voce, info in voce.VOCI.items():
        if (nome_voce != "espressiva" and not tutte) or (info["motore"] == "edge" and not online) \
                or info["motore"] == "elevenlabs":
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
    salva_scelta(voce=nome_voce, effetto_voce=effetto, **({} if emozione is None else {"emozione_voce": emozione}))
    print(f"\nFatto! {nome} userà la voce {nome_voce}. Puoi cambiarla quando vuoi rilanciando questo programma, "
          "oppure in Jarvis con /voce.")


if __name__ == "__main__":
    main()
