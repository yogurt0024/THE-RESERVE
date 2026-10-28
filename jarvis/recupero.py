"""Ritrova la voce di ElevenLabs scelta in un'altra copia di Jarvis sul PC.

Capita quando si scarica Jarvis più volte (uno ZIP nuovo in Download, una cartella sul Desktop...): la voce
scelta con prova_voci.py resta in config.json e in dati/ della copia dove è stata scelta. All'avvio, se in
questa copia la voce di ElevenLabs non è impostata, Jarvis la cerca:
1. nelle altre copie di Jarvis sul PC (accanto a questa, in Download, sul Desktop, in Documenti);
2. nella cronologia del tuo account ElevenLabs, se in questa copia c'è la chiave.
Legge solo le cartelle di Jarvis; copia qui la chiave di ElevenLabs e i ricordi solo se qui mancano.
"""

import json
import shutil
from pathlib import Path

import voce_elevenlabs

CARTELLA = Path(__file__).resolve().parent
# Le voci con cui si cerca: quelle che ci sono se nessuno ne ha scelta una, ed "elevenlabs" senza la voce
# (per esempio se in config.json si è scritto "elevenlabs" a mano).
VOCI_PREDEFINITE = ("", "riccardo", "elevenlabs")
DATI_DA_RECUPERARE = ("chiave_elevenlabs.txt", "memoria.json", "promemoria.json", "conversazione.json")
IMPOSTAZIONI_VOCE = ("voce", "voce_elevenlabs", "modello_elevenlabs", "effetto_voce", "velocita_voce")


def _leggi_config(file):
    try:
        dati = json.loads(file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return dati if isinstance(dati, dict) else None


def radici_predefinite(cartella=CARTELLA):
    casa = Path.home()
    return [cartella.parent.parent, cartella.parent, casa / "Downloads", casa / "Desktop", casa / "Documents",
            casa / "OneDrive" / "Desktop", casa / "OneDrive" / "Documents"]


def altre_copie(cartella=CARTELLA, radici=None):
    """Le altre cartelle di Jarvis sul PC: [(cartella, config)], la più recente prima. Gli ZIP estratti con
    Windows spesso hanno una cartella in più: si guarda fino a tre livelli."""
    qui = cartella.resolve()
    trovate, viste = [], set()
    for radice in radici if radici is not None else radici_predefinite(cartella):
        if not radice.is_dir() or radice == radice.parent:  # la radice del disco no: sarebbe troppo grande
            continue
        for schema in ("jarvis/config.json", "*/jarvis/config.json", "*/*/jarvis/config.json"):
            try:
                file = sorted(radice.glob(schema))
            except OSError:
                continue
            for config_file in file:
                copia = config_file.parent.resolve()
                if copia == qui or copia in viste or not (copia / "cervello.py").exists():
                    continue
                viste.add(copia)
                config = _leggi_config(config_file)
                if config is not None:
                    trovate.append((config_file.stat().st_mtime, copia, config))
    trovate.sort(key=lambda t: t[0], reverse=True)
    return [(copia, config) for _, copia, config in trovate]


def ritrova_voce(config, salva, cartella=CARTELLA, radici=None, forza=False):
    """Se qui la voce di ElevenLabs non è impostata, la ritrova e la rimette. `salva(chiave, valore)` scrive in
    config.json. Con `forza` la cerca anche se è scelta un'altra voce (per esempio con /voce elevenlabs).
    Restituisce un messaggio per l'utente, oppure "" se non c'era niente da fare o da trovare."""
    if (config.get("voce_elevenlabs") or "").strip():
        return ""  # la voce di ElevenLabs è già impostata: chi parla con un'altra voce l'ha scelto
    if not forza and config.get("voce", "") not in VOCI_PREDEFINITE:
        return ""
    dati = cartella / "dati"
    copie = altre_copie(cartella, radici)
    for copia, altra in copie:
        if altra.get("voce") != "elevenlabs" or not (altra.get("voce_elevenlabs") or "").strip():
            continue
        copiati = _recupera_dati(copia, dati)
        if not (dati / "chiave_elevenlabs.txt").exists():
            continue  # senza la chiave quella voce qui non parlerebbe
        for chiave in IMPOSTAZIONI_VOCE:
            if chiave in altra:
                salva(chiave, altra[chiave])
        ricordi = " Ho ripreso da lì anche la memoria." if "memoria.json" in copiati else ""
        return f"Ho ritrovato la voce che avevi scelto (era nella copia di Jarvis in {copia}): torno a usarla.{ricordi}"
    # Nessuna copia ha la voce salvata: basta la chiave (di qui o di un'altra copia) per cercarla su ElevenLabs.
    ricordi = ""
    if not (dati / "chiave_elevenlabs.txt").exists():
        for copia, _ in copie:
            if (copia / "dati" / "chiave_elevenlabs.txt").is_file():
                if "memoria.json" in _recupera_dati(copia, dati):
                    ricordi = " Ho ripreso anche la memoria dalla copia di Jarvis in " + str(copia) + "."
                break
    if not voce_elevenlabs.leggi_chiave():
        return ""
    trovata = voce_elevenlabs.voce_scelta_dalla_cronologia()
    if not trovata:
        return ""
    id_voce, nome = trovata
    salva("voce_elevenlabs", id_voce)
    salva("voce", "elevenlabs")
    salva("effetto_voce", 0.0)  # come la imposta prova_voci.py: la voce di ElevenLabs va bene così com'è
    return f"Ho ritrovato su ElevenLabs la voce che avevi scelto ({nome or id_voce}): torno a usarla.{ricordi}"


def _recupera_dati(copia, dati):
    """Copia qui la chiave di ElevenLabs e i ricordi di un'altra copia, solo quelli che qui mancano."""
    copiati = []
    for nome in DATI_DA_RECUPERARE:
        origine, destinazione = copia / "dati" / nome, dati / nome
        if origine.is_file() and not destinazione.exists():
            dati.mkdir(exist_ok=True)
            shutil.copy2(origine, destinazione)
            copiati.append(nome)
    return copiati
