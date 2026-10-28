"""Prove della voce, con un motore finto al posto di quello vero e senza altoparlanti."""

import threading
import time
import unittest
from unittest import mock

import voce

try:
    import numpy as np
except ImportError:
    np = None


class TestTestoPerLaVoce(unittest.TestCase):
    def test_simboli_e_sigle(self):
        self.assertEqual(voce.per_la_voce("A Cagliari ci sono 22°C e l'umidità è al 60%."),
                         "A Cagliari ci sono 22 gradi e l'umidità è al 60 per cento.")
        self.assertEqual(voce.per_la_voce("Costa 15 € e pesa 2 GB, vedi https://example.com"),
                         "Costa 15 euro e pesa 2 giga, vedi il link")
        self.assertEqual(voce.per_la_voce("- primo punto\n- **secondo**"), "primo punto secondo")

    def test_frasi(self):
        self.assertEqual(voce.dividi_frasi("Certo, signore. Sono le 14:30! Altro?\nEcco"),
                         ["Certo, signore.", "Sono le 14:30!", "Altro?", "Ecco"])


@unittest.skipIf(np is None, "numpy non installato")
class TestEffetto(unittest.TestCase):
    def test_audio_cortissimo(self):
        self.assertEqual(len(voce.effetto_jarvis(np.ones(10, dtype=np.float32), 22050)), 10 + 22050 // 4)

    def test_effetto(self):
        audio = np.sin(np.linspace(0, 2000, 22050)).astype(np.float32)
        uscita = voce.effetto_jarvis(audio, 22050, 0.6)
        self.assertGreater(len(uscita), len(audio))  # c'è la coda dell'eco
        self.assertAlmostEqual(float(np.max(np.abs(uscita))), 0.89, places=3)
        self.assertIs(voce.effetto_jarvis(audio, 22050, 0).dtype, np.dtype(np.float32))
        self.assertEqual(len(voce.effetto_jarvis(audio, 22050, 0)), len(audio))


class MotoreFinto:
    def sintetizza(self, testo):
        return np.sin(np.arange(1600, dtype=np.float32)), 16000


@unittest.skipIf(np is None, "numpy non installato")
class TestVoce(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(voce, "carica_motore", lambda *argomenti: MotoreFinto())
        patch.start()
        self.addCleanup(patch.stop)
        self.dette = []
        self.cambi = []
        self.problemi = []
        self.addCleanup(lambda: self.assertEqual(self.problemi, []))
        self.sblocca = threading.Event()
        self.sblocca.set()

    def riproduci(self, audio, frequenza, interrompi):
        self.dette.append(len(audio))
        while not self.sblocca.is_set():
            if interrompi.wait(0.01):
                return

    def crea(self, **config):
        impostazioni = {"come_chiamarmi": "signore", "dai_del": "lei", "limite_voce": 60}
        impostazioni.update(config)
        v = voce.Voce(impostazioni, avvisa=self.problemi.append, al_cambio=self.cambi.append,
                      riproduci=self.riproduci)
        # Si registra il testo di ogni frase quando la voce la mette in fila per essere letta.
        originale = v._da_dire.put
        v._da_dire.put = lambda elemento: (self.frasi.append(elemento[1]), originale(elemento))
        self.frasi = []
        return v

    def aspetta(self, v):
        for _ in range(200):
            if not v.sta_parlando:
                return
            time.sleep(0.01)
        self.fail("la voce non ha finito di parlare")

    def test_risposta_a_pezzi_e_limite(self):
        v = self.crea()
        v.inizia()
        for pezzo in ["Buongiorno, sig", "nore. Oggi a Cagliari ci sono 22°C. ",
                      "Domani pioverà parecchio, quindi le consiglio l'ombrello. E poi altro."]:
            v.aggiungi(pezzo)
        v.finisci()
        self.aspetta(v)
        self.assertEqual(self.frasi, ["Buongiorno, signore.", "Oggi a Cagliari ci sono 22 gradi.",
                                      "Il resto lo trova sullo schermo, signore."])
        self.assertEqual(self.cambi[0], True)
        self.assertEqual(self.cambi[-1], False)

    def test_zitto(self):
        v = self.crea(limite_voce=1000)
        self.sblocca.clear()  # la prima frase resta "in riproduzione" finché non la si interrompe
        v.di("Prima frase. Seconda frase. Terza frase.")
        time.sleep(0.1)
        self.assertTrue(v.sta_parlando)
        v.zitto()
        self.aspetta(v)
        self.assertEqual(len(self.dette), 1)  # solo la prima frase, interrotta a metà
        v.aggiungi("Questa non va detta.")  # dopo zitto() il resto della risposta si ignora
        v.finisci()
        self.assertNotIn("Questa non va detta.", self.frasi)

    def test_errore_della_voce(self):
        avvisi = []

        def rotta(*argomenti):
            raise voce.ErroreVoce("manca la libreria piper")

        with mock.patch.object(voce, "carica_motore", rotta):
            v = voce.Voce({}, avvisa=avvisi.append, riproduci=self.riproduci)
            v.di("Ciao. Come va?")
            self.aspetta(v)
        self.assertEqual(avvisi, ["La voce non funziona: manca la libreria piper"])  # una volta sola


if __name__ == "__main__":
    unittest.main()


def _crea_chatterbox_finto(cartella):
    """Quattro modelli ONNX minuscoli con gli stessi nomi, ingressi e uscite di quelli veri di Chatterbox.

    Il modello linguistico "dice" i pezzi di voce 20, 21, 22... (la lunghezza della conversazione) e si ferma
    dopo cinque; il decodificatore trasforma ogni pezzo in dieci campioni uguali al numero del pezzo / 1000.
    """
    import onnx
    from onnx import TensorProto as T
    from onnx import helper as h
    from onnx import numpy_helper
    from tokenizers import Tokenizer, models, processors, trainers

    (cartella / "onnx").mkdir(parents=True)

    def costante(nome, valore):
        return h.make_node("Constant", [], [nome], value=numpy_helper.from_array(np.array(valore), nome + "_v"))

    def salva(nome, nodi, ingressi, uscite):
        modello = h.make_model(h.make_graph(nodi, nome, ingressi, uscite), opset_imports=[h.make_opsetid("", 17)],
                               ir_version=8)
        onnx.save(modello, str(cartella / "onnx" / nome))

    salva("speech_encoder.onnx", [
        costante("audio_features", np.zeros((1, 3, 8), dtype=np.float32)),
        costante("audio_tokens", np.array([[1, 2, 3, 4]], dtype=np.int64)),
        costante("speaker_embeddings", np.ones((1, 192), dtype=np.float32)),
        costante("speaker_features", np.ones((1, 20, 80), dtype=np.float32)),
    ], [h.make_tensor_value_info("audio_values", T.FLOAT, [1, "n"])],
        [h.make_tensor_value_info(n, t, None) for n, t in [("audio_features", T.FLOAT), ("audio_tokens", T.INT64),
                                                            ("speaker_embeddings", T.FLOAT),
                                                            ("speaker_features", T.FLOAT)]])
    salva("embed_tokens.onnx", [
        h.make_node("Cast", ["input_ids"], ["f"], to=T.FLOAT),
        costante("asse", np.array([2], dtype=np.int64)),
        h.make_node("Unsqueeze", ["f", "asse"], ["u"]),
        costante("uni", np.ones(8, dtype=np.float32)),
        h.make_node("Mul", ["u", "uni"], ["m"]),
        h.make_node("Add", ["m", "exaggeration"], ["inputs_embeds"]),
    ], [h.make_tensor_value_info("input_ids", T.INT64, [1, "n"]),
        h.make_tensor_value_info("position_ids", T.INT64, [1, "n"]),
        h.make_tensor_value_info("exaggeration", T.FLOAT, [1])],
        [h.make_tensor_value_info("inputs_embeds", T.FLOAT, [1, "n", 8])])
    nodi = [
        h.make_node("Shape", ["attention_mask"], ["forma"]),
        costante("uno", np.array([1], dtype=np.int64)),
        h.make_node("Gather", ["forma", "uno"], ["t"]),
        costante("limite", np.array([3 + 7 + 5], dtype=np.int64)),  # condizionamento + testo + cinque pezzi
        h.make_node("Less", ["t", "limite"], ["presto"]),
        costante("fine", np.array([6562], dtype=np.int64)),
        h.make_node("Where", ["presto", "t", "fine"], ["scelto"]),
        costante("profondita", np.array(8194, dtype=np.int64)),
        costante("valori", np.array([0.0, 10.0], dtype=np.float32)),
        h.make_node("OneHot", ["scelto", "profondita", "valori"], ["unico"]),
        h.make_node("Shape", ["inputs_embeds"], ["forma_e"], end=2),
        costante("v", np.array([8194], dtype=np.int64)),
        h.make_node("Concat", ["forma_e", "v"], ["forma_l"], axis=0),
        h.make_node("Expand", ["unico", "forma_l"], ["logits"]),
        costante("forma_kv", np.array([1, -1, 2, 4], dtype=np.int64)),
        h.make_node("Reshape", ["inputs_embeds", "forma_kv"], ["r"]),
        h.make_node("Transpose", ["r"], ["tr"], perm=[0, 2, 1, 3]),
        h.make_node("Cast", ["tr"], ["nuovo"], to=T.FLOAT16),
    ]
    ingressi = [h.make_tensor_value_info("inputs_embeds", T.FLOAT, [1, "s", 8]),
                h.make_tensor_value_info("attention_mask", T.INT64, [1, "t"])]
    uscite = [h.make_tensor_value_info("logits", T.FLOAT, [1, "s", 8194])]
    for strato in range(2):
        for kv in ("key", "value"):
            nodi.append(h.make_node("Concat", [f"past_key_values.{strato}.{kv}", "nuovo"],
                                    [f"present.{strato}.{kv}"], axis=2))
            ingressi.append(h.make_tensor_value_info(f"past_key_values.{strato}.{kv}", T.FLOAT16,
                                                     ["batch", 2, "past", 4]))
            uscite.append(h.make_tensor_value_info(f"present.{strato}.{kv}", T.FLOAT16, None))
    salva("language_model_q4f16.onnx", nodi, ingressi, uscite)
    salva("conditional_decoder.onnx", [
        h.make_node("Cast", ["speech_tokens"], ["f"], to=T.FLOAT),
        costante("asse", np.array([2], dtype=np.int64)),
        h.make_node("Unsqueeze", ["f", "asse"], ["u"]),
        costante("dieci", np.full(10, 0.001, dtype=np.float32)),
        h.make_node("Mul", ["u", "dieci"], ["m"]),
        costante("piatto", np.array([1, -1], dtype=np.int64)),
        h.make_node("Reshape", ["m", "piatto"], ["waveform"]),
    ], [h.make_tensor_value_info("speech_tokens", T.INT64, [1, "l"]),
        h.make_tensor_value_info("speaker_embeddings", T.FLOAT, [1, 192]),
        h.make_tensor_value_info("speaker_features", T.FLOAT, [1, "f", 80])],
        [h.make_tensor_value_info("waveform", T.FLOAT, [1, "w"])])

    speciali = ["[START]", "[STOP]", "[UNK]", "[SPACE]", "[it]"]
    tokenizzatore = Tokenizer(models.BPE(unk_token="[UNK]"))
    tokenizzatore.train_from_iterator(["ciao a tutti, pronto. sì"], trainers.BpeTrainer(vocab_size=60,
                                                                                         special_tokens=speciali))
    tokenizzatore.post_processor = processors.TemplateProcessing(
        single="[START] $A [STOP]", special_tokens=[("[START]", 0), ("[STOP]", 1)])
    tokenizzatore.save(str(cartella / "tokenizer.json"))
    (cartella / ".completo").write_text("onnx/language_model_q4f16.onnx\n", encoding="utf-8")
    voce.salva_wav(cartella / "riferimento.wav", np.sin(np.arange(24000) / 10).astype(np.float32), 24000)


try:
    import onnx  # noqa: F401
    import onnxruntime  # noqa: F401
    import tokenizers  # noqa: F401
    FINTO_POSSIBILE = np is not None
except ImportError:
    FINTO_POSSIBILE = False


@unittest.skipUnless(FINTO_POSSIBILE, "servono numpy, onnx, onnxruntime e tokenizers")
class TestChatterbox(unittest.TestCase):
    def test_dal_testo_alla_voce(self):
        import tempfile
        from pathlib import Path

        cartella = Path(tempfile.mkdtemp())
        _crea_chatterbox_finto(cartella)
        motore = voce._Chatterbox(cartella, voce.VOCI["espressiva"], 1.0, {"emozione_voce": 0.7})
        self.assertEqual(motore._numeri("Ciao")[:2], [0, 4])  # [START], poi la lingua [it]
        audio, frequenza = motore.sintetizza("Ciao a tutti")
        self.assertEqual(frequenza, 24000)
        # 4 pezzi della voce di riferimento + 5 generati (dopo il condizionamento e i 7 token del testo).
        pezzi = np.round(audio[::10] * 1000).astype(int).tolist()
        self.assertEqual(pezzi, [1, 2, 3, 4, 10, 11, 12, 13, 14])
        self.assertEqual(motore._numeri("Ciao a tutti"), motore._numeri("ciao a tutti."))

    def test_tokenizzatore_in_python_uguale(self):
        import json
        import tempfile
        from pathlib import Path

        import tokenizzatore

        cartella = Path(tempfile.mkdtemp())
        _crea_chatterbox_finto(cartella)
        dati = json.loads((cartella / "tokenizer.json").read_text(encoding="utf-8"))
        libreria = tokenizzatore.carica(cartella / "tokenizer.json")
        python = tokenizzatore.Tokenizzatore(dati).codifica
        for testo in ["[it]ciao[SPACE]a[SPACE]tutti.", "[it]zzz", "[it]pronto?"]:
            self.assertEqual(python(testo), libreria(testo))
