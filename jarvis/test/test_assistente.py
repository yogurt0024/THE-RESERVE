"""Prove di Jarvis completo, con Ollama, Claude e internet finti. I dati veri in dati/ non vengono toccati."""

import json
import os
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cervello
import cervello_claude
import strumenti
from test import finti


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama, cls.url_ollama = finti.avvia(finti.FintoOllama)
        cls.claude, cls.url_claude = finti.avvia(finti.FintoClaude)

    @classmethod
    def tearDownClass(cls):
        cls.ollama.shutdown()
        cls.claude.shutdown()

    def setUp(self):
        finti.FintoOllama.richieste = []
        finti.FintoClaude.richieste = []
        cartella = Path(tempfile.mkdtemp())
        self.cartella = cartella
        for oggetto, nome, file in [(cervello, "FILE_CONFIG", "config.json"), (cervello, "FILE_MEMORIA", "memoria.json"),
                                    (cervello, "FILE_CONVERSAZIONE", "conversazione.json"),
                                    (cervello_claude, "FILE_CHIAVE", "chiave.txt"),
                                    (cervello_claude, "FILE_COSTI", "costi.json"),
                                    (strumenti, "_scarica", None)]:
            sostituto = finti.internet_finto if file is None else cartella / file
            patch = mock.patch.object(oggetto, nome, sostituto)
            patch.start()
            self.addCleanup(patch.stop)
        ambiente = mock.patch.dict(os.environ, {"ANTHROPIC_BASE_URL": self.url_claude})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def jarvis(self, chiave=False, **impostazioni):
        if chiave:
            cervello_claude.FILE_CHIAVE.write_text("sk-ant-test\n", encoding="utf-8")
        config = dict(cervello.CONFIG_PREDEFINITA, ollama_url=self.url_ollama, come_chiamarmi="signore",
                      **impostazioni)
        self.finiti = queue.Queue()  # i compiti in background arrivati alla fine
        assistente = cervello.Assistente(config, avvisa=lambda messaggio: None, al_termine=self.finiti.put)
        assistente.avvia()
        return assistente

    def aspetta_compito(self):
        return self.finiti.get(timeout=10)

    @staticmethod
    def chiedi(assistente, testo):
        """Restituisce (testo della risposta, avvisi, tipi di evento)."""
        eventi = list(assistente.gestisci(testo))
        return ("".join(e[1] for e in eventi if e[0] == "testo"), [e[1] for e in eventi if e[0] == "info"],
                [e[0] for e in eventi])


