"""L'iniziativa di Jarvis: parla per primo quando serve.

Un thread controlla ogni 20 secondi se c'è qualcosa da dire:
- i promemoria arrivati all'ora (anche quelli scaduti mentre il PC era spento);
- il briefing del mattino, una volta al giorno;
- gli avvisi sul PC: batteria scarica, disco quasi pieno, scheda video troppo calda, memoria piena;
- un consiglio di pausa dopo ore di computer senza staccare;
- il diario: quando l'utente fa una pausa, Jarvis riassume le giornate con conversazioni nuove;
- la modalità gioco: si accende da sola quando parte un gioco e si spegne quando il gioco si chiude;
- il ritorno: quando l'utente torna al PC dopo un po', Jarvis lo saluta e gli dice cosa è successo nel frattempo
  (con "presenza_webcam" lo vede anche dalla webcam, prima ancora che tocchi il mouse);
- il telefono: gli avvisi dati mentre l'utente non è al PC arrivano anche all'app ntfy.
"""

import ctypes
import json
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import integrazioni
import promemoria
import strumenti

FILE_STATO = Path(__file__).resolve().parent / "dati" / "iniziativa.json"
PAUSA_DOPO = 2 * 3600  # secondi di computer senza staccare prima di consigliare una pausa
STACCO = 5 * 60  # secondi senza toccare mouse e tastiera che contano come pausa
ASSENZA = 30 * 60  # secondi lontano dal PC dopo i quali, al ritorno, Jarvis saluta


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


def _vede_qualcuno():
    import schermo

    return schermo.vede_qualcuno()


