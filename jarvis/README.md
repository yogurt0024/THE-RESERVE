# Jarvis

Assistente personale ispirato al J.A.R.V.I.S. di Iron Man.
L'intelligenza artificiale gira **tutta sul tuo PC** grazie a Ollama: niente abbonamenti.

## Cosa sa fare

- **Ti sente e ti parla**: è sempre in ascolto, basta dire "Jarvis, ..." (vedi [Voce e ascolto](#voce-e-ascolto)).
  Capisce anche da solo quando parli con lui senza chiamarlo, e interviene se vede che ti serve aiuto.
  Risponde con una voce espressiva che recita, e si interrompe se gli dici "Jarvis, basta".
- **Risponde alle domande** in una finestra in stile Jarvis (oppure nel Prompt dei comandi).
- **Memoria permanente**: si ricorda quello che gli dici con "ricordati che..." e anche la conversazione,
  pure dopo averlo chiuso.
- **Informazioni aggiornate da internet**: meteo, Wikipedia e notizie.
- **Azioni sul PC**: apre siti, ricerche Google e programmi, fa calcoli esatti, imposta timer.
- **Diagnostica del PC**: memoria, disco, temperatura della scheda video, batteria.
- **Volume e musica**: alza, abbassa, muto, pausa, canzone successiva o precedente.
- **Lavora in background**: i lavori lunghi li svolge mentre tu fai altro, e quando ha finito te lo dice a voce
  e con una notifica di Windows (vedi [Compiti in background](#compiti-in-background)).
- **Modalità gioco**: "Jarvis, modalità gioco" e la scheda video resta tutta al gioco.
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
   poi estrai lo ZIP). Se stai aggiornando, copia nella cartella nuova la cartella `dati` di quella vecchia
   (memoria, conversazioni, chiave e modelli già scaricati) e ricopia le tue modifiche a `config.json`.
5. **Voce e ascolto**: servono **Python 3.12** (le librerie della voce non esistono ancora per le versioni
   più nuove) e alcune librerie. Nella cartella `jarvis` apri il Prompt dei comandi e scrivi:

   ```
   py install 3.12
   py -3.12 -m pip install -r requisiti_voce.txt
   py -3.12 prova_voci.py
   py -3.12 prova_ascolto.py
   ```

   - Il primo comando installa Python 3.12 accanto alla versione che hai già (se l'hai già fatto, saltalo).
   - `prova_voci.py` ti fa sentire le voci e salva quella che scegli. La voce espressiva la senti con tre livelli
     di emozione; la prima volta scarica circa 1,5 GB.
   - `prova_ascolto.py` scarica il modello che capisce la voce (circa 700 MB, una volta sola) e scrive quello
     che sente dal microfono: prova a dire "Jarvis, che ore sono?". Si chiude con Ctrl+C.

## Avvio

- **Finestra**: apri la cartella `jarvis`, clicca sulla barra dell'indirizzo, scrivi `cmd` e premi Invio.
  Nella finestra nera scrivi `py -3.12 jarvis.py`. Puoi anche fare doppio clic su **`Jarvis.pyw`**, se
  Windows non lo blocca.
- Anche con `python jarvis.py` va bene: se trova Python 3.12 con le librerie della voce, Jarvis riparte da
  solo con quello.
- **Senza finestra**, tutto nel Prompt dei comandi: `python jarvis.py --testo` (così però non parla e non
  ascolta).

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
| `/compiti`                    | i compiti in background e a che punto sono          |
| `/annulla <numero>`           | ferma un compito in background                      |
| `/gioco`                      | accende o spegne la modalità gioco                  |
| `/ascolto`                    | accende o spegne il microfono                       |
| `/voce [nome]`                | accende o spegne la voce, oppure la cambia (`/voce nicola`) |
| `/pensa`                      | attiva o spegne il ragionamento profondo            |
| `/cervello <modalità>`        | `locale`, `ibrido` o `claude` (vedi sotto)          |
| `/chiave`                     | inserisci la chiave API di Claude                   |
| `/costi`                      | quanto hai speso con Claude                         |
| `/nuova`                      | nuova conversazione (la memoria permanente resta)   |
| `/esci`                       | chiude Jarvis                                       |

Nella finestra, il pulsante **Ferma** (o il tasto Esc) interrompe una risposta e la voce; nel Prompt dei
comandi si usa Ctrl+C. Sotto la casella di testo ci sono gli interruttori per microfono, voce, modalità gioco e
ragionamento profondo.

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
| `compiti_in_background` | `false` per aspettare la risposta del cervello grande invece di continuare a parlare |
| `ascolto`               | `false` per tenere spento il microfono                          |
| `parla`                 | `"sempre"`, `"a_voce"` (risponde a voce solo quando gli parli) oppure `"mai"` |
| `voce`                  | `espressiva`, `riccardo`, `nicola`, `diego` o `giuseppe` (le sceglie `prova_voci.py`) |
| `emozione_voce`         | per la voce espressiva: da `0` (calma) a `1` (teatrale)          |
| `voce_riferimento`      | per la voce espressiva: un file WAV con la voce da imitare (vuoto = Nicola) |
| `effetto_voce`          | quanto effetto "intelligenza artificiale": da `0` (nessuno) a `1`; predefinito `0.6` |
| `velocita_voce`         | `1` è normale; `0.9` più lenta, `1.1` più veloce                |
| `limite_voce`           | quanti caratteri di una risposta legge al massimo: il resto resta nella finestra |
| `modello_ascolto`       | `parakeet` (veloce) oppure `whisper` (un po' più preciso, più lento) |
| `microfono`             | una parte del nome del microfono da usare; vuoto = quello predefinito di Windows |
| `attenzione`            | `"normale"`; `"alta"` (interviene ogni volta che vede un bisogno) oppure `"solo_nome"` (risponde solo se lo chiami) |
| `attenzione_in_gioco`   | `true` per farlo rispondere senza il nome anche in modalità gioco |
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
al secondo) e occupa molta RAM: **mentre giochi usa la modalità gioco** (o chiudi Jarvis), così la memoria torna libera.

Il cervello veloce decide da solo quando una domanda è difficile e la passa al grande, che ci lavora
**in background** (vedi sotto). Con **Ragionamento profondo** attivo risponde sempre il grande, e ragiona
prima di rispondere.

Per cambiare modello: `ollama pull nome-modello` nel Prompt dei comandi, poi cambia `modello` o
`modello_grande` in `config.json`. Alcuni modelli ragionano sempre, anche quando non serve: Jarvis
nasconde quel ragionamento.

## Voce e ascolto

Jarvis è sempre in ascolto: il microfono resta acceso, ma risponde solo quando lo chiami per nome.

- **Tutto in una frase**: "Jarvis, che tempo fa?", "Jarvis, metti un timer di 10 minuti per la pasta",
  oppure con il nome alla fine: "Che ore sono, Jarvis?".
- **In due tempi**: "Jarvis." → "Sì, signore?" → "Apri YouTube". Dopo il suo "Sì?" hai qualche secondo per
  rispondere senza ripetere il nome. Lo stesso quando è lui a farti una domanda.
- **Interromperlo**: "Jarvis, basta" (oppure "Jarvis, stop", "Jarvis, zitto"). Se gli fai un'altra richiesta
  mentre parla, lascia perdere la risposta di prima e passa a quella nuova.
- **Compiti in background a voce**: "Jarvis, in background cercami le novità sul nuovo aggiornamento di
  Minecraft". Quando ha finito te lo dice a voce: "Ho terminato il compito 1, signore..."
- **Modalità gioco**: "Jarvis, modalità gioco" e "Jarvis, fine modalità gioco" (oppure l'interruttore nella
  finestra, o `/gioco`). Toglie i cervelli dalla scheda video, risponde con il processore e rimanda i compiti
  lunghi a fine partita. Il microfono resta acceso, così puoi chiamarlo anche mentre giochi.

### Capisce quando gli parli, anche senza il nome

Non serve dire sempre "Jarvis". Quando sente una frase senza il suo nome, il cervello veloce guarda la frase e
la conversazione appena avuta e decide:
- **è per lui** ("E domani invece?" subito dopo il meteo, "Apri Spotify"): risponde normalmente;
- **ti serve aiuto** anche se non parlavi con lui ("Accidenti, quanto fa 15 per 32?", "Devo ricordarmi di chiamare
  la nonna alle sei"): interviene con discrezione, al massimo una volta ogni minuto e mezzo;
- **non lo riguarda** (parli con qualcuno, sei in chiamata, commenti il gioco): resta in silenzio.

Nel dubbio sta zitto: intervenire a sproposito è peggio. Le frasi che non lo riguardano non vengono salvate da
nessuna parte. In **modalità gioco** risponde solo quando lo chiami per nome, così non si intromette mentre parli
con i tuoi amici. Puoi regolare tutto con `attenzione` e `attenzione_in_gioco` in `config.json`.

Quando gli parli risponde in modo più breve, adatto da ascoltare. Delle risposte lunghe legge l'inizio: il
resto lo trovi scritto nella finestra.

**Le voci** (`py -3.12 prova_voci.py` per sentirle e scegliere, oppure `/voce nome` in Jarvis):

| Voce         | Dove funziona       | Com'è                                                        |
|--------------|---------------------|--------------------------------------------------------------|
| `espressiva` | sul PC              | **recita con emozione**: la più simile a Jarvis (circa 1,5 GB, serve un processore veloce) |
| `riccardo`   | sul PC              | predefinita: veloce e privata, ma piatta                     |
| `nicola`     | sul PC              | più naturale, privata; da scaricare una volta (circa 340 MB) |
| `diego`      | via internet        | voce di Microsoft, molto naturale                            |
| `giuseppe`   | via internet        | voce di Microsoft, molto naturale                            |

**La voce espressiva** usa Chatterbox, un modello che non si limita a leggere: dà intonazione ed emozione alle
frasi. Funziona sul processore con le stesse librerie dell'ascolto, quindi non serve installare altro. Ne imita il
timbro da una voce di riferimento: la prima volta Jarvis la registra da solo con la voce di Nicola (o di Riccardo).
- `emozione_voce` va da `0` (calma, neutra) a `1` (molto teatrale); predefinito `0.6`.
- `voce_riferimento` può indicare un tuo file WAV di 5-10 secondi, per esempio la tua voce. Usa solo voci di chi
  è d'accordo: non quella dell'attore o del doppiatore dei film, che sono persone reali.
- Su un processore lento può fare piccole pause tra una frase e l'altra: `prova_voci.py` ti dice quanto ci mette.

La voce dei film non si può copiare: è quella di persone reali (l'attore e il suo doppiatore). Queste sono
voci maschili, e `effetto_voce` in `config.json` aggiunge un effetto in stile film.

**Consigli**
- Con le **cuffie** (come la tua HyperX) va tutto liscio. Con le casse funziona lo stesso: mentre parla,
  Jarvis ascolta solo le frasi con il suo nome, così non scambia la propria voce per un comando.
- La prima volta che si avvia con la voce, Jarvis scarica i modelli che gli servono (circa 700 MB in tutto):
  nella riga in alto a destra vedi a che punto è.
- Il modello che capisce la voce lavora sul processore, così la scheda video resta libera.

## Compiti in background

Jarvis può lavorare a una cosa mentre tu fai altro, anche mentre continui a parlargli:

- **Da solo**: quando il cervello veloce capisce che una domanda è difficile o lunga, risponde subito
  "Me ne occupo, signore: la avviso appena ho finito." e la passa al cervello grande.
- **Quando lo chiedi tu**: metti **"in background"** (o "in sottofondo") nella richiesta, per esempio
  *"in background cercami le novità sul nuovo aggiornamento di Minecraft"*.

Puoi affidargli più compiti: li svolge uno dopo l'altro, perché il cervello grande occupa quasi tutta la
memoria del PC. Intanto puoi continuargli a parlare: mentre il cervello grande lavora, quello veloce risponde
usando il processore, così non deve aspettare il suo turno. Quando un compito finisce, Jarvis te lo dice a
voce, scrive il resoconto nella conversazione e manda una **notifica di Windows**, così lo vedi anche se la
finestra è nascosta (non durante "Non disturbare").
Il resoconto entra nella conversazione: puoi chiedergli altro su quello che ha trovato.

`/compiti` mostra i compiti e a che punto sono; `/annulla 2` ferma il compito numero 2.
Il primo compito ci mette un po' di più a partire: il cervello grande deve caricarsi in memoria.
Quando chiudi Jarvis, i compiti non ancora finiti si fermano.

### Le tre modalità (`/cervello ...`)

| Modalità  | Come funziona                                                                              |
|-----------|--------------------------------------------------------------------------------------------|
| `locale`  | **predefinita**: cervello veloce e cervello grande, tutto sul PC, gratis e privato         |
| `ibrido`  | cervello veloce sul PC; le domande difficili e il ragionamento profondo passano a Claude (i compiti in background restano al cervello grande) |
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

Voce, ascolto e webcam hanno bisogno di librerie che il Controllo intelligente delle app di Windows
potrebbe bloccare, e che esistono solo per Python 3.12 (non ancora per le versioni più nuove). Per scoprire
quali funzionano sul tuo PC, nella cartella `jarvis`:

```
py -3.12 prova_compatibilita.py
```

Ci vogliono 5-15 minuti. Alla fine il riepilogo è in `dati/compatibilita.txt`: copialo e mandalo.
Non contiene la tua chiave API.

## Test automatici

Per controllare che tutto funzioni dopo una modifica, nella cartella `jarvis`:

```
py -3.12 -m unittest
```

Usano Ollama, Claude, internet, microfono e voce finti: non costano niente e non toccano i tuoi dati.

## Privacy

- Con il cervello `locale`, l'intelligenza artificiale, la memoria e le conversazioni restano sul tuo PC
  (nella cartella `dati`).
- **Il microfono**: l'audio viene analizzato sul PC e subito buttato. Non viene mai salvato né inviato a
  nessuno. Con l'interruttore **Microfono** spento non ascolta proprio. Le frasi dette senza il suo nome le valuta
  il cervello veloce, sul PC; se non lo riguardano, vengono dimenticate subito.
- **La voce**: `riccardo` e `nicola` funzionano sul PC. Con `diego` e `giuseppe` il testo da leggere viene
  inviato a Microsoft.
- Quando risponde **Claude**, la conversazione recente e le tue informazioni in memoria vengono inviate
  ad Anthropic per ottenere la risposta. Con `/cervello locale` non succede mai.
- Per meteo, Wikipedia e notizie Jarvis si collega a Open-Meteo, Wikipedia e Google News e invia
  solo cosa cercare (per esempio il nome della città). Con `"internet": false` non lo fa mai.

## Limiti

- Non vede lo schermo e non legge i file.
- Può capire male qualche parola, soprattutto con rumore o musica di sottofondo: per le cose importanti
  guarda cosa ha scritto nella finestra.
- È un modello piccolo: può sbagliare o inventare. Per le cose importanti controlla sempre.
- Apre solo i programmi elencati in `config.json`.

## Se qualcosa non va

- **"Non riesco a contattare Ollama"**: avvia Ollama dal menu Start e riapri Jarvis.
- **"Il modello ... non è installato"**: esegui il comando `ollama pull` che ti viene mostrato.
- **La finestra non si apre**: avvia con `python jarvis.py` dal Prompt dei comandi per vedere l'errore.
  Se dice che manca tkinter, reinstalla Python lasciando spuntata l'opzione "tcl/tk and IDLE".
- **"Questo modello non sa usare gli strumenti da solo"**: stai usando un modello come `gemma3:4b`;
  usa i comandi oppure passa a `qwen3.5:4b`.
- **"La voce non funziona" o "Non posso ascoltare"**: il messaggio dice cosa manca. Di solito basta avviare
  con `py -3.12 jarvis.py` dopo aver installato le librerie (punto 5 dell'installazione). Se dice che Windows
  blocca una libreria, prova un'altra voce con `py -3.12 prova_voci.py`.
- **Non mi sente**: prova `py -3.12 prova_ascolto.py`. Se usa il microfono sbagliato, scrivi una parte del
  nome di quello giusto in `"microfono"` dentro `config.json` (il nome lo vedi all'inizio della prova).
- **Mi sente ma non risponde**: controlla di dire "Jarvis" all'inizio o alla fine della frase.
  `prova_ascolto.py` ti mostra come trascrive il nome.
