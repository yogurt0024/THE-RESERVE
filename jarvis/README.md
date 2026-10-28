# Jarvis

Assistente personale ispirato al J.A.R.V.I.S. di Iron Man.
L'intelligenza artificiale gira **tutta sul tuo PC** grazie a Ollama: niente abbonamenti.

## Cosa sa fare

- **Risponde alle domande** in una finestra in stile Jarvis (oppure nel Prompt dei comandi).
- **Memoria permanente**: si ricorda quello che gli dici con "ricordati che..." e anche la conversazione,
  pure dopo averlo chiuso.
- **Informazioni aggiornate da internet**: meteo, Wikipedia e notizie.
- **Azioni sul PC**: apre siti, ricerche Google e programmi, fa calcoli esatti, imposta timer.
- **Diagnostica del PC**: memoria, disco, temperatura della scheda video, batteria.
- **Volume e musica**: alza, abbassa, muto, pausa, canzone successiva o precedente.
- **Ragionamento profondo**: per le domande difficili pensa prima di rispondere (più lento, più preciso).
- **Sa cosa sa fare**: chiedigli "cosa sai fare?" o "quali sono i tuoi limiti?".
- **Un modello tutto suo**: puoi addestrare un modello che ha il carattere di Jarvis
  (vedi [addestramento/README.md](addestramento/README.md)).

Con il modello consigliato (`qwen3:4b-instruct`) usa gli strumenti **da solo**: basta chiedere
"che tempo fa a Cagliari?", "chi era Leonardo da Vinci?", "apri youtube", "quanto fa 128 per 47?",
"metti un timer di 10 minuti per la pasta", "come sta il PC?" o "alza il volume".

## Installazione

Se avevi già la prima versione di Jarvis, Python e Ollama sono già installati: salta ai punti 3 e 4.

1. **Python**: scaricalo da <https://www.python.org/downloads/> e installalo.
   Nella prima schermata spunta **"Add python.exe to PATH"**.
2. **Ollama**: scaricalo da <https://ollama.com/download> e installalo.
3. **Il "cervello"**: premi il tasto Windows, scrivi `cmd`, premi Invio e nella finestra nera scrivi
   queste due righe (una alla volta, aspettando che la prima finisca):

   ```
   ollama pull qwen3:4b-instruct
   ollama pull qwen3:4b
   ```

   Ognuno pesa circa 2,5 GB. Il primo risponde velocemente; il secondo serve solo per il
   ragionamento profondo (se non lo installi, Jarvis funziona lo stesso, senza quella funzione).
4. **Jarvis**: scarica questa cartella `jarvis` sul PC (da GitHub: pulsante verde **Code → Download ZIP**,
   poi estrai lo ZIP). Se stai aggiornando e avevi cambiato `config.json`, ricopia le tue modifiche
   nel nuovo file.

## Avvio

- **Finestra**: doppio clic su **`Jarvis.pyw`**.
- **Se Windows lo blocca** ("Controllo intelligente delle app"): apri la cartella `jarvis`, clicca sulla
  barra dell'indirizzo, scrivi `cmd` e premi Invio. Nella finestra nera scrivi `python jarvis.py`.
- **Senza finestra**, tutto nel Prompt dei comandi: `python jarvis.py --testo`.

Quando chiudi Jarvis, la memoria della scheda video viene liberata, così resta tutta per i giochi.

## Comandi

Puoi parlare normalmente, ma ci sono anche dei comandi rapidi:

| Comando                       | Cosa fa                                             |
|-------------------------------|-----------------------------------------------------|
| `/meteo [città]`              | meteo e previsioni dei prossimi giorni              |
| `/wiki <argomento>`           | cerca su Wikipedia                                  |
| `/notizie [argomento]`        | ultime notizie                                      |
| `/cerca <testo>`              | apre una ricerca Google nel browser                 |
| `/apri <programma o sito>`    | per esempio `/apri blocco note` o `/apri youtube.com` |
| `/calcola <conto>`            | per esempio `/calcola (12+3)*2`                     |
| `/timer <minuti> [messaggio]` | per esempio `/timer 10 pasta`                       |
| `/sistema`                    | diagnostica del PC (memoria, disco, scheda video)   |
| `/chiamami <appellativo>`     | come vuoi essere chiamato (`/chiamami` da solo: nessun appellativo) |
| `/tu` oppure `/lei`           | se Jarvis ti dà del tu o del lei                    |
| `/ricorda <cosa>`             | salva un'informazione nella memoria permanente      |
| `/memoria`                    | mostra cosa ricorda                                 |
| `/dimentica <numero>`         | cancella un ricordo (`/dimentica tutto` li cancella tutti) |
| `/pensa`                      | attiva o spegne il ragionamento profondo            |
| `/nuova`                      | nuova conversazione (la memoria permanente resta)   |
| `/esci`                       | chiude Jarvis                                       |

