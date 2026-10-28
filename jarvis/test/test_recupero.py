"""Prove del recupero della voce scelta in un'altra copia di Jarvis o nella cronologia di ElevenLabs."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import recupero
import voce_elevenlabs as el
from test import finti


def copia_di_jarvis(cartella, config, dati=None):
    cartella.mkdir(parents=True)
    (cartella / "cervello.py").write_text("# Jarvis\n", encoding="utf-8")
    (cartella / "config.json").write_text(json.dumps(config), encoding="utf-8")
    for nome, testo in (dati or {}).items():
        (cartella / "dati").mkdir(exist_ok=True)
        (cartella / "dati" / nome).write_text(testo, encoding="utf-8")
    return cartella


class TestRecupero(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = finti.avvia(finti.FintoElevenLabs)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        # Come sul PC: Download con due ZIP estratti, uno anche con la cartella doppia di Windows.
        self.download = Path(tempfile.mkdtemp()) / "Downloads"
        self.qui = copia_di_jarvis(self.download / "THE-RESERVE-nuovo" / "jarvis",
                                   {"voce": "riccardo", "voce_elevenlabs": ""})
        self.config = {"voce": "riccardo", "voce_elevenlabs": "", "effetto_voce": 0.6}
        self.salvate = {}
        for patch in (mock.patch.object(el, "FILE_CHIAVE", self.qui / "dati" / "chiave_elevenlabs.txt"),
                      mock.patch.dict(os.environ, {"ELEVENLABS_BASE_URL": self.url})):
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop("ELEVENLABS_API_KEY", None)

    def salva(self, chiave, valore):
        self.config[chiave] = valore
        self.salvate[chiave] = valore

    def ritrova(self, **argomenti):
        return recupero.ritrova_voce(self.config, self.salva, cartella=self.qui, radici=[self.download],
                                     **argomenti)

    def test_dalla_copia_dove_e_stata_scelta(self):
        copia_di_jarvis(self.download / "THE-RESERVE-vecchio" / "jarvis", {"voce": "riccardo"})
        vecchia = copia_di_jarvis(
            self.download / "THE-RESERVE-voce" / "THE-RESERVE-voce" / "jarvis",
            {"voce": "elevenlabs", "voce_elevenlabs": "giorgio", "effetto_voce": 0.0, "citta": "Cagliari"},
            {"chiave_elevenlabs.txt": "chiave-gratis\n", "memoria.json": '{"fatti": ["Gioco a Minecraft"]}'})
        messaggio = self.ritrova()
        self.assertEqual(messaggio, f"Ho ritrovato la voce che avevi scelto (era nella copia di Jarvis in "
                                    f"{vecchia.resolve()}): torno a usarla. Ho ripreso da lì anche la memoria.")
        self.assertEqual(self.salvate, {"voce": "elevenlabs", "voce_elevenlabs": "giorgio", "effetto_voce": 0.0})
        self.assertEqual(el.leggi_chiave(), "chiave-gratis")
        self.assertIn("Minecraft", (self.qui / "dati" / "memoria.json").read_text(encoding="utf-8"))
        self.assertEqual(self.ritrova(), "")  # già fatto: non lo rifà a ogni avvio

    def test_non_tocca_i_ricordi_che_ci_sono_gia(self):
        copia_di_jarvis(self.download / "altro" / "jarvis", {"voce": "elevenlabs", "voce_elevenlabs": "giorgio"},
                        {"chiave_elevenlabs.txt": "chiave-gratis\n", "memoria.json": '{"fatti": ["vecchio"]}'})
        (self.qui / "dati").mkdir()
        (self.qui / "dati" / "memoria.json").write_text('{"fatti": ["nuovo"]}', encoding="utf-8")
        self.assertTrue(self.ritrova().endswith("torno a usarla."))
        self.assertIn("nuovo", (self.qui / "dati" / "memoria.json").read_text(encoding="utf-8"))

    def test_dalla_cronologia_di_elevenlabs(self):
        (self.qui / "dati").mkdir()
        el.FILE_CHIAVE.write_text("chiave-gratis\n", encoding="utf-8")
        self.assertEqual(self.ritrova(), "Ho ritrovato su ElevenLabs la voce che avevi scelto (Giorgio): torno a "
                                         "usarla.")
        self.assertEqual(self.config["voce"], "elevenlabs")
        self.assertEqual(self.config["voce_elevenlabs"], "giorgio")  # quella confermata, non l'ultima usata
        self.assertEqual(self.config["effetto_voce"], 0.0)

    def test_chiave_in_un_altra_copia_e_voce_dalla_cronologia(self):
        # La scelta non è salvata da nessuna parte, ma una copia vecchia ha la chiave: basta quella.
        vecchia = copia_di_jarvis(self.download / "vecchio" / "jarvis", {"voce": "riccardo"},
                                  {"chiave_elevenlabs.txt": "chiave-gratis\n", "memoria.json": '{"fatti": []}'})
        self.assertEqual(self.ritrova(), "Ho ritrovato su ElevenLabs la voce che avevi scelto (Giorgio): torno a "
                                         "usarla. Ho ripreso anche la memoria dalla copia di Jarvis in "
                                         f"{vecchia.resolve()}.")
        self.assertEqual(el.leggi_chiave(), "chiave-gratis")
        self.assertEqual(self.config["voce_elevenlabs"], "giorgio")

    def test_rispetta_le_scelte(self):
        copia_di_jarvis(self.download / "altro" / "jarvis", {"voce": "elevenlabs", "voce_elevenlabs": "giorgio"},
                        {"chiave_elevenlabs.txt": "chiave-gratis\n"})
        self.config["voce"] = "nicola"  # scelta apposta
        self.assertEqual(self.ritrova(), "")
        self.assertTrue(self.ritrova(forza=True).endswith("torno a usarla."))  # /voce elevenlabs
        self.config.update(voce="riccardo")
        self.salvate.clear()
        self.assertEqual(self.ritrova(), "")  # la voce di ElevenLabs è impostata: riccardo l'ha scelto l'utente
        self.assertEqual(self.salvate, {})

    def test_elevenlabs_scritto_a_mano(self):
        (self.qui / "dati").mkdir()
        el.FILE_CHIAVE.write_text("chiave-gratis\n", encoding="utf-8")
        self.config["voce"] = "elevenlabs"  # ma senza l'identificativo della voce
        self.assertTrue(self.ritrova().startswith("Ho ritrovato su ElevenLabs la voce"))
        self.assertEqual(self.config["voce_elevenlabs"], "giorgio")

    def test_copia_nuova_riprende_tutto_da_quella_di_prima(self):
        vecchia = copia_di_jarvis(
            self.download / "vecchia" / "jarvis",
            {"voce": "elevenlabs", "voce_elevenlabs": "giorgio", "effetto_voce": 0.0, "citta": "Cagliari",
             "impostazione_sparita": True},
            {"chiave_elevenlabs.txt": "chiave-gratis\n", "memoria.json": '{"fatti": ["Gioco a Minecraft"]}',
             "versione.txt": "vecchia\n", "conversazione.json": "{}"})
        (vecchia / "dati" / "diario").mkdir()
        (vecchia / "dati" / "diario" / "2026-10-28.md").write_text("Abbiamo scelto la voce.", encoding="utf-8")
        (vecchia / "dati" / "modelli" / "parakeet").mkdir(parents=True)
        (vecchia / "dati" / "modelli" / "parakeet" / "modello.onnx").write_bytes(b"pesante")
        (vecchia / "dati" / "modelli" / "parakeet" / "altro.onnx.parziale").write_bytes(b"a meta")
        (vecchia / "dati" / "voci_di_prova").mkdir()
        (vecchia / "dati" / "voci_di_prova" / "1.wav").write_bytes(b"prova")
        # Una copia ancora più vecchia, usata prima: non è quella da riprendere.
        piu_vecchia = copia_di_jarvis(self.download / "antica" / "jarvis", {"voce": "riccardo"},
                                      {"memoria.json": '{"fatti": ["antico"]}'})
        os.utime(piu_vecchia / "dati" / "memoria.json", (1, 1))
        (self.qui / "config.json").write_text(json.dumps({"voce": "riccardo", "voce_elevenlabs": "", "citta": "",
                                                          "effetto_voce": 0.6, "nuova_impostazione": 1}),
                                              encoding="utf-8")
        messaggio = recupero.trasloca(self.qui, radici=[self.download])
        self.assertEqual(messaggio, f"Ho ripreso i tuoi dati e le tue impostazioni dalla copia di Jarvis in "
                                    f"{vecchia.resolve()}: memoria, promemoria, diario, chiavi e voce sono come prima.")
        dati = self.qui / "dati"
        self.assertIn("Minecraft", (dati / "memoria.json").read_text(encoding="utf-8"))
        self.assertEqual(el.leggi_chiave(), "chiave-gratis")
        self.assertEqual((dati / "diario" / "2026-10-28.md").read_text(encoding="utf-8"), "Abbiamo scelto la voce.")
        self.assertEqual((dati / "modelli" / "parakeet" / "modello.onnx").read_bytes(), b"pesante")
        self.assertFalse((dati / "modelli" / "parakeet" / "altro.onnx.parziale").exists())
        self.assertFalse((dati / "voci_di_prova").exists())
        self.assertFalse((dati / "versione.txt").exists())  # la versione è quella nuova
        config = json.loads((self.qui / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config, {"voce": "elevenlabs", "voce_elevenlabs": "giorgio", "citta": "Cagliari",
                                  "effetto_voce": 0.0, "nuova_impostazione": 1})
        self.assertEqual(recupero.trasloca(self.qui, radici=[self.download]), "")  # una volta sola

    def test_copia_gia_usata_non_si_tocca(self):
        copia_di_jarvis(self.download / "vecchia" / "jarvis", {"voce": "elevenlabs", "voce_elevenlabs": "giorgio"},
                        {"memoria.json": '{"fatti": ["vecchio"]}'})
        (self.qui / "dati").mkdir()
        (self.qui / "dati" / "conversazione.json").write_text("{}", encoding="utf-8")
        self.assertEqual(recupero.trasloca(self.qui, radici=[self.download]), "")
        self.assertFalse((self.qui / "dati" / "memoria.json").exists())

    def test_voce_impostata_ma_senza_chiave(self):
        # Si è copiato config.json ma non la cartella dati: la chiave si riprende dalla copia di prima.
        copia_di_jarvis(self.download / "vecchia" / "jarvis", {"voce": "elevenlabs", "voce_elevenlabs": "giorgio"},
                        {"chiave_elevenlabs.txt": "chiave-gratis\n"})
        self.config.update(voce="elevenlabs", voce_elevenlabs="giorgio")
        self.assertTrue(self.ritrova().startswith("Ho ripreso la chiave di ElevenLabs dalla copia di Jarvis in "))
        self.assertEqual(el.leggi_chiave(), "chiave-gratis")
        self.assertEqual(self.ritrova(), "")

    def test_niente_da_trovare(self):
        self.assertEqual(self.ritrova(), "")  # né altre copie, né chiave
        (self.qui / "dati").mkdir()
        el.FILE_CHIAVE.write_text("sbagliata\n", encoding="utf-8")
        self.assertEqual(self.ritrova(), "")  # la cronologia non si legge con una chiave sbagliata
        self.assertEqual(self.config["voce"], "riccardo")


if __name__ == "__main__":
    unittest.main()
