"""Gli strumenti di Jarvis: meteo, Wikipedia, notizie, siti, programmi, calcoli e timer.

Ogni strumento è una funzione che restituisce un testo, oppure solleva ErroreStrumento.
Il modello li usa da solo (se lo supporta); l'utente li richiama con /meteo, /wiki, ...
"""

import ast
import ctypes
import json
import math
import operator
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

import documenti
import integrazioni
import promemoria
import rete
import ricordi

AGENTE = "Jarvis/2.0 (assistente personale; https://github.com/yogurt0024/THE-RESERVE)"

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# Codici meteo WMO usati da Open-Meteo.
CONDIZIONI = {
    0: "sereno", 1: "quasi sereno", 2: "parzialmente nuvoloso", 3: "coperto",
    45: "nebbia", 48: "nebbia con brina",
    51: "pioggerella debole", 53: "pioggerella", 55: "pioggerella intensa",
    56: "pioggerella gelata", 57: "pioggerella gelata intensa",
    61: "pioggia debole", 63: "pioggia", 65: "pioggia forte",
    66: "pioggia gelata", 67: "pioggia gelata forte",
    71: "neve debole", 73: "neve", 75: "neve forte", 77: "granelli di neve",
    80: "rovesci deboli", 81: "rovesci", 82: "rovesci violenti",
    85: "rovesci di neve", 86: "forti rovesci di neve",
    95: "temporale", 96: "temporale con grandine", 99: "temporale con grandine forte",
}

STRUMENTI_INTERNET = {"meteo", "wikipedia", "notizie", "cerca_in_rete", "leggi_pagina", "agenda", "manda_al_telefono"}


class ErroreStrumento(Exception):
    pass


def data_italiana(giorno):
    return f"{GIORNI[giorno.weekday()]} {giorno.day} {MESI[giorno.month - 1]} {giorno.year}"


def _scarica(url, parametri=None):
    if parametri:
        url += "?" + urllib.parse.urlencode(parametri)
    richiesta = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(richiesta, timeout=15) as risposta:
            return risposta.read()
    except OSError:
        raise ErroreStrumento("non riesco a collegarmi a internet.") from None


def _gb(valore):
    return f"{valore:.1f}".replace(".", ",") + " GB"


def _gradi(valore):
    return "n.d." if valore is None else f"{round(valore)}°C"


def _numero(valore):
    """Scrive un numero all'italiana: 1.234.567 e 3,14."""
    if isinstance(valore, float) and valore.is_integer() and abs(valore) < 1e15:
        valore = int(valore)
    testo = f"{valore:,}" if isinstance(valore, int) else f"{valore:,.10g}"
    return testo.replace(",", " ").replace(".", ",").replace(" ", ".")


def _durata(minuti):
    if minuti < 1:
        secondi = max(1, round(minuti * 60))
        return "1 secondo" if secondi == 1 else f"{secondi} secondi"
    return "1 minuto" if minuti == 1 else f"{_numero(minuti)} minuti"