class TestModelloLocale(Base):
    def test_risposta_e_cronologia(self):
        j = self.jarvis()
        testo, _, _ = self.chiedi(j, "Ciao")
        self.assertEqual(testo, "Risposta di qwen3.5:4b: Ciao")
        salvata = json.loads(cervello.FILE_CONVERSAZIONE.read_text(encoding="utf-8"))["messaggi"]
        self.assertEqual([m["role"] for m in salvata], ["user", "assistant"])

    def test_strumento_meteo(self):
        j = self.jarvis()
        testo, avvisi, _ = self.chiedi(j, "Che tempo fa a Cagliari?")
        self.assertEqual(avvisi, ["Controllo il meteo di Cagliari..."])
        self.assertEqual(testo, "Adesso a Cagliari fa 22°C.")
        risultato = finti.FintoOllama.richieste[-1]["messages"][-1]
        self.assertEqual(risultato["role"], "tool")
        self.assertIn("Meteo di Cagliari", risultato["content"])

    def test_ragionamento_nascosto(self):
        j = self.jarvis(modello="qwen3:4b", modello_grande="")
        testo, _, eventi = self.chiedi(j, "Ciao")
        self.assertIn("ritira", eventi)  # il ragionamento finito nel testo viene tolto
        self.assertEqual(j.cronologia[-1]["content"], "Risposta di qwen3:4b: Ciao")
        self.chiedi(j, "Ciao di nuovo")
        self.assertIs(finti.FintoOllama.richieste[-1]["think"], True)  # dalla seconda volta lo separa Ollama

    def test_domanda_difficile_al_cervello_grande(self):
        j = self.jarvis(compiti_in_background=False)
        testo, avvisi, _ = self.chiedi(j, "Spiegami la relatività")
        self.assertEqual(avvisi, ["Passo la domanda al cervello grande (qwen3.6:35b-a3b)..."])
        self.assertEqual(testo, "Risposta di qwen3.6:35b-a3b: Spiegami la relatività")
        ultima = finti.FintoOllama.richieste[-1]
        self.assertNotIn("chiedi_al_cervello_avanzato", [s["function"]["name"] for s in ultima["tools"]])

    def test_domanda_difficile_in_background(self):
        j = self.jarvis()
        testo, avvisi, _ = self.chiedi(j, "Spiegami la relatività")
        self.assertEqual(testo, "Me ne occupo, signore: la avviso appena ho finito.")
        self.assertEqual(avvisi, ["Compito 1 affidato al cervello qwen3.6:35b-a3b. /compiti per vederlo."])
        compito = self.aspetta_compito()
        self.assertEqual((compito.numero, compito.stato), (1, "completato"))
        self.assertEqual(compito.risultato, "Risposta di qwen3.6:35b-a3b: Compito da svolgere: Spiegami la relatività")
        lavoro = finti.FintoOllama.richieste[-1]
        self.assertEqual(lavoro["model"], "qwen3.6:35b-a3b")
        self.assertIs(lavoro["think"], True)
        self.assertNotIn("chiedi_al_cervello_avanzato", [s["function"]["name"] for s in lavoro["tools"]])
        self.assertIn("in background", lavoro["messages"][0]["content"])
        # Il resoconto entra nella conversazione: Jarvis sa di cosa si parla se gli si chiede di più.
        self.chiedi(j, "Grazie")
        messaggi = [m["content"] for m in finti.FintoOllama.richieste[-1]["messages"]]
        self.assertIn("(Compito in background 1, completato: Spiegami la relatività)\n" + compito.risultato,
                      messaggi)

    def test_compito_chiesto_esplicitamente(self):
        j = self.jarvis(dai_del="tu")
        testo, _, _ = self.chiedi(j, "In background cercami le novità su Minecraft")
        self.assertEqual(testo, "Me ne occupo, signore: ti avviso appena ho finito.")
        self.assertEqual(self.aspetta_compito().descrizione, "In background cercami le novità su Minecraft")
        testo, _, _ = self.chiedi(j, "Sai lavorare in background?")  # è una domanda, non un compito
        self.assertEqual(testo, "Risposta di qwen3.5:4b: Sai lavorare in background?")

    def test_elenco_e_annullamento_dei_compiti(self):
        j = self.jarvis()
        _, avvisi, _ = self.chiedi(j, "/compiti")
        self.assertTrue(avvisi[0].startswith("Nessun compito in background."))
        self.chiedi(j, "in background un lavoro lento")
        for _ in range(100):
            if j.compiti[0].stato == "in corso":
                break
            time.sleep(0.05)
        _, avvisi, _ = self.chiedi(j, "/annulla 1")
        self.assertEqual(avvisi, ["Compito 1 annullato."])
        _, avvisi, _ = self.chiedi(j, "/annulla 1")
        self.assertEqual(avvisi, ["Nessun compito 1 da fermare: /compiti li mostra tutti."])
        self.chiedi(j, "in background un lavoro veloce")
        self.assertEqual(self.aspetta_compito().numero, 2)  # del compito annullato non arriva nessun avviso
        _, avvisi, _ = self.chiedi(j, "/compiti")
        self.assertEqual(avvisi, ["1. [annullato] in background un lavoro lento\n"
                                  "2. [completato] in background un lavoro veloce"])

    def test_ragionamento_profondo_con_il_cervello_grande(self):
        j = self.jarvis(ragionamento=True)
        testo, _, eventi = self.chiedi(j, "Ciao")
        self.assertEqual(testo, "Risposta di qwen3.6:35b-a3b: Ciao")
        self.assertIn("pensiero", eventi)
        self.assertIs(finti.FintoOllama.richieste[-1]["think"], True)

    def test_senza_cervello_grande(self):
        j = self.jarvis(modello_grande="modello-non-installato")
        self.assertIn("ollama pull modello-non-installato", j.stato())
        self.chiedi(j, "Spiegami la relatività")
        self.assertNotIn("chiedi_al_cervello_avanzato",
                         [s["function"]["name"] for s in finti.FintoOllama.richieste[-1].get("tools", [])])

    @staticmethod
    def ultima_al_modello(modello):
        return [r for r in finti.FintoOllama.richieste if r.get("model") == modello and r.get("messages")][-1]

    def test_domanda_a_voce(self):
        j = self.jarvis()
        list(j.gestisci("Raccontami una barzelletta", a_voce=True))
        sistema = finti.FintoOllama.richieste[-1]["messages"][0]["content"]
        self.assertIn(cervello.ISTRUZIONI_VOCE, sistema)
        self.assertIn("Non puoi vedere lo schermo, sentire la voce", sistema)
        j.voce_attiva = True  # la finestra lo accende quando il microfono funziona
        self.chiedi(j, "E domani?")
        sistema = finti.FintoOllama.richieste[-1]["messages"][0]["content"]
        self.assertNotIn(cervello.ISTRUZIONI_VOCE, sistema)
        self.assertIn("Senti l'utente quando ti parla, anche senza chiamarti per nome", sistema)

    def test_ora_e_data_subito(self):
        j = self.jarvis()
        prima = len(finti.FintoOllama.richieste)
        testo, _, _ = self.chiedi(j, "Che ora sono?")  # come lo trascrive a volte il microfono
        self.assertRegex(testo, r"^(Sono le \d{1,2}(:\d\d| in punto)|È (mezzanotte|l'una)( e \d+)?), signore\.$")
        testo, _, _ = self.chiedi(j, "Jarvis, che giorno è oggi?")
        self.assertTrue(testo.startswith("Oggi è ") and testo.endswith(", signore."))
        self.assertEqual(len(finti.FintoOllama.richieste), prima)  # nessuna domanda al modello
        self.assertEqual(j.cronologia[-1]["content"], testo)
        self.chiedi(j, "Che ore sono a New York?")  # questa no: la risposta non è l'ora del PC
        self.assertEqual(len(finti.FintoOllama.richieste), prima + 1)

    def test_stato_interno_e_regole(self):
        j = self.jarvis()
        self.chiedi(j, "Come stai?")
        sistema = finti.FintoOllama.richieste[-1]["messages"][0]["content"]
        self.assertIn("Come stai adesso (usalo se te lo chiedono, con sincerità): sei acceso da", sistema)
        self.assertIn("mai parole inventate", sistema)
        self.assertIn("Utente: Che ore sono?", sistema)

    def test_aggiornati(self):
        import aggiorna

        with mock.patch.object(aggiorna, "aggiorna", lambda: (2, "Aggiornamento installato: 2 file cambiati.")):
            testo, avvisi, eventi = self.chiedi(self.jarvis(), "Jarvis, aggiornati")
        self.assertEqual(testo, "Aggiornamento installato, signore: mi riavvio.")
        self.assertIn("Aggiornamento installato: 2 file cambiati.", avvisi)
        self.assertEqual(eventi[-1], "riavvia")
        with mock.patch.object(aggiorna, "aggiorna", lambda: (0, "Jarvis era già aggiornato.")):
            _, _, eventi = self.chiedi(self.jarvis(), "/aggiorna")
        self.assertNotIn("riavvia", eventi)

    def test_briefing_e_promemoria(self):
        import promemoria

        with mock.patch.object(promemoria, "FILE_PROMEMORIA", self.cartella / "promemoria.json"):
            promemoria.aggiungi("tra 1 minuto", "chiamare la nonna")
            j = self.jarvis(citta="Cagliari")
            testo, avvisi, _ = self.chiedi(j, "Jarvis, com'è la mia giornata?")
            self.assertEqual(avvisi, ["Controllo il meteo di Cagliari...", "Leggo le ultime notizie..."])
            domanda = finti.FintoOllama.richieste[-1]["messages"][-1]["content"]
            self.assertTrue(domanda.startswith("Fammi il briefing." + cervello.SEPARATORE_DATI))
            for atteso in ("Meteo di Cagliari", "chiamare la nonna", "Esce il nuovo aggiornamento di Minecraft",
                           cervello.ISTRUZIONI_BRIEFING):
                self.assertIn(atteso, domanda)
            self.assertNotIn("tools", finti.FintoOllama.richieste[-1])  # i dati li ha già raccolti Jarvis
            _, avvisi, _ = self.chiedi(j, "/promemoria")
            self.assertTrue(avvisi[0].startswith("Promemoria:\n1. oggi alle "))
            _, avvisi, _ = self.chiedi(j, "/promemoria cancella 1")
            self.assertEqual(avvisi, ["Promemoria cancellato: chiamare la nonna."])

    def test_attenzione_senza_nome(self):
        j = self.jarvis()
        self.chiedi(j, "Che tempo fa a Cagliari?")
        self.assertEqual(j.valuta_frase("Mamma, arrivo!", 3), "ignora")
        self.assertEqual(j.valuta_frase("E domani invece?", 3), "rivolta")
        richiesta = finti.FintoOllama.richieste[-1]
        self.assertEqual(richiesta["format"], cervello.SCHEMA_ATTENZIONE)
        self.assertIs(richiesta["think"], False)
        self.assertEqual(richiesta["options"]["temperature"], 0)
        self.assertIn("Adesso a Cagliari fa 22°C.", richiesta["messages"][1]["content"])  # sa di cosa si parlava
        self.assertIn("ha finito di parlare 3 secondi fa", richiesta["messages"][1]["content"])
        self.assertEqual(j.valuta_frase("Accidenti, quanto fa 15 per 32?"), "bisogno")
        # Interviene di sua iniziativa: con discrezione, e dopo torna normale.
        list(j.gestisci("Accidenti, quanto fa 15 per 32?", a_voce=True, spontaneo=True))
        self.assertIn(cervello.ISTRUZIONI_INTERVENTO, finti.FintoOllama.richieste[-1]["messages"][0]["content"])
        self.chiedi(j, "Grazie")
        self.assertNotIn(cervello.ISTRUZIONI_INTERVENTO, finti.FintoOllama.richieste[-1]["messages"][0]["content"])

    def test_modalita_gioco(self):
        j = self.jarvis()
        testo, _, _ = self.chiedi(j, "Attiva la modalità gioco")
        self.assertTrue(testo.startswith("Modalità gioco attiva, signore: la scheda video è tutta sua."))
        self.assertIn(0, [r.get("keep_alive") for r in finti.FintoOllama.richieste])  # modelli tolti dalla scheda
        _, avvisi, _ = self.chiedi(j, "Spiegami la relatività")
        ultima = self.ultima_al_modello("qwen3.5:4b")
        self.assertEqual(ultima["options"]["num_gpu"], 0)  # risponde il veloce, sul processore
        self.assertNotIn("chiedi_al_cervello_avanzato", [s["function"]["name"] for s in ultima["tools"]])
        _, avvisi, _ = self.chiedi(j, "in background cercami le novità su Minecraft")
        self.assertTrue(avvisi[0].endswith("Lo inizio quando finisce la modalità gioco."))
        time.sleep(1.5)
        self.assertEqual(j.compiti[0].stato, "in coda")  # il cervello grande aspetta la fine della partita
        testo, _, _ = self.chiedi(j, "Fine modalità gioco")
        self.assertEqual(testo, "Modalità gioco terminata, signore: torno a pieno regime. Riprendo i compiti in "
                                "attesa (1).")
        self.assertEqual(self.aspetta_compito().stato, "completato")
        self.chiedi(j, "Ciao")
        self.assertNotIn("num_gpu", self.ultima_al_modello("qwen3.5:4b")["options"])
        _, avvisi, _ = self.chiedi(j, "/gioco")
        self.assertTrue(avvisi[0].startswith("Modalità gioco attiva"))

    def test_veloce_sul_processore_mentre_lavora_il_grande(self):
        j = self.jarvis()
        self.chiedi(j, "in background un lavoro lento")
        for _ in range(100):
            if j.compiti[0].stato == "in corso":
                break
            time.sleep(0.05)
        self.chiedi(j, "Ciao")
        # La scheda video è occupata dal cervello grande: il veloce non aspetta il suo turno.
        self.assertEqual(self.ultima_al_modello("qwen3.5:4b")["options"]["num_gpu"], 0)
        self.assertNotIn("num_gpu", self.ultima_al_modello("qwen3.6:35b-a3b")["options"])
        self.aspetta_compito()

    def test_memoria_e_modo_di_parlare(self):
        j = self.jarvis()
        _, avvisi, _ = self.chiedi(j, "Ricordati che il mio gioco preferito è Minecraft")
        self.assertEqual(avvisi, ["Memorizzato: Il mio gioco preferito è Minecraft"])
        _, avvisi, _ = self.chiedi(j, "Chiamami capo")
        self.assertEqual(avvisi, ['D\'ora in poi la chiamerò "capo".'])
        self.chiedi(j, "chiamami tra 5 minuti")  # non è un appellativo
        self.chiedi(j, "Dammi del tu")
        salvato = json.loads(cervello.FILE_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual((salvato["come_chiamarmi"], salvato["dai_del"]), ("capo", "tu"))
        sistema = finti.FintoOllama.richieste[-1]["messages"][0]["content"]
        self.assertIn("Il mio gioco preferito è Minecraft", sistema)
        self.assertIn("Dai del tu", sistema)


@unittest.skipIf(cervello_claude.anthropic is None, "libreria anthropic non installata")
class TestClaude(Base):
    def test_senza_chiave(self):
        j = self.jarvis()
        self.assertFalse(j.claude.pronto)
        self.assertNotIn("chiedi_al_cervello_avanzato",
                         [s["function"]["name"] for s in finti.FintoOllama.richieste[-1].get("tools", [])])

    def test_claude_in_riserva(self):
        j = self.jarvis(chiave=True)
        self.assertIn("Claude è in riserva", j.stato())
        self.chiedi(j, "Spiegami la relatività")
        self.assertEqual(self.aspetta_compito().risultato,
                         "Risposta di qwen3.6:35b-a3b: Compito da svolgere: Spiegami la relatività")
        self.assertEqual(finti.FintoClaude.richieste, [])

    def test_resoconto_di_un_compito_a_claude(self):
        j = self.jarvis(chiave=True, cervello="claude")
        self.chiedi(j, "in background cercami le novità su Minecraft")
        self.aspetta_compito()  # i compiti li svolge sempre il cervello grande sul PC
        self.chiedi(j, "Cosa hai trovato?")
        messaggi = finti.FintoClaude.richieste[-1]["messages"]
        self.assertEqual([m["role"] for m in messaggi], ["user", "assistant", "user"])  # niente ruoli ripetuti
        self.assertIn("(Compito in background 1, completato", messaggi[1]["content"])

    def test_domanda_difficile_passata_a_claude(self):
        j = self.jarvis(chiave=True, cervello="ibrido")
        testo, avvisi, eventi = self.chiedi(j, "Spiegami la relatività")
        self.assertEqual(testo, "Risposta di Claude: Spiegami la relatività")
        self.assertEqual(avvisi[0], "Passo la domanda al cervello avanzato (Claude)...")
        self.assertIn("pensiero", eventi)
        richiesta = finti.FintoClaude.richieste[-1]
        self.assertEqual(richiesta["model"], "claude-opus-5-5")
        self.assertEqual(richiesta["output_config"], {"effort": "medium"})
        self.assertEqual(richiesta["fallbacks"], "default")

    def test_strumenti_con_claude(self):
        j = self.jarvis(chiave=True, cervello="ibrido", ragionamento=True)
        testo, avvisi, _ = self.chiedi(j, "Che tempo fa a Cagliari?")
        self.assertEqual(testo, "Controllo.\nA Cagliari fa bello, signore.")
        self.assertIn("Controllo il meteo di Cagliari...", avvisi)
        self.assertTrue(avvisi[-1].startswith("Costo di questa risposta"))
        ultima = finti.FintoClaude.richieste[-1]
        self.assertNotIn("web_search", [s["name"] for s in ultima["tools"]])  # non attiva: si fa senza
        self.assertEqual(ultima["messages"][-2]["content"][0], {"type": "thinking", "thinking": "",
                                                                "signature": "firma"})
        self.assertEqual(ultima["messages"][-1]["content"][0]["tool_use_id"], "toolu_1")
        self.assertGreater(json.loads(cervello_claude.FILE_COSTI.read_text())["totale"], 0)

    def test_argomenti_sbagliati_rifiuti_ed_errori(self):
        j = self.jarvis(chiave=True, cervello="claude")
        self.chiedi(j, "argomenti sbagliati: metti un timer")
        risultato = finti.FintoClaude.richieste[-1]["messages"][-1]["content"][0]
        self.assertTrue(risultato["is_error"])
        _, avvisi, _ = self.chiedi(j, "rifiuta questo")
        self.assertIn("Claude ha preferito non rispondere a questa richiesta.", avvisi)
        with self.assertRaisesRegex(cervello.ErroreOllama, "credito"):
            self.chiedi(j, "credito finito?")


if __name__ == "__main__":
    unittest.main()
