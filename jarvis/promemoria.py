"""I promemoria di Jarvis: con data e ora, salvati in dati/promemoria.json.

Restano anche a PC spento: quelli scaduti nel frattempo vengono detti alla riaccensione.
`interpreta_quando` capisce le date come le dice una persona: "domani alle 18", "venerdì 9:30", "tra 2 ore".
"""

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

FILE_PROMEMORIA = Path(__file__).resolve().parent / "dati" / "promemoria.json"
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre"]
_PARTI_DEL_GIORNO = {"stamattina": 9, "stamani": 9, "domattina": 9, "mattina": 9, "mezzogiorno": 12,
                     "pomeriggio": 15, "stasera": 20, "sera": 20, "stanotte": 23, "notte": 23}
_UNITA = {"minut": 1, "or": 60, "giorn": 24 * 60, "settiman": 7 * 24 * 60}
_lucchetto = threading.Lock()


class ErrorePromemoria(Exception):
    pass


def _senza_accenti(testo):
    return testo.replace("ì", "i").replace("è", "e").replace("é", "e").replace("à", "a").replace("ò", "o")


def interpreta_quando(testo, adesso=None):
    """Da "domani alle 18:30", "venerdì", "tra 20 minuti" o "2026-11-03 09:00" a una data e ora precisa."""
    adesso = (adesso or datetime.now()).replace(second=0, microsecond=0)
    t = " " + _senza_accenti(str(testo).lower().strip()) + " "
    t = t.replace("mezz'ora", "30 minuti").replace("un'ora", "1 ora").replace("un quarto d'ora", "15 minuti")
    # Tra quanto: "tra 2 ore", "fra 10 minuti", "tra 3 giorni".
    tra = re.search(r"\b(?:tra|fra)\s+(\d+(?:[.,]\d+)?|un|una)\s+(minut|or|giorn|settiman)", t)
    if tra:
        quanti = 1.0 if tra.group(1) in ("un", "una") else float(tra.group(1).replace(",", "."))
        return adesso + timedelta(minutes=quanti * _UNITA[tra.group(2)])
    # Una data scritta: 2026-11-03, 3/11/2026, 3/11, "3 novembre".
    giorno = None
    if m := re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})", t):
        giorno = _data(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        t = t.replace(m.group(0), " ")
    elif m := re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t):
        anno = int(m.group(3)) if m.group(3) else adesso.year
        giorno = _data(anno + 2000 if anno < 100 else anno, int(m.group(2)), int(m.group(1)))
        if not m.group(3) and giorno < adesso.date():
            giorno = _data(adesso.year + 1, int(m.group(2)), int(m.group(1)))
        t = t.replace(m.group(0), " ")
    elif m := re.search(r"\b(\d{1,2})\s+(" + "|".join(MESI) + r")\b(?:\s+(\d{4}))?", t):
        mese = MESI.index(m.group(2)) + 1
        giorno = _data(int(m.group(3) or adesso.year), mese, int(m.group(1)))
        if not m.group(3) and giorno < adesso.date():
            giorno = _data(adesso.year + 1, mese, int(m.group(1)))
        t = t.replace(m.group(0), " ")
    elif re.search(r"\bdopodomani\b", t):
        giorno = adesso.date() + timedelta(days=2)
    elif re.search(r"\bdomani\b|\bdomattina\b", t):
        giorno = adesso.date() + timedelta(days=1)
    elif re.search(r"\boggi\b|\bstamattina\b|\bstamani\b|\bstasera\b|\bstanotte\b", t):
        giorno = adesso.date()
    else:
        for numero, nome in enumerate(GIORNI):
            if re.search(rf"\b{_senza_accenti(nome)}\b", t):
                giorno = adesso.date() + timedelta(days=(numero - adesso.weekday()) % 7 or 7)
                break
    # L'ora: "alle 18", "18:30", "9.15", "alle 9 e mezza", oppure "stasera", "pomeriggio".
    ora = None
    if m := re.search(r"\b(\d{1,2})[:.](\d{2})\b", t):
        ora = (int(m.group(1)), int(m.group(2)))
    elif m := re.search(r"\b(?:alle|all'|ore|verso le)\s*(\d{1,2})(?:\s+e\s+(mezza|un quarto|tre quarti|\d{1,2}))?\b",
                        t):
        minuti = {"mezza": 30, "un quarto": 15, "tre quarti": 45}.get(m.group(2) or "", None)
        ora = (int(m.group(1)), minuti if minuti is not None else int(m.group(2) or 0))
    else:
        for parola, ore in _PARTI_DEL_GIORNO.items():
            if re.search(rf"\b{parola}\b", t):
                ora = (ore, 0)
                break
    if ora and not (0 <= ora[0] <= 23 and 0 <= ora[1] <= 59):
        raise ErrorePromemoria(f"l'ora {ora[0]}:{ora[1]:02d} non esiste")
    if giorno is None and ora is None:
        raise ErrorePromemoria('non ho capito quando: scrivi per esempio "domani alle 18" o "tra 2 ore"')
    if ora is None:
        ora = (9, 0)
    if giorno is None:  # solo l'ora: oggi, oppure domani se quell'ora è già passata
        giorno = adesso.date()
        if (ora[0], ora[1]) <= (adesso.hour, adesso.minute):
            if 1 <= ora[0] <= 7 and (ora[0] + 12, ora[1]) > (adesso.hour, adesso.minute) and \
                    not re.search(r"\bmattin|\b\d{2}[:.]", t):
                ora = (ora[0] + 12, ora[1])  # "alle 6" detto di pomeriggio: le 18
            else:
                giorno += timedelta(days=1)
    return datetime(giorno.year, giorno.month, giorno.day, ora[0], ora[1])


