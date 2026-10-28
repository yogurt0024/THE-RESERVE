"""Prove delle integrazioni: calendario, Spotify, server di Minecraft (finto), giochi, telefono e ritorno al PC."""

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

import cervello
import iniziativa
import integrazioni
import promemoria
import rete
import strumenti
from test import finti
from test.test_assistente import Base as BaseAssistente

ADESSO = datetime(2026, 10, 28, 15, 0)  # un mercoledì pomeriggio
_FUSO_ORIGINALE = os.environ.get("TZ")


def setUpModule():
    # Gli orari del calendario si convertono nell'ora del PC: le prove fanno finta di essere in Italia.
    os.environ["TZ"] = "Europe/Rome"
    if hasattr(time, "tzset"):
        time.tzset()


def tearDownModule():
    if _FUSO_ORIGINALE is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = _FUSO_ORIGINALE
    if hasattr(time, "tzset"):
        time.tzset()

CALENDARIO = """BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:dentista\r
DTSTART:20261028T170000\r
DTEND:20261028T180000\r
SUMMARY:Dentista\\, controllo\r
LOCATION:Via Roma 1\\, Cagliari\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:compleanno\r
DTSTART;VALUE=DATE:20261029\r
SUMMARY:Compleanno di Luca\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:calcetto\r
DTSTART;TZID=Europe/Rome:20261005T190000\r
RRULE:FREQ=WEEKLY;BYDAY=MO,WE\r
EXDATE;TZID=Europe/Rome:20261102T190000\r
SUMMARY:Calcetto con una descrizione lunghissima che continua\r
  sulla riga dopo\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:calcetto\r
RECURRENCE-ID;TZID=Europe/Rome:20261104T190000\r
DTSTART;TZID=Europe/Rome:20261104T203000\r
SUMMARY:Calcetto (spostato)\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:annullato\r
DTSTART:20261028T120000\r
STATUS:CANCELLED\r
SUMMARY:Riunione annullata\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:corso\r
DTSTART:20261001T090000\r
RRULE:FREQ=DAILY;INTERVAL=2;COUNT=3\r
SUMMARY:Corso\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:affitto\r
DTSTART;VALUE=DATE:20260131\r
RRULE:FREQ=MONTHLY;UNTIL=20261231\r
SUMMARY:Affitto\r
END:VEVENT\r
END:VCALENDAR\r
"""


def eventi_del_giorno(giorno, quanti_giorni=1):
    da = datetime.combine(giorno, datetime.min.time())
    a = datetime.fromordinal(da.toordinal() + quanti_giorni)
    return [(f"{i:%d/%m %H:%M}" if isinstance(i, datetime) else f"{i:%d/%m}", titolo)
            for i, titolo, _, _ in integrazioni.eventi_tra(integrazioni.leggi_ics(CALENDARIO), da, a)]


def con_calendario(indirizzo="https://calendario.finto/base.ics"):
    eventi = integrazioni.leggi_ics(CALENDARIO)
    integrazioni._cache_calendario.update(indirizzo=indirizzo, quando=time.monotonic(), eventi=eventi)
    return indirizzo


