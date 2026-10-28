"""La voce di Jarvis su ElevenLabs: la più fluida e naturale. Usa solo la libreria standard di Python.

La voce non copia nessuno: ElevenLabs la crea da zero partendo da una descrizione (vedi DESCRIZIONE_JARVIS).
La chiave API resta sul PC, in dati/chiave_elevenlabs.txt. Il testo da leggere viene inviato a ElevenLabs.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

CARTELLA_DATI = Path(__file__).resolve().parent / "dati"
FILE_CHIAVE = CARTELLA_DATI / "chiave_elevenlabs.txt"
FREQUENZA = 24000
MODELLO_PREDEFINITO = "eleven_multilingual_v2"
# Come Jarvis: calmo, elegante, con un'ironia asciutta. Una voce nuova, che non imita nessuna persona reale.
DESCRIZIONE_JARVIS = (
    "A refined, calm Italian man in his forties with a warm, deep, velvety baritone voice. He speaks native Italian "
    "with perfect diction and a smooth, flowing, measured pace, with a subtle dry wit, like a sophisticated digital "
    "butler or an elegant artificial intelligence assistant. Confident, reassuring and quietly ironic. Clear, "
    "close, studio-quality recording."
)
TESTO_DI_PROVA = (
    "Buonasera, signore. Tutti i sistemi sono operativi e i compiti di oggi sono completati. Ho controllato il "
    "meteo: domani pioverà, quindi le consiglierei l'ombrello. Se posso permettermi, è anche ora di una pausa: "
    "lavora da tre ore di fila."
)
IMPOSTAZIONI = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True}


class ErroreElevenLabs(Exception):
    def __init__(self, messaggio, stato=""):
        super().__init__(messaggio)
        self.stato = stato  # per esempio "invalid_api_key" o "quota_exceeded"


def leggi_chiave():
    try:
        chiave = FILE_CHIAVE.read_text(encoding="utf-8-sig").strip()
    except OSError:
        chiave = ""
    return chiave or os.environ.get("ELEVENLABS_API_KEY", "")


def salva_chiave(chiave):
    """Controlla la chiave con ElevenLabs e, se va bene, la salva. Restituisce un messaggio per l'utente."""
    chiave = chiave.strip()
    if not chiave or " " in chiave:
        return "Questa non sembra una chiave API di ElevenLabs."
    try:
        piano = descrivi_abbonamento(richiesta("/v1/user/subscription", chiave=chiave))
    except ErroreElevenLabs as e:
        if e.stato != "missing_permissions":
            return f"La chiave non funziona: {e}"
        piano = "Non posso leggere quanti caratteri ti restano: a questa chiave manca il permesso \"User\"."
    FILE_CHIAVE.parent.mkdir(exist_ok=True)
    FILE_CHIAVE.write_text(chiave + "\n", encoding="utf-8")
    return f"Chiave di ElevenLabs salvata sul PC. {piano}"


def descrivi_abbonamento(abbonamento):
    usati, limite = abbonamento.get("character_count", 0), abbonamento.get("character_limit", 0)
    piano = abbonamento.get("tier", "")
    return (f"Piano {piano}: questo mese hai usato {usati:,} caratteri su {limite:,}.".replace(",", ".")
            if limite else f"Piano {piano}.")


