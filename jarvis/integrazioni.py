"""Jarvis e il resto del tuo mondo: calendario, Spotify, server di Minecraft, giochi e telefono.

- Calendario: il link "indirizzo segreto in formato iCal" di Google Calendar (o di qualunque calendario) in
  config.json, alla voce "calendario_ics". Jarvis lo legge e basta: non modifica niente.
- Spotify: trova il brano o la playlist e la apre nell'app di Spotify.
- Minecraft: chiede al server se è acceso, che versione ha e chi sta giocando.
- Giochi: vede quando parte un gioco, per attivare da solo la modalità gioco.
- Telefono: manda avvisi e messaggi all'app ntfy (gratis, senza account) sul telefono.
"""

import calendar
import json
import os
import re
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta, timezone

GIORNI_ICS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
# Il programma di ogni gioco (come lo mostra Gestione attività) e il suo nome. javaw.exe è Minecraft Java.
NOMI_GIOCHI = {"javaw.exe": "Minecraft", "Minecraft.Windows.exe": "Minecraft", "RobloxPlayerBeta.exe": "Roblox",
               "FortniteClient-Win64-Shipping.exe": "Fortnite", "cs2.exe": "Counter-Strike 2",
               "VALORANT-Win64-Shipping.exe": "Valorant", "GTA5.exe": "GTA V", "RocketLeague.exe": "Rocket League",
               "eldenring.exe": "Elden Ring"}
GIOCHI_PREDEFINITI = list(NOMI_GIOCHI)


class ErroreIntegrazione(Exception):
    pass


# --- Calendario (formato iCal) ---

_cache_calendario = {"indirizzo": None, "quando": 0.0, "eventi": []}
_lucchetto = threading.Lock()


def _righe_ics(testo):
    righe = []
    for riga in testo.replace("\r\n", "\n").split("\n"):
        if riga[:1] in (" ", "\t") and righe:
            righe[-1] += riga[1:]  # le righe lunghe continuano su quella dopo
        elif riga:
            righe.append(riga)
    return righe


def _valore_ics(testo):
    return testo.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _data_ics(valore, parametri):
    """Da 20261028 / 20261028T150000 / 20261028T140000Z a date o datetime locale (senza fuso)."""
    valore = valore.strip()
    if "T" not in valore:
        return datetime.strptime(valore[:8], "%Y%m%d").date()
    momento = datetime.strptime(valore[:15], "%Y%m%dT%H%M%S")
    if valore.endswith("Z"):
        return momento.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    fuso = parametri.get("TZID")
    if fuso:
        try:
            from zoneinfo import ZoneInfo

            return momento.replace(tzinfo=ZoneInfo(fuso)).astimezone().replace(tzinfo=None)
        except Exception:  # fuso sconosciuto o dati dei fusi mancanti su Windows: ora locale
            pass
    return momento


def leggi_ics(testo):
    """Gli eventi di un calendario iCal: [{"inizio", "fine", "titolo", "luogo", "regola", "esclusi", "uid"}]."""
    eventi, evento, sostituiti = [], None, {}
    for riga in _righe_ics(testo):
        if riga == "BEGIN:VEVENT":
            evento = {"titolo": "", "luogo": "", "regola": {}, "esclusi": set(), "uid": "", "annullato": False}
            continue
        if riga == "END:VEVENT" and evento is not None:
            if "inizio" in evento and not evento["annullato"]:
                if evento.get("istanza") is not None:  # una ripetizione spostata: sostituisce quella originale
                    sostituiti.setdefault(evento["uid"], set()).add(evento["istanza"])
                eventi.append(evento)
            evento = None
            continue
        if evento is None or ":" not in riga:
            continue
        intestazione, valore = riga.split(":", 1)
        nome, *altri = intestazione.split(";")
        parametri = dict(p.split("=", 1) for p in altri if "=" in p)
        try:
            if nome == "DTSTART":
                evento["inizio"] = _data_ics(valore, parametri)
            elif nome == "DTEND":
                evento["fine"] = _data_ics(valore, parametri)
            elif nome == "SUMMARY":
                evento["titolo"] = _valore_ics(valore)
            elif nome == "LOCATION":
                evento["luogo"] = _valore_ics(valore)
            elif nome == "UID":
                evento["uid"] = valore
            elif nome == "STATUS" and valore.upper() == "CANCELLED":
                evento["annullato"] = True
            elif nome == "RRULE":
                evento["regola"] = dict(p.split("=", 1) for p in valore.split(";") if "=" in p)
            elif nome == "EXDATE":
                evento["esclusi"] |= {_data_ics(v, parametri) for v in valore.split(",")}
            elif nome == "RECURRENCE-ID":
                evento["istanza"] = _data_ics(valore, parametri)
        except ValueError:
            continue
    for evento in eventi:
        if evento["regola"]:
            evento["esclusi"] |= sostituiti.get(evento["uid"], set())
    return eventi


