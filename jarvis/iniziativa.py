"""L'iniziativa di Jarvis: parla per primo quando serve.

Un thread controlla ogni 20 secondi se c'è qualcosa da dire:
- i promemoria arrivati all'ora (anche quelli scaduti mentre il PC era spento);
- il briefing del mattino, una volta al giorno;
- gli avvisi sul PC: batteria scarica, disco quasi pieno, scheda video troppo calda, memoria piena;
- un consiglio di pausa dopo ore di computer senza staccare.
"""

import ctypes
import json
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import promemoria
import strumenti

FILE_STATO = Path(__file__).resolve().parent / "dati" / "iniziativa.json"
PAUSA_DOPO = 2 * 3600  # secondi di computer senza staccare prima di consigliare una pausa
STACCO = 5 * 60  # secondi senza toccare mouse e tastiera che contano come pausa


def secondi_di_inattivita():
    """Da quanti secondi l'utente non tocca mouse e tastiera (None se non si può sapere)."""
    if sys.platform != "win32":
        return None

    class UltimoInput(ctypes.Structure):  # LASTINPUTINFO
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    ultimo = UltimoInput()
    ultimo.cbSize = ctypes.sizeof(ultimo)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(ultimo)):
            return None
        adesso = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
    except (AttributeError, OSError):
        return None
    return ((adesso - ultimo.dwTime) & 0xFFFFFFFF) / 1000


def stato_del_pc():
    """I numeri che servono agli avvisi: batteria, disco, temperatura della scheda video, memoria."""
    stato = {}
    batteria = strumenti._batteria()
    if batteria:
        stato["batteria"], stato["in_carica"] = batteria
    try:
        disco = shutil.disk_usage(Path.home().anchor or "/")
        stato["disco_libero_gb"] = disco.free / 1024**3
    except OSError:
        pass
    scheda = strumenti._scheda_video()
    if scheda:
        stato["temperatura_gpu"] = scheda[3]
    memoria = strumenti._memoria_ram()
    if memoria:
        stato["memoria_usata"] = memoria[0] / memoria[1] * 100
    return stato