class Sorvegliante:
    """Il thread dell'iniziativa. `avvisa(messaggio)` fa parlare Jarvis; `proponi(comando)` gli chiede di fare
    qualcosa (per esempio "/briefing") e restituisce False se in quel momento è occupato; `cambia_gioco(attiva,
    gioco)` accende o spegne la modalità gioco; `saluta(testo)` gli fa dire il saluto quando l'utente torna."""

    def __init__(self, config, avvisa, proponi=None, in_gioco=None, leggi_stato_pc=stato_del_pc,
                 inattivita=secondi_di_inattivita, scrivi_diario=None, cambia_gioco=None,
                 leggi_processi=integrazioni.processi_in_esecuzione, saluta=None, vede_qualcuno=_vede_qualcuno,
                 al_telefono=integrazioni.al_telefono):
        self.config = config
        self.avvisa = avvisa
        self.proponi = proponi or (lambda comando: False)
        self.in_gioco = in_gioco or (lambda: False)
        self.cambia_gioco = cambia_gioco
        self._leggi_processi = leggi_processi
        self._ultimo_controllo_giochi = 0.0
        self._gioco_acceso_da_me = None  # il gioco per cui Jarvis ha acceso da solo la modalità gioco
        self._gioco_ignorato = None  # l'utente ha spento la modalità gioco durante questa partita: non insiste
        self.saluta = saluta or avvisa
        self._vede_qualcuno = vede_qualcuno
        self._al_telefono = al_telefono
        self._lontano = False
        self._salutato = False
        self._ultimo_sguardo = 0.0
        self._mentre_eri_via = []  # gli avvisi dati mentre l'utente non c'era, da riassumere al suo ritorno
        self._leggi_stato_pc = leggi_stato_pc
        self._inattivita = inattivita
        self._ultimi_avvisi = {}  # tipo di avviso → quando è stato dato
        self._ultimo_controllo_pc = 0.0
        self._attivo_da = None  # da quando l'utente usa il PC senza pause
        self._ultima_pausa_consigliata = 0.0
        self.scrivi_diario = scrivi_diario
        self._ultimo_diario = None
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
        if orologio - self._ultimo_controllo_giochi >= 30 or not self._ultimo_controllo_giochi:
            self._ultimo_controllo_giochi = orologio
            self._giochi()
        self._ritorno(adesso, orologio)
        self._diario(orologio)

    def _diario(self, orologio):
        """All'avvio e poi al massimo una volta all'ora, quando l'utente non sta usando il PC."""
        if not self.scrivi_diario or not self.config.get("diario", True):
            return
        if self._ultimo_diario is not None:
            inattivo = self._inattivita()
            if orologio - self._ultimo_diario < 3600 or (inattivo is not None and inattivo < 600):
                return
        self._ultimo_diario = orologio
        self.scrivi_diario()

    # --- Modalità gioco automatica ---

    def _giochi(self):
        if not self.cambia_gioco or not self.config.get("gioco_automatico", True):
            return
        gioco = integrazioni.gioco_aperto(self.config, self._leggi_processi())
        attiva = self.in_gioco()
        if gioco is None:
            self._gioco_ignorato = None
            if self._gioco_acceso_da_me:
                self._gioco_acceso_da_me = None
                if attiva:  # la spegne solo se l'aveva accesa lui
                    self.cambia_gioco(False, None)
            return
        if attiva or gioco == self._gioco_ignorato:
            return
        if self._gioco_acceso_da_me:  # l'aveva accesa Jarvis e l'utente l'ha spenta: per questa partita basta
            self._gioco_ignorato, self._gioco_acceso_da_me = gioco, None
            return
        self._gioco_acceso_da_me = gioco
        self.cambia_gioco(True, gioco)

    # --- Il ritorno dell'utente ---

    def annota(self, messaggio):
        """Un avviso appena dato. Se l'utente non è al PC lo manda al telefono (se collegato) e lo tiene da parte
        per raccontarglielo quando torna. Restituisce True se l'utente era lontano."""
        inattivo = self._inattivita()
        if inattivo is None or inattivo < STACCO:
            return False
        breve = messaggio if len(messaggio) <= 160 else messaggio[:160].rsplit(" ", 1)[0] + "..."
        self._mentre_eri_via = (self._mentre_eri_via + [breve])[-5:]
        if (self.config.get("telefono_ntfy") or "").strip() and self.config.get("avvisi_al_telefono", True):
            try:
                self._al_telefono(self.config, self.config.get("nome", "Jarvis"), messaggio)
            except integrazioni.ErroreIntegrazione:
                pass
        return True

    def _ritorno(self, adesso, orologio):
        inattivo = self._inattivita()
        if inattivo is None:
            return
        if inattivo < 60:  # l'utente sta usando il PC
            if self._lontano and not self._salutato:
                self._bentornato(adesso)
            self._lontano = self._salutato = False
            return
        if inattivo >= ASSENZA:
            self._lontano = True
        if (self._lontano and not self._salutato and self.config.get("presenza_webcam", False)
                and self.config.get("webcam", True) and orologio - self._ultimo_sguardo >= 60):
            self._ultimo_sguardo = orologio
            try:
                visto = self._vede_qualcuno()
            except Exception:  # webcam occupata, staccata o senza opencv: si aspetta il mouse
                visto = False
            if visto:
                self._bentornato(adesso)

    def _bentornato(self, adesso):
        self._salutato = True
        successo, self._mentre_eri_via = self._mentre_eri_via, []
        if not self.config.get("saluto_al_ritorno", True) or self.in_gioco():
            return
        titolo = self.config.get("come_chiamarmi", "")
        t = f", {titolo}" if titolo else ""
        lei = self.config.get("dai_del", "lei") != "tu"
        saluto = "Buongiorno" if 5 <= adesso.hour < 13 else "Buon pomeriggio" if 13 <= adesso.hour < 18 else \
            "Buonasera"
        righe = [f"{saluto}{t}, {'eccola' if lei else 'eccoti'} di nuovo."]
        if successo:
            righe.append(("Mentre era via: " if lei else "Mentre eri via: ")
                         + "; ".join(m.rstrip(".") for m in successo) + ".")
        prossimi = [(q, m) for q, m in promemoria.in_attesa(adesso) if (q - adesso).total_seconds() <= 3600]
        if prossimi:
            quando, cosa = prossimi[0]
            righe.append(f"Tra poco, alle {quando.hour}:{quando.minute:02d}: {cosa}.")
        self.saluta(" ".join(righe))

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