class TestCalendario(unittest.TestCase):
    def test_eventi_semplici_ripetuti_e_annullati(self):
        self.assertEqual(eventi_del_giorno(date(2026, 10, 28)),
                         [("28/10 17:00", "Dentista, controllo"), ("28/10 19:00", "Calcetto con una descrizione "
                                                                                  "lunghissima che continua sulla "
                                                                                  "riga dopo")])
        self.assertEqual(eventi_del_giorno(date(2026, 10, 29)), [("29/10", "Compleanno di Luca")])

    def test_eccezioni_e_spostamenti(self):
        settimana = eventi_del_giorno(date(2026, 11, 2), 3)
        self.assertEqual(settimana, [("04/11 20:30", "Calcetto (spostato)")])  # lunedì escluso, mercoledì spostato

    def test_regole_con_conteggio_intervallo_e_fine(self):
        self.assertEqual(eventi_del_giorno(date(2026, 10, 1), 10),
                         [("01/10 09:00", "Corso"), ("03/10 09:00", "Corso"), ("05/10 09:00", "Corso"),
                          ("05/10 19:00", "Calcetto con una descrizione lunghissima che continua sulla riga dopo"),
                          ("07/10 19:00", "Calcetto con una descrizione lunghissima che continua sulla riga dopo")])
        riunioni = integrazioni.leggi_ics("BEGIN:VEVENT\nDTSTART:20261005T180000\n"
                                          "RRULE:FREQ=MONTHLY;BYDAY=1MO,-1FR;COUNT=4\nSUMMARY:Riunione\nEND:VEVENT")
        trovate = integrazioni.eventi_tra(riunioni, datetime(2026, 10, 1), datetime(2027, 1, 1))
        # Il primo lunedì e l'ultimo venerdì di ogni mese, quattro volte in tutto.
        self.assertEqual([f"{i:%d/%m %H:%M}" for i, _, _, _ in trovate],
                         ["05/10 18:00", "30/10 18:00", "02/11 18:00", "27/11 18:00"])
        affitti = [g for g, titolo in eventi_del_giorno(date(2026, 1, 1), 400) if titolo == "Affitto"]
        # I mesi senza il 31 si saltano; dopo dicembre il calendario non lo ripete più.
        self.assertEqual(affitti, ["31/01", "31/03", "31/05", "31/07", "31/08", "31/10", "31/12"])

    def test_agenda_da_dire(self):
        config = {"calendario_ics": con_calendario()}
        self.assertEqual(integrazioni.agenda(config, "oggi", ADESSO),
                         "Impegni oggi:\n- alle 17:00: Dentista, controllo (Via Roma 1, Cagliari)\n"
                         "- alle 19:00: Calcetto con una descrizione lunghissima che continua sulla riga dopo")
        self.assertEqual(integrazioni.agenda(config, "domani", ADESSO),
                         "Impegni domani:\n- tutto il giorno: Compleanno di Luca")
        settimana = integrazioni.agenda(config, "settimana", ADESSO)
        self.assertIn("- giovedì tutto il giorno: Compleanno di Luca", settimana)
        self.assertIn("- sabato tutto il giorno: Affitto", settimana)
        self.assertNotIn("lunedì", settimana)  # il calcetto del 2 novembre è stato tolto
        self.assertEqual(integrazioni.agenda(config, "oggi", datetime(2026, 10, 30, 9, 0)),
                         "Nel calendario non c'è niente oggi.")
        with self.assertRaises(integrazioni.ErroreIntegrazione):
            integrazioni.agenda({}, "oggi", ADESSO)
        self.assertEqual(integrazioni.oggi_e_domani({}), "")

    def test_scaricare_il_calendario(self):
        integrazioni._cache_calendario.update(indirizzo=None, quando=0.0, eventi=[])
        with self.assertRaises(integrazioni.ErroreIntegrazione):
            integrazioni.scarica_calendario("http://non-sicuro.example/cal.ics")
        aperti = []

        class Risposta:
            def __init__(self, testo):
                self.testo = testo

            def __enter__(self):
                return self

            def __exit__(self, *errore):
                return False

            def read(self, quanto):
                return self.testo.encode()

        def apri(richiesta, timeout):
            aperti.append(richiesta.full_url)
            return Risposta(CALENDARIO if "buono" in richiesta.full_url else "<html>non è un calendario</html>")

        with mock.patch.object(integrazioni.urllib.request, "urlopen", apri):
            eventi = integrazioni.scarica_calendario("webcal://calendario.finto/buono.ics")
            integrazioni.scarica_calendario("webcal://calendario.finto/buono.ics")  # tenuto in memoria
            with self.assertRaises(integrazioni.ErroreIntegrazione):
                integrazioni.scarica_calendario("https://calendario.finto/sbagliato.ics")
        self.assertEqual(len(eventi), 6)  # quello annullato non conta
        self.assertEqual(aperti, ["https://calendario.finto/buono.ics", "https://calendario.finto/sbagliato.ics"])


