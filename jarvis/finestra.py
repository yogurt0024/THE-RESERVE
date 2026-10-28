"""La finestra grafica di Jarvis, fatta con tkinter (incluso in Python).

Il modello lavora in un thread separato e manda gli eventi alla finestra
attraverso una coda, così la finestra non si blocca mai. Lo stesso fanno
l'orecchio (ascolto.py) e la voce (voce.py), che lavorano in background.
"""

import os
import queue
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog

import aggiorna
import ascolto
import iniziativa
import notifiche
import scarica
import voce
import voce_elevenlabs
from cervello import SEPARATORE_DATI, Assistente, ErroreOllama, carica_config

COLORI = {
    "sfondo": "#0b1220",
    "pannello": "#111a2e",
    "bordo": "#1e2a44",
    "testo": "#e2e8f0",
    "attenuato": "#8b9bb4",
    "accento": "#38bdf8",
    "accento_chiaro": "#7dd3fc",
    "utente": "#a5b4fc",
    "avviso": "#fbbf24",
    "errore": "#f87171",
}
CARATTERE = "Segoe UI"
LIMITE_AVVISI_A_VOCE = 350  # dei resoconti dei compiti si legge l'inizio: il resto è nella finestra
PAUSA_TRA_INTERVENTI = 90  # secondi: senza essere chiamato, Jarvis non interviene più spesso di così