def meteo(citta):
    citta = (citta or "").strip()
    if not citta:
        raise ErroreStrumento("non so di quale città vuoi il meteo.")
    luoghi = json.loads(_scarica(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": citta, "count": 1, "language": "it", "format": "json"},
    )).get("results")
    if not luoghi:
        raise ErroreStrumento(f'non trovo la città "{citta}".')
    luogo = luoghi[0]
    dati = json.loads(_scarica("https://api.open-meteo.com/v1/forecast", {
        "latitude": luogo["latitude"],
        "longitude": luogo["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 3,
    }))
    adesso = dati["current"]
    giorni = dati["daily"]
    nome = ", ".join(p for p in (luogo.get("name"), luogo.get("admin1"), luogo.get("country")) if p)
    righe = [
        f"Meteo di {nome} (fonte: Open-Meteo)",
        f"Adesso: {_gradi(adesso['temperature_2m'])} (percepiti {_gradi(adesso['apparent_temperature'])}), "
        f"{CONDIZIONI.get(adesso['weather_code'], 'condizioni sconosciute')}, "
        f"umidità {adesso['relative_humidity_2m']}%, vento {adesso['wind_speed_10m']:.0f} km/h.",
    ]
    for i, (giorno, etichetta) in enumerate(zip(giorni["time"], ["Oggi", "Domani", "Dopodomani"])):
        quando = date.fromisoformat(giorno)
        riga = (
            f"{etichetta} ({GIORNI[quando.weekday()]} {quando.day}): "
            f"{CONDIZIONI.get(giorni['weather_code'][i], 'condizioni sconosciute')}, "
            f"minima {_gradi(giorni['temperature_2m_min'][i])}, massima {_gradi(giorni['temperature_2m_max'][i])}"
        )
        pioggia = giorni["precipitation_probability_max"][i]
        if pioggia is not None:
            riga += f", probabilità di pioggia {pioggia}%"
        righe.append(riga + ".")
    return "\n".join(righe)


def wikipedia(argomento):
    argomento = (argomento or "").strip()
    if not argomento:
        raise ErroreStrumento("non so cosa cercare su Wikipedia.")
    dati = json.loads(_scarica("https://it.wikipedia.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
        "generator": "search", "gsrsearch": argomento, "gsrlimit": 1,
        "prop": "extracts|info", "inprop": "url", "exintro": 1, "explaintext": 1,
    }))
    pagine = dati.get("query", {}).get("pages", [])
    if not pagine or not pagine[0].get("extract", "").strip():
        raise ErroreStrumento(f'non trovo niente su Wikipedia per "{argomento}".')
    pagina = pagine[0]
    estratto = pagina["extract"].strip()
    if len(estratto) > 2500:
        estratto = estratto[:2500].rsplit(" ", 1)[0] + "…"
    return f'Wikipedia, voce "{pagina["title"]}" ({pagina.get("fullurl", "")}):\n{estratto}'


def notizie(argomento=""):
    argomento = (argomento or "").strip()
    lingua = {"hl": "it", "gl": "IT", "ceid": "IT:it"}
    if argomento:
        contenuto = _scarica("https://news.google.com/rss/search", {"q": argomento, **lingua})
    else:
        contenuto = _scarica("https://news.google.com/rss", lingua)
    try:
        radice = ET.fromstring(contenuto)
    except ET.ParseError:
        raise ErroreStrumento("il servizio delle notizie ha risposto in modo strano.") from None
    righe = []
    for notizia in radice.iter("item"):
        riga = f"- {(notizia.findtext('title') or '').strip()}"
        try:
            quando = parsedate_to_datetime(notizia.findtext("pubDate") or "").astimezone()
            riga += f" ({quando:%d/%m %H:%M})"
        except (TypeError, ValueError):
            pass
        righe.append(riga)
        if len(righe) == 8:
            break
    if not righe:
        raise ErroreStrumento(f'non trovo notizie su "{argomento}".' if argomento else "non trovo notizie.")
    intestazione = f'Notizie su "{argomento}"' if argomento else "Notizie principali in Italia"
    return f"{intestazione} (fonte: Google News):\n" + "\n".join(righe)


def apri_sito(indirizzo):
    indirizzo = (indirizzo or "").strip()
    if not re.match(r"https?://", indirizzo, re.IGNORECASE):
        indirizzo = "https://" + indirizzo
    if " " in indirizzo or "." not in indirizzo:
        raise ErroreStrumento(f'"{indirizzo}" non sembra l\'indirizzo di un sito.')
    webbrowser.open(indirizzo)
    return f"Ho aperto {indirizzo} nel browser."


def cerca_sul_web(testo):
    testo = (testo or "").strip()
    if not testo:
        raise ErroreStrumento("non so cosa cercare.")
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(testo))
    return f'Ho aperto nel browser la ricerca Google di "{testo}".'


