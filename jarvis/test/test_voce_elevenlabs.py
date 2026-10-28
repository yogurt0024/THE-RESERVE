"""Prove della voce su ElevenLabs, con un ElevenLabs finto: niente internet e niente crediti consumati."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import voce
import voce_elevenlabs as el
from test import finti

try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(np is None, "numpy non installato")
class TestElevenLabs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = finti.avvia(finti.FintoElevenLabs)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        finti.FintoElevenLabs.richieste = []
        for patch in (mock.patch.object(el, "FILE_CHIAVE", Path(tempfile.mkdtemp()) / "chiave.txt"),
                      mock.patch.dict(os.environ, {"ELEVENLABS_BASE_URL": self.url})):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("ELEVENLABS_API_KEY", None)

    def test_chiave(self):
        self.assertEqual(el.salva_chiave("sbagliata"),
                         "La chiave non funziona: la chiave API di ElevenLabs non è valida")
        self.assertFalse(el.FILE_CHIAVE.exists())
        self.assertEqual(el.salva_chiave(" chiave-buona\n"), "Chiave di ElevenLabs salvata sul PC. Piano creator: "
                                                            "questo mese hai usato 1.200 caratteri su 10.000.")
        self.assertEqual(el.leggi_chiave(), "chiave-buona")

    def test_crea_la_voce_di_jarvis(self):
        el.salva_chiave("chiave-buona")
        voci = el.progetta_voci()
        self.assertEqual([v[0] for v in voci], ["provvisoria-1", "provvisoria-2", "provvisoria-3"])
        self.assertAlmostEqual(float(voci[1][1][0]), 2000 / 32768)
        richiesta = finti.FintoElevenLabs.richieste[-1]
        self.assertEqual(richiesta["percorso"], "/v1/text-to-voice/design?output_format=pcm_24000")
        self.assertEqual(richiesta["voice_description"], el.DESCRIZIONE_JARVIS)
        self.assertEqual(el.crea_voce("provvisoria-2"), "voce-jarvis")
        self.assertEqual(finti.FintoElevenLabs.richieste[-1]["generated_voice_id"], "provvisoria-2")

    def test_piano_gratuito(self):
        self.assertTrue(el.salva_chiave("chiave-gratis").endswith("Piano free: questo mese hai usato 1.200 "
                                                                  "caratteri su 10.000."))
        with self.assertRaises(el.ErroreElevenLabs) as errore:
            el.progetta_voci()
        self.assertEqual(errore.exception.stato, "solo_a_pagamento")
        self.assertEqual(str(errore.exception), "questa funzione di ElevenLabs c'è solo nei piani a pagamento")
        self.assertEqual([v["voice_id"] for v in el.voci_disponibili()], ["anna", "bruno", "giorgio"])
        self.assertEqual(len(el.sintetizza("Ciao.", "giorgio")), 50)  # le voci pronte vanno anche gratis

    def test_discorso_continuo(self):
        el.salva_chiave("chiave-buona")
        motore = voce.carica_motore("elevenlabs", config={"voce_elevenlabs": "voce-jarvis"})
        audio, frequenza = motore.sintetizza("Prima frase.")
        self.assertEqual((len(audio), frequenza), (120, 24000))
        motore.sintetizza("Seconda frase.")
        richiesta = finti.FintoElevenLabs.richieste[-1]
        self.assertEqual(richiesta["previous_text"], "Prima frase.")  # ElevenLabs continua il discorso
        self.assertEqual(richiesta["model_id"], "eleven_multilingual_v2")
        self.assertNotIn("language_code", richiesta)
        self.assertEqual(richiesta["voice_settings"]["speed"], 1.0)

    def test_senza_chiave_o_senza_voce(self):
        with self.assertRaisesRegex(voce.ErroreVoce, "manca la chiave"):
            voce.carica_motore("elevenlabs", config={"voce_elevenlabs": "voce-jarvis"})
        el.salva_chiave("chiave-buona")
        with self.assertRaisesRegex(voce.ErroreVoce, "creala con"):
            voce.carica_motore("elevenlabs", config={})

    def test_voce_di_riserva(self):
        el.salva_chiave("chiave-buona")
        originale = voce.carica_motore

        class Riserva:
            def sintetizza(self, testo):
                return np.ones(1600, dtype=np.float32), 16000

        def carica(nome, *argomenti, **opzioni):
            return originale(nome, *argomenti, **opzioni) if nome == "elevenlabs" else Riserva()

        suonati, avvisi = [], []
        with mock.patch.object(voce, "carica_motore", carica):
            v = voce.Voce({"voce": "elevenlabs", "voce_elevenlabs": "esaurita", "effetto_voce": 0},
                          avvisa=avvisi.append, riproduci=lambda audio, frequenza, interrompi: suonati.append(frequenza))
            v.di("Ciao a tutti. Come va?")
            for _ in range(200):
                if not v.sta_parlando:
                    break
                time.sleep(0.01)
        self.assertEqual(suonati, [16000, 16000])  # ha parlato con la voce di riserva
        self.assertEqual(avvisi, ["La voce non funziona: non sono riuscito a dire una frase "
                                  "(hai finito i caratteri del mese su ElevenLabs)"])
        # Per un po' non riprova ElevenLabs a ogni frase.
        self.assertEqual(len([r for r in finti.FintoElevenLabs.richieste if "esaurita" in r["percorso"]]), 1)


if __name__ == "__main__":
    unittest.main()
