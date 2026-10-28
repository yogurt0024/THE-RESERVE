"""Le abilità di Jarvis: piccoli programmi che scrive da solo quando gli dici "impara a ...".

1. Il cervello grande scrive l'abilità: un file Python con una funzione, la sua descrizione e alcune prove.
2. Jarvis controlla il codice: niente file, programmi, comandi del sistema o librerie fuori da un elenco sicuro.
3. La prova in un processo separato, con tempo e memoria limitati; se le prove non passano, la corregge.
4. Te la propone: diventa uno strumento solo dopo /approva. Le versioni vecchie restano in dati/abilita/versioni.

Questo file fa anche da "recinto": eseguito come programma (python abilita.py) carica un'abilità con i soli
permessi qui sotto e la fa lavorare. Così un'abilità sbagliata non può fare danni né bloccare Jarvis.
"""

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent / "dati" / "abilita"
MODULI_PERMESSI = {"math", "statistics", "datetime", "re", "json", "random", "textwrap", "itertools", "collections",
                   "fractions", "decimal", "calendar", "unicodedata", "functools", "heapq", "bisect"}
BUILTIN_PERMESSI = ["abs", "all", "any", "bool", "chr", "dict", "divmod", "enumerate", "filter", "float",
                    "frozenset", "hex", "int", "isinstance", "iter", "len", "list", "map", "max", "min", "next",
                    "ord", "pow", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
                    "tuple", "zip", "Exception", "ArithmeticError", "IndexError", "KeyError", "LookupError",
                    "OverflowError", "RuntimeError", "TypeError", "ValueError", "ZeroDivisionError"]
# Attributi che porterebbero fuori dal recinto (i "dietro le quinte" di funzioni, generatori ed errori) e i
# metodi che leggono attributi scritti dentro una stringa.
ATTRIBUTI_VIETATI = {"gi_frame", "gi_code", "gi_yieldfrom", "cr_frame", "cr_code", "ag_frame", "ag_code",
                     "f_globals", "f_locals", "f_builtins", "f_back", "f_code", "tb_frame", "tb_next", "format",
                     "format_map", "mro"}
NOMI_VIETATI = {"open", "exec", "eval", "compile", "input", "breakpoint", "globals", "locals", "vars", "dir",
                "getattr", "setattr", "delattr", "hasattr", "help", "exit", "quit", "type", "object", "super",
                "memoryview", "classmethod", "staticmethod", "property", "print"}
TIPI_PERMESSI = {"string", "number", "boolean"}
TEMPO_PROVE = 60  # secondi per tutte le prove insieme
TEMPO_ESECUZIONE = 30  # secondi per una richiesta
MEMORIA_MASSIMA = 1024  # MB

ISTRUZIONI = """Scrivi un'abilità per Jarvis: un file Python che fa una cosa sola, bene. Rispondi solo con il \
codice, dentro un blocco ```python.

Il file deve contenere esattamente:
NOME = "nome_in_minuscolo"   (in italiano, descrive l'azione, per esempio converti_valuta; lettere, numeri e _)
DESCRIZIONE = "Una o due frasi: cosa fa e quando usarla."
PARAMETRI = {"nome_parametro": {"type": "string", "description": "..."}}   (type: string, number o boolean)
OBBLIGATORI = ["nome_parametro"]
def esegui(argomenti, aiuto):
    ...
    return "il risultato, in italiano, come testo"
PROVE = [({"nome_parametro": "valore"}, "una parte del testo che deve uscire"), ...]   (da 3 a 6 prove)

Regole (se non le rispetti, l'abilità viene scartata):
- Puoi importare solo: """ + ", ".join(sorted(MODULI_PERMESSI)) + """.
- Niente file, comandi del sistema, classi, print, global, generatori (yield) o funzioni async.
- Nessun nome, attributo o testo che inizi con il trattino basso; niente .format(): usa le f-string.
- Per internet usa solo `aiuto`: aiuto.cerca(testo) dà una lista di (titolo, indirizzo, estratto); \
aiuto.pagina(indirizzo) dà il testo di una pagina; aiuto.dati(indirizzo) dà il JSON di un servizio pubblico \
(solo https). Se internet non c'è sollevano un errore: gestiscilo con un messaggio chiaro.
- esegui restituisce sempre un testo. Se mancano argomenti o sono sbagliati, restituisce un messaggio che lo spiega.
- Le prove controllano che il testo restituito contenga la parte attesa (maiuscole e minuscole non contano). Se \
puoi, scrivi prove che non usano internet: i risultati devono essere certi.
"""


