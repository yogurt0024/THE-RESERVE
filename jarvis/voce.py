"""La voce di Jarvis: legge ad alta voce le risposte, con un effetto in stile film.

Le voci disponibili sono in VOCI: `py -3.12 prova_voci.py` le fa ascoltare e salva in config.json quella scelta.
Servono numpy, sounddevice e la libreria della voce scelta (vedi requisiti_voce.txt): se mancano, Jarvis
funziona lo stesso, solo senza parlare.
"""

import asyncio
import io
import queue
import re
import threading

import scarica

_PIPER = "rhasspy/piper-voices"
_KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download"

VOCE_PREDEFINITA = "riccardo"
VOCI = {
    "riccardo": {
        "motore": "piper", "cartella": "voce-riccardo",
        "descrizione": "Riccardo: sul PC, privata e veloce, un po' metallica",
        "file": {
            "voce.onnx": scarica.da_huggingface(_PIPER, "it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx"),
            "voce.onnx.json": scarica.da_huggingface(_PIPER, "it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx.json"),
        },
    },
    "nicola": {
        "motore": "kokoro", "nome": "im_nicola", "cartella": "voce-kokoro",
        "descrizione": "Nicola: sul PC, privata, più naturale (scarica circa 340 MB)",
        "file": {
            "kokoro.onnx": [f"{_KOKORO}/model-files-v1.1/kokoro-v1.0.onnx",
                            f"{_KOKORO}/model-files-v1.0/kokoro-v1.0.onnx"],
            "voci.bin": [f"{_KOKORO}/model-files-v1.1/voices-v1.0.bin", f"{_KOKORO}/model-files-v1.0/voices-v1.0.bin"],
        },
    },
    "diego": {
        "motore": "edge", "nome": "it-IT-DiegoNeural",
        "descrizione": "Diego: voce di Microsoft, molto naturale, ma il testo passa da internet",
    },
    "giuseppe": {
        "motore": "edge", "nome": "it-IT-GiuseppeMultilingualNeural",
        "descrizione": "Giuseppe: voce di Microsoft, molto naturale, ma il testo passa da internet",
    },
}
PACCHETTI = {"piper": "piper-tts", "kokoro": "kokoro-onnx", "edge": "edge-tts soundfile"}

# Dove finisce una frase: dopo . ! ? … ; : seguiti da uno spazio, oppure a capo.
_FINE_FRASE = re.compile(r"(?<=[.!?…;:])\s+|\n+")
_PER_LA_VOCE = [
    (re.compile(r"https?://\S+|www\.\S+"), "il link"),
    (re.compile(r"(\d)\s*°\s*C\b"), r"\1 gradi"),
    (re.compile(r"\s*°"), " gradi"),
    (re.compile(r"(\d)\s*%"), r"\1 per cento"),
    (re.compile(r"\bkm/h\b"), "chilometri orari"),
    (re.compile(r"(\d)\s*km\b"), r"\1 chilometri"),
    (re.compile(r"(\d)\s*GB\b"), r"\1 giga"),
    (re.compile(r"(\d)\s*MB\b"), r"\1 mega"),
    (re.compile(r"€\s*(\d[\d.,]*)"), r"\1 euro"),
    (re.compile(r"(\d)\s*€"), r"\1 euro"),
    (re.compile(r"\$\s*(\d[\d.,]*)"), r"\1 dollari"),
    (re.compile(r"(\d)\s*[x×]\s*(\d)"), r"\1 per \2"),
    (re.compile(r"\s*[→⇒]\s*"), ", "),
    (re.compile(r"^\s*-\s+", re.MULTILINE), ""),
    (re.compile(r"[*#_`~|<>\[\]{}]"), " "),
    (re.compile(r"\s+"), " "),
]
_SEGNI_DI_BLOCCO = ("4551", "controllo dell'applicazione", "criterio di controllo", "application control")


class ErroreVoce(Exception):
    pass


def per_la_voce(testo):
    """Riscrive simboli e sigle come si dicono: "22°C" diventa "22 gradi", "50%" diventa "50 per cento"."""
    for schema, sostituto in _PER_LA_VOCE:
        testo = schema.sub(sostituto, testo)
    return testo.strip()


