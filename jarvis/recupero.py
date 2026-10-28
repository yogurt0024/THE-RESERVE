"""Quando si scarica Jarvis di nuovo (uno ZIP nuovo in Download, una cartella sul Desktop...), riprende i tuoi
dati e la tua voce dalla copia di Jarvis usata prima.

- trasloca(): la prima volta che si apre una copia nuova, senza dati, porta qui la cartella dati (memoria,
  conversazioni, promemoria, diario, chiavi, abilità, modelli) e le impostazioni di config.json della copia più
  recente che trova sul PC.
- ritrova_voce(): se in questa copia la voce di ElevenLabs non è impostata (o manca la sua chiave), la cerca nelle
  altre copie e, se serve, nella cronologia del tuo account ElevenLabs.
Le altre copie si cercano accanto a questa, in Download, sul Desktop e in Documenti; si leggono solo le cartelle
di Jarvis, e qui si copia solo quello che manca.
"""

import json
import os
import shutil
from pathlib import Path

import voce_elevenlabs

CARTELLA = Path(__file__).resolve().parent
# Le voci con cui si cerca: quelle che ci sono se nessuno ne ha scelta una, ed "elevenlabs" senza la voce
# (per esempio se in config.json si è scritto "elevenlabs" a mano).
VOCI_PREDEFINITE = ("", "riccardo", "elevenlabs")
DATI_DA_RECUPERARE = ("chiave_elevenlabs.txt", "memoria.json", "promemoria.json", "conversazione.json")
IMPOSTAZIONI_VOCE = ("voce", "voce_elevenlabs", "modello_elevenlabs", "effetto_voce", "velocita_voce")
# Se c'è uno di questi file, la copia è già stata usata: non è una copia nuova da riempire.
FILE_PERSONALI = ("memoria.json", "conversazione.json", "promemoria.json", "chiave_elevenlabs.txt",
                  "chiave_claude.txt", "chiave_github.txt", "versione.txt")
NON_DA_PORTARE = ("versione.txt",)  # la versione è quella della copia nuova
CARTELLE_NON_DA_PORTARE = ("voci_di_prova",)
ultimo_trasloco = ""  # il messaggio dell'ultimo trasloco, che la finestra mostra quando è pronta


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


def trasloca(cartella=CARTELLA, radici=None):
    """La prima volta di una copia nuova: porta qui dati e impostazioni della copia usata prima.
    Va chiamata prima di leggere config.json e i dati. Restituisce un messaggio, oppure "" se non serviva."""
    global ultimo_trasloco
    dati = cartella / "dati"
    if any((dati / nome).exists() for nome in FILE_PERSONALI):
        return ""
    candidate = []
    for copia, config in altre_copie(cartella, radici):
        personali = [copia / "dati" / nome for nome in FILE_PERSONALI if (copia / "dati" / nome).is_file()]
        if personali:
            candidate.append((max(f.stat().st_mtime for f in personali), copia, config))
    if not candidate:
        return ""
    _, copia, vecchia = max(candidate, key=lambda c: c[0])
    origine_dati = copia / "dati"
    for origine in sorted(origine_dati.rglob("*")):
        relativo = origine.relative_to(origine_dati)
        destinazione = dati / relativo
        if (not origine.is_file() or destinazione.exists() or origine.name.endswith(".parziale")
                or relativo.parts[0] in CARTELLE_NON_DA_PORTARE or str(relativo) in NON_DA_PORTARE):
            continue
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        if relativo.parts[0] == "modelli":
            try:  # i modelli sono grandi: sullo stesso disco basta un collegamento, che non occupa altro spazio
                os.link(origine, destinazione)
            except OSError:
                pass  # su un altro disco non si copiano: Jarvis li riscarica da solo
            continue
        shutil.copy2(origine, destinazione)
    file_config = cartella / "config.json"
    attuale = _leggi_config(file_config) or {}
    unita = dict(attuale)
    unita.update({chiave: valore for chiave, valore in vecchia.items() if chiave in attuale})
    if unita != attuale:
        file_config.write_text(json.dumps(unita, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ultimo_trasloco = (f"Ho ripreso i tuoi dati e le tue impostazioni dalla copia di Jarvis in {copia}: memoria, "
                       "promemoria, diario, chiavi e voce sono come prima.")
    return ultimo_trasloco


def ritrova_voce(config, salva, cartella=CARTELLA, radici=None, forza=False):
    """Se qui la voce di ElevenLabs non è impostata, la ritrova e la rimette. `salva(chiave, valore)` scrive in
    config.json. Con `forza` la cerca anche se è scelta un'altra voce (per esempio con /voce elevenlabs).
    Restituisce un messaggio per l'utente, oppure "" se non c'era niente da fare o da trovare."""
    dati = cartella / "dati"
    if (config.get("voce_elevenlabs") or "").strip():
        # La voce di ElevenLabs è già impostata: chi parla con un'altra voce l'ha scelto. Se però manca la chiave
        # (per esempio si è copiato config.json ma non la cartella dati), la si riprende da un'altra copia.
        if config.get("voce") == "elevenlabs" and not (dati / "chiave_elevenlabs.txt").exists():
            for copia, _ in altre_copie(cartella, radici):
                if (copia / "dati" / "chiave_elevenlabs.txt").is_file():
                    _recupera_dati(copia, dati)
                    return f"Ho ripreso la chiave di ElevenLabs dalla copia di Jarvis in {copia}."
        return ""
    if not forza and config.get("voce", "") not in VOCI_PREDEFINITE:
        return ""
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
