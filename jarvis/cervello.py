"""Il cervello di Jarvis: parla con Ollama, ricorda le cose e usa gli strumenti.

Lo usano sia la finestra grafica (finestra.py) sia la modalità testo (jarvis.py).
"""

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import strumenti
from strumenti import ErroreStrumento

CARTELLA = Path(__file__).resolve().parent
FILE_CONFIG = CARTELLA / "config.json"
FILE_MEMORIA = CARTELLA / "dati" / "memoria.json"
FILE_CONVERSAZIONE = CARTELLA / "dati" / "conversazione.json"

CONFIG_PREDEFINITA = {
    "nome": "Jarvis",
    "come_chiamarmi": "",
    "citta": "",
    "modello": "qwen3:4b",
    "ragionamento": False,
    "internet": True,
    "messaggi_da_ricordare": 20,
    "ollama_url": "http://localhost:11434",
    "programmi": {
        "blocco note": "notepad",
        "calcolatrice": "calc",
        "paint": "mspaint",
        "esplora file": "explorer",
        "impostazioni": "ms-settings:",
    },
}

CONTESTO = 8192  # quanti token di conversazione il modello riesce a leggere in una volta
GIRI_STRUMENTI = 4  # quante volte di fila il modello può usare strumenti per una sola risposta
SEPARATORE_DATI = "\n\n--- Dati aggiornati ---\n"

AIUTO = """Comandi:
/meteo [città] — meteo e previsioni
/wiki <argomento> — cerca su Wikipedia
/notizie [argomento] — ultime notizie
/cerca <testo> — apre una ricerca Google nel browser
/apri <programma o sito> — per esempio /apri blocco note oppure /apri youtube.com
/calcola <conto> — per esempio /calcola (12+3)*2
/timer <minuti> [messaggio] — per esempio /timer 10 pasta
/ricorda <cosa> — salva un'informazione nella memoria permanente
/memoria — mostra cosa ricordo
/dimentica <numero> — cancella un ricordo (/dimentica tutto li cancella tutti)
/pensa — attiva o disattiva il ragionamento profondo
/nuova — nuova conversazione
/esci — chiude
Puoi anche chiedere normalmente, per esempio "che tempo fa a Cagliari?" o "ricordati che...\""""

# Ollama gira sullo stesso PC: niente proxy di sistema in mezzo.
_connessione = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ErroreOllama(Exception):
    pass


class _Interrotto(Exception):
    pass


