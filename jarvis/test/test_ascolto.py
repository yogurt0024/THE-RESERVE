"""Prove dell'orecchio di Jarvis, con un microfono, un rilevatore di voce e una trascrizione finti."""

import queue
import threading
import time
import unittest

import ascolto

try:
    import numpy as np
except ImportError:
    np = None


class TestComandi(unittest.TestCase):
    def test_nome_all_inizio_o_alla_fine(self):
        casi = {
            "Jarvis, che tempo fa?": "Che tempo fa?",
            "Ehi Jarvis apri YouTube.": "Apri YouTube.",
            "Che ore sono, Jarvis?": "Che ore sono?",
            "Giarvis metti un timer di 5 minuti": "Metti un timer di 5 minuti",
            "Jarvis.": "",
            "Ok Jarvis": "",
            "Buongiorno Jarvis!": "Buongiorno",
        }
        for frase, comando in casi.items():
            self.assertEqual(ascolto.estrai_comando(frase), comando, frase)

    def test_frasi_non_rivolte_a_jarvis(self):
        for frase in ["Che tempo fa domani?", "Ho visto Travis ieri", "Ieri Jarvis mi ha detto una cosa", ""]:
            self.assertIsNone(ascolto.estrai_comando(frase), frase)

    def test_altro_nome(self):
        self.assertEqual(ascolto.estrai_comando("Friday, accendi la musica", "Friday"), "Accendi la musica")
        self.assertIsNone(ascolto.estrai_comando("Jarvis, accendi la musica", "Friday"))

    def test_stop(self):
        for frase in ["Basta.", "basta così, grazie", "Stop!", "Stai zitto"]:
            self.assertTrue(ascolto.e_stop(frase), frase)
        self.assertFalse(ascolto.e_stop("Basta con i compiti di matematica"))


@unittest.skipIf(np is None, "numpy non installato")
class TestSegmentatore(unittest.TestCase):
    def test_frase_con_silenzio_finale(self):
        s = ascolto.Segmentatore(silenzio_finale=0.2, minimo=0.1, anticipo=0.064)
        blocco = np.ones(ascolto.BLOCCO, dtype=np.float32)
        probabilita = [0.0] * 5 + [0.9] * 10 + [0.0] * 10
        frasi = [f for p in probabilita if (f := s.aggiungi(blocco, p)) is not None]
        self.assertEqual(len(frasi), 1)
        # 2 blocchi di anticipo + 10 di voce + i blocchi di silenzio che chiudono la frase
        self.assertEqual(len(frasi[0]), (2 + 10 + 6) * ascolto.BLOCCO)

    def test_rumore_troppo_breve(self):
        s = ascolto.Segmentatore(silenzio_finale=0.2, minimo=0.25)
        blocco = np.ones(ascolto.BLOCCO, dtype=np.float32)
        self.assertEqual([s.aggiungi(blocco, p) for p in [0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]], [None] * 7)


class RilevatoreFinto:
    """Il "microfono" manda blocchi pieni di 1 quando c'è voce e di 0 quando c'è silenzio."""

    def probabilita(self, blocco):
        return float(blocco[0])

    def azzera(self):
        pass


@unittest.skipIf(np is None, "numpy non installato")
class TestAscolto(unittest.TestCase):
    def setUp(self):
        self.blocchi = queue.Queue()
        self.comandi = queue.Queue()
        self.senza_nome = queue.Queue()
        self.frasi_dette = queue.Queue()  # cosa "si sente" nelle frasi che arrivano, in ordine
        self.jarvis_parla = False

    def sorgente(self):
        while True:
            blocco = self.blocchi.get()
            if blocco is None:
                return
            yield blocco

    def orecchio(self):
        o = ascolto.Ascolto({"nome": "Jarvis"}, al_comando=self.comandi.put, parlando=lambda: self.jarvis_parla,
                            al_senza_nome=lambda testo, secondi: self.senza_nome.put((testo, secondi)),
                            sorgente=self.sorgente(), rilevatore=RilevatoreFinto(),
                            trascrittore=lambda audio: self.frasi_dette.get_nowait())
        o.avvia()
        self.addCleanup(lambda: self.blocchi.put(None))
        return o

    def parla(self, testo, secondi=0.5):
        """Simula una frase di `secondi`, seguita dal silenzio che la chiude."""
        self.frasi_dette.put(testo)
        for _ in range(round(secondi / ascolto.DURATA_BLOCCO)):
            self.blocchi.put(np.ones(ascolto.BLOCCO, dtype=np.float32))
        for _ in range(30):
            self.blocchi.put(np.zeros(ascolto.BLOCCO, dtype=np.float32))

    def comando(self):
        return self.comandi.get(timeout=5)

    def nessun_comando(self):
        time.sleep(0.3)
        self.assertTrue(self.comandi.empty())

    def test_comandi_e_chiacchiere(self):
        self.orecchio()
        self.parla("Jarvis, che tempo fa?")
        self.assertEqual(self.comando(), "Che tempo fa?")
        self.parla("Passami il sale")  # senza il nome: deciderà il cervello se era per Jarvis
        self.nessun_comando()
        self.assertEqual(self.senza_nome.get(timeout=5), ("Passami il sale", None))

    def test_solo_il_nome_poi_la_richiesta(self):
        o = self.orecchio()
        self.parla("Jarvis.")
        self.assertEqual(self.comando(), "")
        o.attendi_comando(secondi=5)  # la finestra risponde "Sì, signore?" e aspetta
        self.parla("apri YouTube")
        self.assertEqual(self.comando(), "Apri YouTube")
        self.parla("e anche la calcolatrice")  # l'attesa vale per una frase sola
        self.nessun_comando()
        self.assertEqual(self.senza_nome.get(timeout=5)[0], "E anche la calcolatrice")

    def test_mentre_jarvis_parla_conta_solo_il_nome(self):
        o = self.orecchio()
        o.attendi_comando(secondi=5)
        self.jarvis_parla = True
        self.parla("Sì, signore?")  # la sua stessa voce che esce dalle casse
        self.nessun_comando()
        self.assertTrue(self.senza_nome.empty())  # non va nemmeno valutata
        self.parla("Jarvis, basta")
        self.assertEqual(self.comando(), "Basta")

    def test_pausa(self):
        o = self.orecchio()
        o.pausa(True)
        self.parla("Jarvis, che ore sono?")
        self.nessun_comando()
        o.pausa(False)
        self.frasi_dette = queue.Queue()
        self.parla("Jarvis, che ore sono?")
        self.assertEqual(self.comando(), "Che ore sono?")


if __name__ == "__main__":
    unittest.main()