class Sorvegliante:
    """Il thread dell'iniziativa. `avvisa(messaggio)` fa parlare Jarvis; `proponi(comando)` gli chiede di fare
    qualcosa (per esempio "/briefing") e restituisce False se in quel momento è occupato."""

    def __init__(self, config, avvisa, proponi=None, in_gioco=None, leggi_stato_pc=stato_del_pc,
                 inattivita=secondi_di_inattivita):
        self.config = config
        self.avvisa = avvisa
        self.proponi = proponi or (lambda comando: False)
        self.in_gioco = in_gioco or (lambda: False)
        self._leggi_stato_pc = leggi_stato_pc
        self._inattivita = inattivita
        self._ultimi_avvisi = {}  # tipo di avviso → quando è stato dato
        self._ultimo_controllo_pc = 0.0
        self._attivo_da = None  # da quando l'utente usa il PC senza pause
        self._ultima_pausa_consigliata = 0.0
        self._chiuso = threading.Event()

    def avvia(self):
        threading.Thread(target=self._lavora, daemon=True).start()

    def chiudi(self):
        self._chiuso.set()

    def _lavora(self):
        while not self._chiuso.is_set():
            try:
                self.controlla()
            except Exception:  # l'iniziativa non deve mai far cadere Jarvis
                pass
            self._chiuso.wait(20)

    def controlla(self, adesso=None, orologio=None):
        adesso = adesso or datetime.now()
        orologio = time.monotonic() if orologio is None else orologio
        self._promemoria(adesso)
        self._briefing(adesso)
        if orologio - self._ultimo_controllo_pc >= 120 or not self._ultimo_controllo_pc:
            self._ultimo_controllo_pc = orologio
            if self.config.get("avvisi_pc", True):
                self._avvisi_pc(orologio)
        if self.config.get("consigli_pausa", True):
            self._pausa(orologio)

    # --- Promemoria ---

    def _promemoria(self, adesso):
        for quando, messaggio in promemoria.scaduti(adesso):
            if (adesso - quando).total_seconds() > 600:  # è scaduto mentre Jarvis era spento
                self.avvisa(f"Promemoria (era per {promemoria.descrivi_quando(quando, adesso)}): {messaggio}")
            else:
                self.avvisa(f"Promemoria: {messaggio}")

    # --- Briefing del mattino ---

    def _briefing(self, adesso):
        if not self.config.get("briefing", True) or self.in_gioco():
            return
        try:
            ora, minuti = (int(x) for x in str(self.config.get("ora_briefing", "07:30")).split(":"))
        except ValueError:
            ora, minuti = 7, 30
        if not (ora, minuti) <= (adesso.hour, adesso.minute) < (12, 0):
            return
        stato = _leggi_stato()
        oggi = adesso.date().isoformat()
        if stato.get("ultimo_briefing") == oggi:
            return
        if self.proponi("/briefing"):
            stato["ultimo_briefing"] = oggi
            _scrivi_stato(stato)

    # --- Avvisi sul PC ---

    def _avvisi_pc(self, orologio):
        stato = self._leggi_stato_pc()
        titolo = self.config.get("come_chiamarmi", "")
        t = f", {titolo}" if titolo else ""
        batteria = stato.get("batteria")
        if batteria is not None and not stato.get("in_carica") and batteria <= 20:
            livello = "critica" if batteria <= 10 else "bassa"
            self._avviso(f"batteria_{livello}", orologio, 3600,
                         f"La batteria è al {batteria}%{t}: conviene collegare il caricatore.")
        disco = stato.get("disco_libero_gb")
        if disco is not None and disco < 5:
            self._avviso("disco", orologio, 6 * 3600,
                         f"Il disco è quasi pieno{t}: restano {strumenti._numero(round(disco, 1))} GB liberi.")
        temperatura = stato.get("temperatura_gpu")
        if temperatura is not None and temperatura >= 85:
            self._avviso("temperatura", orologio, 900,
                         f"La scheda video è a {temperatura} gradi{t}: è molto calda, conviene controllare "
                         "le ventole o fare una pausa dal gioco.")
        memoria = stato.get("memoria_usata")
        if memoria is not None and memoria >= 93:
            self._avviso("memoria", orologio, 900,
                         f"La memoria del PC è piena al {memoria:.0f}%{t}: se qualcosa rallenta, chiudere un "
                         "programma aiuterà.")

    def _avviso(self, tipo, orologio, pausa, messaggio):
        """Dà l'avviso, ma non più di una volta ogni `pausa` secondi per lo stesso problema."""
        ultimo = self._ultimi_avvisi.get(tipo)
        if ultimo is None or orologio - ultimo >= pausa:
            self._ultimi_avvisi[tipo] = orologio
            self.avvisa(messaggio)

    # --- Pause ---

    def _pausa(self, orologio):
        inattivo = self._inattivita()
        if inattivo is None:
            return
        if inattivo >= STACCO:
            self._attivo_da = None
            return
        if self._attivo_da is None:
            self._attivo_da = orologio - inattivo
            return
        if self.in_gioco() or orologio - self._attivo_da < PAUSA_DOPO:
            return
        if orologio - self._ultima_pausa_consigliata < PAUSA_DOPO:
            return
        self._ultima_pausa_consigliata = orologio
        ore = int((orologio - self._attivo_da) // 3600)
        titolo = self.config.get("come_chiamarmi", "")
        t = f", {titolo}" if titolo else ""
        durata = f"{ore} {'ora' if ore == 1 else 'ore'} di fila{t}"
        if self.config.get("dai_del", "lei") != "tu":
            self.avvisa(f"È al computer da {durata}: una pausa di qualche minuto le farebbe bene.")
        else:
            self.avvisa(f"Sei al computer da {durata}: una pausa di qualche minuto ti farebbe bene.")


def _leggi_stato():
    try:
        dati = json.loads(FILE_STATO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dati if isinstance(dati, dict) else {}


def _scrivi_stato(stato):
    FILE_STATO.parent.mkdir(exist_ok=True)
    FILE_STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=2), encoding="utf-8")
