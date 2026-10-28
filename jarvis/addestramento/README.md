# Il tuo modello Jarvis

Qui si crea un modello addestrato apposta per **essere** Jarvis, invece di un modello generico a cui si
chiede di comportarsi come lui. Si parte dal cervello veloce, Qwen3.5-4B (lo stesso di `qwen3.5:4b`), e gli si
insegnano centinaia di conversazioni d'esempio, comprese quelle in cui passa le domande difficili al cervello
grande.

## Cosa impara e cosa no

**Impara:**
- il carattere di Jarvis: dà del lei, è calmo, elegante, con un'ironia asciutta;
- a rispondere in modo breve e preciso, aggiungendo un consiglio quando serve (l'ombrello, una pausa);
- quando usare gli strumenti e come raccontarne i risultati (meteo, calcoli, timer, diagnostica...);
- a essere onesto sui propri limiti e a rifiutare con garbo le richieste pericolose.

**Non impara:**
- abilità nuove: quelle vengono dal codice di Jarvis (gli strumenti);
- conoscenze nuove o una grande intelligenza in più: resta un modello piccolo.

## Cosa c'è in questa cartella

| File                         | A cosa serve                                                        |
|------------------------------|---------------------------------------------------------------------|
| `dataset.jsonl`              | gli esempi di addestramento, già pronti                             |
| `Jarvis_addestramento.ipynb` | il programma che addestra il modello su Google Colab                |
| `crea_modello.py`            | crea il modello `jarvis` in Ollama dal file scaricato               |
| `dialoghi.py`                | i dialoghi scritti a mano: modificali per cambiare il carattere     |
| `genera_dataset.py`          | rigenera `dataset.jsonl` dopo aver cambiato i dialoghi              |

## Cosa serve

- Un account Google (gratis). L'addestramento usa una scheda video di Google, gratis, su Google Colab:
  la tua 3050 non basterebbe.
- Circa un'ora e mezza, con la pagina di Colab aperta.
- Il modello `qwen3.5:4b` già installato in Ollama.

## Passo 1: addestramento su Google Colab

1. Apri <https://colab.research.google.com> e accedi con il tuo account Google.
2. Menu **File → Carica blocco note** e scegli `Jarvis_addestramento.ipynb` (in questa cartella).
3. Menu **Runtime → Cambia tipo di runtime**, scegli **T4 GPU** e premi **Salva**.
4. Menu **Runtime → Esegui tutto**.
5. Quando compare il pulsante **Scegli file**, carica `dataset.jsonl` (in questa cartella).
6. Quando chiede di collegare **Google Drive**, accetta: lì verrà salvato il modello.
7. Aspetta, lasciando la pagina aperta. Al punto 7 del notebook vedrai le prime risposte del nuovo Jarvis.
8. Alla fine compare **"Fatto!"**.

**Se qualcosa va storto con Qwen3.5** (è un modello recente e questa strada non ho potuto provarla), nella
cella 4 del notebook cambia `BASE = "qwen3.5"` in `BASE = "qwen3"` e rifai **Runtime → Esegui tutto**: è la
strada già collaudata, che parte da `qwen3:4b-instruct` (installalo con `ollama pull qwen3:4b-instruct`).
Mandami anche il messaggio di errore, così sistemo la strada di Qwen3.5.

## Passo 2: scarica il modello

Apri Google Drive: nella cartella **Jarvis** trovi `jarvis-qwen3.5.gguf` (circa 3 GB). Scaricalo e mettilo in
questa cartella (`jarvis/addestramento`).

## Passo 3: crealo in Ollama

Apri questa cartella, clicca sulla barra dell'indirizzo, scrivi `cmd` e premi Invio. Poi scrivi:

```
python crea_modello.py
```

## Passo 4: usalo

In `config.json` (nella cartella `jarvis`) scrivi `"modello": "jarvis"` e riapri Jarvis.
Il cervello grande resta `qwen3.6:35b-a3b`. Se il nuovo Jarvis non ti convince, rimetti
`"modello": "qwen3.5:4b"`: puoi cambiare quando vuoi.

## Renderlo ancora più tuo

Il modello addestrato dà del **lei**, come il vero Jarvis: gli esempi sono scritti così. Con `"dai_del": "tu"`
proverà a darti del tu, ma a volte potrebbe tornare al lei. Come chiamarti, invece, lo puoi cambiare
liberamente ("chiamami capo"): gli esempi usano appellativi diversi apposta.

- Apri `dialoghi.py` e aggiungi o cambia i dialoghi. `{T}` diventa ", signore" (o come hai scelto di essere
  chiamato in `config.json`).
- Poi rigenera gli esempi con `python genera_dataset.py` e ripeti dal passo 1.
- Più dialoghi belli scrivi, più il carattere diventa solido. Scrivili con parole tue: le battute dei film
  sono protette dal diritto d'autore.

## Se qualcosa non va

- **"Nessuna GPU"**: controlla il punto 3. Se Colab dice che le GPU gratuite non sono disponibili, riprova
  più tardi: l'uso gratuito ha dei limiti giornalieri.
- **La pagina si è disconnessa**: menu **Runtime → Esegui tutto** e si riparte.
- **"Serve il modello di partenza"**: scrivi il comando `ollama pull` che ti viene mostrato.