def _inizio_del_giorno(valore):
    return valore if isinstance(valore, datetime) else datetime.combine(valore, datetime.min.time())


def _giorni_del_mese(inizio, anno, mese, regola):
    """I giorni di un mese in cui si ripete un evento mensile: "il 15", "l'ultimo giorno" (BYMONTHDAY=-1),
    "il primo lunedì" (BYDAY=1MO), "l'ultimo venerdì" (BYDAY=-1FR)."""
    lunghezza = calendar.monthrange(anno, mese)[1]
    giorni = []
    if regola.get("BYDAY"):
        for voce in regola["BYDAY"].split(","):
            m = re.fullmatch(r"([+-]?\d*)(MO|TU|WE|TH|FR|SA|SU)", voce.strip())
            if not m:
                continue
            settimanale = [g for g in range(1, lunghezza + 1)
                           if date(anno, mese, g).weekday() == GIORNI_ICS.index(m.group(2))]
            if not m.group(1):
                giorni += settimanale  # tutti i lunedì del mese
            elif -len(settimanale) <= int(m.group(1)) <= len(settimanale) and int(m.group(1)):
                n = int(m.group(1))
                giorni.append(settimanale[n - 1 if n > 0 else n])
    else:
        for voce in str(regola.get("BYMONTHDAY", inizio.day)).split(","):
            try:
                giorno = int(voce)
            except ValueError:
                continue
            giorno = lunghezza + giorno + 1 if giorno < 0 else giorno
            if 1 <= giorno <= lunghezza:  # il 31 nei mesi più corti si salta
                giorni.append(giorno)
    return [inizio.replace(year=anno, month=mese, day=g) for g in sorted(set(giorni))]


def _ripetizioni(evento, fine):
    """Le date di inizio di un evento (anche ripetuto) fino a `fine`."""
    inizio = evento["inizio"]
    regola = evento["regola"]
    if not regola:
        yield inizio
        return
    frequenza = regola.get("FREQ", "")
    passo = max(1, int(regola.get("INTERVAL", "1") or 1))
    quanti = int(regola["COUNT"]) if regola.get("COUNT", "").isdigit() else None
    fino_a = None
    if regola.get("UNTIL"):
        try:
            fino_a = _inizio_del_giorno(_data_ics(regola["UNTIL"], {}))
        except ValueError:
            pass
    giorni = [GIORNI_ICS.index(g[-2:]) for g in regola.get("BYDAY", "").split(",") if g[-2:] in GIORNI_ICS]
    fatti = 0
    for k in range(3000):  # un limite, per sicurezza
        if frequenza == "DAILY":
            candidati = [inizio + timedelta(days=k * passo)]
        elif frequenza == "WEEKLY":
            settimana = inizio - timedelta(days=inizio.weekday()) + timedelta(weeks=k * passo)
            candidati = [settimana + timedelta(days=g) for g in sorted(giorni or [inizio.weekday()])]
        elif frequenza == "MONTHLY":
            mese = inizio.month - 1 + k * passo
            anno, mese = inizio.year + mese // 12, mese % 12 + 1
            candidati = _giorni_del_mese(inizio, anno, mese, regola)
        elif frequenza == "YEARLY":
            try:
                candidati = [inizio.replace(year=inizio.year + k * passo)]
            except ValueError:
                candidati = []  # il 29 febbraio
        else:
            yield inizio
            return
        for candidato in candidati:
            if candidato < inizio:
                continue
            if (fino_a and _inizio_del_giorno(candidato) > fino_a) or _inizio_del_giorno(candidato) >= fine:
                return
            if quanti is not None and fatti >= quanti:
                return
            fatti += 1
            if candidato not in evento["esclusi"]:
                yield candidato