class ServerMinecraftFinto:
    """Risponde come un server di Minecraft alla richiesta di stato della lista server."""

    def __init__(self, stato):
        self.stato = stato
        self.saluti = []
        self.presa = socket.socket()
        self.presa.bind(("127.0.0.1", 0))
        self.presa.listen()
        self.porta = self.presa.getsockname()[1]
        threading.Thread(target=self._servi, daemon=True).start()

    def _servi(self):
        while True:
            try:
                connessione, _ = self.presa.accept()
            except OSError:
                return
            with connessione:
                connessione.settimeout(5)
                saluto = self._pacchetto(connessione)
                self._pacchetto(connessione)  # la richiesta di stato
                self.saluti.append(saluto)
                dati = json.dumps(self.stato).encode()
                corpo = integrazioni._varint(0) + integrazioni._varint(len(dati)) + dati
                connessione.sendall(integrazioni._varint(len(corpo)) + corpo)

    @staticmethod
    def _pacchetto(connessione):
        lunghezza = integrazioni._leggi_varint(connessione)
        dati = b""
        while len(dati) < lunghezza:
            dati += connessione.recv(lunghezza - len(dati))
        return dati

    def chiudi(self):
        self.presa.close()


class TestMinecraft(unittest.TestCase):
    def test_server_acceso(self):
        server = ServerMinecraftFinto({
            "version": {"name": "1.21.4", "protocol": 769},
            "players": {"max": 10, "online": 2, "sample": [{"name": "Yogurt", "id": "1"}, {"name": "Luca", "id": "2"}]},
            "description": {"text": "§aIl server ", "extra": [{"text": "di casa"}]}})
        self.addCleanup(server.chiudi)
        risposta = integrazioni.server_minecraft(f"127.0.0.1:{server.porta}")
        self.assertEqual(risposta, f"Il server 127.0.0.1:{server.porta} è acceso.\nVersione: 1.21.4.\n"
                                   "Giocatori: 2 su 10 (Yogurt, Luca).\nMessaggio del server: Il server di casa")
        self.assertIn(b"127.0.0.1", server.saluti[0])
        # Lo stesso dallo strumento del modello, con l'indirizzo salvato in config.json.
        config = {"server_minecraft": f"127.0.0.1:{server.porta}", "internet": True}
        self.assertTrue(strumenti.esegui("server_minecraft", {}, config, None).startswith("Il server "))

    def test_server_spento(self):
        presa = socket.socket()
        presa.bind(("127.0.0.1", 0))
        porta = presa.getsockname()[1]
        presa.close()  # nessuno ascolta su questa porta
        risposta = strumenti.esegui("server_minecraft", {"indirizzo": f"127.0.0.1:{porta}"}, {"internet": True}, None)
        self.assertTrue(risposta.startswith(f"Errore: il server 127.0.0.1:{porta} non risponde"))
        self.assertTrue(strumenti.esegui("server_minecraft", {}, {"internet": True}, None)
                        .startswith("Errore: dimmi l'indirizzo del server"))


class FintoNtfy(BaseHTTPRequestHandler):
    messaggi = []

    def log_message(self, *argomenti):
        pass

    def do_POST(self):
        lunghezza = int(self.headers.get("Content-Length", 0))
        FintoNtfy.messaggi.append(json.loads(self.rfile.read(lunghezza)))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"id":"x"}')


