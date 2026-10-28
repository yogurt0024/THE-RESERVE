"""Prove delle abilità: il controllo del codice, il recinto, l'approvazione e l'apprendimento con il cervello finto."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import abilita
import cervello
import strumenti
from test import finti
from test.test_assistente import Base as BaseAssistente

BUONA = finti.ABILITA_CONTA_VOCALI
TESTA = "NOME = 'prova'\nDESCRIZIONE = 'Una prova del recinto.'\nPARAMETRI = {}\nOBBLIGATORI = []\nPROVE = [({}, '')]\n"


def con_esegui(corpo):
    return TESTA + "\n\ndef esegui(argomenti, aiuto):\n" + "".join(f"    {riga}\n" for riga in corpo.splitlines())


class TestControllo(unittest.TestCase):
    def test_codice_permesso(self):
        abilita.controlla(BUONA)
        abilita.controlla(con_esegui("import math\nfrom datetime import date\nreturn str(math.pi) + str(date.today())"))

    def test_codice_vietato(self):
        casi = {
            "import os": "la libreria os non è permessa",
            "import subprocess as s": "la libreria subprocess non è permessa",
            "from math import *": "si possono importare solo nomi pubblici",
            "x = ().__class__": "l'attributo .__class__ non è permesso",
            "x = open('a')": "il nome open non è permesso",
            "x = eval('1')": "il nome eval non è permesso",
            "x = getattr(1, 'real')": "il nome getattr non è permesso",
            "x = '{0}'.format(1)": "l'attributo .format non è permesso",
            "x = 'a__b'": "due trattini bassi",
            "class A:\n    pass": "fuori dalle funzioni",
            "for i in range(3):\n    pass": "fuori dalle funzioni",
        }
        for codice, motivo in casi.items():
            with self.assertRaises(abilita.ErroreAbilita, msg=codice) as errore:
                abilita.controlla(codice + "\n" + TESTA)
            self.assertIn(motivo, str(errore.exception), codice)
        for corpo, motivo in {"g = (x for x in [1])\nreturn str(g.gi_frame)": ".gi_frame",
                              "def f():\n    yield 1\nreturn ''": "Yield",
                              "global x\nreturn ''": "Global"}.items():
            with self.assertRaises(abilita.ErroreAbilita) as errore:
                abilita.controlla(con_esegui(corpo))
            self.assertIn(motivo, str(errore.exception))
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita.controlla(TESTA)
        self.assertIn("manca la funzione esegui", str(errore.exception))
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita.controlla("def esegui(argomenti, aiuto):\n    return ''\n")
        self.assertIn("manca NOME, DESCRIZIONE", str(errore.exception))

    def test_estrai_codice(self):
        self.assertEqual(abilita.estrai_codice("Ecco:\n```python\nx = 1\n```\nFatto."), "x = 1\n")
        self.assertEqual(abilita.estrai_codice("x = 2"), "x = 2\n")

    def test_scheda(self):
        buona = {"nome": "conta_vocali", "descrizione": "Conta le vocali di un testo.", "obbligatori": ["testo"],
                 "parametri": {"testo": {"type": "string", "description": "Il testo"}}}
        abilita.controlla_scheda(buona)
        for cambio, motivo in [({"nome": "Conta Vocali"}, "NOME"), ({"nome": "meteo"}, "già di uno strumento"),
                               ({"descrizione": "corta"}, "DESCRIZIONE"),
                               ({"parametri": {"testo": {"type": "list", "description": "x"}}}, "type"),
                               ({"obbligatori": ["altro"]}, "OBBLIGATORI")]:
            with self.assertRaises(abilita.ErroreAbilita) as errore:
                abilita.controlla_scheda(dict(buona, **cambio), strumenti.nomi_riservati())
            self.assertIn(motivo, str(errore.exception))


class TestRecinto(unittest.TestCase):
    def test_prove_e_esecuzione(self):
        info = abilita.prova(BUONA)
        self.assertEqual((info["nome"], info["prove"]), ("conta_vocali", 3))
        self.assertEqual(abilita._nel_recinto("esegui", BUONA, {"testo": "Minecraft"}),
                         "In «Minecraft» ci sono 3 vocali.")

    def test_prova_che_non_passa(self):
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita.prova(BUONA.replace('"2 vocali"', '"7 vocali"'))
        self.assertEqual(str(errore.exception), "la prova 1 non passa: con {'testo': 'Jarvis'} ho ottenuto «In "
                                                "«Jarvis» ci sono 2 vocali.», che non contiene «7 vocali»")

    def test_niente_vie_di_fuga(self):
        # Le librerie permesse arrivano senza le altre librerie che usano dentro (re usa enum, che usa sys).
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita._nel_recinto("esegui", con_esegui("import re\nreturn str(re.enum.sys.modules)"))
        self.assertIn("AttributeError", str(errore.exception))
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita._nel_recinto("esegui", con_esegui("return 5"))
        self.assertIn("deve restituire un testo", str(errore.exception))

    def test_internet_spento_e_ciclo_infinito(self):
        codice = con_esegui("try:\n    return aiuto.pagina('https://example.com')\nexcept ValueError as e:\n"
                            "    return 'Niente internet: ' + str(e)")
        self.assertEqual(abilita._nel_recinto("esegui", codice, internet=False),
                         "Niente internet: internet è disattivato")
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita._nel_recinto("esegui", con_esegui("while True:\n    pass"), tempo=3)
        self.assertIn("ci mette troppo", str(errore.exception))

    def test_troppa_memoria(self):
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita._nel_recinto("esegui", con_esegui("x = 'a' * (4 * 1024 ** 3)\nreturn 'ok'"), tempo=20)
        self.assertIn("MemoryError", str(errore.exception))


class Cartella(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(abilita, "CARTELLA", Path(tempfile.mkdtemp()) / "abilita")
        patch.start()
        self.addCleanup(patch.stop)


class TestArchivio(Cartella):
    def test_proponi_approva_migliora_ripristina(self):
        info = abilita.prova(BUONA)
        abilita.proponi(BUONA, info, "contare le vocali")
        self.assertEqual(list(abilita.proposte()), ["conta_vocali"])
        self.assertEqual(abilita.schemi(), [])  # finché non è approvata non si usa
        self.assertFalse(abilita.approva("conta_vocali"))
        self.assertEqual(abilita.proposte(), {})
        schema = abilita.schemi()[0]["function"]
        self.assertEqual(schema["name"], "conta_vocali")
        self.assertEqual(schema["parameters"]["required"], ["testo"])
        self.assertEqual(abilita.esegui("conta_vocali", {"testo": "ciao"}), "In «ciao» ci sono 3 vocali.")
        # Lo strumento passa da strumenti.py, come tutti gli altri.
        config = dict(cervello.CONFIG_PREDEFINITA)
        self.assertIn("conta_vocali", [s["function"]["name"] for s in strumenti.schemi(config)])
        self.assertEqual(strumenti.descrivi("conta_vocali", {}), "Uso l'abilità conta_vocali...")
        self.assertEqual(strumenti.esegui("conta_vocali", {"testo": "oca"}, config, None),
                         "In «oca» ci sono 2 vocali.")
        self.assertNotIn("conta_vocali", [s["function"]["name"] for s in strumenti.schemi(dict(config, abilita=False))])
        # Una versione nuova: la vecchia resta da parte e si può rimettere.
        nuova = BUONA.replace("vocali.", "vocali, signore.")
        abilita.proponi(nuova, abilita.prova(nuova), "più gentile")
        self.assertTrue(abilita.approva("conta_vocali"))
        self.assertTrue(abilita.esegui("conta_vocali", {"testo": "ciao"}).endswith("signore."))
        abilita.ripristina("conta_vocali")
        self.assertEqual(abilita.esegui("conta_vocali", {"testo": "ciao"}), "In «ciao» ci sono 3 vocali.")
        abilita.togli("conta_vocali")
        self.assertEqual(abilita.attive(), {})
        self.assertTrue(strumenti.esegui("conta_vocali", {"testo": "x"}, config, None).startswith("Errore:"))

    def test_file_cambiato_dopo_l_approvazione(self):
        abilita.proponi(BUONA, abilita.prova(BUONA), "contare le vocali")
        abilita.approva("conta_vocali")
        file = abilita.CARTELLA / "conta_vocali.py"
        file.write_text(BUONA.replace("vocali.", "vocali!"), encoding="utf-8")
        with self.assertRaises(abilita.ErroreAbilita) as errore:
            abilita.esegui("conta_vocali", {"testo": "ciao"})
        self.assertIn("è stato cambiato dopo l'approvazione", str(errore.exception))

    def test_rifiuta(self):
        abilita.proponi(BUONA, abilita.prova(BUONA), "contare le vocali")
        abilita.rifiuta("conta_vocali")
        self.assertEqual(abilita.proposte(), {})
        with self.assertRaises(abilita.ErroreAbilita):
            abilita.rifiuta("conta_vocali")
        with self.assertRaises(abilita.ErroreAbilita):
            abilita.approva("conta_vocali")


class TestImparare(BaseAssistente):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(abilita, "CARTELLA", self.cartella / "abilita")
        patch.start()
        self.addCleanup(patch.stop)

    def test_impara_corregge_e_aspetta_il_permesso(self):
        j = self.jarvis()
        testo, _, _ = self.chiedi(j, "Jarvis, impara a contare le vocali")
        self.assertEqual(testo, "Ci lavoro, signore: scrivo l'abilità, la provo e poi gliela propongo. Ci vorrà "
                                "qualche minuto (compito 1).")
        compito = self.aspetta_compito()
        self.assertEqual(compito.stato, "completato")
        self.assertEqual(compito.risultato,
                         "Ho imparato una cosa nuova, signore: Conta quante vocali ci sono in una parola o in una "
                         "frase. Si chiama conta_vocali e ha superato 3 prove. La uso solo con il suo permesso: dica "
                         "\"Jarvis, approva\" oppure scriva /approva conta_vocali (/rifiuta conta_vocali per "
                         "scartarla).")
        richieste = [r for r in finti.FintoOllama.richieste
                     if r.get("messages") and r["messages"][0]["content"].startswith("Scrivi un'abilità")]
        self.assertEqual(len(richieste), 2)  # la prima versione aveva una prova sbagliata: l'ha corretta
        self.assertEqual(richieste[0]["model"], "qwen3.6:35b-a3b")
        self.assertIn("la prova 1 non passa", richieste[1]["messages"][-1]["content"])
        self.assertIn("meteo", richieste[0]["messages"][0]["content"])  # i nomi già occupati
        self.assertNotIn("conta_vocali", [s["function"]["name"] for s in strumenti.schemi(j.config)])
        _, avvisi, _ = self.chiedi(j, "/abilita")
        self.assertEqual(avvisi, ["Le abilità che ho imparato:\n- conta_vocali (in attesa di /approva): Conta quante "
                                  "vocali ci sono in una parola o in una frase."])
        testo, _, _ = self.chiedi(j, "Jarvis, approva")
        self.assertEqual(testo, "Fatto, signore: da ora so usare l'abilità conta_vocali. Conta quante vocali ci sono "
                                "in una parola o in una frase.")
        self.assertIn("conta_vocali", [s["function"]["name"] for s in strumenti.schemi(j.config)])
        self.assertEqual(j._esegui("conta_vocali", {"testo": "Jarvis"}), "In «Jarvis» ci sono 2 vocali.")
        _, avvisi, _ = self.chiedi(j, "/abilita conta_vocali")
        self.assertTrue(avvisi[0].startswith("conta_vocali (attiva): Conta quante vocali"))
        self.assertIn("Richiesta: contare le vocali", avvisi[0])

    def test_migliora_e_versioni(self):
        j = self.jarvis()
        _, avvisi, _ = self.chiedi(j, "/migliora conta_vocali anche le consonanti")
        self.assertTrue(avvisi[0].startswith("Non conosco un'abilità che si chiama conta_vocali"))
        abilita.proponi(BUONA, abilita.prova(BUONA), "contare le vocali")
        abilita.approva("conta_vocali")
        testo, _, _ = self.chiedi(j, "Jarvis, migliora l'abilità conta_vocali: conta anche le consonanti")
        self.assertTrue(testo.startswith("Ci lavoro, signore"))
        compito = self.aspetta_compito()
        self.assertTrue(compito.risultato.startswith("Ho preparato la nuova versione dell'abilità conta_vocali, "
                                                     "signore: "), compito.risultato)
        richiesta = [r for r in finti.FintoOllama.richieste
                     if r.get("messages") and r["messages"][0]["content"].startswith("Scrivi un'abilità")][-1]
        self.assertIn("Migliorala così: conta anche le consonanti", richiesta["messages"][1]["content"])
        self.assertIn('NOME = "conta_vocali"', richiesta["messages"][1]["content"])
        _, avvisi, _ = self.chiedi(j, "/approva")
        self.assertTrue(avvisi[0].endswith("La versione di prima resta da parte (/abilita ripristina conta_vocali)."))
        self.assertEqual(j._esegui("conta_vocali", {"testo": "albero"}),
                         "In «albero» ci sono 3 vocali e 3 consonanti.")
        _, avvisi, _ = self.chiedi(j, "/abilita ripristina conta_vocali")
        self.assertEqual(j._esegui("conta_vocali", {"testo": "albero"}), "In «albero» ci sono 3 vocali.")
        _, avvisi, _ = self.chiedi(j, "/rifiuta")
        self.assertEqual(avvisi, ["Non ci sono riuscito: non ci sono abilità nuove in attesa."])

    def test_le_domande_non_sono_ordini(self):
        j = self.jarvis()
        testo, _, _ = self.chiedi(j, "Puoi imparare a fare il caffè?")
        self.assertTrue(testo.startswith("Risposta di qwen3.5:4b"))
        self.assertEqual(j.compiti, [])
        self.assertIn("impara a ...", finti.FintoOllama.richieste[-1]["messages"][0]["content"])
        testo, _, _ = self.chiedi(j, "Jarvis, approva")
        self.assertEqual(testo, "Non posso approvarla, signore: non ci sono abilità nuove in attesa.")
        cervello_spento = self.jarvis(abilita=False)
        testo, _, _ = self.chiedi(cervello_spento, "Jarvis, impara a contare le vocali")
        self.assertTrue(testo.startswith("Risposta di qwen3.5:4b"))


if __name__ == "__main__":
    unittest.main()