def richiesta(percorso, corpo=None, chiave=None, grezza=False):
    """Chiama l'API di ElevenLabs. Restituisce il JSON della risposta, oppure i byte se `grezza`."""
    chiave = chiave or leggi_chiave()
    if not chiave:
        raise ErroreElevenLabs("manca la chiave di ElevenLabs: inseriscila con  py -3.12 prova_voci.py")
    base = os.environ.get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/")
    dati = None if corpo is None else json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(base + percorso, data=dati,
                                 headers={"xi-api-key": chiave, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as risposta:
            contenuto = risposta.read()
    except urllib.error.HTTPError as e:
        raise ErroreElevenLabs(*_spiega_errore(e)) from None
    except OSError as e:
        raise ErroreElevenLabs(f"ElevenLabs non risponde (serve internet): {e}") from None
    return contenuto if grezza else json.loads(contenuto)


def _spiega_errore(errore):
    try:
        dettaglio = json.loads(errore.read()).get("detail", {})
    except (ValueError, AttributeError):
        dettaglio = {}
    if isinstance(dettaglio, str):
        dettaglio = {"message": dettaglio}
    stato, messaggio = dettaglio.get("status", ""), dettaglio.get("message", "")
    if stato == "missing_permissions":
        spiegazione = f"alla chiave API manca un permesso ({messaggio})"
    elif stato == "quota_exceeded":
        spiegazione = "hai finito i caratteri del mese su ElevenLabs"
    elif errore.code == 401 or stato in ("invalid_api_key", "needs_authorization"):
        spiegazione = "la chiave API di ElevenLabs non è valida"
    elif stato == "voice_not_found" or errore.code == 404:
        spiegazione = "su ElevenLabs non trovo la voce di Jarvis: ricreala con  py -3.12 prova_voci.py"
    elif errore.code == 429:
        spiegazione = "troppe richieste insieme a ElevenLabs: riprovo tra poco"
    else:
        spiegazione = f"ElevenLabs ha risposto con l'errore {errore.code}" + (f": {messaggio}" if messaggio else "")
    return spiegazione, stato


def pcm_in_audio(dati):
    """I byte PCM a 16 bit che manda ElevenLabs, come numeri tra -1 e 1."""
    import numpy as np

    return np.frombuffer(dati[:len(dati) // 2 * 2], dtype="<i2").astype(np.float32) / 32768


def progetta_voci(descrizione=DESCRIZIONE_JARVIS, testo=TESTO_DI_PROVA, seme=None):
    """ElevenLabs crea alcune voci nuove dalla descrizione. Restituisce [(id provvisorio, audio, frequenza)]."""
    corpo = {"voice_description": descrizione, "model_id": "eleven_multilingual_ttv_v2", "text": testo}
    if seme is not None:
        corpo["seed"] = seme
    risposta = richiesta(f"/v1/text-to-voice/design?output_format=pcm_{FREQUENZA}", corpo)
    voci = []
    for anteprima in risposta.get("previews", []):
        dati = base64.b64decode(anteprima["audio_base_64"])
        if "mpeg" in anteprima.get("media_type", "") or dati[:3] == b"ID3":
            raise ErroreElevenLabs("ElevenLabs ha mandato l'anteprima in MP3 invece che in PCM")
        voci.append((anteprima["generated_voice_id"], pcm_in_audio(dati), FREQUENZA))
    if not voci:
        raise ErroreElevenLabs("ElevenLabs non ha creato nessuna voce: riprova cambiando la descrizione")
    return voci


def crea_voce(id_provvisorio, nome="Jarvis", descrizione=DESCRIZIONE_JARVIS):
    """Salva nel tuo account ElevenLabs la voce scelta tra quelle progettate. Restituisce il suo voice_id."""
    risposta = richiesta("/v1/text-to-voice", {"voice_name": nome, "voice_description": descrizione,
                                               "generated_voice_id": id_provvisorio})
    return risposta["voice_id"]


def sintetizza(testo, voce, modello=MODELLO_PREDEFINITO, velocita=1.0, precedente=""):
    """Il testo letto dalla voce `voce`. `precedente` è la frase detta appena prima: rende il discorso continuo."""
    corpo = {"text": testo, "model_id": modello,
             "voice_settings": dict(IMPOSTAZIONI, speed=min(1.2, max(0.7, velocita)))}  # i limiti di ElevenLabs
    if precedente:
        corpo["previous_text"] = precedente
    if not modello.startswith("eleven_multilingual_v2"):  # gli altri modelli accettano la lingua esplicita
        corpo["language_code"] = "it"
    return pcm_in_audio(richiesta(f"/v1/text-to-speech/{voce}?output_format=pcm_{FREQUENZA}", corpo, grezza=True))
