"""Prove dei pezzi della finestra che non hanno bisogno dello schermo: sottotitoli, colori e sensori."""

import unittest

import sensori

try:
    import hud
except ImportError:  # Python senza tkinter
    hud = None


@unittest.skipIf(hud is None, "tkinter non installato")
class TestHud(unittest.TestCase):
    def test_sottotitoli_delle_risposte_lunghe(self):
        self.assertEqual(hud.coda_del_testo("Sono le 18:00, signore."), "Sono le 18:00, signore.")
        lungo = "Prima frase molto lunga che serve solo a riempire. " * 6 + "Ultima frase da vedere bene."
        coda = hud.coda_del_testo(lungo, 120)
        self.assertTrue(coda.startswith("… "))
        self.assertTrue(coda.endswith("Ultima frase da vedere bene."))
        self.assertLessEqual(len(coda), 122)
        self.assertEqual(hud.coda_del_testo("a\n\nb   c"), "a b c")

    def test_colori(self):
        self.assertEqual(hud.mescola("#000000", "#ffffff", 0), "#000000")
        self.assertEqual(hud.mescola("#000000", "#ffffff", 1), "#ffffff")
        self.assertEqual(hud.mescola("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(hud.mescola("#000000", "#ffffff", 7), "#ffffff")  # oltre i limiti si ferma


class TestSensori(unittest.TestCase):
    def test_letture(self):
        lettore = sensori.Sensori()
        lettore.leggi()
        dati = lettore.leggi()
        self.assertIsInstance(dati, dict)
        for chiave in ("cpu", "ram", "disco"):
            if chiave in dati:
                self.assertTrue(0 <= dati[chiave] <= 100, (chiave, dati[chiave]))


if __name__ == "__main__":
    unittest.main()