def carica_config():
    config = dict(CONFIG_PREDEFINITA)
    if FILE_CONFIG.exists():
        try:
            # utf-8-sig: il Blocco note di Windows a volte salva con il BOM.
            config.update(json.loads(FILE_CONFIG.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError as e:
            raise SystemExit(f"config.json non è valido (riga {e.lineno}): {e.msg}")
    return config


def _leggi_json(file):
    try:
        dati = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dati if isinstance(dati, dict) else {}


def _scrivi_json(file, dati):
    file.parent.mkdir(exist_ok=True)
    file.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")


class PulitoreMarkdown:
    """Toglie la formattazione Markdown dal testo che arriva a pezzi dal modello.

    Restituisce coppie (testo, grassetto): titoli e **parole** diventano grassetto
    e gli elenchi puntati iniziano con "• ". Un "*" isolato tra numeri resta (2 * 3).
    """

    def __init__(self):
        self.inizio_riga = True
        self.prefisso = ""  # simboli a inizio riga non ancora decifrati (#, *, -, spazi)
        self.asterischi = 0  # asterischi in sospeso: * o ** si capisce dal carattere dopo
        self.precedente = ""
        self.grassetto = False
        self.titolo = False
        self.vuoto = True  # niente spazi o righe vuote prima del testo vero
        self.uscita = []

    def aggiungi(self, testo):
        for c in testo:
            self._carattere(c)
        return self._svuota()

    def a_capo(self):
        """Fa ripartire il testo da una riga nuova, per esempio dopo l'uso di uno strumento."""
        self.prefisso = ""
        if not self.inizio_riga:
            self._nuova_riga()
        self.vuoto = True
        return self._svuota()

    def fine(self):
        self._asterischi_prima_di("")
        self.prefisso = ""
        return self._svuota()

    def _carattere(self, c):
        if self.inizio_riga:
            if c in " \t#*-+>":
                self.prefisso += c
                return
            prefisso, self.prefisso = self.prefisso, ""
            if c == "\n":
                self._nuova_riga()  # riga vuota o di soli simboli (---, ***): resta vuota
                return
            self.inizio_riga = False
            self._apri_riga(prefisso)
        if c == "\n":
            self._nuova_riga()
        elif c == "*":
            self.asterischi += 1
        else:
            self._asterischi_prima_di(c)
            self._scrivi(c)

    def _apri_riga(self, prefisso):
        resto = prefisso.lstrip()
        rientro = prefisso[: len(prefisso) - len(resto)]
        simbolo = re.match(r"(#+|>|[*+-](?=\s))\s*", resto)
        if simbolo:
            resto = resto[simbolo.end():]
            if simbolo.group(1).startswith("#"):
                self.titolo = True
            elif simbolo.group(1) != ">":
                self._scrivi(rientro + "• ")
        else:
            self._scrivi(rientro)
        for c in resto:
            if c == "*":
                self.asterischi += 1
            else:
                self._asterischi_prima_di(c)
                self._scrivi(c)

    def _asterischi_prima_di(self, successivo):
        n, self.asterischi = self.asterischi, 0
        if (n // 2) % 2:
            self.grassetto = not self.grassetto
        # Un asterisco attaccato a una parola è corsivo (*così*): si toglie.
        if n % 2 and not (self.precedente.isalpha() or successivo.isalpha()):
            self._scrivi("*")

    def _nuova_riga(self):
        self._asterischi_prima_di("\n")
        self.grassetto = self.titolo = False
        self._scrivi("\n")
        self.inizio_riga = True

    def _scrivi(self, testo):
        if not testo or (self.vuoto and not testo.strip()):
            return
        self.vuoto = False
        self.uscita.append((testo, self.grassetto or self.titolo))
        self.precedente = testo[-1]

    def _svuota(self):
        uniti = []
        for testo, grassetto in self.uscita:
            if uniti and uniti[-1][1] == grassetto:
                uniti[-1] = (uniti[-1][0] + testo, grassetto)
            else:
                uniti.append((testo, grassetto))
        self.uscita = []
        return uniti


class Assistente:
    """Tiene la conversazione e la memoria e produce le risposte come eventi:

    ("testo", pezzo, grassetto)  un pezzo della risposta
    ("info", messaggio)          un avviso (strumento in uso, esito di un comando)
    ("pensiero",)                il modello sta ragionando
    ("pulisci",)                 la conversazione è stata cancellata
    """

    def __init__(self, config, avvisa=print):
        self.config = config
        self.nome = config["nome"]
        self.modello = config["modello"]
        self.avvisa = avvisa  # chiamata dai timer, da un altro thread
        self.ragionamento = bool(config["ragionamento"])
        self.limite = max(2, int(config["messaggi_da_ricordare"]))
        self.supporta_strumenti = False
        self.supporta_ragionamento = False
        self.fatti = _leggi_json(FILE_MEMORIA).get("fatti", [])
        self.cronologia = _leggi_json(FILE_CONVERSAZIONE).get("messaggi", [])[-self.limite:]
        self._ricorda_frase = re.compile(
            rf"^(?:{re.escape(self.nome)}[,:!]?\s+)?ricorda(?:ti)?\s+(?:che\s+)?(.+)", re.IGNORECASE
        )

    # --- Ollama ---

    def _richiesta(self, percorso, dati=None, timeout=300):
        url = self.config["ollama_url"].rstrip("/") + percorso
        corpo = None if dati is None else json.dumps(dati).encode("utf-8")
        req = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/json"})
        try:
            return _connessione.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            try:
                messaggio = json.loads(e.read()).get("error", "")
            except ValueError:
                messaggio = ""
            raise ErroreOllama(messaggio or f"Ollama ha risposto con l'errore {e.code}.") from None
        except OSError:
            raise ErroreOllama(
                "Non riesco a contattare Ollama. Controlla che sia installato e avviato "
                "(l'icona del lama vicino all'orologio di Windows)."
            ) from None

    def _carica(self, tieni_in_memoria=None, timeout=300):
        """Senza messaggi, Ollama si limita a caricare il modello (o a scaricarlo con keep_alive 0)."""
        dati = {"model": self.modello, "messages": [], "stream": False, "options": {"num_ctx": CONTESTO}}
        if tieni_in_memoria is not None:
            dati["keep_alive"] = tieni_in_memoria
        self._richiesta("/api/chat", dati, timeout).close()

    def avvia(self):
        with self._richiesta("/api/tags", timeout=5) as risposta:
            installati = {m["name"] for m in json.load(risposta).get("models", [])}
        if self.modello not in installati and f"{self.modello}:latest" not in installati:
            raise ErroreOllama(
                f'Il modello "{self.modello}" non è installato. '
                f"Apri il Prompt dei comandi e scrivi:\n    ollama pull {self.modello}"
            )
        with self._richiesta("/api/show", {"model": self.modello}, timeout=30) as risposta:
            capacita = set(json.load(risposta).get("capabilities") or [])
        self.supporta_strumenti = "tools" in capacita
        self.supporta_ragionamento = "thinking" in capacita
        self._carica()

    def chiudi(self):
        try:
            # Libera la memoria della scheda video, così resta tutta per i giochi.
            self._carica(tieni_in_memoria=0, timeout=5)
        except ErroreOllama:
            pass

    def stato(self):
        righe = [f"{self.nome} è pronto (modello {self.modello})."]
        if self.supporta_strumenti:
            righe.append("Uso gli strumenti da solo: meteo, Wikipedia, notizie, siti, programmi, calcoli e timer.")
        else:
            righe.append(
                "Questo modello non sa usare gli strumenti da solo: usa i comandi (/aiuto), "
                "oppure installa qwen3:4b."
            )
        if self.supporta_ragionamento:
            righe.append(f"Ragionamento profondo: {'attivo' if self.ragionamento else 'spento'} (/pensa per cambiarlo).")
        if self.fatti:
            quante = "1 cosa" if len(self.fatti) == 1 else f"{len(self.fatti)} cose"
            righe.append(f"Ho {quante} in memoria (/memoria per vederle).")
        if self.cronologia:
            righe.append("Riprendo la conversazione di prima (/nuova per ricominciare).")
        return "\n".join(righe)

    # --- Memoria ---

    def _ricorda(self, fatto):
        fatto = fatto.strip().rstrip(".!")
        fatto = fatto[:1].upper() + fatto[1:]
        if fatto.casefold() not in (f.casefold() for f in self.fatti):
            self.fatti.append(fatto)
            _scrivi_json(FILE_MEMORIA, {"fatti": self.fatti})
        return fatto

    def _salva_conversazione(self):
        _scrivi_json(FILE_CONVERSAZIONE, {"messaggi": self.cronologia})

    def _prompt_di_sistema(self):
        adesso = datetime.now()
        righe = [
            f"Sei {self.nome}, l'assistente personale dell'utente, ispirato al J.A.R.V.I.S. di Iron Man: "
            "cortese, preciso e con un pizzico di ironia.",
            "Rispondi sempre in italiano, in modo chiaro e conciso, a meno che non ti venga chiesto di approfondire.",
            'Scrivi testo semplice, senza tabelle, titoli o asterischi; per gli elenchi inizia le righe con "- ".',
            "Se non conosci una risposta o non sei sicuro, dillo invece di inventare.",
            f"Oggi è {strumenti.data_italiana(adesso)} e sono le {adesso:%H:%M}.",
        ]
        if self.config["come_chiamarmi"]:
            righe.append(f'Chiama l\'utente "{self.config["come_chiamarmi"]}".')
        if self.config["citta"]:
            righe.append(f"L'utente vive a {self.config['citta']}: se chiede il meteo senza dire dove, intende lì.")
        righe += [
            "",
            "Come funzioni (usalo se l'utente ti chiede cosa sai fare o quali sono i tuoi limiti):",
            f"- Sei un programma che gira interamente sul PC dell'utente, con il modello {self.modello} tramite Ollama.",
            "- Hai una memoria permanente: ricordi le cose che l'utente ti chiede di ricordare "
            "e gli ultimi messaggi, anche dopo essere stato chiuso.",
        ]
        if self.supporta_strumenti:
            righe.append(
                "- Hai degli strumenti: "
                + ("meteo, Wikipedia, notizie, " if self.config["internet"] else "")
                + "aprire siti, aprire ricerche nel browser, aprire programmi, calcoli esatti e timer. "
                "Usali quando servono, invece di inventare dati aggiornati o fare conti a mente."
            )
        else:
            righe.append(
                "- Non puoi usare strumenti da solo: per meteo, Wikipedia, notizie, calcoli, timer "
                "e per aprire programmi l'utente può usare i comandi elencati da /aiuto."
            )
        if not self.config["internet"]:
            righe.append("- Non sei collegato a internet.")
        righe += [
            "- Non puoi vedere lo schermo, sentire la voce dell'utente, né leggere o modificare file.",
            "- Le tue conoscenze generali si fermano al tuo addestramento: per i fatti recenti servono gli strumenti.",
        ]
        if self.fatti:
            righe += ["", "Cose che l'utente ti ha chiesto di ricordare (scritte in prima persona dall'utente):"]
            righe += [f"- {f}" for f in self.fatti]
        return "\n".join(righe)

    # --- Conversazione ---

    def gestisci(self, testo, stop=None):
        """Risponde a un messaggio dell'utente (domanda o /comando). `stop` è un threading.Event."""
        testo = testo.strip()
        if testo.startswith("/"):
            domanda = yield from self._comando(testo)
            if domanda is None:
                return
            # Il comando ha già scaricato i dati: niente strumenti, o il modello li riscaricherebbe.
            yield from self._chiedi(domanda, stop, con_strumenti=False)
            return
        ricordo = self._ricorda_frase.match(testo)
        if ricordo and not testo.endswith("?"):
            yield ("info", f"Memorizzato: {self._ricorda(ricordo.group(1))}")
        yield from self._chiedi(testo, stop)

    def _comando(self, testo):
        """Esegue un /comando. Restituisce la domanda da passare al modello, se serve."""
        nome, _, argomento = testo[1:].partition(" ")
        nome, argomento = nome.lower(), argomento.strip()
        try:
            if nome == "aiuto":
                yield ("info", AIUTO)
            elif nome == "nuova":
                self.cronologia.clear()
                self._salva_conversazione()
                yield ("pulisci",)
                yield ("info", "Conversazione dimenticata: ricominciamo. La memoria permanente resta.")
            elif nome == "ricorda":
                if not argomento:
                    yield ("info", "Scrivi cosa ricordare, per esempio: /ricorda il mio gioco preferito è Minecraft")
                else:
                    yield ("info", f"Memorizzato: {self._ricorda(argomento)}")
            elif nome == "memoria":
                if self.fatti:
                    elenco = "\n".join(f"{i}. {f}" for i, f in enumerate(self.fatti, 1))
                    yield ("info", f"Ecco cosa ricordo:\n{elenco}")
                else:
                    yield ("info", 'La memoria è vuota. Dimmi "ricordati che..." oppure usa /ricorda.')
            elif nome == "dimentica":
                yield ("info", self._dimentica(argomento))
            elif nome == "pensa":
                if self.supporta_ragionamento:
                    self.ragionamento = not self.ragionamento
                    stato = "attivo: risposte più accurate ma più lente" if self.ragionamento else "spento"
                    yield ("info", f"Ragionamento profondo {stato}.")
                else:
                    yield ("info", f"Il modello {self.modello} non supporta il ragionamento profondo.")
            elif nome in ("meteo", "wiki", "notizie"):
                return (yield from self._comando_internet(nome, argomento))
            elif nome == "apri":
                sito = re.match(r"(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", argomento)
                if sito:
                    yield ("info", strumenti.apri_sito(argomento))
                else:
                    yield ("info", strumenti.apri_programma(argomento, self.config["programmi"]))
            elif nome == "cerca":
                yield ("info", strumenti.cerca_sul_web(argomento))
            elif nome == "calcola":
                yield ("info", strumenti.calcola(argomento))
            elif nome == "timer":
                minuti, _, messaggio = argomento.partition(" ")
                yield ("info", strumenti.timer(minuti, messaggio, self.avvisa))
            else:
                yield ("info", f"Comando sconosciuto: /{nome}. Scrivi /aiuto per l'elenco.")
        except ErroreStrumento as e:
            yield ("info", f"Non ci sono riuscito: {e}")
        return None

    def _comando_internet(self, nome, argomento):
        if not self.config["internet"]:
            yield ("info", 'Internet è disattivato: in config.json metti "internet": true.')
            return None
        if nome == "meteo":
            citta = argomento or self.config["citta"]
            if not citta:
                yield ("info", 'Di quale città? Per esempio /meteo Cagliari (o scrivi la tua città in config.json).')
                return None
            yield ("info", strumenti.descrivi("meteo", {"citta": citta}))
            return f"Che tempo fa a {citta}?{SEPARATORE_DATI}{strumenti.meteo(citta)}"
        if nome == "wiki":
            if not argomento:
                yield ("info", "Cosa cerco? Per esempio /wiki Leonardo da Vinci")
                return None
            yield ("info", strumenti.descrivi("wikipedia", {"argomento": argomento}))
            return f"Parlami di {argomento}.{SEPARATORE_DATI}{strumenti.wikipedia(argomento)}"
        yield ("info", strumenti.descrivi("notizie", {"argomento": argomento}))
        domanda = f"Quali sono le ultime notizie su {argomento}?" if argomento else "Quali sono le ultime notizie?"
        return f"{domanda}{SEPARATORE_DATI}{strumenti.notizie(argomento)}"

    def _dimentica(self, argomento):
        if argomento.lower() == "tutto":
            self.fatti.clear()
            _scrivi_json(FILE_MEMORIA, {"fatti": self.fatti})
            return "Ho cancellato tutta la memoria."
        if argomento.isdigit() and 1 <= int(argomento) <= len(self.fatti):
            fatto = self.fatti.pop(int(argomento) - 1)
            _scrivi_json(FILE_MEMORIA, {"fatti": self.fatti})
            return f"Ho dimenticato: {fatto}"
        return "Scrivi il numero del ricordo da cancellare (lo vedi con /memoria), oppure /dimentica tutto."

    def _chiedi(self, domanda, stop, con_strumenti=True):
        self.cronologia.append({"role": "user", "content": domanda})
        messaggi = [{"role": "system", "content": self._prompt_di_sistema()}] + self.cronologia
        pulitore = PulitoreMarkdown()
        risposta = []  # testo pulito, per la cronologia
        interrotto = False
        try:
            for giro in range(GIRI_STRUMENTI + 1):
                dati = {"model": self.modello, "messages": messaggi, "stream": True,
                        "options": {"num_ctx": CONTESTO}}
                if self.supporta_ragionamento:
                    dati["think"] = self.ragionamento
                if con_strumenti and self.supporta_strumenti and giro < GIRI_STRUMENTI:
                    dati["tools"] = strumenti.schemi(self.config)
                contenuto, chiamate = yield from self._flusso(dati, pulitore, risposta, stop)
                if not chiamate:
                    break
                yield from self._emetti(pulitore.a_capo(), risposta)
                messaggi.append({"role": "assistant", "content": contenuto, "tool_calls": chiamate})
                for chiamata in chiamate:
                    funzione = chiamata.get("function", {})
                    nome, argomenti = funzione.get("name", ""), funzione.get("arguments") or {}
                    if isinstance(argomenti, str):
                        try:
                            argomenti = json.loads(argomenti)
                        except ValueError:
                            argomenti = {}
                    if not isinstance(argomenti, dict):
                        argomenti = {}
                    yield ("info", strumenti.descrivi(nome, argomenti))
                    risultato = strumenti.esegui(nome, argomenti, self.config, self.avvisa)
                    messaggi.append({"role": "tool", "content": risultato, "tool_name": nome})
            yield from self._emetti(pulitore.fine(), risposta)
        except (KeyboardInterrupt, _Interrotto):
            interrotto = True
            yield ("info", "Risposta interrotta.")
        finally:
            testo = "".join(risposta).strip()
            if testo:
                self.cronologia.append({"role": "assistant", "content": testo + (" [interrotta]" if interrotto else "")})
            else:
                self.cronologia.pop()
            del self.cronologia[:-self.limite]
            self._salva_conversazione()

    def _flusso(self, dati, pulitore, risposta, stop):
        """Legge la risposta di Ollama mentre arriva. Restituisce (testo, strumenti chiesti)."""
        contenuto, chiamate = [], []
        pensiero_segnalato = False
        try:
            with self._richiesta("/api/chat", dati) as flusso:
                for riga in flusso:
                    if stop is not None and stop.is_set():
                        raise _Interrotto
                    if not riga.strip():
                        continue
                    parte = json.loads(riga)
                    if "error" in parte:
                        raise ErroreOllama(parte["error"])
                    messaggio = parte.get("message", {})
                    if messaggio.get("thinking") and not pensiero_segnalato:
                        pensiero_segnalato = True
                        yield ("pensiero",)
                    chiamate.extend(messaggio.get("tool_calls") or [])
                    if messaggio.get("content"):
                        contenuto.append(messaggio["content"])
                        yield from self._emetti(pulitore.aggiungi(messaggio["content"]), risposta)
                    if parte.get("done"):
                        break
        except OSError:
            raise ErroreOllama("La connessione con Ollama si è interrotta.") from None
        return "".join(contenuto), chiamate

    @staticmethod
    def _emetti(segmenti, risposta):
        for testo, grassetto in segmenti:
            risposta.append(testo)
            yield ("testo", testo, grassetto)