def apri_programma(nome, programmi):
    chiave = (nome or "").strip().lower()
    if not chiave:
        raise ErroreStrumento("non so quale programma aprire.")
    noti = {k.lower(): v for k, v in programmi.items()}
    percorso = noti.get(chiave)
    if percorso is None:
        # "il blocco note" o "blocco" bastano per trovare "blocco note".
        percorso = next((v for k, v in noti.items() if k in chiave or chiave in k), None)
    if percorso is None:
        raise ErroreStrumento(
            f'non conosco il programma "{nome}". Posso aprire: {", ".join(programmi)}. '
            "Altri programmi si aggiungono in config.json."
        )
    if not hasattr(os, "startfile"):
        raise ErroreStrumento("posso aprire programmi solo su Windows.")
    try:
        os.startfile(percorso)
    except OSError:
        raise ErroreStrumento(f'non riesco ad aprire "{nome}" ({percorso}): controlla config.json.') from None
    return f"Ho aperto {nome}."


_OPERAZIONI = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNZIONI = {
    "sqrt": math.sqrt, "radice": math.sqrt, "abs": abs, "round": round, "arrotonda": round,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
    "log": math.log, "ln": math.log, "log10": math.log10,
    "floor": math.floor, "ceil": math.ceil, "factorial": math.factorial, "fattoriale": math.factorial,
}
_COSTANTI = {"pi": math.pi, "pigreco": math.pi, "e": math.e}


def _valuta(nodo):
    """Calcola un'espressione già analizzata, permettendo solo numeri, operazioni e funzioni note."""
    if isinstance(nodo, ast.Constant) and type(nodo.value) in (int, float):
        return nodo.value
    if isinstance(nodo, ast.Name) and nodo.id.lower() in _COSTANTI:
        return _COSTANTI[nodo.id.lower()]
    if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERAZIONI:
        return _OPERAZIONI[type(nodo.op)](_valuta(nodo.operand))
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERAZIONI:
        sinistra, destra = _valuta(nodo.left), _valuta(nodo.right)
        # Evita conti enormi che bloccherebbero il PC, come 9**9**9.
        if isinstance(nodo.op, ast.Pow) and (abs(destra) > 1000 or abs(sinistra) > 1e100):
            raise ValueError("numero troppo grande")
        return _OPERAZIONI[type(nodo.op)](sinistra, destra)
    if (
        isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
        and nodo.func.id.lower() in _FUNZIONI and not nodo.keywords
    ):
        funzione = _FUNZIONI[nodo.func.id.lower()]
        argomenti = [_valuta(a) for a in nodo.args]
        if funzione is math.factorial and argomenti and argomenti[0] > 1000:
            raise ValueError("numero troppo grande")
        return funzione(*argomenti)
    raise ValueError("espressione non permessa")


def calcola(espressione):
    espressione = (espressione or "").strip()
    testo = espressione.replace("^", "**").replace("×", "*").replace("÷", "/").replace(":", "/")
    if not re.search(r"[a-zA-Z]", testo):
        testo = re.sub(r"(\d),(\d)", r"\1.\2", testo)  # 3,5 → 3.5
    try:
        risultato = _valuta(ast.parse(testo, mode="eval").body)
        if isinstance(risultato, complex) or (isinstance(risultato, float) and not math.isfinite(risultato)):
            raise ValueError("risultato non reale")
    except ZeroDivisionError:
        raise ErroreStrumento("non si può dividere per zero.") from None
    except (SyntaxError, TypeError, ValueError, OverflowError):
        raise ErroreStrumento(f'non riesco a calcolare "{espressione}".') from None
    return f"{espressione} = {_numero(risultato)}"


