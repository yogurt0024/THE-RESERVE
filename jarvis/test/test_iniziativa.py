"""Prove dell'iniziativa di Jarvis: promemoria, briefing, avvisi sul PC e pause. Niente orologi veri."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import iniziativa
import promemoria
import strumenti

ADESSO = datetime(2026, 10, 28, 15, 0)  # un mercoledì pomeriggio


class Base(unittest.TestCase):
    def setUp(self):
        cartella = Path(tempfile.mkdtemp())
        for patch in (mock.patch.object(promemoria, "FILE_PROMEMORIA", cartella / "promemoria.json"),
                      mock.patch.object(iniziativa, "FILE_STATO", cartella / "iniziativa.json")):
            patch.start()
            self.addCleanup(patch.stop)


class TestPromemoria(Base):
    def test_come_lo_dice_una_persona(self):
        casi = {"domani alle 18": "29/10 18:00", "venerdì 9:30": "30/10 09:30", "tra 2 ore": "28/10 17:00",
                "tra mezz'ora": "28/10 15:30", "alle 6": "28/10 18:00", "alle 9": "29/10 09:00",
                "stasera": "28/10 20:00", "3 novembre alle 9 e mezza": "03/11 09:30", "2026-11-03 10:15": "03/11 10:15",
                "mercoledì": "04/11 09:00"}
        for testo, atteso in casi.items():
            self.assertEqual(f"{promemoria.interpreta_quando(testo, ADESSO):%d/%m %H:%M}", atteso, testo)
        for sbagliato in ["boh", "alle 25", "31/2"]:
            with self.assertRaises(promemoria.ErrorePromemoria):
                promemoria.interpreta_quando(sbagliato, ADESSO)

    def test_aggiungi_elenca_cancella_scaduti(self):
        self.assertEqual(promemoria.aggiungi("domani alle 18", "chiamare la nonna", ADESSO),
                         "Promemoria salvato per domani alle 18:00: chiamare la nonna.")
        promemoria.aggiungi("tra 10 minuti", "spegnere il forno.", ADESSO)
        self.assertEqual(promemoria.descrivi_elenco(ADESSO),
                         "Promemoria:\n1. oggi alle 15:10: spegnere il forno\n2. domani alle 18:00: chiamare la nonna")
        with self.assertRaises(promemoria.ErrorePromemoria):
            promemoria.aggiungi("oggi alle 9", "passato", ADESSO)
        self.assertEqual(promemoria.cancella(2, ADESSO), "Promemoria cancellato: chiamare la nonna.")
        self.assertEqual(promemoria.scaduti(ADESSO), [])
        self.assertEqual([m for _, m in promemoria.scaduti(datetime(2026, 10, 28, 15, 11))], ["spegnere il forno"])
        self.assertEqual(promemoria.descrivi_elenco(ADESSO), "Non ci sono promemoria.")

    def test_strumento_per_il_modello(self):
        risposta = strumenti.esegui("promemoria", {"quando": "tra 2 ore", "messaggio": "pasta"}, {}, None)
        self.assertTrue(risposta.startswith("Promemoria salvato per oggi alle "))
        self.assertTrue(strumenti.esegui("promemoria", {"quando": "boh", "messaggio": "x"}, {}, None)
                        .startswith("Errore: non ho capito quando"))
        self.assertIn("1. ", strumenti.esegui("elenco_promemoria", {}, {}, None))


class TestSorvegliante(Base):
    def crea(self, stato_pc=None, inattivita=None, **config):
        self.avvisi, self.proposte = [], []
        self.libero = True
        self.gioco = False

        def proponi(comando):
            self.proposte.append(comando)
            return self.libero

        return iniziativa.Sorvegliante(dict({"come_chiamarmi": "signore"}, **config), avvisa=self.avvisi.append,
                                       proponi=proponi, in_gioco=lambda: self.gioco,
                                       leggi_stato_pc=lambda: stato_pc or {}, inattivita=inattivita or (lambda: None))

    def test_promemoria_all_ora_giusta_e_dopo_lo_spegnimento(self):
        promemoria.aggiungi("oggi alle 15:10", "spegnere il forno", ADESSO)
        promemoria.aggiungi("oggi alle 18", "chiamare la nonna", ADESSO)
        s = self.crea()
        s.controlla(datetime(2026, 10, 28, 15, 10), orologio=1)
        self.assertEqual(self.avvisi, ["Promemoria: spegnere il forno"])
        s.controlla(datetime(2026, 10, 29, 8, 0), orologio=2)  # il PC era spento alle 18
        self.assertEqual(self.avvisi[-1], "Promemoria (era per ieri alle 18:00): chiamare la nonna")

    def test_briefing_una_volta_al_giorno(self):
        s = self.crea(ora_briefing="07:30")
        s.controlla(datetime(2026, 10, 28, 7, 0), orologio=1)
        self.assertEqual(self.proposte, [])  # troppo presto
        self.libero = False
        s.controlla(datetime(2026, 10, 28, 7, 31), orologio=2)  # Jarvis è occupato: riproverà
        self.libero = True
        s.controlla(datetime(2026, 10, 28, 7, 32), orologio=3)
        s.controlla(datetime(2026, 10, 28, 9, 0), orologio=4)
        self.assertEqual(self.proposte, ["/briefing", "/briefing"])
        self.gioco = True
        s.controlla(datetime(2026, 10, 29, 8, 0), orologio=5)  # in modalità gioco no
        self.assertEqual(len(self.proposte), 2)

    def test_avvisi_sul_pc(self):
        s = self.crea(stato_pc={"batteria": 15, "in_carica": False, "temperatura_gpu": 90, "disco_libero_gb": 3.24,
                                "memoria_usata": 50})
        s.controlla(ADESSO, orologio=1000)
        self.assertEqual(self.avvisi, [
            "La batteria è al 15%, signore: conviene collegare il caricatore.",
            "Il disco è quasi pieno, signore: restano 3,2 GB liberi.",
            "La scheda video è a 90 gradi, signore: è molto calda, conviene controllare le ventole o fare una "
            "pausa dal gioco."])
        s.controlla(ADESSO, orologio=1200)  # due minuti dopo: niente doppioni
        self.assertEqual(len(self.avvisi), 3)
        s.controlla(ADESSO, orologio=1000 + 1000)  # dopo un quarto d'ora la temperatura si ridice
        self.assertEqual(len(self.avvisi), 4)

    def test_pausa(self):
        inattivo = [0]
        s = self.crea(inattivita=lambda: inattivo[0])
        s.controlla(ADESSO, orologio=1)
        s.controlla(ADESSO, orologio=3600)
        self.assertEqual(self.avvisi, [])
        s.controlla(ADESSO, orologio=2 * 3600 + 10)
        self.assertEqual(self.avvisi, ["È al computer da 2 ore di fila, signore: una pausa di qualche minuto "
                                       "le farebbe bene."])
        inattivo[0] = 600  # si è alzato per dieci minuti
        s.controlla(ADESSO, orologio=3 * 3600)
        inattivo[0] = 0
        s.controlla(ADESSO, orologio=4 * 3600)
        s.controlla(ADESSO, orologio=5 * 3600)
        self.assertEqual(len(self.avvisi), 1)  # la pausa ha azzerato il conto


if __name__ == "__main__":
    unittest.main()
