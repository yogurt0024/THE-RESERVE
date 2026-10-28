"""Prove della voce, con un motore finto al posto di quello vero e senza altoparlanti."""

import threading
import time
import unittest
from unittest import mock

import voce

try:
    import numpy as np
except ImportError:
    np = None


class TestTestoPerLaVoce(unittest.TestCase):
    def test_simboli_e_sigle(self):
        self.assertEqual(voce.per_la_voce("A Cagliari ci sono 22°C e l'umidità è al 60%."),
                         "A Cagliari ci sono 22 gradi e l'umidità è al 60 per cento.")
        self.assertEqual(voce.per_la_voce("Costa 15 € e pesa 2 GB, vedi https://example.com"),
                         "Costa 15 euro e pesa 2 giga, vedi il link")
        self.assertEqual(voce.per_la_voce("- primo punto\n- **secondo**"), "primo punto secondo")

    def test_frasi(self):
        self.assertEqual(voce.dividi_frasi("Certo, signore. Sono le 14:30! Altro?\nEcco"),
                         ["Certo, signore.", "Sono le 14:30!", "Altro?", "Ecco"])


@unittest.skipIf(np is None, "numpy non installato")
class TestEffetto(unittest.TestCase):
    def test_audio_cortissimo(self):
        self.assertEqual(len(voce.effetto_jarvis(np.ones(10, dtype=np.float32), 22050)), 10 + 22050 // 4)

    def test_effetto(self):
        audio = np.sin(np.linspace(0, 2000, 22050)).astype(np.float32)
        uscita = voce.effetto_jarvis(audio, 22050, 0.6)
        self.assertGreater(len(uscita), len(audio))  # c'è la coda dell'eco
        self.assertAlmostEqual(float(np.max(np.abs(uscita))), 0.89, places=3)
        self.assertIs(voce.effetto_jarvis(audio, 22050, 0).dtype, np.dtype(np.float32))
        self.assertEqual(len(voce.effetto_jarvis(audio, 22050, 0)), len(audio))


class MotoreFinto:
    def sintetizza(self, testo):
        return np.sin(np.arange(1600, dtype=np.float32)), 16000


@unittest.skipIf(np is None, "numpy non installato")
class TestVoce(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(voce, "carica_motore", lambda *argomenti: MotoreFinto())
        patch.start()
        self.addCleanup(patch.stop)
        self.dette = []
        self.cambi = []
        self.problemi = []
        self.addCleanup(lambda: self.assertEqual(self.problemi, []))
        self.sblocca = threading.Event()
        self.sblocca.set()

    def riproduci(self, audio, frequenza, interrompi):
        self.dette.append(len(audio))
        while not self.sblocca.is_set():
            if interrompi.wait(0.01):
                return

    def crea(self, **config):
        impostazioni = {"come_chiamarmi": "signore", "dai_del": "lei", "limite_voce": 60}
        impostazioni.update(config)
        v = voce.Voce(impostazioni, avvisa=self.problemi.append, al_cambio=self.cambi.append,
                      riproduci=self.riproduci)
        # Si registra il testo di ogni frase quando la voce la mette in fila per essere letta.
        originale = v._da_dire.put
        v._da_dire.put = lambda elemento: (self.frasi.append(elemento[1]), originale(elemento))
        self.frasi = []
        return v

    def aspetta(self, v):
        for _ in range(200):
            if not v.sta_parlando:
                return
            time.sleep(0.01)
        self.fail("la voce non ha finito di parlare")

    def test_risposta_a_pezzi_e_limite(self):
        v = self.crea()
        v.inizia()
        for pezzo in ["Buongiorno, sig", "nore. Oggi a Cagliari ci sono 22°C. ",
                      "Domani pioverà parecchio, quindi le consiglio l'ombrello. E poi altro."]:
            v.aggiungi(pezzo)
        v.finisci()
        self.aspetta(v)
        self.assertEqual(self.frasi, ["Buongiorno, signore.", "Oggi a Cagliari ci sono 22 gradi.",
                                      "Il resto lo trova nella finestra, signore."])
        self.assertEqual(self.cambi[0], True)
        self.assertEqual(self.cambi[-1], False)

    def test_zitto(self):
        v = self.crea(limite_voce=1000)
        self.sblocca.clear()  # la prima frase resta "in riproduzione" finché non la si interrompe
        v.di("Prima frase. Seconda frase. Terza frase.")
        time.sleep(0.1)
        self.assertTrue(v.sta_parlando)
        v.zitto()
        self.aspetta(v)
        self.assertEqual(len(self.dette), 1)  # solo la prima frase, interrotta a metà
        v.aggiungi("Questa non va detta.")  # dopo zitto() il resto della risposta si ignora
        v.finisci()
        self.assertNotIn("Questa non va detta.", self.frasi)

    def test_errore_della_voce(self):
        avvisi = []

        def rotta(*argomenti):
            raise voce.ErroreVoce("manca la libreria piper")

        with mock.patch.object(voce, "carica_motore", rotta):
            v = voce.Voce({}, avvisa=avvisi.append, riproduci=self.riproduci)
            v.di("Ciao. Come va?")
            self.aspetta(v)
        self.assertEqual(avvisi, ["La voce non funziona: manca la libreria piper"])  # una volta sola


if __name__ == "__main__":
    unittest.main()