def eventi_tra(eventi, da, a):
    """Gli eventi che cadono tra `da` e `a` (datetime), in ordine: [(inizio, titolo, luogo, tutto_il_giorno)]."""
    trovati = []
    for evento in eventi:
        for inizio in _ripetizioni(evento, a):
            if da <= _inizio_del_giorno(inizio) < a or (not isinstance(inizio, datetime) and
                                                       da.date() <= inizio < a.date()):
                trovati.append((inizio, evento["titolo"], evento["luogo"], not isinstance(inizio, datetime)))
    trovati.sort(key=lambda e: _inizio_del_giorno(e[0]))
    return trovati


def scarica_calendario(indirizzo):
    """Gli eventi del calendario (tenuti per 15 minuti, per non scaricarlo a ogni domanda)."""
    with _lucchetto:
        if _cache_calendario["indirizzo"] == indirizzo and time.monotonic() - _cache_calendario["quando"] < 900:
            return _cache_calendario["eventi"]
    if indirizzo.startswith("webcal://"):
        indirizzo_http = "https://" + indirizzo[len("webcal://"):]
    else:
        indirizzo_http = indirizzo
    if not indirizzo_http.startswith("https://"):
        raise ErroreIntegrazione("il link del calendario deve iniziare con https://")
    richiesta = urllib.request.Request(indirizzo_http, headers={"User-Agent": "Jarvis"})
    try:
        with urllib.request.urlopen(richiesta, timeout=20) as risposta:
            testo = risposta.read(5_000_000).decode("utf-8", errors="replace")
    except OSError as e:
        raise ErroreIntegrazione(f"non riesco a leggere il calendario ({e})") from None
    if "BEGIN:VCALENDAR" not in testo:
        raise ErroreIntegrazione("il link non è un calendario in formato iCal")
    eventi = leggi_ics(testo)
    with _lucchetto:
        _cache_calendario.update(indirizzo=indirizzo, quando=time.monotonic(), eventi=eventi)
    return eventi


def agenda(config, quando="oggi", adesso=None):
    """Gli impegni di oggi, domani o della settimana, da dire all'utente."""
    indirizzo = (config.get("calendario_ics") or "").strip()
    if not indirizzo:
        raise ErroreIntegrazione("il calendario non è collegato: incolla il suo link iCal in config.json, alla voce "
                                 "calendario_ics (vedi il README)")
    adesso = adesso or datetime.now()
    oggi = datetime.combine(adesso.date(), datetime.min.time())
    quando = (quando or "oggi").lower().strip()
    if quando == "domani":
        da, a, descrizione = oggi + timedelta(days=1), oggi + timedelta(days=2), "domani"
    elif quando in ("settimana", "questa settimana", "prossimi giorni"):
        da, a, descrizione = oggi, oggi + timedelta(days=7), "nei prossimi 7 giorni"
    else:
        da, a, descrizione = oggi, oggi + timedelta(days=1), "oggi"
    eventi = eventi_tra(scarica_calendario(indirizzo), da, a)
    if not eventi:
        return f"Nel calendario non c'è niente {descrizione}."
    righe = []
    for inizio, titolo, luogo, tutto_il_giorno in eventi:
        giorno = "" if descrizione != "nei prossimi 7 giorni" else \
            f"{['lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì', 'sabato', 'domenica'][inizio.weekday()]} "
        ora = "tutto il giorno" if tutto_il_giorno else f"alle {inizio.hour}:{inizio.minute:02d}"
        righe.append(f"- {giorno}{ora}: {titolo}" + (f" ({luogo})" if luogo else ""))
    return f"Impegni {descrizione}:\n" + "\n".join(righe)


