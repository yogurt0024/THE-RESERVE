"""Legge i file tokenizer.json di Hugging Face e trasforma il testo in numeri, solo con Python.

Fa lo stesso lavoro della libreria `tokenizers` (che è scritta in Rust e il Controllo intelligente delle app
potrebbe bloccare) per le configurazioni più comuni: token speciali, normalizzazione, pre-divisione, modelli
BPE, WordLevel e WordPiece, e i token aggiunti all'inizio e alla fine. Se il file usa qualcosa che qui manca,
lo dice invece di sbagliare in silenzio.
"""

import json
import re
import unicodedata


class TokenizzatoreNonSupportato(Exception):
    pass


def carica(percorso):
    """Usa la libreria `tokenizers` se c'è e funziona, altrimenti questa versione in Python."""
    try:
        from tokenizers import Tokenizer

        libreria = Tokenizer.from_file(str(percorso))
        return lambda testo: libreria.encode(testo).ids
    except Exception:  # assente, oppure bloccata da Windows
        return Tokenizzatore(json.loads(open(percorso, encoding="utf-8").read())).codifica


def _schema(pattern):
    if "String" in pattern:
        return re.compile(re.escape(pattern["String"]))
    return re.compile(pattern["Regex"])


class Tokenizzatore:
    def __init__(self, dati):
        self.aggiunti = {t["content"]: t["id"] for t in dati.get("added_tokens", [])}
        self._aggiunti = (re.compile("|".join(re.escape(t) for t in sorted(self.aggiunti, key=len, reverse=True)))
                          if self.aggiunti else None)
        self.normalizzatore = dati.get("normalizer")
        self.pre = dati.get("pre_tokenizer")
        self.modello = dati["model"]
        self.post = dati.get("post_processor")
        self.vocabolario = self.modello.get("vocab", {})
        if isinstance(self.vocabolario, list):  # modelli Unigram: non supportati
            raise TokenizzatoreNonSupportato("modello Unigram")
        self._fusioni = {}
        tipo = self.modello.get("type") or ("BPE" if "merges" in self.modello else None)
        self._tipo = tipo
        if tipo == "BPE":
            for rango, fusione in enumerate(self.modello.get("merges", [])):
                a, b = fusione.split(" ", 1) if isinstance(fusione, str) else fusione
                self._fusioni[(a, b)] = rango
        elif tipo not in ("WordLevel", "WordPiece"):
            raise TokenizzatoreNonSupportato(f"modello {tipo}")
        self._controlla(self.normalizzatore, _NORMALIZZATORI, "normalizzatore")
        self._controlla(self.pre, _PRE, "pre_tokenizer")
        self._controlla(self.post, _POST, "post_processor")

    @staticmethod
    def _controlla(parte, ammessi, nome):
        if parte is None:
            return
        if parte["type"] not in ammessi:
            raise TokenizzatoreNonSupportato(f"{nome} {parte['type']}")
        for figlio in parte.get("normalizers", []) + parte.get("pretokenizers", []) + parte.get("processors", []):
            Tokenizzatore._controlla(figlio, ammessi, nome)

    def codifica(self, testo):
        ids = []
        for pezzo, aggiunto in self._dividi_aggiunti(testo):
            if aggiunto:
                ids.append(self.aggiunti[pezzo])
                continue
            for parola in self._pre_dividi(self._normalizza(self.normalizzatore, pezzo)):
                ids += self._modello(parola)
        return self._post(ids)

    def _dividi_aggiunti(self, testo):
        if self._aggiunti is None:
            yield testo, False
            return
        inizio = 0
        for trovato in self._aggiunti.finditer(testo):
            if trovato.start() > inizio:
                yield testo[inizio:trovato.start()], False
            yield trovato.group(), True
            inizio = trovato.end()
        if inizio < len(testo):
            yield testo[inizio:], False

    def _normalizza(self, n, testo):
        if n is None:
            return testo
        tipo = n["type"]
        if tipo == "Sequence":
            for figlio in n["normalizers"]:
                testo = self._normalizza(figlio, testo)
            return testo
        if tipo == "Lowercase":
            return testo.lower()
        if tipo in ("NFD", "NFKD", "NFC", "NFKC"):
            return unicodedata.normalize(tipo, testo)
        if tipo == "Replace":
            return _schema(n["pattern"]).sub(lambda _: n["content"], testo)
        if tipo == "Prepend":
            return n["prepend"] + testo if testo else testo
        if tipo == "Strip":
            if n.get("strip_left", True):
                testo = testo.lstrip()
            return testo.rstrip() if n.get("strip_right", True) else testo
        if tipo == "StripAccents":
            return "".join(c for c in testo if not unicodedata.combining(c))
        raise TokenizzatoreNonSupportato(f"normalizzatore {tipo}")

    def _pre_dividi(self, testo, p=None, primo=True):
        p = self.pre if p is None and primo else p
        if p is None:
            return [testo] if testo else []
        tipo = p["type"]
        if tipo == "Sequence":
            pezzi = [testo]
            for figlio in p["pretokenizers"]:
                pezzi = [s for pezzo in pezzi for s in self._pre_dividi(pezzo, figlio, False)]
            return pezzi
        if tipo == "Whitespace":
            return re.findall(r"\w+|[^\w\s]+", testo)
        if tipo == "WhitespaceSplit":
            return testo.split()
        if tipo == "Punctuation":
            return _dividi(testo, re.compile(r"[^\w\s]"), p.get("behavior", "Isolated"))
        if tipo == "Digits":
            return _dividi(testo, re.compile(r"\d" if p.get("individual_digits") else r"\d+"), "Isolated")
        if tipo == "Split":
            return _dividi(testo, _schema(p["pattern"]), p.get("behavior", "Isolated"), p.get("invert", False))
        if tipo == "Metaspace":
            sostituto = p.get("replacement", "▁")
            testo = testo.replace(" ", sostituto)
            schema = p.get("prepend_scheme", "always" if p.get("add_prefix_space", True) else "never")
            if schema != "never" and not testo.startswith(sostituto):
                testo = sostituto + testo
            if not p.get("split", True):
                return [testo]
            return _dividi(testo, re.compile(re.escape(sostituto)), "MergedWithNext")
        raise TokenizzatoreNonSupportato(f"pre_tokenizer {tipo}")

    def _modello(self, parola):
        m = self.modello
        sconosciuto = m.get("unk_token")
        if self._tipo == "WordLevel":
            return [self.vocabolario.get(parola, self.vocabolario.get(sconosciuto))]
        if self._tipo == "WordPiece":
            return self._wordpiece(parola)
        if m.get("ignore_merges") and parola in self.vocabolario:
            return [self.vocabolario[parola]]
        prefisso = m.get("continuing_subword_prefix") or ""
        suffisso = m.get("end_of_word_suffix") or ""
        simboli = [(prefisso if i else "") + c + (suffisso if i == len(parola) - 1 else "") for i, c in enumerate(parola)]
        while len(simboli) > 1:
            migliore = min(range(len(simboli) - 1),
                           key=lambda i: self._fusioni.get((simboli[i], simboli[i + 1]), float("inf")))
            coppia = (simboli[migliore], simboli[migliore + 1])
            if coppia not in self._fusioni:
                break
            unito = coppia[0] + coppia[1][len(prefisso):]
            nuovi, i = [], 0
            while i < len(simboli):
                if i < len(simboli) - 1 and (simboli[i], simboli[i + 1]) == coppia:
                    nuovi.append(unito)
                    i += 2
                else:
                    nuovi.append(simboli[i])
                    i += 1
            simboli = nuovi
        ids = []
        for simbolo in simboli:
            if simbolo in self.vocabolario:
                ids.append(self.vocabolario[simbolo])
            elif m.get("byte_fallback") and all(f"<0x{b:02X}>" in self.vocabolario for b in simbolo.encode()):
                ids += [self.vocabolario[f"<0x{b:02X}>"] for b in simbolo.encode()]
            elif sconosciuto is not None:
                if not (m.get("fuse_unk") and ids and ids[-1] == self.vocabolario[sconosciuto]):
                    ids.append(self.vocabolario[sconosciuto])
        return ids

    def _wordpiece(self, parola):
        m = self.modello
        prefisso = m.get("continuing_subword_prefix", "##")
        sconosciuto = self.vocabolario[m.get("unk_token", "[UNK]")]
        if len(parola) > m.get("max_input_chars_per_word", 100):
            return [sconosciuto]
        ids, inizio = [], 0
        while inizio < len(parola):
            fine = len(parola)
            while fine > inizio:
                pezzo = (prefisso if inizio else "") + parola[inizio:fine]
                if pezzo in self.vocabolario:
                    ids.append(self.vocabolario[pezzo])
                    break
                fine -= 1
            else:
                return [sconosciuto]
            inizio = fine
        return ids

    def _post(self, ids, p=None, primo=True):
        p = self.post if p is None and primo else p
        if p is None:
            return ids
        tipo = p["type"]
        if tipo == "Sequence":
            for figlio in p["processors"]:
                ids = self._post(ids, figlio, False)
            return ids
        if tipo == "TemplateProcessing":
            risultato = []
            for elemento in p["single"]:
                if "Sequence" in elemento:
                    risultato += ids
                else:
                    risultato += p["special_tokens"][elemento["SpecialToken"]["id"]]["ids"]
            return risultato
        if tipo in ("BertProcessing", "RobertaProcessing"):
            return [p["cls"][1]] + ids + [p["sep"][1]]
        return ids  # ByteLevel non cambia i numeri