class TestTelefonoSpotifyGiochi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ntfy, cls.url_ntfy = finti.avvia(FintoNtfy)

    @classmethod
    def tearDownClass(cls):
        cls.ntfy.shutdown()

    def setUp(self):
        FintoNtfy.messaggi = []

    def test_telefono(self):
        canale = integrazioni.nuovo_canale_ntfy()
        self.assertRegex(canale, r"^jarvis-[a-z0-9]{16}$")
        self.assertNotEqual(canale, integrazioni.nuovo_canale_ntfy())
        config = {"telefono_ntfy": canale, "server_ntfy": self.url_ntfy, "internet": True}
        self.assertEqual(integrazioni.al_telefono(config, "Jarvis", "Prova", attendi=True),
                         "Messaggio inviato al telefono.")
        self.assertEqual(FintoNtfy.messaggi, [{"topic": canale, "title": "Jarvis", "message": "Prova"}])
        risposta = strumenti.esegui("manda_al_telefono", {"messaggio": "Latte, pane"}, dict(config, nome="Jarvis"),
                                    None)
        self.assertEqual(risposta, "Messaggio inviato al telefono.")
        self.assertEqual(FintoNtfy.messaggi[-1]["message"], "Latte, pane")
        self.assertEqual(strumenti.esegui("manda_al_telefono", {"messaggio": " "}, config, None),
                         "Errore: cosa devo mandare al telefono?")
        with self.assertRaises(integrazioni.ErroreIntegrazione):
            integrazioni.al_telefono({}, "Jarvis", "Prova")
        spento = dict(config, server_ntfy="http://127.0.0.1:1")
        with self.assertRaises(integrazioni.ErroreIntegrazione):
            integrazioni.al_telefono(spento, "Jarvis", "Prova", attendi=True)

    def test_strumenti_solo_se_collegati(self):
        base = dict(cervello.CONFIG_PREDEFINITA)
        nomi = {s["function"]["name"] for s in strumenti.schemi(base)}
        self.assertTrue({"spotify", "server_minecraft"} <= nomi)
        self.assertFalse({"agenda", "manda_al_telefono"} & nomi)
        collegato = dict(base, calendario_ics="https://x/y.ics", telefono_ntfy="jarvis-abc")
        nomi = {s["function"]["name"] for s in strumenti.schemi(collegato)}
        self.assertTrue({"agenda", "manda_al_telefono"} <= nomi)
        prompt = cervello.prompt_di_sistema(collegato, "qwen3.5:4b", {"tools"}, [])
        self.assertIn("il calendario dell'utente", prompt)
        self.assertIn("messaggi al telefono", prompt)
        self.assertNotIn("calendario", cervello.prompt_di_sistema(base, "qwen3.5:4b", {"tools"}, []))

    def test_spotify(self):
        aperti = []
        with mock.patch.object(rete, "cerca", lambda domanda: [
                ("Back in Black", "https://www.acdc.com", ""),
                ("Back in Black - AC/DC", "https://open.spotify.com/intl-it/track/08mG3Y1vljYA6bvDt4Wqkj", "")]), \
                mock.patch.object(integrazioni.webbrowser, "open", aperti.append), \
                mock.patch.object(integrazioni, "_apri", lambda uri: aperti.append(uri) or True):
            self.assertEqual(integrazioni.spotify("back in black"),
                             "Ho aperto «back in black» su Spotify: se non parte da solo, premi play.")
        self.assertEqual(aperti, ["spotify:track:08mG3Y1vljYA6bvDt4Wqkj"])
        aperti.clear()
        with mock.patch.object(rete, "cerca", lambda domanda: []), \
                mock.patch.object(integrazioni.webbrowser, "open", aperti.append), \
                mock.patch.object(integrazioni, "_apri", lambda uri: False):
            self.assertEqual(integrazioni.spotify("lo-fi per studiare"),
                             "L'app di Spotify non c'è: ho aperto la ricerca «lo-fi per studiare» sul sito.")
        self.assertEqual(aperti, ["https://open.spotify.com/search/lo-fi%20per%20studiare"])

    def test_giochi(self):
        self.assertEqual(integrazioni.gioco_aperto({}, {"explorer.exe", "javaw.exe"}), "javaw.exe")
        self.assertIsNone(integrazioni.gioco_aperto({}, {"explorer.exe"}))
        self.assertEqual(integrazioni.gioco_aperto({"giochi": ["Terraria.exe"]}, {"terraria.exe"}), "Terraria.exe")
        self.assertEqual(integrazioni.nome_del_gioco("javaw.exe"), "Minecraft")
        self.assertEqual(integrazioni.nome_del_gioco("Terraria.exe"), "Terraria")


