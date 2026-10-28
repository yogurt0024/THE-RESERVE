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
- **Due cervelli sul tuo PC**: uno veloce per tutto il resto e uno grande per le domande difficili,
  gratis e privati (vedi [I cervelli di Jarvis](#i-cervelli-di-jarvis)). Claude è una riserva opzionale.
- **Un modello tutto suo**: puoi addestrare un modello che ha il carattere di Jarvis
  (vedi [addestramento/README.md](addestramento/README.md)).

Con i modelli consigliati usa gli strumenti **da solo**: basta chiedere
"che tempo fa a Cagliari?", "chi era Leonardo da Vinci?", "apri youtube", "quanto fa 128 per 47?",
"metti un timer di 10 minuti per la pasta", "come sta il PC?" o "alza il volume".

## Installazione

Se avevi già la prima versione di Jarvis, Python e Ollama sono già installati: salta ai punti 3 e 4.

1. **Python**: scaricalo da <https://www.python.org/downloads/> e installalo.
   Nella prima schermata spunta **"Add python.exe to PATH"**.
2. **Ollama**: scaricalo da <https://ollama.com/download> e installalo.
3. **I "cervelli"**: premi il tasto Windows, scrivi `cmd`, premi Invio e nella finestra nera scrivi
   queste due righe (una alla volta, aspettando che la prima finisca):

   ```
   ollama pull qwen3.5:4b
   ollama pull qwen3.6:35b-a3b
   ```

   Il primo (3,3 GB) è il cervello veloce. Il secondo (24 GB) è il cervello grande per le domande
   difficili: servono almeno 25 GB liberi sul disco e 32 GB di RAM. Se non lo installi, Jarvis funziona
   lo stesso, solo meno intelligente sulle domande difficili.
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
| `/cervello <modalità>`        | `locale`, `ibrido` o `claude` (vedi sotto)          |
| `/chiave`                     | inserisci la chiave API di Claude                   |
| `/costi`                      | quanto hai speso con Claude                         |
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
| `modello_grande`        | il cervello grande per le domande difficili; vuoto = nessuno   |
| `ragionamento`          | `true` per avere il ragionamento profondo già attivo all'avvio  |
| `cervello`              | `"locale"`, `"ibrido"` o `"claude"` (vedi sotto)                |
| `modello_claude`        | quale modello di Claude usare (predefinito `claude-opus-5-5`)   |
| `sforzo_claude`         | quanto ragiona Claude: `low`, `medium`, `high` (più alto = più preciso e più caro) |
| `mostra_costi`          | `false` per non vedere il costo di ogni risposta di Claude      |
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

## I cervelli di Jarvis

| Cervello   | Modello              | Peso   | A cosa serve                                                          |
|------------|----------------------|--------|-----------------------------------------------------------------------|
| veloce     | `qwen3.5:4b`         | 3,3 GB | risponde a quasi tutto, usa gli strumenti; sta tutto nella scheda video |
| grande     | `qwen3.6:35b-a3b`    | 24 GB  | le domande difficili e il ragionamento profondo; usa scheda video e RAM insieme |
| addestrato | `jarvis`             | 3,3 GB | il cervello veloce con il carattere di Jarvis (vedi [addestramento](addestramento/README.md)) |

Il cervello grande è un modello "MoE": è enorme, ma per ogni parola ne usa solo una piccola parte,
per questo gira anche sul tuo PC. È più lento del veloce (qualche secondo per iniziare, poi alcune parole
al secondo) e occupa molta RAM: **mentre giochi chiudi Jarvis**, così la memoria torna libera.

Il cervello veloce decide da solo quando una domanda è difficile e la passa al grande
("Passo la domanda al cervello grande..."). Con **Ragionamento profondo** attivo risponde sempre il grande,
e ragiona prima di rispondere.

Per cambiare modello: `ollama pull nome-modello` nel Prompt dei comandi, poi cambia `modello` o
`modello_grande` in `config.json`. Alcuni modelli ragionano sempre, anche quando non serve: Jarvis
nasconde quel ragionamento.

### Le tre modalità (`/cervello ...`)

| Modalità  | Come funziona                                                                              |
|-----------|--------------------------------------------------------------------------------------------|
| `locale`  | **predefinita**: cervello veloce e cervello grande, tutto sul PC, gratis e privato         |
| `ibrido`  | cervello veloce sul PC; le domande difficili e il ragionamento profondo passano a Claude    |
| `claude`  | risponde sempre Claude                                                                     |

### Claude (riserva opzionale)

Claude è più intelligente anche del cervello grande, ma funziona via internet e si paga a consumo.
È spento finché non scrivi `/cervello ibrido` o `/cervello claude`.

**Come prepararlo:**
1. Nel Prompt dei comandi: `python -m pip install anthropic`.
2. Su <https://console.anthropic.com> crea una chiave API. Lì imposta anche un **limite di spesa
   mensile**, così non puoi spendere più di quanto vuoi.
3. In Jarvis scrivi `/chiave` e incollala. Resta salvata solo sul tuo PC, in `dati/chiave_claude.txt`.
   **Non mandarla mai a nessuno e non incollarla in chat.**

**Quanto costa:** una risposta normale costa di solito meno di un centesimo di dollaro, una lunga con
ricerche sul web qualche centesimo. Dopo ogni risposta Jarvis mostra una stima del costo; `/costi`
mostra il totale del mese. Il conto preciso è sempre su console.anthropic.com. Con Claude, Jarvis può
anche **cercare sul web** davvero, se la ricerca web è attiva nelle impostazioni del tuo account.

## Prova di compatibilità

Le prossime funzioni (voce, parola "Jarvis", webcam) hanno bisogno di librerie che il Controllo
intelligente delle app di Windows potrebbe bloccare. Per scoprirlo, nella cartella `jarvis`:

```
python prova_compatibilita.py
```

Ci vogliono 5-15 minuti. Alla fine il riepilogo è in `dati/compatibilita.txt`: copialo e mandalo.
Non contiene la tua chiave API.

## Test automatici

Per controllare che tutto funzioni dopo una modifica, nella cartella `jarvis`:

```
python -m unittest
```

Usano Ollama, Claude e internet finti: non costano niente e non toccano i tuoi dati.

## Privacy

- Con il cervello `locale`, l'intelligenza artificiale, la memoria e le conversazioni restano sul tuo PC
  (nella cartella `dati`).
- Quando risponde **Claude**, la conversazione recente e le tue informazioni in memoria vengono inviate
  ad Anthropic per ottenere la risposta. Con `/cervello locale` non succede mai.
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
  usa i comandi oppure passa a `qwen3.5:4b`.