def timer(minuti, messaggio, avvisa):
    try:
        minuti = float(str(minuti).replace(",", "."))
    except ValueError:
        raise ErroreStrumento("dimmi dopo quanti minuti deve suonare il timer.") from None
    if not 0 < minuti <= 24 * 60:
        raise ErroreStrumento("il timer deve durare al massimo 24 ore.")
    messaggio = (messaggio or "").strip() or "tempo scaduto!"
    allarme = threading.Timer(minuti * 60, avvisa, args=[f"Timer: {messaggio}"])
    allarme.daemon = True
    allarme.start()
    scadenza = datetime.now() + timedelta(minutes=minuti)
    return f"Timer di {_durata(minuti)} impostato: suonerà alle {scadenza:%H:%M:%S}."


def _memoria_ram():
    """(GB usati, GB totali), oppure None se non si riesce a leggerla."""
    try:
        if sys.platform == "win32":
            class StatoMemoria(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                    (nome, ctypes.c_ulonglong) for nome in (
                        "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                        "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]
            stato = StatoMemoria()
            stato.dwLength = ctypes.sizeof(stato)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stato)):
                return None
            totale, libera = stato.ullTotalPhys, stato.ullAvailPhys
        else:
            pagina = os.sysconf("SC_PAGE_SIZE")
            totale, libera = os.sysconf("SC_PHYS_PAGES") * pagina, os.sysconf("SC_AVPHYS_PAGES") * pagina
    except (AttributeError, OSError, ValueError):
        return None
    return (totale - libera) / 1024**3, totale / 1024**3


def _batteria():
    """(percentuale, in carica) su Windows, None se non c'è una batteria."""
    if sys.platform != "win32":
        return None

    class StatoAlimentazione(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    stato = StatoAlimentazione()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(stato)):
        return None
    if stato.BatteryFlag & 128 or stato.BatteryLifePercent == 255:  # 128 = nessuna batteria
        return None
    return stato.BatteryLifePercent, stato.ACLineStatus == 1


def _ore_di_accensione():
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
            return ctypes.windll.kernel32.GetTickCount64() / 3_600_000
        with open("/proc/uptime") as f:
            return float(f.read().split()[0]) / 3600
    except (AttributeError, OSError, ValueError):
        return None


def _scheda_video():
    """Dati della scheda NVIDIA letti con nvidia-smi (installato insieme ai driver)."""
    try:
        risultato = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # niente finestra nera su Windows
        )
        nome, usata, totale, temperatura, utilizzo = [p.strip() for p in risultato.stdout.splitlines()[0].split(",")]
        return nome, int(usata) / 1024, int(totale) / 1024, int(temperatura), int(utilizzo)
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None


def diagnostica():
    righe = [
        f"Diagnostica del sistema ({datetime.now():%d/%m/%Y %H:%M})",
        f"Sistema: {platform.system()} {platform.release()}, processore con {os.cpu_count()} core.",
    ]
    ore = _ore_di_accensione()
    if ore is not None:
        righe.append(f"Acceso da: {int(ore)} ore e {int(ore % 1 * 60)} minuti.")
    ram = _memoria_ram()
    if ram:
        righe.append(f"Memoria RAM: {_gb(ram[0])} usati su {_gb(ram[1])} ({ram[0] / ram[1]:.0%}).")
    disco = os.path.abspath(os.sep)
    spazio = shutil.disk_usage(disco)
    righe.append(f"Disco {disco}: {spazio.free / 1024**3:.0f} GB liberi su {spazio.total / 1024**3:.0f} GB.")
    scheda = _scheda_video()
    if scheda:
        nome, usata, totale, temperatura, utilizzo = scheda
        righe.append(f"Scheda video {nome}: {_gb(usata)} usati su {_gb(totale)}, "
                     f"temperatura {temperatura}°C, utilizzo {utilizzo}%.")
    batteria = _batteria()
    if batteria:
        righe.append(f"Batteria: {batteria[0]}%{' (in carica)' if batteria[1] else ''}.")
    return "\n".join(righe)