def dividi_frasi(testo):
    return [f.strip() for f in _FINE_FRASE.split(testo) if f.strip()]


def effetto_jarvis(audio, frequenza, intensita=0.6):
    """Il tocco "intelligenza artificiale" dei film: voce più asciutta e luminosa, un leggero riflesso
    metallico e l'eco di una stanza. Con intensità 0 la voce resta com'è."""
    import numpy as np

    x = np.asarray(audio, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if intensita <= 0 or len(x) == 0:
        return x
    # Via i bassi che rimbombano (sotto i 120 Hz circa) e più presenza sulle consonanti.
    finestra = max(1, int(frequenza / 120))
    if len(x) > finestra:
        x = x - np.convolve(x, np.full(finestra, 1 / finestra, dtype=np.float32), mode="same")
    x = x + 0.5 * intensita * np.diff(x, prepend=x[:1])
    # Riflesso metallico (due copie ravvicinate) ed eco della stanza (copie più lontane e più deboli).
    ritardi = [(6, 0.30), (11, 0.20), (31, 0.16), (47, 0.11), (67, 0.08), (97, 0.05)]
    coda = int(frequenza * 0.25)
    uscita = np.zeros(len(x) + coda, dtype=np.float32)
    uscita[:len(x)] += x
    for millisecondi, volume in ritardi:
        inizio = int(frequenza * millisecondi / 1000)
        uscita[inizio:inizio + len(x)] += volume * intensita * x
    picco = float(np.max(np.abs(uscita)))
    return uscita * (0.89 / picco) if picco > 0 else uscita


def carica_motore(nome, velocita=1.0, avanzamento=None):
    """Prepara una voce di VOCI: la scarica la prima volta, poi la carica. Può richiedere qualche secondo."""
    info = VOCI.get(nome)
    if info is None:
        raise ErroreVoce(f'non conosco la voce "{nome}": quelle disponibili sono {", ".join(VOCI)}')
    cartella = scarica.CARTELLA_MODELLI / info.get("cartella", nome)
    try:
        for file, indirizzi in info.get("file", {}).items():
            scarica.scarica(indirizzi, cartella / file, avanzamento)
        return _MOTORI[info["motore"]](cartella, info, velocita)
    except scarica.ErroreDownload as e:
        raise ErroreVoce(str(e)) from None
    except ImportError as e:
        raise ErroreVoce(spiega_errore_di_libreria(e, PACCHETTI[info["motore"]])) from None
    except ErroreVoce:
        raise
    except Exception as e:  # onnxruntime e le librerie della voce hanno i loro tipi di errore
        if any(segno in str(e).lower() for segno in _SEGNI_DI_BLOCCO):
            raise ErroreVoce(spiega_errore_di_libreria(e, PACCHETTI[info["motore"]])) from None
        raise ErroreVoce(f"la voce {nome} non si carica: {e}") from None


def spiega_errore_di_libreria(errore, pacchetto):
    if any(segno in str(errore).lower() for segno in _SEGNI_DI_BLOCCO):
        return (f"Windows (Controllo intelligente delle app) blocca la libreria {pacchetto.split()[0]}: "
                "scegli un'altra voce con prova_voci.py")
    return f"manca la libreria {pacchetto.split()[0]}: installala con  py -3.12 -m pip install {pacchetto}"


class _Piper:
    def __init__(self, cartella, info, velocita):
        from piper import PiperVoice, SynthesisConfig

        self._voce = PiperVoice.load(str(cartella / "voce.onnx"))
        self._impostazioni = SynthesisConfig(length_scale=1 / velocita)
        self.sintetizza("Pronto.")  # la prima frase è più lenta; e così un eventuale blocco di Windows si vede subito

    def sintetizza(self, testo):
        import numpy as np

        pezzi = list(self._voce.synthesize(testo, syn_config=self._impostazioni))
        if not pezzi:
            return np.zeros(0, dtype=np.float32), self._voce.config.sample_rate
        return np.concatenate([p.audio_float_array for p in pezzi]), pezzi[0].sample_rate


class _Kokoro:
    def __init__(self, cartella, info, velocita):
        from kokoro_onnx import Kokoro

        self._kokoro = Kokoro(str(cartella / "kokoro.onnx"), str(cartella / "voci.bin"))
        self._nome, self._velocita = info["nome"], velocita
        self.sintetizza("Pronto.")

    def sintetizza(self, testo):
        return self._kokoro.create(testo, voice=self._nome, speed=self._velocita, lang="it")


class _Edge:
    def __init__(self, cartella, info, velocita):
        import edge_tts  # noqa: F401  (controlla subito che le librerie ci siano)
        import soundfile  # noqa: F401

        self._nome = info["nome"]
        self._velocita = f"{round((velocita - 1) * 100):+d}%"

    def sintetizza(self, testo):
        import edge_tts
        import soundfile

        async def scarica_audio():
            dati = bytearray()
            async for parte in edge_tts.Communicate(testo, self._nome, rate=self._velocita).stream():
                if parte["type"] == "audio":
                    dati += parte["data"]
            return bytes(dati)

        try:
            mp3 = asyncio.run(scarica_audio())
        except Exception as e:  # edge-tts e aiohttp hanno molti tipi di errore di rete
            raise ErroreVoce(f"la voce di Microsoft non risponde (serve internet): {e}") from None
        return soundfile.read(io.BytesIO(mp3), dtype="float32")


_MOTORI = {"piper": _Piper, "kokoro": _Kokoro, "edge": _Edge}


def _riproduci_con_sounddevice(audio, frequenza, interrompi):
    import sounddevice

    sounddevice.play(audio, frequenza)
    while sounddevice.get_stream().active:
        if interrompi.wait(0.05):
            sounddevice.stop()
            return


class Voce:
    """Legge il testo ad alta voce in background: le frasi si mettono in fila e si possono interrompere.

    Mentre arriva una risposta: inizia(), poi aggiungi() per ogni pezzo e finisci(). Per un avviso: di().
    `al_cambio(parlando)` viene chiamata (da un altro thread) quando Jarvis comincia o smette di parlare.
    """

    def __init__(self, config, avvisa=None, al_cambio=None, riproduci=None):
        self.config = config
        self.avvisa = avvisa or (lambda messaggio: None)
        self.al_cambio = al_cambio
        self._riproduci = riproduci or _riproduci_con_sounddevice
        self._motore = None
        self._nome_motore = None
        self._fallita = None  # la voce che non si è riusciti a caricare
        self.errore = ""
        self._errori_segnalati = set()
        self._carica_lucchetto = threading.Lock()
        self._lucchetto = threading.Lock()
        self._da_dire = queue.Queue()
        self._da_suonare = queue.Queue()
        self._generazione = 0  # cresce a ogni zitto(): le frasi delle generazioni vecchie si buttano
        self._in_fila = 0  # frasi messe in fila e non ancora finite di dire
        self._interrompi = threading.Event()
        self._risposta = ""  # l'ultimo pezzo della risposta, che può essere una frase a metà
        self._detti = 0
        self._troncata = False
        self._zittita = False
        threading.Thread(target=self._sintetizza, daemon=True).start()
        threading.Thread(target=self._suona, daemon=True).start()

    @property
    def nome(self):
        return self.config.get("voce") or VOCE_PREDEFINITA

    @property
    def sta_parlando(self):
        return self._in_fila > 0

    def prepara(self, avanzamento=None, riprova=True):
        """Scarica (la prima volta) e carica la voce. Restituisce l'errore, oppure "" se è pronta.

        Se la voce non si è caricata, ci riprova solo con `riprova` (per esempio quando la si riaccende).
        """
        with self._carica_lucchetto:
            nome = self.nome
            if self._motore is not None and self._nome_motore == nome:
                return ""
            if not riprova and self._fallita == nome:
                return self.errore
            try:
                self._motore = carica_motore(nome, float(self.config.get("velocita_voce", 1.0)), avanzamento)
                self._nome_motore, self._fallita, self.errore = nome, None, ""
            except ErroreVoce as e:
                self._motore, self._fallita, self.errore = None, nome, str(e)
                self._errori_segnalati.discard(self.errore)  # chi riprova deve sapere com'è andata
                self._segnala(self.errore)
            return self.errore

    # --- Cosa dire ---

    def di(self, testo, limite=0):
        """Dice un testo intero, per esempio un avviso. Se supera `limite` caratteri, ne dice solo l'inizio."""
        detti = 0
        for frase in dividi_frasi(testo):
            if limite and detti and detti + len(frase) > limite:
                self._metti_in_fila(self._frase_del_resto())
                break
            detti += len(frase)
            self._metti_in_fila(frase)

    def inizia(self):
        """Comincia una nuova risposta (quella di prima, se c'era, continua finché non finisce)."""
        self._risposta, self._detti, self._troncata, self._zittita = "", 0, False, False

    def aggiungi(self, pezzo):
        if self._troncata or self._zittita:
            return
        self._risposta += pezzo
        frasi = _FINE_FRASE.split(self._risposta)
        self._risposta = frasi.pop()  # l'ultima può essere ancora a metà
        for frase in frasi:
            self._frase_della_risposta(frase)

    def finisci(self):
        if self._zittita:
            return
        self._frase_della_risposta(self._risposta)
        self._risposta = ""
        if self._troncata:
            self._metti_in_fila(self._frase_del_resto())
            self._troncata = False

    def zitto(self):
        """Smette subito di parlare e butta le frasi in fila."""
        with self._lucchetto:
            self._generazione += 1
            self._interrompi.set()
            self._zittita = True
        for coda in (self._da_dire, self._da_suonare):
            while True:
                try:
                    coda.get_nowait()
                except queue.Empty:
                    break
                self._fatta()

    def _frase_della_risposta(self, frase):
        frase = frase.strip()
        if not frase or self._troncata:
            return
        # Le risposte lunghe restano nella finestra: a voce se ne dice l'inizio.
        if self._detti and self._detti + len(frase) > int(self.config.get("limite_voce", 400)):
            self._troncata = True
            return
        self._detti += len(frase)
        self._metti_in_fila(frase)

    def _frase_del_resto(self):
        titolo = self.config.get("come_chiamarmi", "")
        t = f", {titolo}" if titolo else ""
        return f"Il resto lo {'trovi' if self.config.get('dai_del') == 'tu' else 'trova'} nella finestra{t}."

    def _metti_in_fila(self, frase):
        testo = per_la_voce(frase)
        if not re.search(r"\w", testo):
            return
        with self._lucchetto:
            self._in_fila += 1
            inizia_a_parlare = self._in_fila == 1
            self._da_dire.put((self._generazione, testo))
        if inizia_a_parlare and self.al_cambio:
            self.al_cambio(True)

    def _fatta(self):
        with self._lucchetto:
            self._in_fila = max(0, self._in_fila - 1)
            finito = self._in_fila == 0
        if finito and self.al_cambio:
            self.al_cambio(False)

    def _segnala(self, errore):
        if errore not in self._errori_segnalati:
            self._errori_segnalati.add(errore)
            self.avvisa(f"La voce non funziona: {errore}")

    # --- I due thread: uno prepara l'audio della frase dopo mentre l'altro dice quella di adesso ---

    def _sintetizza(self):
        while True:
            generazione, testo = self._da_dire.get()
            audio = frequenza = None
            if generazione == self._generazione:
                if not self.prepara(riprova=False):  # se la voce non si carica, l'ha già detto prepara()
                    try:
                        audio, frequenza = self._motore.sintetizza(testo)
                        audio = effetto_jarvis(audio, frequenza, float(self.config.get("effetto_voce", 0.6)))
                    except Exception as e:  # una frase che non si riesce a dire non deve fermare le altre
                        audio = None
                        self._segnala(f"non sono riuscito a dire una frase ({e})")
            if audio is None or generazione != self._generazione:
                self._fatta()
            else:
                self._da_suonare.put((generazione, audio, frequenza))

    def _suona(self):
        while True:
            generazione, audio, frequenza = self._da_suonare.get()
            if generazione == self._generazione:
                self._interrompi.clear()
                if generazione == self._generazione:  # zitto() potrebbe essere arrivato proprio adesso
                    try:
                        self._riproduci(audio, frequenza, self._interrompi)
                    except Exception as e:
                        self._segnala(f"non riesco a usare gli altoparlanti ({e})")
            self._fatta()