Nella finestra, il pulsante **Ferma** (o il tasto Esc) interrompe una risposta; nel Prompt dei comandi si usa Ctrl+C.

Anche senza comandi puoi dire **"chiamami capo"** (o il tuo nome), **"non chiamarmi più signore"**,
**"dammi del tu"** o **"dammi del lei"**: Jarvis cambia subito e se lo ricorda anche alla prossima apertura.

## Personalizzare

Apri `config.json` con il Blocco note:

| Impostazione            | Cosa fa                                                         |
|-------------------------|-----------------------------------------------------------------|
| `nome`                  | il nome dell'assistente (per esempio `"Friday"`)                |
| `come_chiamarmi`        | come deve chiamarti (per esempio `"capo"`); vuoto = nessuno     |
| `dai_del`               | `"lei"` (formale, come il vero Jarvis) oppure `"tu"`            |
| `citta`                 | la tua città: la usa per il meteo quando non dici dove          |
| `modello`               | il modello per le risposte normali (vedi sotto)                 |
| `modello_ragionamento`  | il modello per il ragionamento profondo; vuoto = nessuno        |
| `ragionamento`          | `true` per avere il ragionamento profondo già attivo all'avvio  |
| `internet`              | `false` per non usare mai internet (niente meteo, Wikipedia, notizie) |
| `messaggi_da_ricordare` | quanti messaggi recenti tiene a mente                           |
| `programmi`             | i programmi che Jarvis può aprire (vedi sotto)                  |
| `ollama_url`            | indirizzo di Ollama; non va cambiato                            |

Attenzione a lasciare virgolette e virgole come sono.

### Aggiungere programmi

Per aggiungere un programma serve il suo percorso: fai clic destro sul collegamento del programma →
**Proprietà** e copia il campo **Destinazione**. Poi aggiungilo in `programmi`, scrivendo `\\` al posto
di ogni `\`. Per esempio:

```json
"programmi": {
  "blocco note": "notepad",
  "calcolatrice": "calc",
  "curseforge": "C:\\Users\\TuoNome\\AppData\\Local\\Programs\\CurseForge Windows\\CurseForge.exe"
}
```

Poi potrai dire "apri curseforge".

## Quale modello usare

Con una scheda video da 6 GB:

| Modello             | Peso   | Note                                                                 |
|---------------------|--------|----------------------------------------------------------------------|
| `qwen3:4b-instruct` | 2,5 GB | **consigliato per `modello`**: veloce, usa gli strumenti da solo     |
| `qwen3:4b`          | 2,5 GB | **consigliato per `modello_ragionamento`**: ragiona sempre prima di rispondere, quindi è più lento |
| `qwen3:8b`          | 5,2 GB | più intelligente, ma lento: occupa quasi tutta la scheda video       |
| `gemma3:4b`         | 3,3 GB | italiano molto naturale, ma non usa gli strumenti da solo: servono i comandi |

Per cambiarlo: `ollama pull nome-modello` nel Prompt dei comandi, poi cambia `modello` in `config.json`.

Alcuni modelli (come `qwen3:4b`) ragionano sempre, anche quando non serve. Jarvis nasconde quel
ragionamento: nella finestra scompare da solo; nel Prompt dei comandi può comparire una volta,
poi Jarvis impara a nasconderlo.

## Privacy

- L'intelligenza artificiale, la memoria e le conversazioni restano sul tuo PC (nella cartella `dati`).
- Per meteo, Wikipedia e notizie Jarvis si collega a Open-Meteo, Wikipedia e Google News e invia
  solo cosa cercare (per esempio il nome della città). Con `"internet": false` non lo fa mai.

## Limiti

- Non sente e non parla (per ora), non vede lo schermo e non legge i file.
- È un modello piccolo: può sbagliare o inventare. Per le cose importanti controlla sempre.
- Apre solo i programmi elencati in `config.json`.

## Se qualcosa non va

- **"Non riesco a contattare Ollama"**: avvia Ollama dal menu Start e riapri Jarvis.
- **"Il modello ... non è installato"**: esegui il comando `ollama pull` che ti viene mostrato.
- **La finestra non si apre**: avvia con `python jarvis.py` dal Prompt dei comandi per vedere l'errore.
  Se dice che manca tkinter, reinstalla Python lasciando spuntata l'opzione "tcl/tk and IDLE".
- **"Questo modello non sa usare gli strumenti da solo"**: stai usando un modello come `gemma3:4b`;
  usa i comandi oppure passa a `qwen3:4b-instruct`.