def _data(anno, mese, giorno):
    try:
        return datetime(anno, mese, giorno).date()
    except ValueError:
        raise ErrorePromemoria(f"la data {giorno}/{mese}/{anno} non esiste") from None


def descrivi_quando(momento, adesso=None):
    adesso = adesso or datetime.now()
    differenza = (momento.date() - adesso.date()).days
    ora = f"alle {momento.hour}:{momento.minute:02d}"
    if differenza == 0:
        return f"oggi {ora}"
    if differenza == -1:
        return f"ieri {ora}"
    if differenza == 1:
        return f"domani {ora}"
    if 1 < differenza < 7:
        return f"{GIORNI[momento.weekday()]} {ora}"
    return f"{GIORNI[momento.weekday()]} {momento.day} {MESI[momento.month - 1]} {ora}"


def _leggi():
    try:
        dati = json.loads(FILE_PROMEMORIA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return dati if isinstance(dati, list) else []


def _scrivi(elenco):
    FILE_PROMEMORIA.parent.mkdir(exist_ok=True)
    FILE_PROMEMORIA.write_text(json.dumps(elenco, ensure_ascii=False, indent=2), encoding="utf-8")


def aggiungi(quando, messaggio, adesso=None):
    """Salva un promemoria. Restituisce la conferma da dire all'utente."""
    adesso = adesso or datetime.now()
    momento = interpreta_quando(quando, adesso)
    if momento <= adesso:
        raise ErrorePromemoria(f"{descrivi_quando(momento, adesso)} è già passato")
    messaggio = (messaggio or "").strip().rstrip(".") or "promemoria"
    with _lucchetto:
        elenco = _leggi()
        elenco.append({"quando": momento.isoformat(timespec="minutes"), "messaggio": messaggio})
        elenco.sort(key=lambda p: p["quando"])
        _scrivi(elenco)
    return f"Promemoria salvato per {descrivi_quando(momento, adesso)}: {messaggio}."


def in_attesa(adesso=None):
    """I promemoria futuri, in ordine: [(data e ora, messaggio)]."""
    adesso = adesso or datetime.now()
    with _lucchetto:
        elenco = _leggi()
    return [(datetime.fromisoformat(p["quando"]), p["messaggio"]) for p in elenco
            if datetime.fromisoformat(p["quando"]) > adesso]


def descrivi_elenco(adesso=None):
    futuri = in_attesa(adesso)
    if not futuri:
        return "Non ci sono promemoria."
    return "Promemoria:\n" + "\n".join(f"{n}. {descrivi_quando(q, adesso)}: {m}" for n, (q, m) in enumerate(futuri, 1))


def cancella(numero, adesso=None):
    """Cancella il promemoria con quel numero (quello di descrivi_elenco)."""
    futuri = in_attesa(adesso)
    try:
        quando, messaggio = futuri[int(numero) - 1]
    except (ValueError, IndexError):
        raise ErrorePromemoria("non c'è un promemoria con quel numero: guarda l'elenco con /promemoria") from None
    with _lucchetto:
        elenco = [p for p in _leggi() if not (p["quando"] == quando.isoformat(timespec="minutes")
                                               and p["messaggio"] == messaggio)]
        _scrivi(elenco)
    return f"Promemoria cancellato: {messaggio}."


def scaduti(adesso=None):
    """Toglie e restituisce i promemoria arrivati all'ora: [(data e ora, messaggio)]."""
    adesso = adesso or datetime.now()
    with _lucchetto:
        elenco = _leggi()
        arrivati = [p for p in elenco if datetime.fromisoformat(p["quando"]) <= adesso]
        if arrivati:
            _scrivi([p for p in elenco if p not in arrivati])
    return [(datetime.fromisoformat(p["quando"]), p["messaggio"]) for p in arrivati]