# Tasti multimediali di Windows: (codice del tasto, quante volte premerlo)
_TASTI = {
    "alza_volume": (0xAF, 5, "Ho alzato il volume."),
    "abbassa_volume": (0xAE, 5, "Ho abbassato il volume."),
    "muto": (0xAD, 1, "Ho attivato o disattivato l'audio."),
    "play_pausa": (0xB3, 1, "Ho messo in pausa o fatto ripartire la riproduzione."),
    "successiva": (0xB0, 1, "Sono passato alla traccia successiva."),
    "precedente": (0xB1, 1, "Sono tornato alla traccia precedente."),
}


def multimedia(azione):
    if azione not in _TASTI:
        raise ErroreStrumento(f'azione "{azione}" sconosciuta. Possibili: {", ".join(_TASTI)}.')
    if sys.platform != "win32":
        raise ErroreStrumento("il controllo di volume e musica funziona solo su Windows.")
    tasto, volte, frase = _TASTI[azione]
    for _ in range(volte):
        ctypes.windll.user32.keybd_event(tasto, 0, 0, 0)
        ctypes.windll.user32.keybd_event(tasto, 0, 2, 0)  # 2 = tasto rilasciato
    return frase


def _schema(nome, descrizione, parametri, obbligatori):
    return {
        "type": "function",
        "function": {
            "name": nome,
            "description": descrizione,
            "parameters": {"type": "object", "properties": parametri, "required": obbligatori},
        },
    }


def _testo(descrizione):
    return {"type": "string", "description": descrizione}


