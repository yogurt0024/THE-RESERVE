"""Jarvis: assistente personale che gira sul tuo PC grazie a Ollama.

Avvio:  python jarvis.py           apre la finestra grafica
        python jarvis.py --testo   resta nel Prompt dei comandi
Le impostazioni (nome, modello, città, ...) sono in config.json.
"""

import getpass
import sys

import notifiche
from cervello import Assistente, ErroreOllama, carica_config


def mostra(eventi, nome):
    """Stampa gli eventi di una risposta mentre arrivano."""
    etichetta = False
    a_capo = True
    try:
        for evento in eventi:
            if evento[0] == "testo":
                if not etichetta:
                    print(f"{nome}: ", end="")
                    etichetta = True
                print(evento[1], end="", flush=True)
                a_capo = evento[1].endswith("\n")
            elif evento[0] in ("info", "pensiero"):
                if not a_capo:
                    print()
                print("» " + ("(sto ragionando...)" if evento[0] == "pensiero" else evento[1]))
                a_capo = True
            elif evento[0] == "ritira":
                # Il Prompt dei comandi non può cancellare il testo già scritto: si va a capo.
                if not a_capo:
                    print()
                print("» (fine del ragionamento, ecco la risposta)")
                a_capo = True
                etichetta = False
    except KeyboardInterrupt:
        eventi.close()
        if not a_capo:
            print()
        print("» Risposta interrotta.")
        a_capo = True
    except ErroreOllama as e:
        if not a_capo:
            print()
        print(f"[Errore] {e}")
        a_capo = True
    if not a_capo:
        print()
    print()


def terminale(config):
    nome = config["nome"]
    def avvisa(messaggio):
        print(f"\n» {messaggio}\a\nTu: ", end="", flush=True)
        notifiche.mostra(nome, messaggio)

    def al_termine(compito):
        esito = {"completato": "completato", "errore": "non riuscito"}.get(compito.stato, compito.stato)
        print(f"\n» Compito {compito.numero} {esito}: {compito.descrizione}\n{nome}: {compito.risultato}\a\n\nTu: ",
              end="", flush=True)
        notifiche.mostra(f"{nome}: compito {compito.numero} {esito}", compito.risultato)

    assistente = Assistente(config, avvisa=avvisa, al_termine=al_termine)
    print(f"Avvio di {nome} con il modello {config['modello']}...")
    try:
        assistente.avvia()
    except ErroreOllama as e:
        raise SystemExit(f"Errore: {e}")
    print(assistente.stato())
    print("Scrivi una domanda, oppure /aiuto per i comandi.\n")

    while True:
        try:
            domanda = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not domanda:
            continue
        if domanda.lower() in ("/esci", "esci"):
            break
        if domanda.lower() == "/chiave":
            chiave = getpass.getpass("Incolla la chiave API di Claude (mentre la incolli non si vede): ")
            print(f"» {assistente.imposta_chiave(chiave)}\n")
            continue
        mostra(assistente.gestisci(domanda), nome)

    print(f"{nome}: Arrivederci!")
    assistente.chiudi()


def main():
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if "--testo" not in sys.argv[1:]:
        try:
            import finestra
        except ImportError:
            print("La finestra grafica non è disponibile (manca tkinter): uso la modalità testo.\n")
        else:
            finestra.avvia()
            return
    terminale(carica_config())


if __name__ == "__main__":
    main()