def _dividi(testo, schema, comportamento, inverti=False):
    """Divide il testo come fa `tokenizers` con i suoi comportamenti (Isolated, Removed, Merged...)."""
    if inverti and comportamento == "Contiguous":
        raise TokenizzatoreNonSupportato("Split Contiguous invertito")
    pezzi, inizio = [], 0
    for trovato in schema.finditer(testo):
        if trovato.start() == trovato.end():
            continue
        pezzi.append((testo[inizio:trovato.start()], False))
        pezzi.append((trovato.group(), True))
        inizio = trovato.end()
    pezzi.append((testo[inizio:], False))
    pezzi = [(p, (not c) if inverti else c) for p, c in pezzi if p]
    if comportamento == "Removed":
        return [p for p, c in pezzi if not c]
    if comportamento == "Isolated":
        return [p for p, _ in pezzi]
    risultato = []
    if comportamento == "MergedWithPrevious":
        libero = False  # l'ultimo pezzo può ancora prendersi un separatore
        for p, c in pezzi:
            if c and libero:
                risultato[-1] += p
                libero = False
            else:
                risultato.append(p)
                libero = not c
    elif comportamento == "MergedWithNext":
        attesa = None  # un separatore che aspetta il pezzo dopo
        for p, c in pezzi:
            if c:
                if attesa is not None:
                    risultato.append(attesa)
                attesa = p
            else:
                risultato.append((attesa or "") + p)
                attesa = None
        if attesa is not None:
            risultato.append(attesa)
    elif comportamento == "Contiguous":
        for p, c in pezzi:
            if risultato and c and risultato[-1][1]:
                risultato[-1] = (risultato[-1][0] + p, True)
            else:
                risultato.append((p, c))
        risultato = [p for p, _ in risultato]
    else:
        raise TokenizzatoreNonSupportato(f"comportamento {comportamento}")
    return risultato


_NORMALIZZATORI = {"Sequence", "Lowercase", "NFD", "NFKD", "NFC", "NFKC", "Replace", "Prepend", "Strip", "StripAccents"}
_PRE = {"Sequence", "Whitespace", "WhitespaceSplit", "Punctuation", "Digits", "Split", "Metaspace"}
_POST = {"Sequence", "TemplateProcessing", "BertProcessing", "RobertaProcessing", "ByteLevel"}