def schemi(config):
    """Descrive al modello gli strumenti che può usare."""
    elenco = []
    if config["internet"]:
        elenco += [
            _schema("meteo", "Meteo attuale e previsioni dei prossimi 3 giorni per una città.",
                    {"citta": _testo("Nome della città, per esempio Cagliari")}, ["citta"]),
            _schema("wikipedia",
                    "Cerca un argomento su Wikipedia in italiano e ne restituisce il riassunto. "
                    "Usalo per verificare fatti su persone, luoghi, storia, scienza.",
                    {"argomento": _testo("Cosa cercare")}, ["argomento"]),
            _schema("notizie",
                    "Ultime notizie da Google News. Senza argomento restituisce le notizie principali in Italia.",
                    {"argomento": _testo("Argomento delle notizie (facoltativo)")}, []),
            _schema("cerca_in_rete",
                    "Cerca sul web e legge la prima pagina trovata. Usalo per fatti recenti, prezzi, orari, guide, "
                    "recensioni e tutto quello che Wikipedia non sa.",
                    {"domanda": _testo("Cosa cercare, con parole chiave precise")}, ["domanda"]),
            _schema("leggi_pagina", "Legge il testo di una pagina web (per esempio un risultato della ricerca).",
                    {"indirizzo": _testo("Indirizzo della pagina")}, ["indirizzo"]),
        ]
        if (config.get("calendario_ics") or "").strip():
            elenco.append(_schema("agenda", "Gli impegni del calendario dell'utente.",
                                  {"quando": {"type": "string", "enum": ["oggi", "domani", "settimana"],
                                              "description": "Quali giorni"}}, []))
        if (config.get("telefono_ntfy") or "").strip():
            elenco.append(_schema("manda_al_telefono",
                                  "Manda un messaggio al telefono dell'utente (una lista, un indirizzo, un appunto "
                                  "da avere con sé). Usalo solo quando l'utente lo chiede.",
                                  {"titolo": _testo("Titolo breve"), "messaggio": _testo("Il testo da mandare")},
                                  ["messaggio"]))
    elenco += [
        _schema("apri_sito", "Apre un sito web nel browser dell'utente.",
                {"indirizzo": _testo("Indirizzo del sito, per esempio youtube.com")}, ["indirizzo"]),
        _schema("cerca_sul_web",
                "Apre una ricerca Google nel browser dell'utente. Tu non vedi i risultati: "
                "usalo solo quando l'utente vuole vedere una ricerca.",
                {"testo": _testo("Cosa cercare")}, ["testo"]),
        _schema("apri_programma",
                f"Apre un programma sul PC dell'utente. Programmi disponibili: {', '.join(config['programmi'])}.",
                {"nome": _testo("Nome del programma, tra quelli disponibili")}, ["nome"]),
        _schema("calcola",
                "Calcola un'espressione matematica in modo esatto. Usalo per qualsiasi conto invece di farlo a mente. "
                "% è il resto della divisione: per le percentuali scrivi per esempio 250 * 17 / 100.",
                {"espressione": _testo("Espressione, per esempio (12.5 + 3) * 2 oppure sqrt(144)")},
                ["espressione"]),
        _schema("timer", "Imposta un timer: allo scadere l'utente riceve un avviso.",
                {"minuti": {"type": "number", "description": "Dopo quanti minuti suonare (0.5 = 30 secondi)"},
                 "messaggio": _testo("Cosa ricordare all'utente allo scadere (facoltativo)")},
                ["minuti"]),
        _schema("promemoria",
                "Salva un promemoria con data e ora: all'ora giusta Jarvis lo dice all'utente, anche dopo un "
                "riavvio del PC. Usalo per \"ricordami di...\" con un momento preciso.",
                {"quando": _testo("Quando, come lo direbbe l'utente: \"domani alle 18\", \"venerdì 9:30\", "
                                  "\"tra 2 ore\", \"3 novembre alle 10\""),
                 "messaggio": _testo("Cosa ricordare, per esempio: chiamare la nonna")},
                ["quando", "messaggio"]),
        _schema("elenco_promemoria", "Elenca i promemoria in attesa, con il loro numero.", {}, []),
        _schema("cancella_promemoria", "Cancella un promemoria in attesa.",
                {"numero": {"type": "number", "description": "Il numero del promemoria nell'elenco"}}, ["numero"]),
        _schema("cerca_file",
                "Cerca un file per nome nelle cartelle Documenti, Desktop e Download dell'utente.",
                {"nome": _testo("Una o più parole del nome del file")}, ["nome"]),
        _schema("leggi_file",
                "Legge un documento dell'utente (testo, Word, PDF...) per rispondere a domande su di esso. "
                "Non lo modifica.",
                {"percorso": _testo("Il percorso del file, come lo restituisce cerca_file"),
                 "da": {"type": "number", "description": "Da che carattere continuare a leggere (facoltativo)"}},
                ["percorso"]),
        _schema("ricorda",
                "Salva nella memoria permanente una cosa importante e duratura sull'utente: impegni, gusti, "
                "persone care, informazioni utili in futuro.",
                {"fatto": _testo("Il fatto, scritto in prima persona come lo direbbe l'utente: "
                                 "\"Venerdì ho la verifica di storia\"")}, ["fatto"]),
        _schema("ricordi",
                "Cerca nel tuo diario e nelle conversazioni passate (\"di cosa abbiamo parlato ieri?\", "
                "\"ti ricordi quel modpack?\").",
                {"cosa": _testo("Cosa cercare (facoltativo)"),
                 "giorno": _testo("Un giorno preciso: oggi, ieri o una data come 2026-10-27 (facoltativo)")}, []),
        _schema("guarda_schermo",
                "Guarda lo schermo dell'utente in questo momento e risponde a una domanda su quello che si vede.",
                {"domanda": _testo("Cosa vuoi sapere, per esempio: cosa c'è scritto nell'errore?")}, ["domanda"]),
        _schema("diagnostica",
                "Controlla lo stato del PC: memoria RAM, disco, scheda video (memoria e temperatura), "
                "batteria e da quanto tempo è acceso.",
                {}, []),
        _schema("multimedia", "Controlla volume e musica del PC.",
                {"azione": {"type": "string", "enum": list(_TASTI), "description": "Cosa fare"}}, ["azione"]),
        _schema("spotify", "Fa partire su Spotify un brano, un album, un artista o una playlist.",
                {"cosa": _testo("Cosa ascoltare, per esempio: Back in Black AC/DC, oppure: playlist lo-fi")}, []),
        _schema("server_minecraft",
                "Controlla un server di Minecraft: se è acceso, la versione e chi sta giocando.",
                {"indirizzo": _testo("Indirizzo del server, con la porta se non è 25565 (facoltativo: "
                                     "senza, quello salvato in config.json)")}, []),
    ]
    if config.get("webcam", True):
        elenco.append(_schema("guarda_webcam",
                              "Scatta una foto con la webcam e risponde a una domanda su quello che si vede. Usalo "
                              "solo quando l'utente te lo chiede (\"guardami\", \"cosa ho in mano?\").",
                              {"domanda": _testo("Cosa vuoi sapere")}, ["domanda"]))
    return elenco