def _mescola(colore1, colore2, quota):
    """Colore a metà strada tra due colori #rrggbb (quota 0 = colore1, 1 = colore2)."""
    a = [int(colore1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(colore2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * quota):02x}" for x, y in zip(a, b))


class Finestra:
    def __init__(self, config):
        self.config = config
        self.nome = config["nome"]
        self.eventi = queue.Queue()
        self.stop = threading.Event()
        self.occupato = True  # finché il modello non è pronto non si può scrivere
        self.lavoro = "avvio in corso..."  # cosa sta facendo il cervello, per la riga di stato
        self.a_capo = True
        self.etichetta_scritta = False
        self.fase = 0
        self.compiti_da_mostrare = []  # finiti mentre Jarvis stava rispondendo ad altro
        self.assistente = Assistente(config, avvisa=lambda messaggio: self.eventi.put(("avviso", messaggio)),
                                     al_termine=lambda compito: self.eventi.put(("compito", compito)))
        # Voce e orecchio: lavorano in background e parlano con la finestra attraverso la stessa coda.
        self.voce = voce.Voce(config, avvisa=lambda messaggio: self.eventi.put(("problema_voce", messaggio)),
                              al_cambio=lambda parla: self.eventi.put(("parlando", parla)))
        self.sorvegliante = iniziativa.Sorvegliante(
            config, avvisa=lambda messaggio: self.eventi.put(("avviso", messaggio)), proponi=self._proponi,
            in_gioco=lambda: self.assistente.modalita_gioco, scrivi_diario=self.assistente.scrivi_diari)
        self.orecchio = self._nuovo_orecchio()
        self.orecchio_avviato = False
        self.stato_ascolto = ""
        self.stato_voce = ""  # per esempio quanto manca a finire di scaricare la voce
        self.parlando = False
        self.risposta_a_voce = False  # la risposta in arrivo va letta ad alta voce
        self.domanda_a_voce = False
        self.ultima_risposta = ""
        self.comando_in_attesa = None  # un comando a voce arrivato mentre Jarvis era occupato
        self.valutando = False  # il cervello sta decidendo se una frase senza il nome era per lui
        self.ultimo_intervento = 0.0
        self.consigliato = False  # il consiglio di usare Python 3.12 si dà una volta sola
        self.da_riavviare = False  # dopo un aggiornamento

        self.root = tk.Tk()
        self.root.title(self.nome)
        self.root.geometry("780x680")
        self.root.minsize(480, 420)
        self.root.configure(bg=COLORI["sfondo"])
        self.root.protocol("WM_DELETE_WINDOW", self._chiudi)
        self._costruisci()
        self._leggi_eventi()
        self._anima()
        threading.Thread(target=self._avvia, daemon=True).start()

    # --- Aspetto ---

    def _costruisci(self):
        c = COLORI
        testata = tk.Frame(self.root, bg=c["sfondo"], padx=16, pady=12)
        testata.pack(fill="x")
        self.reattore = tk.Canvas(testata, width=28, height=28, bg=c["sfondo"], highlightthickness=0)
        self.reattore.pack(side="left")
        self.anello = self.reattore.create_oval(3, 3, 25, 25, outline=c["accento"], width=3)
        self.nucleo = self.reattore.create_oval(10, 10, 18, 18, fill=c["accento"], outline="")
        tk.Label(testata, text=self.nome.upper(), font=(CARATTERE, 15, "bold"),
                 fg=c["accento"], bg=c["sfondo"]).pack(side="left", padx=10)
        self.stato = tk.Label(testata, text=self.lavoro, font=(CARATTERE, 10),
                              fg=c["attenuato"], bg=c["sfondo"])
        self.stato.pack(side="right")

        fondo = tk.Frame(self.root, bg=c["sfondo"], padx=16, pady=12)
        fondo.pack(side="bottom", fill="x")  # prima della chat, così resta sempre visibile
        riga = tk.Frame(fondo, bg=c["sfondo"])
        riga.pack(fill="x")
        self.campo = tk.Entry(riga, font=(CARATTERE, 12), bg=c["pannello"], fg=c["testo"],
                              insertbackground=c["testo"], relief="flat", highlightthickness=1,
                              highlightbackground=c["bordo"], highlightcolor=c["accento"])
        self.campo.pack(side="left", fill="x", expand=True, ipady=8)
        self.campo.bind("<Return>", lambda _: self._invia())
        self.campo.bind("<Escape>", lambda _: self._ferma())
        self.pulsante = self._bottone(riga, "Invia", self._invia_o_ferma, principale=True)
        self.pulsante.pack(side="left", padx=(8, 0))

        comandi = tk.Frame(fondo, bg=c["sfondo"])
        comandi.pack(fill="x", pady=(8, 0))
        for testo, comando in (("Nuova conversazione", "/nuova"), ("Memoria", "/memoria"),
                               ("Compiti", "/compiti"), ("Aiuto", "/aiuto")):
            self._bottone(comandi, testo, lambda comando=comando: self._invia(comando, mostra=False)).pack(
                side="left", padx=(0, 6))

        interruttori = tk.Frame(fondo, bg=c["sfondo"])
        interruttori.pack(fill="x", pady=(6, 0))
        self.microfono = tk.BooleanVar(value=bool(self.config["ascolto"]))
        self._casella(interruttori, "Microfono", self.microfono, self._cambia_microfono).pack(side="left")
        self.parla = tk.BooleanVar(value=self.config["parla"] != "mai")
        self._casella(interruttori, "Voce", self.parla, self._cambia_voce).pack(side="left", padx=(10, 0))
        self.gioco = tk.BooleanVar(value=False)
        self._casella(interruttori, "Modalità gioco", self.gioco, self._cambia_gioco).pack(side="left", padx=(10, 0))
        self.ragionamento = tk.BooleanVar(value=False)
        self.casella = self._casella(interruttori, "Ragionamento profondo", self.ragionamento,
                                     self._cambia_ragionamento)
        self.casella.configure(state="disabled")
        self.casella.pack(side="right")

        cornice = tk.Frame(self.root, bg=c["bordo"], padx=1, pady=1)
        cornice.pack(fill="both", expand=True, padx=16)
        self.chat = tk.Text(cornice, wrap="word", font=(CARATTERE, 11), bg=c["pannello"], fg=c["testo"],
                            relief="flat", borderwidth=0, highlightthickness=0, padx=16, pady=12,
                            spacing1=2, spacing3=2, cursor="arrow", state="disabled")
        barra = tk.Scrollbar(cornice, command=self.chat.yview)
        self.chat.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("tu", foreground=c["utente"], font=(CARATTERE, 10, "bold"), spacing1=12)
        self.chat.tag_configure("jarvis", foreground=c["accento"], font=(CARATTERE, 10, "bold"), spacing1=12)
        self.chat.tag_configure("grassetto", font=(CARATTERE, 11, "bold"))
        self.chat.tag_configure("info", foreground=c["attenuato"], font=(CARATTERE, 10, "italic"))
        self.chat.tag_configure("avviso", foreground=c["avviso"], font=(CARATTERE, 11, "bold"))
        self.chat.tag_configure("errore", foreground=c["errore"])

    def _bottone(self, genitore, testo, comando, principale=False):
        c = COLORI
        if principale:
            colori = dict(bg=c["accento"], fg=c["sfondo"], activebackground=c["accento_chiaro"],
                          activeforeground=c["sfondo"], font=(CARATTERE, 10, "bold"), padx=16, pady=7)
        else:
            colori = dict(bg=c["pannello"], fg=c["testo"], activebackground=c["bordo"],
                          activeforeground=c["testo"], font=(CARATTERE, 10), padx=10, pady=3)
        return tk.Button(genitore, text=testo, command=comando, relief="flat", borderwidth=0,
                         cursor="hand2", **colori)

    def _casella(self, genitore, testo, variabile, comando):
        c = COLORI
        return tk.Checkbutton(genitore, text=testo, variable=variabile, command=comando, font=(CARATTERE, 10),
                              bg=c["sfondo"], fg=c["attenuato"], selectcolor=c["pannello"],
                              activebackground=c["sfondo"], activeforeground=c["testo"], highlightthickness=0)

    def _anima(self):
        """Il "reattore" in alto a sinistra pulsa mentre Jarvis lavora o parla."""
        if self.occupato or self.parlando:
            self.fase = (self.fase + 1) % 24
            quota = abs(12 - self.fase) / 12
            colore = _mescola(COLORI["accento"], COLORI["sfondo"], quota * 0.8)
        else:
            colore = COLORI["accento"]
        self.reattore.itemconfigure(self.anello, outline=colore)
        self.reattore.itemconfigure(self.nucleo, fill=colore)
        self.root.after(50, self._anima)

    # --- Scrittura nella chat ---

    def _scrivi(self, testo, tag=()):
        self.chat.configure(state="normal")
        self.chat.insert("end", testo, tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")
        self.a_capo = testo.endswith("\n")

    def _riga(self, testo, tag):
        if not self.a_capo:
            self._scrivi("\n")
        self._scrivi(testo + "\n", tag)

    def _messaggio(self, chi, testo, tag):
        if not self.a_capo:
            self._scrivi("\n")
        self._scrivi(chi + "\n", tag)
        if testo:
            self._scrivi(testo + "\n")

    def _pulisci(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.a_capo = True

    # --- Comportamento ---

    def _avvia(self):
        try:
            self.assistente.avvia()
        except ErroreOllama as e:
            self.eventi.put(("errore_avvio", str(e)))
            return
        self.eventi.put(("pronto",))
        self.sorvegliante.avvia()
        if self.config["controlla_aggiornamenti"] and aggiorna.c_e_un_aggiornamento():
            self.eventi.put(("info", "C'è una versione nuova di Jarvis: di' \"Jarvis, aggiornati\" oppure scrivi "
                                     "/aggiorna. I tuoi dati e le tue impostazioni restano come sono."))
        if self.config["ascolto"]:
            self.eventi.put(("avvia_orecchio",))
        if self.config["parla"] != "mai":
            self._prepara_voce(saluta=True)

    def _prepara_voce(self, saluta=False, nuova=False):
        """Carica la voce (la prima volta la scarica) senza bloccare la finestra."""
        def avanzamento(nome, scaricati, totale):
            self.eventi.put(("stato_voce", scarica.descrivi_avanzamento(nome, scaricati, totale)))

        pronta = not self.voce.prepara(avanzamento)  # se non va, lo dice la voce stessa ("problema_voce")
        if pronta and saluta:
            self.voce.di(self._saluto())
        elif pronta and nuova:
            self.voce.di(f"Ecco la mia nuova voce{self._t()}.")
        self.eventi.put(("stato_voce", ""))

    def _t(self):
        titolo = self.config["come_chiamarmi"]
        return f", {titolo}" if titolo else ""

    def _saluto(self):
        ora = datetime.now().hour
        saluto = "Buongiorno" if 5 <= ora < 13 else "Buon pomeriggio" if ora < 18 else "Buonasera"
        return f"{saluto}{self._t()}. Tutti i sistemi sono operativi."

    def _invia_o_ferma(self):
        if self.occupato:
            self._ferma()
        else:
            self._invia()

    def _ferma(self):
        self.stop.set()
        self.voce.zitto()

    def _invia(self, testo=None, mostra=True, a_voce=False, spontaneo=False):
        if self.occupato:
            return
        if testo is None:
            testo = self.campo.get().strip()
            self.campo.delete(0, "end")
        if not testo:
            return
        minuscolo = testo.lower()
        if minuscolo in ("/esci", "esci"):
            self._chiudi()
            return
        if minuscolo == "/chiave":
            self._chiedi_chiave()
            return
        if minuscolo == "/chiave elevenlabs":
            self._chiedi_chiave_elevenlabs()
            return
        if minuscolo == "/ascolto":
            self.microfono.set(not self.microfono.get())
            self._cambia_microfono()
            return
        if minuscolo == "/voce" or minuscolo.startswith("/voce "):
            self._comando_voce(testo[6:].strip().lower())
            return
        if mostra:
            self._messaggio("Tu (ti ho sentito)" if spontaneo else "Tu (a voce)" if a_voce else "Tu", testo, "tu")
        self.etichetta_scritta = False
        self.domanda_a_voce = a_voce
        self.ultima_risposta = ""
        parla = self.config["parla"]
        self.risposta_a_voce = parla == "sempre" or (parla == "a_voce" and a_voce)
        if self.risposta_a_voce:
            self.voce.inizia()
        self._occupa(True)
        threading.Thread(target=self._lavora, args=(testo, a_voce, spontaneo), daemon=True).start()

    def _chiedi_chiave(self):
        chiave = simpledialog.askstring(
            "Chiave API di Claude", "Incolla la chiave API (inizia con sk-ant-).\nResta salvata solo sul tuo PC.",
            show="*", parent=self.root)
        if chiave:
            self._riga(self.assistente.imposta_chiave(chiave), "info")
            self.casella.configure(state="normal" if self.assistente.supporta_ragionamento else "disabled")

    def _chiedi_chiave_elevenlabs(self):
        chiave = simpledialog.askstring(
            "Chiave API di ElevenLabs", "Incolla la chiave API di ElevenLabs.\nResta salvata solo sul tuo PC.",
            show="*", parent=self.root)
        if not chiave:
            return

        def salva():
            self.eventi.put(("info", voce_elevenlabs.salva_chiave(chiave)))
            if self.config["voce"] == "elevenlabs" and self.config["parla"] != "mai":
                self._prepara_voce(nuova=True)

        threading.Thread(target=salva, daemon=True).start()

    def _lavora(self, testo, a_voce, spontaneo=False):
        try:
            for evento in self.assistente.gestisci(testo, self.stop, a_voce=a_voce, spontaneo=spontaneo):
                self.eventi.put(evento)
        except ErroreOllama as e:
            self.eventi.put(("errore", str(e)))
        except Exception as e:  # mostra l'errore invece di lasciare la finestra bloccata
            self.eventi.put(("errore", f"Errore imprevisto: {e}"))
        finally:
            self.eventi.put(("fatto",))

    def _occupa(self, occupato):
        self.occupato = occupato
        if occupato:
            self.stop.clear()
        self.lavoro = "sto elaborando..." if occupato else "pronto"
        self.pulsante.configure(text="Ferma" if occupato else "Invia")
        self._aggiorna_stato()

    def _aggiorna_stato(self):
        parti = [self.lavoro]
        if self.parlando:
            parti.append("sto parlando")
        elif self.stato_voce:
            parti.append(self.stato_voce)
        elif self.stato_ascolto:
            parti.append(self.stato_ascolto)
        if self.assistente.modalita_gioco:
            parti.append("modalità gioco")
        attivi = len(self.assistente.compiti_attivi())
        if attivi:
            parti.append(f"{attivi} {'compito' if attivi == 1 else 'compiti'} in background")
        self.stato.configure(text=" · ".join(parti))

    def _mostra_compito(self, compito):
        esito = {"completato": "completato", "errore": "non riuscito"}.get(compito.stato, compito.stato)
        if not self.a_capo:
            self._scrivi("\n")
        self._scrivi(f"{self.nome} · compito {compito.numero} {esito}\n", "jarvis")
        self._scrivi(f"{compito.descrizione}\n", "info")
        self._scrivi(compito.risultato + "\n")
        self.root.bell()
        notifiche.mostra(f"{self.nome}: compito {compito.numero} {esito}", compito.risultato)
        if self.config["parla"] != "mai":
            if compito.stato == "completato":
                annuncio = f"Ho terminato il compito {compito.numero}{self._t()}. {compito.risultato}"
            else:
                annuncio = f"Non sono riuscito a completare il compito {compito.numero}{self._t()}."
            self.voce.di(annuncio, limite=LIMITE_AVVISI_A_VOCE)
        self._aggiorna_stato()

    # --- Voce e ascolto ---

    def _comando_vocale(self, testo):
        if ascolto.e_stop(testo):
            self.voce.zitto()
            if self.occupato:
                self.stop.set()
            return
        self.voce.zitto()
        if not testo:  # ha detto solo "Jarvis": risponde e aspetta la richiesta
            lei = self.config["dai_del"] != "tu"
            risposte = ["Sì{t}?", "Mi dica{t}." if lei else "Dimmi{t}.", "Eccomi{t}.", "Sono qui{t}."]
            if self.config["parla"] != "mai":
                self.voce.di(random.choice(risposte).format(t=self._t()))
            self.orecchio.attendi_comando()
            self.stato_ascolto = f"{'la' if lei else 'ti'} ascolto..."
            self._aggiorna_stato()
            self.root.after(10000, self._fine_attesa)
            return
        self._fine_attesa()
        if self.occupato:  # interrompe la risposta in corso: il nuovo comando parte appena possibile
            self.comando_in_attesa = testo
            self.stop.set()
            return
        self._invia(testo, a_voce=True)

    def _fine_attesa(self):
        if self.stato_ascolto.endswith("ascolto..."):
            self.stato_ascolto = "in ascolto" if self.orecchio.pronto else ""
            self._aggiorna_stato()

    def _nuovo_orecchio(self):
        return ascolto.Ascolto(self.config, al_comando=lambda testo: self.eventi.put(("comando_vocale", testo)),
                               al_stato=lambda testo: self.eventi.put(("stato_ascolto", testo)),
                               al_senza_nome=lambda testo, secondi: self.eventi.put(("senza_nome", testo, secondi)),
                               parlando=lambda: self.voce.sta_parlando)

    def _senza_nome(self, testo, secondi):
        """Una frase sentita senza "Jarvis": il cervello veloce decide se era per lui o se all'utente serve aiuto."""
        attenzione = self.config["attenzione"]
        in_gioco = self.assistente.modalita_gioco and not self.config["attenzione_in_gioco"]
        if attenzione == "solo_nome" or in_gioco or self.occupato or self.valutando or not testo:
            return
        self.valutando = True

        def valuta():
            try:
                decisione = self.assistente.valuta_frase(testo, secondi)
            except ErroreOllama:
                decisione = "ignora"
            self.eventi.put(("decisione", testo, decisione))

        threading.Thread(target=valuta, daemon=True).start()

    def _decisione(self, testo, decisione):
        self.valutando = False
        if self.occupato or decisione == "ignora" or testo.lower().strip(" .!") == "esci":
            return
        if decisione == "rivolta":
            self._invia(testo, a_voce=True)
            return
        # Un bisogno: interviene di sua iniziativa, ma senza diventare invadente.
        adesso = time.monotonic()
        if self.config["attenzione"] != "alta" and adesso - self.ultimo_intervento < PAUSA_TRA_INTERVENTI:
            return
        self.ultimo_intervento = adesso
        self._invia(testo, a_voce=True, spontaneo=True)

    def _avvia_orecchio(self):
        if self.orecchio.errore:  # l'ultima volta non è partito: ci riprova da capo
            self.orecchio = self._nuovo_orecchio()
            self.orecchio_avviato = False
        if not self.orecchio_avviato:
            self.orecchio_avviato = True
            self.orecchio.avvia()
        else:
            self.orecchio.pausa(False)

    def _cambia_microfono(self):
        acceso = self.microfono.get()
        avviso = self.assistente.salva_impostazione("ascolto", acceso)
        if acceso:
            self._avvia_orecchio()
        else:
            self.orecchio.pausa(True)
        self._riga(("Microfono acceso: chiamami dicendo \"" + self.nome + "\"." if acceso else
                    "Microfono spento: non ascolto più.") + avviso, "info")

    def _cambia_voce(self):
        acceso = self.parla.get()
        avviso = self.assistente.salva_impostazione("parla", "sempre" if acceso else "mai")
        if acceso:
            threading.Thread(target=self._prepara_voce, daemon=True).start()
        else:
            self.voce.zitto()
        self._riga(("Voce attiva." if acceso else "Voce spenta: rispondo solo per iscritto.") + avviso, "info")

    def _comando_voce(self, nome):
        if not nome:
            self.parla.set(not self.parla.get())
            self._cambia_voce()
            return
        if nome not in voce.VOCI:
            elenco = "\n".join(f"- {n}: {v['descrizione']}" for n, v in voce.VOCI.items())
            self._riga(f"Le voci disponibili (per esempio /voce nicola):\n{elenco}", "info")
            return
        avviso = self.assistente.salva_impostazione("voce", nome)
        self.voce.zitto()
        self.parla.set(True)
        if self.config["parla"] == "mai":
            self.assistente.salva_impostazione("parla", "sempre")
        self._riga(f"Cambio voce: {voce.VOCI[nome]['descrizione']}.{avviso}", "info")
        threading.Thread(target=self._prepara_voce, kwargs={"nuova": True}, daemon=True).start()

    def _cambia_gioco(self):
        attiva = self.gioco.get()

        def cambia():
            self.eventi.put(("info", self.assistente.imposta_modalita_gioco(attiva)))
            self.eventi.put(("stato_voce", self.stato_voce))  # ridisegna la riga di stato

        threading.Thread(target=cambia, daemon=True).start()

    def _cambia_ragionamento(self):
        self.assistente.ragionamento = self.ragionamento.get()

    # --- Eventi (arrivano dagli altri thread attraverso la coda) ---

    def _leggi_eventi(self):
        try:
            while True:
                self._gestisci(self.eventi.get_nowait())
        except queue.Empty:
            pass
        self.root.after(30, self._leggi_eventi)

    def _gestisci(self, evento):
        tipo = evento[0]
        if tipo == "testo":
            if not self.etichetta_scritta:
                self._messaggio(self.nome, "", "jarvis")
                self.chat.mark_set("risposta", "end-1c")  # da qui comincia il testo della risposta
                self.chat.mark_gravity("risposta", "left")
                self.etichetta_scritta = True
            self._scrivi(evento[1], "grassetto" if evento[2] else ())
            self.ultima_risposta += evento[1]
            if self.risposta_a_voce:
                self.voce.aggiungi(evento[1])
        elif tipo == "info":
            self._riga(evento[1], "info")
        elif tipo == "pensiero":
            self.lavoro = "sto ragionando..."
            self._aggiorna_stato()
            self._riga("Sto ragionando...", "info")
        elif tipo == "ritira":
            if self.etichetta_scritta:  # il modello aveva scritto il suo ragionamento: si cancella
                self.chat.configure(state="normal")
                self.chat.delete("risposta", "end-1c")
                self.chat.configure(state="disabled")
                self.a_capo = True
            self.ultima_risposta = ""
            if self.risposta_a_voce:
                self.voce.zitto()
                self.voce.inizia()
        elif tipo == "pulisci":
            self._pulisci()
        elif tipo == "riavvia":
            self.da_riavviare = True
        elif tipo == "errore":
            self._riga(evento[1], "errore")
            if self.risposta_a_voce:
                self.voce.di(f"Mi dispiace{self._t()}, c'è un problema: i dettagli sono nella finestra.")
        elif tipo == "avviso":
            self._riga(f"⏰ {evento[1]}", "avviso")
            self.root.bell()
            notifiche.mostra(self.nome, evento[1])
            if self.config["parla"] != "mai":
                self.voce.di(self._avviso_a_voce(evento[1]))
            else:
                self._in_primo_piano()
        elif tipo == "compito":
            if self.occupato:
                self.compiti_da_mostrare.append(evento[1])
            else:
                self._mostra_compito(evento[1])
        elif tipo == "fatto":
            if self.risposta_a_voce:
                self.voce.finisci()
            # Se Jarvis ha fatto una domanda a voce, la risposta dell'utente non ha bisogno del nome.
            if self.domanda_a_voce and self.ultima_risposta.rstrip().endswith("?"):
                self.orecchio.attendi_comando()
            self._occupa(False)
            for compito in self.compiti_da_mostrare:
                self._mostra_compito(compito)
            self.compiti_da_mostrare.clear()
            self.ragionamento.set(self.assistente.ragionamento)
            self.gioco.set(self.assistente.modalita_gioco)
            if not self.a_capo:
                self._scrivi("\n")
            if self.da_riavviare:
                self._riavvia_quando_ha_finito()
                return
            self._comando_rimasto()
        elif tipo == "pronto":
            self._mostra_cronologia()
            self._riga(self.assistente.stato(), "info")
            if self.assistente.supporta_ragionamento:
                self.casella.configure(state="normal")
                self.ragionamento.set(self.assistente.ragionamento)
            self._occupa(False)
            self.campo.focus_set()
            self._comando_rimasto()
        elif tipo == "avvia_orecchio":
            self._avvia_orecchio()
        elif tipo == "comando_vocale":
            self._comando_vocale(evento[1])
        elif tipo == "proponi":
            if not self.occupato:
                self._invia(evento[1], mostra=False, a_voce=True)
        elif tipo == "senza_nome":
            self._senza_nome(evento[1], evento[2])
        elif tipo == "decisione":
            self._decisione(evento[1], evento[2])
        elif tipo == "stato_ascolto":
            testo = evento[1]
            if testo.startswith("ascolto non disponibile"):
                self._riga(f"Non posso ascoltare: {testo.partition(': ')[2]}{self._consiglio_python()}", "info")
                self.microfono.set(False)
                testo = ""
            elif testo == "in ascolto" and not self.assistente.voce_attiva:
                self.assistente.voce_attiva = True
                senza_nome = ("" if self.config["attenzione"] == "solo_nome" else
                              " Puoi anche parlarmi senza nome: capisco da solo quando ti rivolgi a me.")
                self._riga(f"Ti ascolto: chiamami dicendo \"{self.nome}\" (per esempio \"{self.nome}, che ore "
                           f"sono?\").{senza_nome} Per interrompermi: \"{self.nome}, basta\".", "info")
            self.stato_ascolto = testo
            self._aggiorna_stato()
        elif tipo == "stato_voce":
            self.stato_voce = evento[1]
            self._aggiorna_stato()
        elif tipo == "problema_voce":
            self._riga(evento[1] + self._consiglio_python(), "info")
        elif tipo == "parlando":
            self.parlando = evento[1]
            self._aggiorna_stato()
        elif tipo == "errore_avvio":
            self._riga(f"{evento[1]}\n\nSistema il problema e riapri {self.nome}.", "errore")
            self.lavoro = "non disponibile"
            self._aggiorna_stato()
            self.occupato = False  # ferma l'animazione; casella di testo e pulsante restano disattivati
            self.pulsante.configure(state="disabled")
            self.campo.configure(state="disabled")

    def _comando_rimasto(self):
        if self.comando_in_attesa and not self.occupato:
            testo, self.comando_in_attesa = self.comando_in_attesa, None
            self._invia(testo, a_voce=True)

    def _avviso_a_voce(self, messaggio):
        ricordo = "Ti ricordo" if self.config["dai_del"] == "tu" else "Le ricordo"
        if messaggio.startswith("Timer: "):
            cosa = messaggio.removeprefix("Timer: ").strip()
            if cosa == "tempo scaduto!":
                return f"Il tempo è scaduto{self._t()}."
            return f"Il timer è scaduto{self._t()}: {cosa}"
        if messaggio.startswith("Promemoria: "):
            return f"{ricordo}{self._t()}: {messaggio.removeprefix('Promemoria: ')}."
        if messaggio.startswith("Promemoria (era per "):
            quando, _, cosa = messaggio.removeprefix("Promemoria (era per ").partition("): ")
            return f"Mentre ero spento è scaduto un promemoria, era per {quando}{self._t()}: {cosa}."
        return messaggio

    def _proponi(self, comando):
        """L'iniziativa chiede di fare qualcosa (per esempio il briefing): si fa solo se Jarvis è libero."""
        if self.occupato or self.comando_in_attesa or self.parlando:
            return False
        self.eventi.put(("proponi", comando))
        return True

    def _consiglio_python(self):
        if sys.version_info >= (3, 13) and not self.consigliato:
            self.consigliato = True
            return ("\nLa voce ha bisogno di Python 3.12: avvia Jarvis con  py -3.12 jarvis.py  "
                    "(le librerie si installano con  py -3.12 -m pip install -r requisiti_voce.txt).")
        return ""

    def _mostra_cronologia(self):
        for messaggio in self.assistente.cronologia:
            if messaggio["role"] == "user":
                self._messaggio("Tu", messaggio["content"].split(SEPARATORE_DATI)[0], "tu")
            else:
                self._messaggio(self.nome, messaggio["content"], "jarvis")

    def _in_primo_piano(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(500, lambda: self.root.attributes("-topmost", False))

    def _riavvia_quando_ha_finito(self):
        """Dopo un aggiornamento: lascia finire la frase, poi riapre Jarvis con la versione nuova."""
        if self.voce.sta_parlando:
            self.root.after(300, self._riavvia_quando_ha_finito)
            return
        self._chiudi()
        jarvis = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis.py")
        subprocess.Popen([sys.executable, jarvis], env=dict(os.environ, JARVIS_PYTHON_312="1"))

    def _chiudi(self):
        self.sorvegliante.chiudi()
        self.stop.set()
        self.voce.zitto()
        self.orecchio.chiudi()
        self.root.withdraw()
        self.assistente.chiudi()
        self.root.destroy()


def avvia():
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # testo nitido sugli schermi ad alta risoluzione
        except (AttributeError, OSError):
            pass
    try:
        config = carica_config()
    except SystemExit as e:
        tk.Tk().withdraw()
        messagebox.showerror("Jarvis", str(e))
        return
    Finestra(config).root.mainloop()
