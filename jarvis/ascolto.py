"""L'orecchio di Jarvis: ascolta sempre il microfono e capisce quando qualcuno gli parla.

1. Silero VAD riconosce quando c'è una voce: silenzio e rumori vengono ignorati.
2. Il modello di trascrizione (Parakeet o Whisper, con onnx-asr) scrive la frase, tutto sul PC.
3. Se la frase comincia o finisce con "Jarvis", è un comando.
L'audio non viene mai salvato né inviato a nessuno.
"""

import difflib
import os
import queue
import re
import threading
import time
import unicodedata
from collections import deque

import scarica

FREQUENZA = 16000
BLOCCO = 512  # 32 ms di audio: la misura che vuole Silero VAD
DURATA_BLOCCO = BLOCCO / FREQUENZA

MODELLO_PREDEFINITO = "parakeet"
MODELLI_ASCOLTO = {
    "parakeet": {
        "nome": "nemo-parakeet-tdt-0.6b-v3", "repo": "istupakov/parakeet-tdt-0.6b-v3-onnx", "quantizzazione": "int8",
        "schemi": ["config.json", "vocab.txt", "encoder-model?int8.onnx*", "decoder_joint-model?int8.onnx*"],
        "descrizione": "Parakeet: veloce anche senza scheda video (circa 670 MB)",
    },
    "whisper": {
        "nome": "onnx-community/whisper-large-v3-turbo", "repo": "onnx-community/whisper-large-v3-turbo",
        "quantizzazione": "int8", "lingua": "it",
        "schemi": ["config.json", "vocab.json", "added_tokens.json", "onnx/encoder_model?int8.onnx*",
                   "onnx/decoder_model_merged?int8.onnx*"],
        "descrizione": "Whisper: un po' più preciso con l'italiano, ma più lento (circa 1 GB)",
    },
    "canary": {
        "nome": "nemo-canary-1b-v2", "repo": "istupakov/canary-1b-v2-onnx", "quantizzazione": "int8", "lingua": "it",
        "schemi": ["config.json", "vocab.txt", "encoder-model?int8.onnx*", "decoder-model?int8.onnx*"],
        "descrizione": "Canary: ascolta sempre in italiano, preciso anche con le frasi brevi (circa 1 GB)",
    },
}
RILEVATORE = ("istupakov/silero-vad-onnx", "silero_vad.onnx")

_SALUTI = {"ehi", "hey", "ehy", "ei", "ehm", "ok", "okay", "ciao", "senti", "scusa", "scusami", "allora", "oh", "ah",
           "eh", "e", "buongiorno", "buonasera", "salve", "dai"}
_SALUTI_VERI = {"ciao", "buongiorno", "buonasera", "salve"}
_NOMI = {"jarvis", "giarvis", "jarvi", "giarvi", "jervis", "gervis", "garvis", "jarbis", "giarbis", "jarviss",
         "jarvice", "jarvys", "djarvis", "charvis", "harvis", "yarvis"}
_STOP = {"basta", "stop", "zitto", "stai zitto", "silenzio", "fermati", "ferma", "fermo", "smettila", "taci",
         "basta così", "ok basta", "basta grazie", "grazie basta", "basta così grazie", "lascia stare",
         "lascia perdere", "annulla", "non importa"}
# Frasi che Whisper a volte "sente" nel rumore.
_ALLUCINAZIONI = ("sottotitoli", "amara.org", "grazie per la visione", "iscriviti", "qtss")


class ErroreAscolto(Exception):
    pass


def _semplice(parola):
    parola = unicodedata.normalize("NFD", parola.lower())
    return "".join(c for c in parola if unicodedata.category(c) != "Mn")


def e_jarvis(parola, nome="jarvis"):
    parola = _semplice(parola)
    nome = _semplice(nome)
    if nome == "jarvis" and parola in _NOMI:
        return True
    return difflib.SequenceMatcher(None, parola, nome).ratio() >= 0.8


