# Jarvis

Assistente personale che risponde alle tue domande, ispirato al J.A.R.V.I.S. di Iron Man.
Gira **tutto sul tuo PC**: niente abbonamenti e niente dati inviati su internet.

## Cosa serve

- Windows 10 o 11
- Una scheda video NVIDIA (va bene una RTX 3050 da 6 GB)
- Circa 5 GB liberi sul disco

## Installazione (una volta sola)

1. **Python**: scaricalo da <https://www.python.org/downloads/> e installalo.
   Nella prima schermata dell'installazione spunta **"Add python.exe to PATH"**.
2. **Ollama** (il programma che fa girare l'intelligenza artificiale): scaricalo da
   <https://ollama.com/download> e installalo. Si avvia da solo e resta come icona
   di un lama vicino all'orologio di Windows.
3. **Il "cervello"**: premi il tasto Windows, scrivi `cmd` e premi Invio. Nella finestra nera scrivi:

   ```
   ollama pull gemma3:4b
   ```

   Scarica circa 3 GB. Aspetta che finisca.
4. **Jarvis**: scarica questa cartella `jarvis` sul PC. Da GitHub: pulsante verde **Code → Download ZIP**,
   poi estrai lo ZIP.

## Uso

Fai doppio clic su **`avvia.bat`** e scrivi le tue domande.

| Comando  | Cosa fa                                     |
|----------|---------------------------------------------|
| `/nuova` | dimentica la conversazione e ricomincia     |
| `/aiuto` | mostra i comandi                            |
| `/esci`  | chiude Jarvis                               |
| Ctrl+C   | interrompe una risposta troppo lunga        |

Jarvis si ricorda di quello che vi siete detti finché resta aperto.
Quando lo chiudi, libera la memoria della scheda video, così resta tutta per i giochi.

## Personalizzare

Apri `config.json` con il Blocco note:

| Impostazione            | Cosa fa                                                       |
|-------------------------|---------------------------------------------------------------|
| `nome`                  | il nome dell'assistente (per esempio `"Friday"`)              |
| `come_chiamarmi`        | come deve chiamarti (per esempio `"capo"`); vuoto = nessuno   |
| `modello`               | quale modello usare (vedi sotto)                              |
| `messaggi_da_ricordare` | quanti messaggi recenti tiene a mente durante la conversazione |
| `ollama_url`            | indirizzo di Ollama; non va cambiato                          |

Attenzione a lasciare le virgolette e le virgole come sono.

## Quale modello usare

Con 6 GB di memoria video conviene restare sotto i 5 GB circa.

| Modello       | Peso   | Note                                                    |
|---------------|--------|---------------------------------------------------------|
| `gemma3:4b`   | 3,3 GB | predefinito: veloce, scrive bene in italiano            |
| `llama3.1:8b` | 4,9 GB | a volte più preciso, ma più lento e occupa quasi tutta la scheda video |

Per provarne un altro: `ollama pull nome-modello` nel Prompt dei comandi, poi cambia `modello` in `config.json`.

## Limiti

- Non è collegato a internet: non conosce le notizie recenti e non sa che tempo fa.
  Sa però che giorno è e che ore sono.
- Può sbagliare o inventare: per cose importanti controlla sempre.
- La prima risposta dopo l'avvio può metterci qualche secondo in più.

## Se qualcosa non va

- **"Non riesco a contattare Ollama"**: avvia Ollama dal menu Start e riprova.
- **"Il modello ... non è installato"**: esegui il comando `ollama pull` che ti viene mostrato.
- **La finestra si chiude subito o dice che Python non esiste**: reinstalla Python
  spuntando "Add python.exe to PATH".