class TestSorvegliante(unittest.TestCase):
    def setUp(self):
        cartella = Path(tempfile.mkdtemp())
        for patch in (mock.patch.object(promemoria, "FILE_PROMEMORIA", cartella / "promemoria.json"),
                      mock.patch.object(iniziativa, "FILE_STATO", cartella / "iniziativa.json")):
            patch.start()
            self.addCleanup(patch.stop)
        self.avvisi, self.saluti, self.cambi, self.telefono = [], [], [], []
        self.processi = set()
        self.inattivo = 0
        self.gioco = False
        self.volto = False

    def crea(self, **config):
        def cambia_gioco(attiva, gioco):
            self.cambi.append((attiva, gioco))
            self.gioco = attiva

        return iniziativa.Sorvegliante(
            dict({"come_chiamarmi": "signore", "avvisi_pc": False, "briefing": False, "consigli_pausa": False,
                  "nome": "Jarvis"}, **config),
            avvisa=self.avvisi.append, in_gioco=lambda: self.gioco, inattivita=lambda: self.inattivo,
            cambia_gioco=cambia_gioco, leggi_processi=lambda: self.processi, saluta=self.saluti.append,
            vede_qualcuno=lambda: self.volto,
            al_telefono=lambda config, titolo, messaggio: self.telefono.append((titolo, messaggio)))

    def test_modalita_gioco_automatica(self):
        s = self.crea()
        s.controlla(ADESSO, orologio=1)
        self.processi = {"explorer.exe", "javaw.exe"}
        s.controlla(ADESSO, orologio=10)  # si controlla ogni 30 secondi
        self.assertEqual(self.cambi, [])
        s.controlla(ADESSO, orologio=31)
        self.assertEqual(self.cambi, [(True, "javaw.exe")])
        self.processi = {"explorer.exe"}
        s.controlla(ADESSO, orologio=61)
        self.assertEqual(self.cambi[-1], (False, None))
        # Se l'utente la spegne durante la partita, Jarvis non insiste fino alla prossima partita.
        self.processi = {"javaw.exe"}
        s.controlla(ADESSO, orologio=91)
        self.gioco = False
        s.controlla(ADESSO, orologio=121)
        s.controlla(ADESSO, orologio=151)
        self.assertEqual(len(self.cambi), 3)
        # E se l'aveva accesa l'utente, Jarvis non la spegne quando il gioco si chiude.
        self.processi = set()
        s.controlla(ADESSO, orologio=181)
        self.gioco = True
        self.processi = {"javaw.exe"}
        s.controlla(ADESSO, orologio=211)
        self.processi = set()
        s.controlla(ADESSO, orologio=241)
        self.assertEqual(len(self.cambi), 3)
        self.assertTrue(self.gioco)

    def test_niente_modalita_automatica_se_spenta(self):
        s = self.crea(gioco_automatico=False)
        self.processi = {"javaw.exe"}
        s.controlla(ADESSO, orologio=1)
        self.assertEqual(self.cambi, [])

    def test_ritorno_al_pc_con_quello_che_e_successo(self):
        promemoria.aggiungi("oggi alle 15:40", "chiamare la nonna", ADESSO)
        s = self.crea(telefono_ntfy="jarvis-abc")
        self.inattivo = 10
        self.assertFalse(s.annota("Timer: pasta"))  # l'utente è al PC: niente telefono
        self.inattivo = 31 * 60
        s.controlla(ADESSO, orologio=1)
        self.assertTrue(s.annota("Promemoria: stendere i panni"))
        self.assertTrue(s.annota("Compito 1 completato (cerca i modpack): " + "molto lungo " * 30))
        self.assertEqual([t for t, _ in self.telefono], ["Jarvis", "Jarvis"])
        self.assertEqual(self.saluti, [])
        self.inattivo = 2
        s.controlla(ADESSO, orologio=2)
        self.assertEqual(len(self.saluti), 1)
        saluto = self.saluti[0]
        self.assertTrue(saluto.startswith("Buon pomeriggio, signore, eccola di nuovo. Mentre era via: Promemoria: "
                                          "stendere i panni; Compito 1 completato (cerca i modpack): molto lungo"))
        self.assertLess(len(saluto), 400)
        self.assertTrue(saluto.endswith("Tra poco, alle 15:40: chiamare la nonna."))
        s.controlla(ADESSO, orologio=3)
        self.assertEqual(len(self.saluti), 1)  # una volta sola

    def test_assenza_breve_niente_saluto(self):
        s = self.crea()
        self.inattivo = 10 * 60
        s.controlla(ADESSO, orologio=1)
        self.inattivo = 0
        s.controlla(ADESSO, orologio=2)
        self.assertEqual(self.saluti, [])

    def test_presenza_dalla_webcam(self):
        s = self.crea(presenza_webcam=True, dai_del="tu")
        self.inattivo = 40 * 60
        s.controlla(datetime(2026, 10, 28, 21, 0), orologio=100)
        self.assertEqual(self.saluti, [])
        self.volto = True
        s.controlla(datetime(2026, 10, 28, 21, 0), orologio=130)  # la webcam si guarda una volta al minuto
        self.assertEqual(self.saluti, [])
        s.controlla(datetime(2026, 10, 28, 21, 1), orologio=161)
        self.assertEqual(self.saluti, ["Buonasera, signore, eccoti di nuovo."])
        s.controlla(datetime(2026, 10, 28, 21, 2), orologio=300)
        self.inattivo = 0  # ora tocca il mouse: non lo saluta di nuovo
        s.controlla(datetime(2026, 10, 28, 21, 3), orologio=301)
        self.assertEqual(len(self.saluti), 1)

    def test_in_gioco_niente_saluto(self):
        s = self.crea()
        self.gioco = True
        self.inattivo = 40 * 60
        s.controlla(ADESSO, orologio=1)
        self.inattivo = 0
        s.controlla(ADESSO, orologio=2)
        self.assertEqual(self.saluti, [])


