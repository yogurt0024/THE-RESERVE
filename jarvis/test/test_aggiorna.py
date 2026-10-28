"""Prove dell'aggiornamento automatico, con un GitHub finto e una cartella di Jarvis finta."""

import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import aggiorna
from test import finti


def pacchetto(file):
    dati = io.BytesIO()
    with zipfile.ZipFile(dati, "w") as archivio:
        for nome, contenuto in file.items():
            archivio.writestr(f"THE-RESERVE-ramo/jarvis/{nome}", contenuto)
        archivio.writestr("THE-RESERVE-ramo/README.md", "fuori dalla cartella jarvis")
    return dati.getvalue()


class TestAggiorna(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = finti.avvia(finti.FintoGitHub)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.cartella = Path(tempfile.mkdtemp())
        for patch in (mock.patch.object(aggiorna, "CARTELLA", self.cartella),
                      mock.patch.dict(os.environ, {"JARVIS_GITHUB_API": self.url, "JARVIS_GITHUB_ZIP": self.url})):
            patch.start()
            self.addCleanup(patch.stop)
        (self.cartella / "dati").mkdir()
        (self.cartella / "dati" / "chiave_elevenlabs.txt").write_text("la mia chiave")
        (self.cartella / "cervello.py").write_text("vecchio")
        (self.cartella / "voce.py").write_text("uguale")
        (self.cartella / "config.json").write_text(json.dumps({"voce": "elevenlabs", "citta": "Cagliari"}))
        finti.FintoGitHub.privato = False
        finti.FintoGitHub.chiavi_ricevute = []
        finti.FintoGitHub.sha = "v2"
        finti.FintoGitHub.archivio = pacchetto({
            "cervello.py": "nuovo", "voce.py": "uguale", "abilita/nuova.py": "abilità",
            "config.json": json.dumps({"voce": "riccardo", "citta": "", "attenzione": "normale"}),
            "dati/chiave_elevenlabs.txt": "da non usare", "../fuori.py": "pericoloso"})

    def test_aggiorna_senza_toccare_dati_e_scelte(self):
        self.assertIsNone(aggiorna.c_e_un_aggiornamento())  # versione installata sconosciuta
        cambiati, messaggio = aggiorna.aggiorna()
        self.assertEqual((cambiati, messaggio), (3, "Aggiornamento installato: 3 file cambiati."))
        self.assertEqual((self.cartella / "cervello.py").read_text(), "nuovo")
        self.assertEqual((self.cartella / "abilita" / "nuova.py").read_text(), "abilità")
        self.assertEqual((self.cartella / "dati" / "chiave_elevenlabs.txt").read_text(), "la mia chiave")
        self.assertFalse((self.cartella.parent / "fuori.py").exists())
        config = json.loads((self.cartella / "config.json").read_text())
        self.assertEqual(config, {"voce": "elevenlabs", "citta": "Cagliari", "attenzione": "normale"})
        self.assertIs(aggiorna.c_e_un_aggiornamento(), False)
        self.assertEqual(aggiorna.aggiorna(), (0, "Jarvis era già aggiornato."))
        finti.FintoGitHub.sha = "v3"
        self.assertIs(aggiorna.c_e_un_aggiornamento(), True)

    def test_repository_privato(self):
        finti.FintoGitHub.privato = True
        with self.assertRaises(aggiorna.ErroreAggiornamento) as errore:
            aggiorna.aggiorna()
        self.assertIn("perché è privato. Collega GitHub con /chiave github", str(errore.exception))
        self.assertEqual(aggiorna.salva_chiave("sbagliata"), "La chiave non funziona: la chiave di GitHub non è "
                                                             "valida o è scaduta: creane una nuova e inseriscila "
                                                             "con /chiave github")
        self.assertFalse((self.cartella / "dati" / "chiave_github.txt").exists())
        self.assertTrue(aggiorna.salva_chiave(" github-buona\n").startswith("Chiave di GitHub salvata sul PC"))
        self.assertEqual(aggiorna.aggiorna(), (3, "Aggiornamento installato: 3 file cambiati."))
        self.assertEqual((self.cartella / "cervello.py").read_text(), "nuovo")
        self.assertIs(aggiorna.c_e_un_aggiornamento(), False)
        # La chiave va solo a GitHub: l'indirizzo temporaneo del pacchetto non la riceve.
        self.assertIn(("/repos/yogurt0024/THE-RESERVE/zipball/claude/beautiful-gauss-ld6wqw", "Bearer github-buona"),
                      finti.FintoGitHub.chiavi_ricevute)
        self.assertIn(("/temporaneo/pacchetto.zip", None), finti.FintoGitHub.chiavi_ricevute)


if __name__ == "__main__":
    unittest.main()