# --- Spotify ---

def spotify(cosa):
    """Trova un brano, un album o una playlist e lo apre nell'app di Spotify (o sul sito se l'app non c'è)."""
    cosa = (cosa or "").strip()
    if not cosa:
        _apri("spotify:")
        return "Ho aperto Spotify."
    trovato = None
    try:
        import rete

        for _, indirizzo, _ in rete.cerca(f"{cosa} site:open.spotify.com"):
            m = re.search(r"open\.spotify\.com/(?:intl-\w+/)?(track|album|playlist|artist)/(\w+)", indirizzo)
            if m:
                trovato = m.groups()
                break
    except Exception:  # senza internet o senza risultati si apre la ricerca dentro Spotify
        trovato = None
    if trovato:
        tipo, codice = trovato
        if _apri(f"spotify:{tipo}:{codice}"):
            return f"Ho aperto «{cosa}» su Spotify: se non parte da solo, premi play."
        webbrowser.open(f"https://open.spotify.com/{tipo}/{codice}")
        return f"L'app di Spotify non c'è: ho aperto «{cosa}» sul sito."
    if _apri("spotify:search:" + urllib.parse.quote(cosa)):
        return f"Ho aperto la ricerca «{cosa}» su Spotify: scegli il brano e premi play."
    webbrowser.open("https://open.spotify.com/search/" + urllib.parse.quote(cosa))
    return f"L'app di Spotify non c'è: ho aperto la ricerca «{cosa}» sul sito."


def _apri(uri):
    if sys.platform != "win32":
        return False
    try:
        os.startfile(uri)
        return True
    except OSError:
        return False


# --- Server di Minecraft ---

def _varint(numero):
    risultato = b""
    numero &= 0xFFFFFFFF
    while True:
        byte = numero & 0x7F
        numero >>= 7
        risultato += bytes([byte | (0x80 if numero else 0)])
        if not numero:
            return risultato


def _leggi_varint(connessione):
    numero = 0
    for i in range(5):
        byte = connessione.recv(1)
        if not byte:
            raise ErroreIntegrazione("il server ha chiuso la connessione")
        numero |= (byte[0] & 0x7F) << (7 * i)
        if not byte[0] & 0x80:
            return numero
    raise ErroreIntegrazione("il server ha risposto in modo strano")


def _testo_motd(descrizione):
    if isinstance(descrizione, str):
        return re.sub(r"§.", "", descrizione)
    if isinstance(descrizione, dict):
        return _testo_motd(descrizione.get("text", "")) + "".join(_testo_motd(e) for e in descrizione.get("extra", []))
    if isinstance(descrizione, list):
        return "".join(_testo_motd(e) for e in descrizione)
    return ""


def server_minecraft(indirizzo, timeout=5):
    """Chiede al server di Minecraft come sta (lo stesso controllo della lista server del gioco)."""
    indirizzo = (indirizzo or "").strip()
    if not indirizzo:
        raise ErroreIntegrazione("dimmi l'indirizzo del server, o scrivilo in config.json alla voce server_minecraft")
    host, _, porta = indirizzo.rpartition(":") if re.search(r":\d+$", indirizzo) else (indirizzo, "", "25565")
    try:
        with socket.create_connection((host, int(porta)), timeout) as connessione:
            connessione.settimeout(timeout)
            nome = host.encode()
            saluto = _varint(0) + _varint(767) + _varint(len(nome)) + nome + struct.pack(">H", int(porta)) + _varint(1)
            connessione.sendall(_varint(len(saluto)) + saluto + _varint(1) + _varint(0))
            _leggi_varint(connessione)  # lunghezza del pacchetto
            _leggi_varint(connessione)  # tipo del pacchetto
            lunghezza = _leggi_varint(connessione)
            dati = b""
            while len(dati) < lunghezza:
                pezzo = connessione.recv(lunghezza - len(dati))
                if not pezzo:
                    break
                dati += pezzo
    except (OSError, ValueError) as e:
        raise ErroreIntegrazione(f"il server {indirizzo} non risponde: è spento, oppure Radmin VPN non è collegato "
                                 f"({e})") from None
    try:
        stato = json.loads(dati.decode("utf-8"))
    except ValueError:
        raise ErroreIntegrazione("il server ha risposto in modo strano") from None
    giocatori = stato.get("players", {})
    nomi = [g.get("name", "") for g in giocatori.get("sample", []) or []]
    righe = [f"Il server {indirizzo} è acceso.",
             f"Versione: {stato.get('version', {}).get('name', '?')}.",
             f"Giocatori: {giocatori.get('online', 0)} su {giocatori.get('max', '?')}"
             + (f" ({', '.join(nomi)})." if nomi else ".")]
    motd = " ".join(_testo_motd(stato.get("description", "")).split())
    if motd:
        righe.append(f"Messaggio del server: {motd}")
    return "\n".join(righe)


