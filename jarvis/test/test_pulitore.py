import random
import unittest

from cervello import PulitoreMarkdown

RISPOSTA = """Certamente, signore. Ecco un elenco:

**Cosa so fare:**

*   Rispondere alle domande 😊.
*   Fare **calcoli**: 2 * 3 = 6, 2*3=6, -5°C, 1. primo

## Conclusione
Sono un *potente* strumento.
---
  - sotto punto **importante** fine"""


def pulisci(pezzi):
    pulitore, uscita = PulitoreMarkdown(), []
    for pezzo in pezzi:
        uscita += pulitore.aggiungi(pezzo)
    return uscita + pulitore.fine()


def con_grassetto(segmenti):
    """Testo con il grassetto tra parentesi quadre, carattere per carattere."""
    return "".join(f"[{c}]" if g else c for t, g in segmenti for c in t).replace("][", "")


class TestPulitore(unittest.TestCase):
    def test_toglie_markdown_ed_emoji(self):
        self.assertEqual(con_grassetto(pulisci([RISPOSTA])), (
            "Certamente, signore. Ecco un elenco:\n\n[Cosa so fare:]\n\n• Rispondere alle domande.\n"
            "• Fare [calcoli]: 2 * 3 = 6, 2*3=6, -5°C, 1. primo\n\n[Conclusione]\nSono un potente strumento.\n\n"
            "  • sotto punto [importante] fine"))

    def test_stesso_risultato_comunque_arrivino_i_pezzi(self):
        atteso = con_grassetto(pulisci([RISPOSTA]))
        for seme in range(200):
            caso, pezzi, i = random.Random(seme), [], 0
            while i < len(RISPOSTA):
                n = caso.randint(1, 6)
                pezzi.append(RISPOSTA[i:i + n])
                i += n
            self.assertEqual(con_grassetto(pulisci(pezzi)), atteso, seme)

    def test_spazi_attorno_alle_emoji(self):
        for testo, atteso in [("fa bello 😊, signore.", "fa bello, signore."), ("Fatto 👍", "Fatto"),
                              ("Ciao 😊 come stai", "Ciao come stai"), ("il prezzo * 3", "il prezzo * 3")]:
            self.assertEqual("".join(t for t, _ in pulisci([testo])), atteso)

    def test_a_capo_dopo_uno_strumento(self):
        p = PulitoreMarkdown()
        uscita = p.aggiungi("\n\n  Controllo il meteo.") + p.a_capo() + p.aggiungi("\n\nEcco il meteo") + p.fine()
        self.assertEqual("".join(t for t, _ in uscita), "Controllo il meteo.\nEcco il meteo")


if __name__ == "__main__":
    unittest.main()
