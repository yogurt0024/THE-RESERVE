"""La voce di Jarvis: legge ad alta voce le risposte, con un effetto in stile film.

Le voci disponibili sono in VOCI: `py -3.12 prova_voci.py` le fa ascoltare e salva in config.json quella scelta.
Servono numpy, sounddevice e la libreria della voce scelta (vedi requisiti_voce.txt): se mancano, Jarvis
funziona lo stesso, solo senza parlare.
"""

import asyncio
import io
import json
import os
import queue
import re
import threading
import time
import unicodedata
import wave
from pathlib import Path

import scarica
import tokenizzatore
import voce_elevenlabs

_PIPER = "rhasspy/piper-voices"
_KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download"
_CHATTERBOX = "onnx-community/chatterbox-multilingual-ONNX"

VOCE_PREDEFINITA = "riccardo"
VOCI = {
    "elevenlabs": {
        "motore": "elevenlabs",
        "descrizione": "Jarvis su ElevenLabs: la più fluida e naturale, creata apposta per lui (via internet)",
    },
    "espressiva": {
        "motore": "chatterbox", "cartella": "voce-espressiva",
        "descrizione": "Espressiva: recita con emozione, con il timbro di Nicola (Chatterbox, sul PC; scarica "
                       "circa 1,5 GB e ha bisogno di un processore veloce)",
    },
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
PACCHETTI = {"piper": "piper-tts", "kokoro": "kokoro-onnx", "edge": "edge-tts soundfile", "chatterbox": "onnxruntime",
             "elevenlabs": "numpy"}

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


def raggruppa(frasi, minimo):
    """Unisce le frasi in pezzi di almeno `minimo` caratteri (l'ultimo può essere più corto)."""
    pezzi, pezzo = [], ""
    for frase in frasi:
        pezzo = f"{pezzo} {frase}".strip()
        if len(pezzo) >= minimo:
            pezzi.append(pezzo)
            pezzo = ""
    return pezzi + ([pezzo] if pezzo else [])


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


def carica_motore(nome, velocita=1.0, avanzamento=None, config=None):
    """Prepara una voce di VOCI: la scarica la prima volta, poi la carica. Può richiedere qualche secondo."""
    info = VOCI.get(nome)
    if info is None:
        raise ErroreVoce(f'non conosco la voce "{nome}": quelle disponibili sono {", ".join(VOCI)}')
    cartella = scarica.CARTELLA_MODELLI / info.get("cartella", nome)
    motore = _MOTORI[info["motore"]]
    try:
        for file, indirizzi in info.get("file", {}).items():
            scarica.scarica(indirizzi, cartella / file, avanzamento)
        if hasattr(motore, "scarica_file"):
            motore.scarica_file(cartella, avanzamento)
        return motore(cartella, info, velocita, config or {})
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
    def __init__(self, cartella, info, velocita, config):
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
    def __init__(self, cartella, info, velocita, config):
        from kokoro_onnx import Kokoro

        self._kokoro = Kokoro(str(cartella / "kokoro.onnx"), str(cartella / "voci.bin"))
        self._nome, self._velocita = info["nome"], velocita
        self.sintetizza("Pronto.")

    def sintetizza(self, testo):
        return self._kokoro.create(testo, voice=self._nome, speed=self._velocita, lang="it")


class _Edge:
    def __init__(self, cartella, info, velocita, config):
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


INIZIO_PARLATO, FINE_PARLATO = 6561, 6562  # i "segnali" di inizio e fine della voce nel modello di Chatterbox
FREQUENZA_CHATTERBOX = 24000
TESTO_DI_RIFERIMENTO = ("Buongiorno. Ho controllato tutti i sistemi e funziona ogni cosa a dovere. Oggi il cielo è "
                        "sereno, la temperatura è piacevole, e sono pronto ad aiutarla con qualunque cosa le serva.")
# Il modello linguistico di Chatterbox, dal più adatto al processore al più pesante.
_MODELLI_LINGUISTICI = ["language_model_q4.onnx", "language_model_q4f16.onnx", "language_model_quantized.onnx",
                        "language_model.onnx"]


class _Chatterbox:
    """Chatterbox (Resemble AI): un modello che recita, con un controllo dell'emozione da 0 a 1.

    Funziona con onnxruntime, come l'ascolto: niente PyTorch. Imita il timbro di una voce di riferimento,
    che di solito Jarvis registra da solo con la voce di Nicola (o di Riccardo, se Nicola non c'è).
    """

    @staticmethod
    def scarica_file(cartella, avanzamento):
        if (cartella / ".completo").exists():
            return
        schemi = ["tokenizer.json", "default_voice.wav", "onnx/speech_encoder.onnx*", "onnx/embed_tokens.onnx*",
                  "onnx/conditional_decoder.onnx*", "onnx/language_model*.onnx*"]
        tutti = scarica.file_su_huggingface(_CHATTERBOX, schemi)
        modello = next(f"onnx/{m}" for m in _MODELLI_LINGUISTICI if f"onnx/{m}" in tutti)
        for file in tutti:
            if not file.startswith("onnx/language_model") or file.startswith(modello):
                scarica.scarica(scarica.da_huggingface(_CHATTERBOX, file), cartella / file, avanzamento)
        (cartella / ".completo").write_text(modello + "\n", encoding="utf-8")

    def __init__(self, cartella, info, velocita, config):
        import numpy as np
        import onnxruntime

        self._np = np
        self.emozione = float(config.get("emozione_voce", 0.6))
        self.lingua = "it"
        opzioni = onnxruntime.SessionOptions()
        opzioni.intra_op_num_threads = max(1, (os.cpu_count() or 2) - 2)  # lascia un po' di respiro al PC

        def sessione(file):
            return onnxruntime.InferenceSession(str(cartella / "onnx" / file), opzioni,
                                                providers=["CPUExecutionProvider"])

        modello = (cartella / ".completo").read_text(encoding="utf-8").strip().removeprefix("onnx/")
        self._codificatore = sessione("speech_encoder.onnx")
        self._incorpora = sessione("embed_tokens.onnx")
        self._lingua = sessione(modello)
        self._decodificatore = sessione("conditional_decoder.onnx")
        self._ingressi_incorpora = {i.name for i in self._incorpora.get_inputs()}
        self._ingressi_lingua = {i.name for i in self._lingua.get_inputs()}
        self._uscite_lingua = [u.name for u in self._lingua.get_outputs()]
        # La memoria del modello parte vuota: (1, teste, 0, dimensione), in float16 se il modello la vuole così.
        predefinite = (1, 16, 0, 64)
        self._cache_vuota = {
            i.name: np.zeros([d if isinstance(d, int) and n != 2 else predefinite[n] for n, d in enumerate(i.shape)],
                             dtype=np.float16 if "float16" in i.type else np.float32)
            for i in self._lingua.get_inputs() if i.name.startswith("past_key_values")}

        dati = json.loads((cartella / "tokenizer.json").read_text(encoding="utf-8"))
        vocabolario = set(dati["model"].get("vocab", {})) | {t["content"] for t in dati.get("added_tokens", [])}
        if f"[{self.lingua}]" not in vocabolario:
            raise ErroreVoce("questo modello di Chatterbox non conosce l'italiano")
        # Il modello è stato addestrato con gli spazi scritti come [SPACE]: se il file non lo fa da solo, lo si fa qui.
        self._spazio = "[SPACE]" in vocabolario and " " not in vocabolario
        self._codifica = tokenizzatore.carica(cartella / "tokenizer.json")

        riferimento = self._riferimento(cartella, config)
        audio = leggi_wav(riferimento, FREQUENZA_CHATTERBOX)[:FREQUENZA_CHATTERBOX * 10]  # bastano 10 secondi
        uscite = self._codificatore.run(None, {"audio_values": audio[None, :].astype(np.float32)})
        nomi = [u.name for u in self._codificatore.get_outputs()]
        per_nome = dict(zip(nomi, uscite))
        self._condizionamento, self._token_di_riferimento, self._timbro, self._caratteristiche = (
            per_nome.get(nome, uscite[i]) for i, nome in
            enumerate(["audio_features", "audio_tokens", "speaker_embeddings", "speaker_features"]))
        self.sintetizza("Pronto.")

    @staticmethod
    def _riferimento(cartella, config):
        scelto = (config.get("voce_riferimento") or "").strip()
        if scelto:
            if not Path(scelto).is_file():
                raise ErroreVoce(f"non trovo la voce di riferimento {scelto} (controlla config.json)")
            return Path(scelto)
        mio = cartella / "riferimento.wav"
        if mio.exists():
            return mio
        for nome in ("nicola", "riccardo"):  # una voce sintetica, che si può imitare senza chiedere il permesso a nessuno
            try:
                audio, frequenza = carica_motore(nome).sintetizza(TESTO_DI_RIFERIMENTO)
            except ErroreVoce:
                continue
            salva_wav(mio, effetto_jarvis(audio, frequenza, 0), frequenza)
            return mio
        return cartella / "default_voice.wav"

    def _numeri(self, testo):
        testo = unicodedata.normalize("NFKD", _punteggiatura_per_chatterbox(testo).lower())
        testo = f"[{self.lingua}]{testo}"
        if self._spazio:
            testo = testo.replace(" ", "[SPACE]")
        return self._codifica(testo)

    def sintetizza(self, testo):
        np = self._np
        ids = np.array([self._numeri(testo)], dtype=np.int64)
        posizioni = np.where(ids >= INIZIO_PARLATO, 0, np.arange(ids.shape[1])[None, :] - 1).astype(np.int64)
        incorporati = np.concatenate([self._condizionamento, self._incorpora_token(ids, posizioni)], axis=1)
        maschera = np.ones((1, incorporati.shape[1]), dtype=np.int64)
        passato = dict(self._cache_vuota)
        generati = [INIZIO_PARLATO]
        lunghezza = 0
        # Circa 25 "pezzi di voce" al secondo: il limite evita che una frase difficile vada avanti all'infinito.
        for passo in range(min(1000, 75 + 3 * len(testo))):
            ingressi = {"inputs_embeds": incorporati, "attention_mask": maschera, **passato}
            if "position_ids" in self._ingressi_lingua:
                ingressi["position_ids"] = np.arange(lunghezza, lunghezza + incorporati.shape[1])[None, :]
            lunghezza += incorporati.shape[1]
            uscite = dict(zip(self._uscite_lingua, self._lingua.run(None, ingressi)))
            logit = uscite.get("logits", uscite[self._uscite_lingua[0]])[0, -1, :].astype(np.float32)
            prossimo = int(np.argmax(_penalita(logit, generati, 1.2)))
            if prossimo == FINE_PARLATO:
                break
            generati.append(prossimo)
            passato = {nome.replace("present", "past_key_values", 1): valore for nome, valore in uscite.items()
                       if nome.startswith("present")}
            incorporati = self._incorpora_token(np.array([[prossimo]], dtype=np.int64),
                                                np.array([[passo + 1]], dtype=np.int64))
            maschera = np.concatenate([maschera, np.ones((1, 1), dtype=np.int64)], axis=1)
        parlato = [t for t in generati[1:] if t < INIZIO_PARLATO]
        token = np.concatenate([self._token_di_riferimento, np.array([parlato], dtype=np.int64)], axis=1)
        onda = self._decodificatore.run(None, {"speech_tokens": token, "speaker_embeddings": self._timbro,
                                               "speaker_features": self._caratteristiche})[0]
        return np.squeeze(onda).astype(np.float32), FREQUENZA_CHATTERBOX

    def _incorpora_token(self, ids, posizioni):
        ingressi = {"input_ids": ids, "position_ids": posizioni}
        if "exaggeration" in self._ingressi_incorpora:
            ingressi["exaggeration"] = self._np.array([self.emozione], dtype=self._np.float32)
        return self._incorpora.run(None, ingressi)[0]


def _penalita(logit, generati, penalita):
    """Rende meno probabili i pezzi di voce già usati, così il modello non si incanta su un suono."""
    usati = list(set(generati))
    valori = logit[usati]
    logit = logit.copy()
    logit[usati] = [v * penalita if v < 0 else v / penalita for v in valori]
    return logit


def _punteggiatura_per_chatterbox(testo):
    """Come la prepara Chatterbox: maiuscola iniziale, punteggiatura semplice, un punto alla fine."""
    testo = " ".join(testo.split())
    if not testo:
        return testo
    testo = testo[0].upper() + testo[1:]
    for vecchio, nuovo in [("...", ", "), ("…", ", "), (":", ","), (" - ", ", "), (";", ", "), ("—", "-"),
                           ("–", "-"), (" ,", ","), ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")]:
        testo = testo.replace(vecchio, nuovo)
    testo = testo.rstrip()
    return testo if testo[-1:] in ".!?-," else testo + "."


def leggi_wav(percorso, frequenza):
    """Legge un file WAV (PCM) come numeri tra -1 e 1, in mono e alla frequenza voluta."""
    import numpy as np

    try:
        with wave.open(str(percorso), "rb") as w:
            canali, larghezza, originale = w.getnchannels(), w.getsampwidth(), w.getframerate()
            dati = w.readframes(w.getnframes())
    except (OSError, wave.Error, EOFError) as e:
        raise ErroreVoce(f"non riesco a leggere {percorso}: serve un file WAV ({e})") from None
    tipi = {1: (np.uint8, 128, 128), 2: (np.int16, 0, 32768), 4: (np.int32, 0, 2 ** 31)}
    if larghezza not in tipi:
        raise ErroreVoce(f"{percorso}: formato WAV non supportato (usa un WAV a 16 bit)")
    tipo, zero, scala = tipi[larghezza]
    audio = (np.frombuffer(dati, dtype=tipo).astype(np.float32) - zero) / scala
    audio = audio.reshape(-1, canali).mean(axis=1)
    if originale != frequenza and len(audio):
        lunghezza = round(len(audio) * frequenza / originale)
        audio = np.interp(np.linspace(0, len(audio) - 1, lunghezza), np.arange(len(audio)), audio)
    return audio.astype(np.float32)


def salva_wav(percorso, audio, frequenza):
    import numpy as np

    Path(percorso).parent.mkdir(parents=True, exist_ok=True)
    dati = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(percorso), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(frequenza))
        w.writeframes(dati)


class _ElevenLabs:
    """La voce creata per Jarvis su ElevenLabs (vedi voce_elevenlabs.py): fluida e naturale, ma via internet."""

    def __init__(self, cartella, info, velocita, config):
        import numpy  # noqa: F401  (serve per trasformare l'audio)

        if not voce_elevenlabs.leggi_chiave():
            raise ErroreVoce("manca la chiave di ElevenLabs: inseriscila con  py -3.12 prova_voci.py")
        self._voce = (config.get("voce_elevenlabs") or "").strip()
        if not self._voce:
            raise ErroreVoce("la voce di Jarvis su ElevenLabs non c'è ancora: creala con  py -3.12 prova_voci.py")
        self._modello = config.get("modello_elevenlabs") or voce_elevenlabs.MODELLO_PREDEFINITO
        self._velocita = velocita
        self._precedente, self._quando = "", 0.0

    def sintetizza(self, testo):
        # La frase detta subito prima aiuta ElevenLabs a continuare il discorso con l'intonazione giusta.
        precedente = self._precedente if time.monotonic() - self._quando < 20 else ""
        try:
            audio = voce_elevenlabs.sintetizza(testo, self._voce, self._modello, self._velocita, precedente)
        except voce_elevenlabs.ErroreElevenLabs as e:
            raise ErroreVoce(str(e)) from None
        self._precedente, self._quando = testo, time.monotonic()
        return audio, voce_elevenlabs.FREQUENZA


_MOTORI = {"piper": _Piper, "kokoro": _Kokoro, "edge": _Edge, "chatterbox": _Chatterbox, "elevenlabs": _ElevenLabs}


def _riproduci_con_sounddevice(audio, frequenza, interrompi):
    import sounddevice

    sounddevice.play(audio, frequenza)
    while sounddevice.get_stream().active:
        if interrompi.wait(0.05):
            sounddevice.stop()
            return


# Quanti caratteri chiedere insieme a ogni voce. ElevenLabs dà l'intonazione giusta solo se riceve frasi intere
# e collegate: a pezzetti ogni frammento ripartirebbe da capo e la voce suonerebbe a scatti. Le voci sul PC
# invece vanno bene frase per frase, e così cominciano a parlare prima.
PEZZO_MINIMO = {"elevenlabs": 140}


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
        self._riserva_motore = None  # una voce sul PC per quando quella scelta non risponde (internet, crediti)
        self._riserva_provata = False
        self._usa_riserva_fino = 0.0
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
        self._pezzo = ""  # frasi intere della risposta, che aspettano di essere dette insieme
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

    @property
    def in_riserva(self):
        """True se in questo momento parla con la voce di riserva invece che con quella scelta."""
        riserva = self.config.get("voce_di_riserva", VOCE_PREDEFINITA)
        if not riserva or riserva == self.nome:
            return False
        return time.monotonic() < self._usa_riserva_fino or self._fallita == self.nome

    @property
    def _minimo(self):
        return PEZZO_MINIMO.get(VOCI.get(self.nome, {}).get("motore"), 0)

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
                self._motore = carica_motore(nome, float(self.config.get("velocita_voce", 1.0)), avanzamento,
                                             self.config)
                self._nome_motore, self._fallita, self.errore = nome, None, ""
            except ErroreVoce as e:
                self._motore, self._fallita, self.errore = None, nome, str(e)
                self._errori_segnalati.discard(self.errore)  # chi riprova deve sapere com'è andata
                self._segnala(self.errore)
            return self.errore

    # --- Cosa dire ---

    def di(self, testo, limite=0):
        """Dice un testo intero, per esempio un avviso. Se supera `limite` caratteri, ne dice solo l'inizio."""
        detti, da_dire, resto = 0, [], False
        for frase in dividi_frasi(testo):
            if limite and detti and detti + len(frase) > limite:
                resto = True
                break
            detti += len(frase)
            da_dire.append(frase)
        for pezzo in raggruppa(da_dire, self._minimo):
            self._metti_in_fila(pezzo)
        if resto:
            self._metti_in_fila(self._frase_del_resto())

    def inizia(self):
        """Comincia una nuova risposta (quella di prima, se c'era, continua finché non finisce)."""
        self._risposta, self._pezzo, self._detti, self._troncata, self._zittita = "", "", 0, False, False

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
        if self._pezzo:
            self._metti_in_fila(self._pezzo)
            self._pezzo = ""
        if self._troncata:
            self._metti_in_fila(self._frase_del_resto())
            self._troncata = False

    def zitto(self):
        """Smette subito di parlare e butta le frasi in fila."""
        with self._lucchetto:
            self._generazione += 1
            self._interrompi.set()
            self._zittita = True
            self._pezzo = ""
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
        self._pezzo = f"{self._pezzo} {frase}".strip()
        if len(self._pezzo) >= self._minimo:
            self._metti_in_fila(self._pezzo)
            self._pezzo = ""

    def _frase_del_resto(self):
        titolo = self.config.get("come_chiamarmi", "")
        t = f", {titolo}" if titolo else ""
        return f"Il resto lo {'trovi' if self.config.get('dai_del') == 'tu' else 'trova'} sullo schermo{t}."

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
                audio, frequenza = self._audio_della_frase(testo)
            if audio is None or generazione != self._generazione:
                self._fatta()
            else:
                self._da_suonare.put((generazione, audio, frequenza))

    def _audio_della_frase(self, testo):
        """La frase con la voce scelta; se non va (per esempio niente internet), con quella di riserva."""
        principale = None
        if time.monotonic() >= self._usa_riserva_fino and not self.prepara(riprova=False):
            principale = self._motore  # se la voce non si carica, l'ha già detto prepara()
        if principale is not None:
            errore = None
            for tentativo in range(2):  # al primo errore (per esempio un attimo senza rete) si riprova subito
                try:
                    audio, frequenza = principale.sintetizza(testo)
                except Exception as e:  # una frase che non si riesce a dire non deve fermare le altre
                    errore = e
                    if tentativo == 0:
                        time.sleep(0.5)
                    continue
                # L'effetto "intelligenza artificiale" è per le voci sul PC: quella di ElevenLabs resta com'è,
                # come quando l'hai scelta.
                effetto = 0.0 if self._nome_motore == "elevenlabs" else float(self.config.get("effetto_voce", 0.6))
                return effetto_jarvis(audio, frequenza, effetto), frequenza
            self._segnala(f"non sono riuscito a dire una frase ({errore})")
            self._usa_riserva_fino = time.monotonic() + 120  # per due minuti parla con l'altra voce
        riserva = self._riserva()
        if riserva is not None:
            try:
                audio, frequenza = riserva.sintetizza(testo)
            except Exception as e:
                self._segnala(f"non sono riuscito a dire una frase ({e})")
                return None, None
            return effetto_jarvis(audio, frequenza, float(self.config.get("effetto_voce", 0.6))), frequenza
        return None, None

    def _riserva(self):
        nome = self.config.get("voce_di_riserva", VOCE_PREDEFINITA)
        if not nome or nome == self.nome:
            return None
        if not self._riserva_provata:
            self._riserva_provata = True
            try:
                self._riserva_motore = carica_motore(nome, float(self.config.get("velocita_voce", 1.0)),
                                                     config=self.config)
            except ErroreVoce:
                self._riserva_motore = None
        return self._riserva_motore

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
