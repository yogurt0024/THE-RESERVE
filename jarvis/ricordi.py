"""Il diario di Jarvis: tiene traccia di cosa fate insieme, giorno per giorno, e lo sa ritrovare.

- dati/diario/AAAA-MM-GG.jsonl: le conversazioni del giorno, così come sono avvenute;
- dati/diario/AAAA-MM-GG.md: il riassunto del giorno, scritto da Jarvis (cosa avete fatto, cosa ricordare e
  cosa potrebbe fare meglio).
Tutto resta sul PC. Con "diario": false in config.json non si scrive niente.
"""

import json
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

CARTELLA_DIARIO = Path(__file__).resolve().parent / "dati" / "diario"
ISTRUZIONI_DIARIO = (
    "Scrivi il diario di questa giornata come lo scriverebbe Jarvis, in prima persona e in italiano semplice. "
    "Tre parti, ognuna di due-cinque frasi:\n"
    "Cosa abbiamo fatto: gli argomenti e le richieste della giornata.\n"
    "Da ricordare: impegni, scadenze, gusti o fatti personali dell'utente emersi oggi (se non ce ne sono, scrivi "
    "\"niente di particolare\").\n"
    "Cosa posso fare meglio: dove ho sbagliato, non ho capito o non sapevo fare qualcosa, e cosa mi servirebbe "
    "imparare."
)
_PAROLE_VUOTE = set("il lo la i gli le un uno una di a da in con su per tra fra e o che chi cosa come quando "
                    "dove perché non si mi ti ci vi è ho ha hai abbiamo del della dei delle al alla ai alle nel "
                    "nella sono era mio mia tuo tua suo sua".split())
_lucchetto = threading.Lock()


def _file(giorno, estensione):
    return CARTELLA_DIARIO / f"{giorno.isoformat()}.{estensione}"


def registra(domanda, risposta, adesso=None):
    """Aggiunge uno scambio al registro del giorno."""
    adesso = adesso or datetime.now()
    riga = json.dumps({"ora": adesso.strftime("%H:%M"), "utente": domanda, "jarvis": risposta}, ensure_ascii=False)
    with _lucchetto:
        CARTELLA_DIARIO.mkdir(parents=True, exist_ok=True)
        with open(_file(adesso.date(), "jsonl"), "a", encoding="utf-8") as f:
            f.write(riga + "\n")


def scambi(giorno):
    try:
        righe = _file(giorno, "jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    risultato = []
    for riga in righe:
        try:
            risultato.append(json.loads(riga))
        except ValueError:
            continue
    return risultato


def riassunto(giorno):
    try:
        return _file(giorno, "md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def da_riassumere(oggi=None):
    """I giorni con conversazioni nuove rispetto al loro riassunto (oggi compreso)."""
    oggi = oggi or date.today()
    if not CARTELLA_DIARIO.is_dir():
        return []
    giorni = []
    for registro in sorted(CARTELLA_DIARIO.glob("*.jsonl")):
        try:
            giorno = date.fromisoformat(registro.stem)
        except ValueError:
            continue
        riassunto_md = _file(giorno, "md")
        if giorno <= oggi and (not riassunto_md.exists() or riassunto_md.stat().st_mtime < registro.stat().st_mtime):
            giorni.append(giorno)
    return giorni


def testo_per_il_riassunto(giorno, massimo=12000):
    righe = [f"{s['ora']} Utente: {s['utente']}\n{s['ora']} Jarvis: {s['jarvis']}" for s in scambi(giorno)]
    testo = "\n".join(righe)
    return testo[-massimo:]  # se la giornata è lunghissima, conta la parte più recente


def salva_riassunto(giorno, testo):
    with _lucchetto:
        CARTELLA_DIARIO.mkdir(parents=True, exist_ok=True)
        _file(giorno, "md").write_text(f"# Diario del {giorno:%d/%m/%Y}\n\n{testo.strip()}\n", encoding="utf-8")


def ultimo_riassunto(prima_di=None):
    """(giorno, testo) dell'ultimo diario prima di oggi, per ricordare cosa avete fatto l'ultima volta."""
    prima_di = prima_di or date.today()
    for giorni_fa in range(1, 31):
        giorno = prima_di - timedelta(days=giorni_fa)
        testo = riassunto(giorno)
        if testo:
            return giorno, testo
    return None, ""


def _parole(testo):
    return {p[:6] for p in re.findall(r"[a-zàèéìòù0-9]{3,}", testo.lower()) if p not in _PAROLE_VUOTE}


def cerca(cosa, quanti=5):
    """Cerca nei diari e nelle conversazioni passate. Restituisce il testo per il modello."""
    cercate = _parole(cosa or "")
    if not cercate:
        raise ValueError("dimmi cosa cercare nei ricordi")
    trovati = []
    if CARTELLA_DIARIO.is_dir():
        for registro in CARTELLA_DIARIO.glob("*.jsonl"):
            giorno = registro.stem
            for scambio in scambi(date.fromisoformat(giorno)):
                testo = f"Utente: {scambio['utente']} / Jarvis: {scambio['jarvis']}"
                punteggio = len(cercate & _parole(testo))
                if punteggio:
                    trovati.append((punteggio, giorno, scambio["ora"], testo[:400]))
        for diario in CARTELLA_DIARIO.glob("*.md"):
            for paragrafo in diario.read_text(encoding="utf-8").split("\n\n"):
                punteggio = len(cercate & _parole(paragrafo))
                if punteggio:
                    trovati.append((punteggio + 0.5, diario.stem, "diario", paragrafo.strip()[:400]))
    if not trovati:
        return f'Nei miei ricordi non trovo niente su "{cosa}".'
    trovati.sort(key=lambda t: (t[0], t[1]), reverse=True)
    righe = [f"- {giorno} ({ora}): {testo}" for _, giorno, ora, testo in trovati[:quanti]]
    return f'Ricordi su "{cosa}" (dal più pertinente):\n' + "\n".join(righe)


def diario_di(giorno_testo, oggi=None):
    """Il diario di un giorno: "oggi", "ieri", "l'altro ieri" o una data AAAA-MM-GG / GG/MM."""
    oggi = oggi or date.today()
    t = (giorno_testo or "oggi").lower().strip()
    if t in ("oggi", ""):
        giorno = oggi
    elif t == "ieri":
        giorno = oggi - timedelta(days=1)
    elif t in ("l'altro ieri", "altro ieri", "avantieri"):
        giorno = oggi - timedelta(days=2)
    else:
        try:
            giorno = date.fromisoformat(t)
        except ValueError:
            m = re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$", t)
            if not m:
                raise ValueError('scrivi il giorno come "oggi", "ieri" o una data (per esempio 2026-10-27)') from None
            giorno = date(int(m.group(3) or oggi.year), int(m.group(2)), int(m.group(1)))
    testo = riassunto(giorno)
    if testo:
        return testo
    conversazioni = scambi(giorno)
    if conversazioni:
        return f"Il diario del {giorno:%d/%m} non è ancora scritto. Le conversazioni di quel giorno:\n" + \
            testo_per_il_riassunto(giorno, 4000)
    return f"Il {giorno:%d/%m} non abbiamo parlato."