def valida(nome, argomenti, elenco):
    """Controlla gli argomenti chiesti dal modello contro lo schema dello strumento.

    Restituisce None se vanno bene, altrimenti una frase che spiega il problema.
    """
    schema = next((s["function"]["parameters"] for s in elenco if s["function"]["name"] == nome), None)
    if schema is None:
        return f"lo strumento {nome} non esiste"
    if not isinstance(argomenti, dict):
        return "gli argomenti devono essere un oggetto JSON"
    mancanti = [campo for campo in schema["required"] if campo not in argomenti]
    if mancanti:
        return f"manca {', '.join(mancanti)}"
    for campo, valore in argomenti.items():
        regola = schema["properties"].get(campo)
        if regola is None:
            return f"argomento sconosciuto: {campo}"
        if regola["type"] == "string" and not isinstance(valore, str):
            return f"{campo} deve essere un testo"
        if regola["type"] == "number" and (isinstance(valore, bool) or not isinstance(valore, (int, float))):
            return f"{campo} deve essere un numero"
        if "enum" in regola and valore not in regola["enum"]:
            return f"{campo} deve essere uno tra: {', '.join(regola['enum'])}"
    return None


def descrivi(nome, argomenti):
    """Frase da mostrare all'utente mentre lo strumento lavora."""
    a = {k: str(v) for k, v in argomenti.items()}
    try:
        durata = _durata(float(a.get("minuti", "").replace(",", ".")))
    except ValueError:
        durata = "?"
    frasi = {
        "meteo": f"Controllo il meteo di {a.get('citta', '')}...",
        "wikipedia": f"Cerco «{a.get('argomento', '')}» su Wikipedia...",
        "notizie": f"Cerco notizie su «{a['argomento']}»..." if a.get("argomento") else "Leggo le ultime notizie...",
        "apri_sito": f"Apro {a.get('indirizzo', '')}...",
        "cerca_sul_web": f"Apro la ricerca di «{a.get('testo', '')}» nel browser...",
        "apri_programma": f"Apro {a.get('nome', '')}...",
        "calcola": f"Calcolo {a.get('espressione', '')}...",
        "timer": f"Imposto un timer di {durata}...",
        "promemoria": f"Salvo il promemoria ({a.get('quando', '')})...",
        "cerca_in_rete": f"Cerco «{a.get('domanda', '')}» sul web...",
        "leggi_pagina": f"Leggo {a.get('indirizzo', '')}...",
        "cerca_file": f"Cerco i file «{a.get('nome', '')}»...",
        "leggi_file": f"Leggo {a.get('percorso', '').replace(chr(92), '/').rsplit('/', 1)[-1]}...",
        "ricorda": "Lo annoto nella memoria...",
        "ricordi": "Cerco nei miei ricordi...",
        "guarda_schermo": "Guardo lo schermo...",
        "guarda_webcam": "Guardo dalla webcam...",
        "elenco_promemoria": "Guardo i promemoria...",
        "cancella_promemoria": "Cancello il promemoria...",
        "diagnostica": "Eseguo la diagnostica del sistema...",
        "multimedia": "Comando a volume e musica...",
        "agenda": "Guardo il calendario...",
        "spotify": f"Cerco «{a.get('cosa', '')}» su Spotify..." if a.get("cosa") else "Apro Spotify...",
        "server_minecraft": "Controllo il server di Minecraft...",
        "manda_al_telefono": "Lo mando al telefono...",
    }
    return frasi.get(nome, f"Uso lo strumento {nome}...")