# --- Giochi in esecuzione ---

def processi_in_esecuzione():
    """I nomi dei programmi aperti (solo su Windows; altrove un insieme vuoto)."""
    if sys.platform != "win32":
        return set()
    try:
        risultato = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return set()
    return {riga.split('","')[0].strip('"').lower() for riga in risultato.stdout.splitlines() if riga}


def nome_del_gioco(programma):
    """"Minecraft" per javaw.exe, "Roblox" per RobloxPlayerBeta.exe, e così via."""
    for nome_programma, nome in NOMI_GIOCHI.items():
        if nome_programma.lower() == (programma or "").lower():
            return nome
    return os.path.splitext(programma or "")[0]


def gioco_aperto(config, processi):
    """Il nome del primo gioco della lista che è aperto, oppure None."""
    for gioco in config.get("giochi") or GIOCHI_PREDEFINITI:
        if gioco.lower() in processi:
            return gioco
    return None


# --- Telefono (ntfy) ---

def nuovo_canale_ntfy():
    """Un nome di canale lungo e casuale: chi non lo conosce non può leggere i messaggi."""
    return "jarvis-" + secrets.token_urlsafe(12).replace("_", "x").replace("-", "y").lower()


def al_telefono(config, titolo, messaggio, attendi=False):
    """Manda un messaggio all'app ntfy del telefono, se il canale è configurato. Restituisce un esito."""
    canale = (config.get("telefono_ntfy") or "").strip()
    if not canale:
        raise ErroreIntegrazione("il telefono non è collegato: scrivi /telefono e segui le istruzioni")
    if not (messaggio or "").strip():
        raise ErroreIntegrazione("cosa devo mandare al telefono?")
    server = (config.get("server_ntfy") or "https://ntfy.sh").rstrip("/")
    corpo = json.dumps({"topic": canale, "title": titolo, "message": messaggio[:3500]}).encode("utf-8")

    def invia():
        richiesta = urllib.request.Request(server, data=corpo,
                                           headers={"Content-Type": "application/json", "User-Agent": "Jarvis"})
        with urllib.request.urlopen(richiesta, timeout=15) as risposta:
            risposta.read()

    if not attendi:
        threading.Thread(target=lambda: _senza_errori(invia), daemon=True).start()
        return "Messaggio inviato al telefono."
    try:
        invia()
    except OSError as e:
        raise ErroreIntegrazione(f"non riesco a mandare il messaggio al telefono ({e})") from None
    return "Messaggio inviato al telefono."


def _senza_errori(funzione):
    try:
        funzione()
    except OSError:
        pass


def oggi_e_domani(config, adesso=None):
    """Gli impegni del calendario di oggi, per il briefing ("" se il calendario non c'è o non risponde)."""
    if not (config.get("calendario_ics") or "").strip():
        return ""
    try:
        return agenda(config, "oggi", adesso)
    except ErroreIntegrazione as e:
        return f"Il calendario non risponde ({e})."
