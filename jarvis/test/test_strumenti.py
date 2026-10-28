import unittest
from unittest import mock

import strumenti
from test import finti

CONFIG = {"internet": True, "citta": "", "programmi": {"blocco note": "notepad"}}


class TestCalcola(unittest.TestCase):
    def test_risultati(self):
        for espressione, atteso in [("2+2", "4"), ("3,5 * 2", "7"), ("sqrt(144)", "12"), ("2^10", "1.024"),
                                    ("10/3", "3,333333333"), ("5460*71/100", "3.876,6"), ("10:4", "2,5")]:
            self.assertEqual(strumenti.calcola(espressione), f"{espressione} = {atteso}")

    def test_rifiuta_codice_e_conti_enormi(self):
        for espressione in ["__import__('os')", "9**9**9", "1/0", "factorial(5000)", "abc", ""]:
            with self.assertRaises(strumenti.ErroreStrumento):
                strumenti.calcola(espressione)


class TestValida(unittest.TestCase):
    def test_argomenti(self):
        elenco = strumenti.schemi(CONFIG)
        self.assertIsNone(strumenti.valida("timer", {"minuti": 5}, elenco))
        self.assertIsNone(strumenti.valida("multimedia", {"azione": "muto"}, elenco))
        self.assertIn("numero", strumenti.valida("timer", {"minuti": "cinque"}, elenco))
        self.assertIn("manca", strumenti.valida("meteo", {}, elenco))
        self.assertIn("uno tra", strumenti.valida("multimedia", {"azione": "balla"}, elenco))
        self.assertIn("non esiste", strumenti.valida("vola", {}, elenco))


class TestInternet(unittest.TestCase):
    def test_meteo(self):
        with mock.patch.object(strumenti, "_scarica", finti.internet_finto):
            testo = strumenti.meteo("Cagliari")
        self.assertIn("Meteo di Cagliari, Sardegna, Italia", testo)
        self.assertIn("Adesso: 21°C (percepiti 20°C), parzialmente nuvoloso", testo)
        self.assertIn("probabilità di pioggia 80%", testo)

    def test_senza_internet(self):
        risultato = strumenti.esegui("meteo", {"citta": "Cagliari"}, dict(CONFIG, internet=False), print)
        self.assertTrue(risultato.startswith("Errore: internet è disattivato"))


class TestPC(unittest.TestCase):
    def test_programma_sconosciuto(self):
        risultato = strumenti.esegui("apri_programma", {"nome": "Photoshop"}, CONFIG, print)
        self.assertIn("non conosco il programma", risultato)

    def test_diagnostica(self):
        self.assertTrue(strumenti.diagnostica().startswith("Diagnostica del sistema"))


if __name__ == "__main__":
    unittest.main()