def esegui(nome, argomenti, config, avvisa):
    """Esegue lo strumento chiesto dal modello. Gli errori diventano testo, così il modello può spiegarli."""
    try:
        if nome in STRUMENTI_INTERNET and not config["internet"]:
            raise ErroreStrumento("internet è disattivato in config.json.")
        if nome == "meteo":
            return meteo(argomenti.get("citta") or config["citta"])
        if nome == "wikipedia":
            return wikipedia(argomenti.get("argomento"))
        if nome == "notizie":
            return notizie(argomenti.get("argomento"))
        if nome == "apri_sito":
            return apri_sito(argomenti.get("indirizzo"))
        if nome == "cerca_sul_web":
            return cerca_sul_web(argomenti.get("testo"))
        if nome == "apri_programma":
            return apri_programma(argomenti.get("nome"), config["programmi"])
        if nome == "calcola":
            return calcola(str(argomenti.get("espressione", "")))
        if nome == "timer":
            return timer(argomenti.get("minuti"), argomenti.get("messaggio"), avvisa)
        if nome == "cerca_in_rete":
            return rete.cerca_in_rete(argomenti.get("domanda"))
        if nome == "leggi_pagina":
            return rete.leggi_pagina(argomenti.get("indirizzo"))
        if nome == "cerca_file":
            return documenti.cerca_file(argomenti.get("nome"), config)
        if nome == "leggi_file":
            return documenti.leggi_file(argomenti.get("percorso"), config, argomenti.get("da", 0))
        if nome == "ricordi":
            if argomenti.get("giorno"):
                return ricordi.diario_di(argomenti["giorno"])
            return ricordi.cerca(argomenti.get("cosa"))
        if nome == "promemoria":
            return promemoria.aggiungi(argomenti.get("quando"), argomenti.get("messaggio"))
        if nome == "elenco_promemoria":
            return promemoria.descrivi_elenco()
        if nome == "cancella_promemoria":
            return promemoria.cancella(argomenti.get("numero"))
        if nome == "diagnostica":
            return diagnostica()
        if nome == "multimedia":
            return multimedia(argomenti.get("azione"))
        if nome == "agenda":
            return integrazioni.agenda(config, argomenti.get("quando") or "oggi")
        if nome == "spotify":
            return integrazioni.spotify(argomenti.get("cosa"))
        if nome == "server_minecraft":
            return integrazioni.server_minecraft(argomenti.get("indirizzo") or config.get("server_minecraft"))
        if nome == "manda_al_telefono":
            return integrazioni.al_telefono(config, argomenti.get("titolo") or config.get("nome", "Jarvis"),
                                            argomenti.get("messaggio") or "", attendi=True)
        raise ErroreStrumento(f"lo strumento {nome} non esiste.")
    except (ErroreStrumento, promemoria.ErrorePromemoria, rete.ErroreRete, documenti.ErroreDocumenti,
            integrazioni.ErroreIntegrazione, ValueError) as e:
        return f"Errore: {e}"
    except Exception as e:  # una risposta imprevista da un sito non deve far cadere Jarvis
        return f"Errore: qualcosa è andato storto ({e})."