def estrai_comando(testo, nome="Jarvis"):
    """Se la frase è rivolta a Jarvis, restituisce il comando ("" se c'è solo il nome); altrimenti None.

    "Jarvis, che tempo fa?" → "Che tempo fa?"   "Che ore sono, Jarvis?" → "Che ore sono?"
    """
    parole = list(re.finditer(r"[^\W\d_]+(?:'[^\W\d_]+)?", testo))
    if not parole:
        return None
    for i, parola in enumerate(parole[:3]):
        if e_jarvis(parola.group(), nome):
            if all(_semplice(p.group()) in _SALUTI for p in parole[:i]):
                comando = _pulisci(testo[parola.end():])
                # "Buongiorno Jarvis" è un saluto, da ricambiare; "Ehi Jarvis" invece è solo una chiamata.
                if not comando and any(_semplice(p.group()) in _SALUTI_VERI for p in parole[:i]):
                    return _pulisci(testo[:parola.start()].rstrip(" ,"))
                return comando
            break
    ultima = parole[-1]
    if len(parole) > 1 and e_jarvis(ultima.group(), nome):
        finale = testo[ultima.end():].strip()
        return _pulisci(testo[:ultima.start()].rstrip(" ,;:-") + (finale[:1] if finale[:1] in "?!." else ""))
    return None


def _pulisci(comando):
    comando = comando.strip().lstrip(",.;:!-– ").strip()
    if not re.search(r"\w", comando):
        return ""
    return comando[:1].upper() + comando[1:]


def e_stop(comando):
    """ "basta", "stop", "zitto"...: l'utente vuole che Jarvis smetta di parlare."""
    return " ".join(re.findall(r"\w+", comando.lower())) in _STOP


class Segmentatore:
    """Mette insieme i blocchi di audio in frasi, guardando quanto è probabile che ognuno contenga voce."""

    def __init__(self, soglia=0.5, silenzio_finale=0.7, massimo=15.0, minimo=0.25, anticipo=0.3):
        self.soglia = soglia
        self.blocchi_silenzio = round(silenzio_finale / DURATA_BLOCCO)
        self.blocchi_massimi = round(massimo / DURATA_BLOCCO)
        self.blocchi_minimi = round(minimo / DURATA_BLOCCO)
        self._prima = deque(maxlen=round(anticipo / DURATA_BLOCCO))  # l'audio appena prima che inizi la voce
        self._frase = None
        self._silenzio = self._voce = 0

    @property
    def in_corso(self):
        return self._frase is not None

    def azzera(self):
        self._prima.clear()
        self._frase = None

    def aggiungi(self, blocco, probabilita):
        """Restituisce l'audio di una frase appena finita, oppure None."""
        import numpy as np

        if self._frase is None:
            if probabilita < self.soglia:
                self._prima.append(blocco)
                return None
            self._frase, self._silenzio, self._voce = list(self._prima), 0, 0
            self._prima.clear()
        self._frase.append(blocco)
        if probabilita >= self.soglia:
            self._voce += 1
        if probabilita >= self.soglia - 0.15:
            self._silenzio = 0
        else:
            self._silenzio += 1
        if self._silenzio < self.blocchi_silenzio and len(self._frase) < self.blocchi_massimi:
            return None
        frase, voce = self._frase, self._voce
        self._frase = None
        return np.concatenate(frase) if voce >= self.blocchi_minimi else None


class RilevatoreVoce:
    """Silero VAD, un blocco alla volta: quanto è probabile che sia una voce umana (da 0 a 1)."""

    def __init__(self, percorso):
        import numpy as np
        import onnxruntime

        opzioni = onnxruntime.SessionOptions()
        opzioni.inter_op_num_threads = opzioni.intra_op_num_threads = 1
        self._np = np
        self._sessione = onnxruntime.InferenceSession(str(percorso), opzioni, providers=["CPUExecutionProvider"])
        self._frequenza = np.array([FREQUENZA], dtype=np.int64)
        self.azzera()

    def azzera(self):
        self._stato = self._np.zeros((2, 1, 128), dtype=self._np.float32)
        self._contesto = self._np.zeros(64, dtype=self._np.float32)

    def probabilita(self, blocco):
        ingresso = self._np.concatenate([self._contesto, blocco])[None, :]
        uscita, self._stato = self._sessione.run(
            ["output", "stateN"], {"input": ingresso, "state": self._stato, "sr": self._frequenza})
        self._contesto = blocco[-64:]
        return float(uscita[0, 0])