class ErroreAbilita(Exception):
    pass


# --- Il controllo del codice (prima di eseguirlo) ---

def _errore_nodo(nodo, motivo):
    riga = getattr(nodo, "lineno", None)
    return ErroreAbilita(f"{motivo} (riga {riga})" if riga else motivo)


def controlla(codice):
    """Solleva ErroreAbilita se il codice usa qualcosa che non è permesso."""
    try:
        albero = ast.parse(codice)
    except SyntaxError as e:
        raise ErroreAbilita(f"il codice ha un errore di sintassi alla riga {e.lineno}: {e.msg}") from None
    for istruzione in albero.body:
        if isinstance(istruzione, ast.Expr) and isinstance(istruzione.value, ast.Constant):
            continue  # la descrizione del file
        if not isinstance(istruzione, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Assign, ast.AnnAssign)):
            raise _errore_nodo(istruzione, "fuori dalle funzioni ci possono essere solo import, costanti e funzioni")
    for nodo in ast.walk(albero):
        if isinstance(nodo, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith, ast.Yield,
                             ast.YieldFrom, ast.Global, ast.Nonlocal)):
            raise _errore_nodo(nodo, f"non si possono usare {type(nodo).__name__}")
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            if isinstance(nodo, ast.ImportFrom) and (nodo.level or not nodo.module):
                raise _errore_nodo(nodo, "gli import relativi non sono permessi")
            moduli = [nodo.module] if isinstance(nodo, ast.ImportFrom) else [a.name for a in nodo.names]
            for modulo in moduli:
                if modulo not in MODULI_PERMESSI:
                    raise _errore_nodo(nodo, f"la libreria {modulo} non è permessa")
            for alias in nodo.names:
                if alias.name == "*" or alias.name.startswith("_") or (alias.asname or "").startswith("_"):
                    raise _errore_nodo(nodo, "si possono importare solo nomi pubblici, uno per uno")
        nomi = []
        if isinstance(nodo, ast.Name):
            nomi.append(nodo.id)
        elif isinstance(nodo, ast.FunctionDef):
            nomi.append(nodo.name)
        elif isinstance(nodo, ast.arg):
            nomi.append(nodo.arg)
        elif isinstance(nodo, ast.keyword) and nodo.arg:
            nomi.append(nodo.arg)
        elif isinstance(nodo, ast.alias):
            nomi.append(nodo.asname or nodo.name)
        for nome in nomi:
            if nome.startswith("_") or nome in NOMI_VIETATI:
                raise _errore_nodo(nodo, f"il nome {nome} non è permesso")
        if isinstance(nodo, ast.Attribute) and (nodo.attr.startswith("_") or nodo.attr in ATTRIBUTI_VIETATI):
            raise _errore_nodo(nodo, f"l'attributo .{nodo.attr} non è permesso")
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and "__" in nodo.value:
            raise _errore_nodo(nodo, "i testi con due trattini bassi di fila non sono permessi")
    funzione = next((n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name == "esegui"), None)
    if funzione is None or [a.arg for a in funzione.args.args] != ["argomenti", "aiuto"]:
        raise ErroreAbilita("manca la funzione esegui(argomenti, aiuto)")
    definiti = {t.id for n in albero.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    mancanti = [c for c in ("NOME", "DESCRIZIONE", "PARAMETRI", "OBBLIGATORI", "PROVE") if c not in definiti]
    if mancanti:
        raise ErroreAbilita(f"manca {', '.join(mancanti)}")


def estrai_codice(testo):
    """Il codice dentro il blocco ```python della risposta del modello (o tutta la risposta, se non c'è)."""
    blocchi = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", testo or "", re.S | re.I)
    codice = max(blocchi, key=len) if blocchi else (testo or "")
    return codice.strip() + "\n"


def controlla_scheda(info, nomi_occupati=()):
    """Controlla nome, descrizione e parametri dichiarati dall'abilità."""
    nome = info.get("nome")
    if not isinstance(nome, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", nome):
        raise ErroreAbilita("NOME deve essere in minuscolo, con lettere, numeri e trattini bassi (da 3 a 41)")
    if nome in nomi_occupati:
        raise ErroreAbilita(f"il nome {nome} è già di uno strumento di Jarvis: scegline un altro")
    descrizione = info.get("descrizione")
    if not isinstance(descrizione, str) or not 10 <= len(descrizione) <= 400:
        raise ErroreAbilita("DESCRIZIONE deve essere una frase (da 10 a 400 caratteri)")
    parametri = info.get("parametri")
    if not isinstance(parametri, dict) or len(parametri) > 8:
        raise ErroreAbilita("PARAMETRI deve essere un dizionario (al massimo 8 parametri)")
    for chiave, regola in parametri.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", str(chiave)) or not isinstance(regola, dict):
            raise ErroreAbilita(f"il parametro {chiave} non è scritto bene")
        if regola.get("type") not in TIPI_PERMESSI or not isinstance(regola.get("description"), str):
            raise ErroreAbilita(f"il parametro {chiave} deve avere type (string, number o boolean) e description")
    obbligatori = info.get("obbligatori")
    if not isinstance(obbligatori, list) or any(o not in parametri for o in obbligatori):
        raise ErroreAbilita("OBBLIGATORI deve elencare solo nomi di PARAMETRI")


# --- Il recinto: un processo separato che esegue l'abilità ---

def _python():
    """L'interprete per il recinto: python.exe anche se Jarvis è partito con pythonw.exe (senza finestra)."""
    eseguibile = Path(sys.executable)
    if eseguibile.name.lower() == "pythonw.exe" and (eseguibile.parent / "python.exe").exists():
        return str(eseguibile.parent / "python.exe")
    return sys.executable


def _nel_recinto(azione, codice, argomenti=None, internet=True, tempo=TEMPO_ESECUZIONE):
    richiesta = json.dumps({"azione": azione, "codice": codice, "argomenti": argomenti or {}, "internet": internet})
    try:
        esito = subprocess.run([_python(), "-I", str(Path(__file__).resolve())], input=richiesta, text=True,
                               encoding="utf-8", capture_output=True, timeout=tempo,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ErroreAbilita(f"ci mette troppo (più di {tempo} secondi): forse resta bloccata in un ciclo") from None
    except OSError as e:
        raise ErroreAbilita(f"non riesco ad avviare il recinto ({e})") from None
    righe = [r for r in esito.stdout.splitlines() if r.startswith("{")]
    if not righe:
        dettaglio = (esito.stderr or "").strip().splitlines()[-1:] or ["si è fermata senza risposta"]
        raise ErroreAbilita(f"si è bloccata ({dettaglio[0][:200]})")
    risposta = json.loads(righe[-1])
    if not risposta.get("ok"):
        raise ErroreAbilita(risposta.get("errore", "errore sconosciuto"))
    return risposta["risultato"]


def prova(codice, nomi_occupati=(), internet=True):
    """Controlla il codice, legge la scheda e fa girare le prove nel recinto. Restituisce la scheda."""
    controlla(codice)
    info = _nel_recinto("prova", codice, internet=internet, tempo=TEMPO_PROVE)
    controlla_scheda(info, nomi_occupati)
    return info


# --- Dove stanno le abilità ---

def _impronta(codice):
    return hashlib.sha256(codice.encode("utf-8")).hexdigest()


def _scheda_salvata(file):
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def attive():
    """{nome: scheda} delle abilità approvate."""
    risultato = {}
    if CARTELLA.is_dir():
        for file in sorted(CARTELLA.glob("*.json")):
            scheda = _scheda_salvata(file)
            if scheda and (CARTELLA / f"{file.stem}.py").exists():
                risultato[file.stem] = scheda
    return risultato


def proposte():
    risultato = {}
    cartella = CARTELLA / "proposte"
    if cartella.is_dir():
        for file in sorted(cartella.glob("*.json")):
            scheda = _scheda_salvata(file)
            if scheda and (cartella / f"{file.stem}.py").exists():
                risultato[file.stem] = scheda
    return risultato


def codice_di(nome, proposta=False):
    cartella = CARTELLA / "proposte" if proposta else CARTELLA
    try:
        return (cartella / f"{nome}.py").read_text(encoding="utf-8")
    except OSError:
        raise ErroreAbilita(f"non conosco l'abilità {nome}") from None


def proponi(codice, info, richiesta):
    """Salva un'abilità che ha passato le prove, in attesa di approvazione."""
    cartella = CARTELLA / "proposte"
    cartella.mkdir(parents=True, exist_ok=True)
    nome = info["nome"]
    scheda = dict(info, richiesta=richiesta, impronta=_impronta(codice),
                  creata=datetime.now().isoformat("T", "seconds"))
    (cartella / f"{nome}.py").write_text(codice, encoding="utf-8")
    (cartella / f"{nome}.json").write_text(json.dumps(scheda, ensure_ascii=False, indent=2), encoding="utf-8")
    return scheda


def _archivia(nome):
    """Sposta la versione attiva di un'abilità tra le versioni vecchie."""
    if not (CARTELLA / f"{nome}.py").exists():
        return
    versioni = CARTELLA / "versioni"
    versioni.mkdir(parents=True, exist_ok=True)
    data = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    for estensione in ("py", "json"):
        file = CARTELLA / f"{nome}.{estensione}"
        if file.exists():
            shutil.move(str(file), str(versioni / f"{nome}-{data}.{estensione}"))


def approva(nome):
    cartella = CARTELLA / "proposte"
    if not (cartella / f"{nome}.py").exists():
        raise ErroreAbilita(f"non c'è nessuna abilità {nome} da approvare")
    sostituita = (CARTELLA / f"{nome}.py").exists()
    _archivia(nome)
    shutil.move(str(cartella / f"{nome}.py"), str(CARTELLA / f"{nome}.py"))
    shutil.move(str(cartella / f"{nome}.json"), str(CARTELLA / f"{nome}.json"))
    return sostituita


def rifiuta(nome):
    cartella = CARTELLA / "proposte"
    if not (cartella / f"{nome}.py").exists():
        raise ErroreAbilita(f"non c'è nessuna abilità {nome} in attesa")
    for estensione in ("py", "json"):
        (cartella / f"{nome}.{estensione}").unlink(missing_ok=True)


def togli(nome):
    if not (CARTELLA / f"{nome}.py").exists():
        raise ErroreAbilita(f"non conosco l'abilità {nome}")
    _archivia(nome)


def ripristina(nome):
    """Rimette la versione precedente di un'abilità (quella attiva, se c'è, va tra le versioni)."""
    versioni = sorted((CARTELLA / "versioni").glob(f"{nome}-*.py")) if (CARTELLA / "versioni").is_dir() else []
    versioni = [v for v in versioni if re.fullmatch(rf"{re.escape(nome)}-\d{{8}}-\d{{6}}-\d{{6}}", v.stem)]
    if not versioni:
        raise ErroreAbilita(f"non ho versioni precedenti dell'abilità {nome}")
    ultima = versioni[-1]
    codice, scheda = ultima.read_text(encoding="utf-8"), ultima.with_suffix(".json").read_text(encoding="utf-8")
    ultima.unlink()
    ultima.with_suffix(".json").unlink()
    _archivia(nome)
    (CARTELLA / f"{nome}.py").write_text(codice, encoding="utf-8")
    (CARTELLA / f"{nome}.json").write_text(scheda, encoding="utf-8")


def schemi():
    """Le abilità approvate, descritte al modello come strumenti."""
    elenco = []
    for nome, scheda in attive().items():
        elenco.append({"type": "function", "function": {
            "name": nome, "description": scheda["descrizione"] + " (Un'abilità che hai imparato da solo.)",
            "parameters": {"type": "object", "properties": scheda["parametri"], "required": scheda["obbligatori"]}}})
    return elenco


def esegui(nome, argomenti, internet=True):
    """Fa lavorare un'abilità approvata, nel recinto. Restituisce il testo per il modello."""
    scheda = attive().get(nome)
    if scheda is None:
        raise ErroreAbilita(f"non conosco l'abilità {nome}")
    codice = codice_di(nome)
    if _impronta(codice) != scheda.get("impronta"):
        raise ErroreAbilita(f"il file dell'abilità {nome} è stato cambiato dopo l'approvazione: per sicurezza non "
                            "lo uso (rifalla con \"impara a ...\" oppure /abilita ripristina)")
    controlla(codice)
    return _nel_recinto("esegui", codice, argomenti, internet=internet)


# --- Dentro il recinto (questa parte gira nel processo separato) ---

class _Modulo:
    """Una libreria permessa, ridotta alle sole funzioni e costanti pubbliche (niente altre librerie dentro)."""

    def __init__(self, modulo):
        import types

        for nome, valore in vars(modulo).items():
            if not nome.startswith("_") and not isinstance(valore, types.ModuleType) and nome != "main":
                setattr(self, nome, valore)


def _importa(nome, globali=None, locali=None, da=(), livello=0):
    if livello or nome not in MODULI_PERMESSI:
        raise ImportError(f"la libreria {nome} non è permessa")
    import importlib

    return _Modulo(importlib.import_module(nome))


class _Aiuto:
    """Quello che un'abilità può fare su internet: solo indirizzi pubblici, solo leggere."""

    def __init__(self, internet):
        self._internet = internet

    def _controlla(self):
        if not self._internet:
            raise ValueError("internet è disattivato")

    def cerca(self, testo):
        self._controlla()
        import rete

        try:
            return [tuple(r) for r in rete.cerca(str(testo))]
        except rete.ErroreRete as e:
            raise ValueError(str(e)) from None

    def pagina(self, indirizzo):
        self._controlla()
        import rete

        try:
            return rete.leggi_pagina(str(indirizzo), massimo=6000)
        except rete.ErroreRete as e:
            raise ValueError(str(e)) from None

    def dati(self, indirizzo):
        self._controlla()
        import urllib.error
        import urllib.request

        import rete

        indirizzo = str(indirizzo)
        if not indirizzo.startswith("https://"):
            raise ValueError("aiuto.dati vuole un indirizzo https://")
        try:
            rete._controlla_indirizzo(indirizzo)
            richiesta = urllib.request.Request(indirizzo, headers={"User-Agent": rete.AGENTE,
                                                                   "Accept": "application/json"})
            with urllib.request.urlopen(richiesta, timeout=15) as risposta:
                rete._controlla_indirizzo(risposta.geturl())
                return json.loads(risposta.read(2_000_000).decode("utf-8", errors="replace"))
        except rete.ErroreRete as e:
            raise ValueError(str(e)) from None
        except (OSError, ValueError) as e:
            raise ValueError(f"il servizio non risponde come previsto ({e})") from None


def _limita_memoria(megabyte=MEMORIA_MASSIMA):
    """Un tetto alla memoria del recinto, così un'abilità sbagliata non rallenta il PC (se il sistema lo permette)."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class LimitiBase(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class Limiti(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
                _fields_ = [("BasicLimitInformation", LimitiBase), ("IoInfo", ctypes.c_uint64 * 6),
                            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            kernel32 = ctypes.windll.kernel32
            kernel32.CreateJobObjectW.restype = ctypes.c_void_p
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                                         wintypes.DWORD]
            kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            lavoro = kernel32.CreateJobObjectW(None, None)
            limiti = Limiti()
            limiti.BasicLimitInformation.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
            limiti.ProcessMemoryLimit = megabyte * 1024 * 1024
            kernel32.SetInformationJobObject(lavoro, 9, ctypes.byref(limiti), ctypes.sizeof(limiti))
            kernel32.AssignProcessToJobObject(lavoro, kernel32.GetCurrentProcess())
        else:
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (megabyte * 1024 * 1024, megabyte * 1024 * 1024))
    except Exception:  # il tetto è una sicurezza in più: se il sistema non lo permette, restano gli altri controlli
        pass


def _carica(codice):
    import builtins

    controlla(codice)
    sicuri = {nome: getattr(builtins, nome) for nome in BUILTIN_PERMESSI}
    sicuri["__import__"] = _importa
    spazio = {"__builtins__": sicuri, "__name__": "abilita"}
    exec(compile(codice, "abilita", "exec"), spazio)
    return spazio


def _testo(valore, massimo=4000):
    if not isinstance(valore, str):
        raise ErroreAbilita(f"esegui deve restituire un testo, invece ha restituito {type(valore).__name__}")
    return valore[:massimo]


def _lavora(richiesta):
    spazio = _carica(richiesta["codice"])
    aiuto = _Aiuto(richiesta.get("internet", True))
    if richiesta["azione"] == "esegui":
        try:
            return _testo(spazio["esegui"](dict(richiesta.get("argomenti") or {}), aiuto))
        except ErroreAbilita:
            raise
        except Exception as e:
            raise ErroreAbilita(f"si è fermata con l'errore {type(e).__name__}: {e}") from None
    info = {"nome": spazio.get("NOME"), "descrizione": spazio.get("DESCRIZIONE"), "parametri": spazio.get("PARAMETRI"),
            "obbligatori": spazio.get("OBBLIGATORI")}
    prove = spazio.get("PROVE")
    if not isinstance(prove, (list, tuple)) or not 1 <= len(prove) <= 10:
        raise ErroreAbilita("PROVE deve essere una lista da 1 a 10 prove")
    for numero, prova_ in enumerate(prove, 1):
        if not (isinstance(prova_, (list, tuple)) and len(prova_) == 2 and isinstance(prova_[0], dict)
                and isinstance(prova_[1], str)):
            raise ErroreAbilita(f"la prova {numero} deve essere (argomenti, testo atteso)")
        argomenti, atteso = prova_
        try:
            risultato = _testo(spazio["esegui"](dict(argomenti), aiuto))
        except ErroreAbilita:
            raise
        except Exception as e:
            raise ErroreAbilita(f"la prova {numero} con {argomenti} si è fermata con l'errore "
                                f"{type(e).__name__}: {e}") from None
        if atteso.lower() not in risultato.lower():
            raise ErroreAbilita(f"la prova {numero} non passa: con {argomenti} ho ottenuto «{risultato[:300]}», "
                                f"che non contiene «{atteso}»")
    info["prove"] = len(prove)
    return info


def _recinto():
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # per rete.py (con -I la cartella non c'è)
    _limita_memoria()
    try:
        richiesta = json.loads(sys.stdin.read())
        risposta = {"ok": True, "risultato": _lavora(richiesta)}
    except ErroreAbilita as e:
        risposta = {"ok": False, "errore": str(e)}
    except MemoryError:
        risposta = {"ok": False, "errore": "ha usato troppa memoria"}
    except Exception as e:  # anche un'abilità scritta male deve dare una risposta leggibile
        risposta = {"ok": False, "errore": f"{type(e).__name__}: {e}"}
    sys.stdout.write("\n" + json.dumps(risposta, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    _recinto()