class TestComandi(BaseAssistente):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ntfy, cls.url_ntfy = finti.avvia(FintoNtfy)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.ntfy.shutdown()

    def test_telefono(self):
        j = self.jarvis(server_ntfy=self.url_ntfy)
        _, avvisi, _ = self.chiedi(j, "/telefono prova")
        self.assertEqual(avvisi, ["Prima collega il telefono: scrivi /telefono."])
        _, avvisi, _ = self.chiedi(j, "/telefono")
        canale = j.config["telefono_ntfy"]
        self.assertTrue(canale.startswith("jarvis-"))
        self.assertIn(f"Premi + e scrivi il canale: {canale}", avvisi[0])
        self.assertEqual(json.loads(cervello.FILE_CONFIG.read_text(encoding="utf-8"))["telefono_ntfy"], canale)
        _, avvisi, _ = self.chiedi(j, "/telefono prova")
        self.assertEqual(avvisi, ["Messaggio inviato al telefono."])
        self.assertEqual(FintoNtfy.messaggi[-1]["topic"], canale)
        _, avvisi, _ = self.chiedi(j, "/telefono spegni")
        self.assertEqual(avvisi, ["Ho scollegato il telefono: non gli mando più niente."])
        self.assertEqual(j.config["telefono_ntfy"], "")

    def test_calendario_e_briefing(self):
        j = self.jarvis(citta="Cagliari")
        _, avvisi, _ = self.chiedi(j, "/calendario")
        self.assertIn("Indirizzo segreto in formato iCal", avvisi[0])
        _, avvisi, _ = self.chiedi(j, "/calendario non-un-link")
        self.assertTrue(avvisi[0].startswith("Il link deve iniziare con https://"))
        indirizzo = con_calendario("https://calendario.finto/mio.ics")
        _, avvisi, _ = self.chiedi(j, f"/calendario {indirizzo}")
        self.assertEqual(avvisi, ["Calendario collegato: da ora lo uso per l'agenda e il briefing."])
        self.assertEqual(j.config["calendario_ics"], indirizzo)
        class OggiFinto(datetime):
            @classmethod
            def now(cls, tz=None):
                return ADESSO

        with mock.patch.object(cervello, "datetime", OggiFinto):
            self.chiedi(j, "/briefing")
        domanda = finti.FintoOllama.richieste[-1]["messages"][-1]["content"]
        self.assertIn("Impegni oggi:", domanda)
        self.assertIn("agenda", {s["function"]["name"] for s in strumenti.schemi(j.config)})
        _, avvisi, _ = self.chiedi(j, "/agenda domani")
        self.assertEqual(avvisi, ["Guardo il calendario..."])


if __name__ == "__main__":
    unittest.main()