def carica_rilevatore(avanzamento=None):
    repo, file = RILEVATORE
    return RilevatoreVoce(scarica.scarica(scarica.da_huggingface(repo, file),
                                          scarica.CARTELLA_MODELLI / "ascolto-vad" / file, avanzamento))


def carica_trascrittore(nome=MODELLO_PREDEFINITO, avanzamento=None):
    """Scarica (la prima volta) e carica il modello che trascrive la voce. Restituisce trascrivi(audio) → testo."""
    import numpy as np
    import onnx_asr
    import onnxruntime

    info = MODELLI_ASCOLTO.get(nome)
    if info is None:
        raise ErroreAscolto(f'non conosco il modello di ascolto "{nome}": usa {" oppure ".join(MODELLI_ASCOLTO)}')
    cartella = scarica.CARTELLA_MODELLI / f"ascolto-{nome}"
    completo = cartella / ".completo"
    if not completo.exists():
        for file in scarica.file_su_huggingface(info["repo"], info["schemi"]):
            scarica.scarica(scarica.da_huggingface(info["repo"], file), cartella / file, avanzamento)
        completo.write_text("ok\n", encoding="utf-8")
    opzioni = onnxruntime.SessionOptions()
    opzioni.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)  # metà dei core: il PC resta reattivo
    modello = onnx_asr.load_model(info["nome"], cartella, quantization=info["quantizzazione"], sess_options=opzioni,
                                  providers=["CPUExecutionProvider"])
    lingua = {"language": info["lingua"]} if info.get("lingua") else {}

    def trascrivi(audio):
        return modello.recognize(audio, sample_rate=FREQUENZA, **lingua)

    trascrivi(np.zeros(FREQUENZA // 2, dtype=np.float32))  # la prima volta è più lenta: meglio adesso
    return trascrivi


def ricampiona(audio, frequenza):
    """Porta l'audio a 16000 Hz. Prima toglie le frequenze troppo alte, che altrimenti diventerebbero un fruscio
    sopra la voce e confonderebbero la trascrizione."""
    import numpy as np

    if frequenza == FREQUENZA or len(audio) == 0:
        return audio
    if frequenza > FREQUENZA:
        taglio = 0.45 * FREQUENZA / frequenza  # poco sotto la metà dei 16000 Hz, rispetto alla frequenza di partenza
        n = np.arange(-15, 16)
        filtro = 2 * taglio * np.sinc(2 * taglio * n) * np.hamming(len(n))
        audio = np.convolve(audio, filtro / filtro.sum(), mode="same")
    lunghezza = round(len(audio) * FREQUENZA / frequenza)
    return np.interp(np.linspace(0, len(audio) - 1, lunghezza), np.arange(len(audio)), audio).astype(np.float32)


def normalizza(audio):
    """Porta la voce sempre allo stesso volume: chi parla piano o lontano dal microfono viene capito meglio."""
    import numpy as np

    audio = audio - float(np.mean(audio))
    picco = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if picco < 1e-4:
        return audio.astype(np.float32)
    return (audio * min(20.0, 0.7 / picco)).astype(np.float32)


class Ascolto:
    """Ascolta il microfono in background e chiama `al_comando(testo)` quando qualcuno parla a Jarvis.

    `testo` è "" quando l'utente ha detto solo "Jarvis": allora basta chiamare attendi_comando() e la frase
    successiva sarà un comando anche senza il nome. Le altre frasi arrivano a `al_senza_nome`. `al_stato(testo)` descrive cosa sta facendo l'orecchio.
    `parlando()` dice se Jarvis sta parlando: in quel momento conta solo chi lo chiama per nome, così la sua
    stessa voce, uscendo dalle casse, non diventa un comando. Tutte le funzioni vengono chiamate da altri thread.
    """

    def __init__(self, config, al_comando, al_stato=None, parlando=None, al_sentito=None, al_senza_nome=None,
                 sorgente=None, rilevatore=None, trascrittore=None):
        self.config = config
        self.al_comando = al_comando
        # al_senza_nome(testo, secondi): una frase senza il nome; `secondi` da quando Jarvis ha smesso di parlare
        self.al_senza_nome = al_senza_nome or (lambda testo, secondi: None)
        self.al_stato = al_stato or (lambda testo: None)
        self.al_sentito = al_sentito or (lambda testo: None)  # ogni frase trascritta, anche se non è un comando
        self.parlando = parlando or (lambda: False)
        self._sorgente, self._rilevatore, self._trascrittore = sorgente, rilevatore, trascrittore
        self.errore = ""
        self.pronto = False
        self.in_pausa = False
        self._chiuso = threading.Event()
        self._frasi = queue.Queue()
        self._attesa_da = None  # da quando la prossima frase è un comando anche senza il nome
        self._attesa_secondi = 0
        self._fine_parlato = 0.0  # quando Jarvis ha smesso di parlare l'ultima volta
        self._thread = None

    def avvia(self):
        self._thread = threading.Thread(target=self._lavora, daemon=True)
        self._thread.start()

    def chiudi(self):
        self._chiuso.set()

    def pausa(self, in_pausa):
        self.in_pausa = in_pausa
        self.al_stato("microfono spento" if in_pausa else "in ascolto")

    def attendi_comando(self, secondi=8):
        """La prossima frase, se arriva entro `secondi` da quando Jarvis ha finito di parlare, è un comando."""
        self._attesa_secondi = secondi
        self._attesa_da = time.monotonic()

    # --- Il lavoro in background ---

    def _prepara(self):
        def avanzamento(nome, scaricati, totale):
            self.al_stato(scarica.descrivi_avanzamento(nome, scaricati, totale))

        try:
            if self._rilevatore is None:
                self.al_stato("preparo l'ascolto...")
                self._rilevatore = carica_rilevatore(avanzamento)
            if self._trascrittore is None:
                self._trascrittore = carica_trascrittore(self.config.get("modello_ascolto") or MODELLO_PREDEFINITO,
                                                         avanzamento)
        except ImportError as e:
            raise ErroreAscolto(_spiega_libreria(e)) from None
        except (scarica.ErroreDownload, ErroreAscolto) as e:
            raise ErroreAscolto(str(e)) from None
        except Exception as e:  # onnxruntime e onnx-asr hanno i loro tipi di errore
            raise ErroreAscolto(_spiega_libreria(e) if _bloccato(e) else f"il modello non si carica: {e}") from None

    def _lavora(self):
        try:
            self._prepara()
            blocchi = self._sorgente if self._sorgente is not None else self._dal_microfono()
            threading.Thread(target=self._trascrivi, daemon=True).start()
            self.pronto = True
            self.al_stato("microfono spento" if self.in_pausa else "in ascolto")
            segmentatore = Segmentatore()
            jarvis_parlava = False
            inizio = 0.0
            for blocco in blocchi:
                if self._chiuso.is_set():
                    break
                adesso = time.monotonic()
                parla = self.parlando()
                if parla:
                    self._fine_parlato = adesso
                if self.in_pausa:
                    if segmentatore.in_corso:
                        segmentatore.azzera()
                        self._rilevatore.azzera()
                    continue
                era_in_corso = segmentatore.in_corso
                frase = segmentatore.aggiungi(blocco, self._rilevatore.probabilita(blocco))
                if segmentatore.in_corso and not era_in_corso:
                    inizio, jarvis_parlava = adesso, parla
                    self.al_stato("ti sento...")
                jarvis_parlava = jarvis_parlava or parla
                if era_in_corso and not segmentatore.in_corso:
                    self.al_stato("in ascolto")
                    if frase is not None:
                        self._frasi.put((frase, inizio, jarvis_parlava))
        except ErroreAscolto as e:
            self.errore = str(e)
            self.al_stato(f"ascolto non disponibile: {e}")
        except Exception as e:  # il microfono scollegato, per esempio
            self.errore = f"il microfono ha smesso di funzionare ({e})"
            self.al_stato(f"ascolto non disponibile: {self.errore}")
        finally:
            self.pronto = False
            self._frasi.put(None)

    def _trascrivi(self):
        while True:
            elemento = self._frasi.get()
            if elemento is None or self._chiuso.is_set():
                return
            audio, inizio, jarvis_parlava = elemento
            try:
                testo = (self._trascrittore(normalizza(audio)) or "").strip()
            except Exception as e:  # una frase non trascritta non deve fermare l'ascolto
                self.al_stato(f"non sono riuscito a trascrivere: {e}")
                continue
            self._interpreta(testo, inizio, jarvis_parlava)

    def _interpreta(self, testo, inizio, jarvis_parlava):
        self.al_sentito(testo)
        if not testo or any(a in testo.lower() for a in _ALLUCINAZIONI):
            return
        comando = estrai_comando(testo, self.config.get("nome", "Jarvis"))
        if comando is None:
            if jarvis_parlava:
                return  # mentre parla conta solo chi lo chiama per nome: potrebbe essere la sua voce dalle casse
            if self._attesa_da is not None and inizio >= self._attesa_da:
                aperta = inizio <= max(self._attesa_da, self._fine_parlato) + self._attesa_secondi
                self._attesa_da = None
                if aperta:  # subito dopo il suo "Sì?" o una sua domanda: è la risposta
                    self.al_comando(_pulisci(testo))
                    return
            # Senza il nome: decide chi la riceve se è rivolta a Jarvis (o se l'utente ha bisogno di lui).
            self.al_senza_nome(_pulisci(testo), inizio - self._fine_parlato if self._fine_parlato else None)
            return
        self._attesa_da = None
        self.al_comando(comando)

    def _dal_microfono(self):
        import numpy as np

        try:
            import sounddevice
        except OSError as e:  # sounddevice c'è, ma manca la sua libreria audio
            raise ErroreAscolto(f"non riesco a usare il microfono ({e})") from None

        arrivati = queue.Queue()

        def ricevi(dati, quanti, tempo, stato):
            arrivati.put(dati[:, 0].copy())

        dispositivo = self._microfono(sounddevice)
        try:
            flusso = sounddevice.InputStream(samplerate=FREQUENZA, channels=1, dtype="float32", blocksize=BLOCCO,
                                             device=dispositivo, callback=ricevi)
            frequenza = FREQUENZA
        except sounddevice.PortAudioError:  # alcuni microfoni non accettano 16000 Hz: si converte dopo
            try:
                frequenza = int(sounddevice.query_devices(dispositivo, "input")["default_samplerate"])
                flusso = sounddevice.InputStream(samplerate=frequenza, channels=1, dtype="float32",
                                                 blocksize=round(BLOCCO * frequenza / FREQUENZA),
                                                 device=dispositivo, callback=ricevi)
            except (sounddevice.PortAudioError, ValueError) as e:
                raise ErroreAscolto(f"non riesco ad aprire il microfono ({e}): è collegato?") from None
        resto = np.zeros(0, dtype=np.float32)
        with flusso:
            while not self._chiuso.is_set():
                try:
                    dati = arrivati.get(timeout=0.5)
                except queue.Empty:
                    continue
                resto = np.concatenate([resto, ricampiona(dati, frequenza)])
                while len(resto) >= BLOCCO:
                    yield resto[:BLOCCO]
                    resto = resto[BLOCCO:]

    def _microfono(self, sounddevice):
        nome = (self.config.get("microfono") or "").strip().lower()
        if not nome:
            return None
        for numero, dispositivo in enumerate(sounddevice.query_devices()):
            if dispositivo["max_input_channels"] > 0 and nome in dispositivo["name"].lower():
                return numero
        raise ErroreAscolto(f'non trovo il microfono "{self.config["microfono"]}" (controlla config.json)')


def _bloccato(errore):
    testo = str(errore).lower()
    return any(segno in testo for segno in ("4551", "controllo dell'applicazione", "criterio di controllo",
                                             "application control"))


def _spiega_libreria(errore):
    if _bloccato(errore):
        return "Windows (Controllo intelligente delle app) blocca una libreria dell'ascolto"
    nome = getattr(errore, "name", "") or ""
    pacchetto = {"onnx_asr": "onnx-asr", "sounddevice": "sounddevice", "onnxruntime": "onnxruntime",
                 "numpy": "numpy"}.get(nome.split(".")[0], "")
    if pacchetto:
        return f"manca la libreria {pacchetto}: installa tutto con  py -3.12 -m pip install -r requisiti_voce.txt"
    return f"una libreria non si carica ({errore})"
