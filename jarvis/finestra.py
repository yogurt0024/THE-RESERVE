"""La finestra di Jarvis: un HUD in stile Iron Man (hud.py), senza chat.

Il modello lavora in un thread separato e manda gli eventi alla finestra attraverso una coda, così la finestra
non si blocca mai. Lo stesso fanno l'orecchio (ascolto.py), la voce (voce.py), l'iniziativa (iniziativa.py) e i
sensori del PC. Per scrivere a Jarvis basta iniziare a digitare; F2 apre la cronologia.
"""

import os
import queue
import random
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, simpledialog

import aggiorna
import ascolto
import hud
import iniziativa
import integrazioni
import notifiche
import promemoria
import recupero
import scarica
import sensori
import strumenti
import voce
import voce_elevenlabs
from cervello import SEPARATORE_DATI, Assistente, ErroreOllama, carica_config

LIMITE_AVVISI_A_VOCE = 350  # dei resoconti dei compiti si legge l'inizio: il resto è nella scheda
PAUSA_TRA_INTERVENTI = 90  # secondi: senza essere chiamato, Jarvis non interviene più spesso di così
LIMITE_RIGA = 260  # caratteri: le informazioni più lunghe (o su più righe) si aprono in una scheda


class Finestra:
    def __init__(self, config):
        self.config = config
        self.nome = config["nome"]
        self.eventi = queue.Queue()
        self.stop = threading.Event()
        self.occupato = True  # finché il modello non è pronto non si può chiedere niente
        self.pronto = False
        self.errore_avvio = False
        self.etichetta_scritta = False  # è già arrivato del testo della risposta in corso
        self.compiti_da_mostrare = []  # finiti mentre Jarvis stava rispondendo ad altro
        self.registro = []  # (chi, testo): la cronologia, che si apre con F2
        self.assistente = Assistente(config, avvisa=lambda messaggio: self.eventi.put(("avviso", messaggio)),
                                     al_termine=lambda compito: self.eventi.put(("compito", compito)))
        # Voce e orecchio: lavorano in background e parlano con la finestra attraverso la stessa coda.
        self.voce = voce.Voce(config, avvisa=lambda messaggio: self.eventi.put(("problema_voce", messaggio)),
                              al_cambio=lambda parla: self.eventi.put(("parlando", parla)))
        self.sorvegliante = iniziativa.Sorvegliante(
            config, avvisa=lambda messaggio: self.eventi.put(("avviso", messaggio)), proponi=self._proponi,
            in_gioco=lambda: self.assistente.modalita_gioco, scrivi_diario=self.assistente.scrivi_diari,
            cambia_gioco=lambda attiva, gioco: self.eventi.put(("gioco_automatico", attiva, gioco)),
            saluta=lambda testo: self.eventi.put(("saluto", testo)))
        self.orecchio = self._nuovo_orecchio()
        self.orecchio_avviato = False
        self.microfono = bool(config["ascolto"])
        self.stato_ascolto = ""
        self.stato_voce = ""  # per esempio quanto manca a finire di scaricare la voce
        self.parlando = False
        self.risposta_a_voce = False  # la risposta in arrivo va letta ad alta voce
        self.domanda_a_voce = False
        self.ultima_risposta = ""
        self.comando_in_attesa = None  # (testo, a_voce): arrivato mentre Jarvis era occupato
        self.valutando = False  # il cervello sta decidendo se una frase senza il nome era per lui
        self.ultimo_intervento = 0.0
        self.consigliato = False  # il consiglio di usare Python 3.12 si dà una volta sola
        self.da_riavviare = False  # dopo un aggiornamento
        self.eventi_calendario = []
        self.chiuso = threading.Event()

        self.root = tk.Tk()
        self.root.title(self.nome)
        self.root.geometry("1280x800")
        self.root.minsize(640, 480)
        self.root.configure(bg=hud.COLORI["sfondo"])
        self.root.protocol("WM_DELETE_WINDOW", self._chiudi)
        self.hud = hud.Hud(self.root, self.nome)
        self.hud.al_invio = lambda testo: self._invia(testo)
        self.hud.al_clic_indicatore = self._clic_indicatore
        self.hud.imposta_indicatore("microfono", self.microfono)
        self.hud.imposta_indicatore("voce", config["parla"] != "mai")
        self.hud.imposta_indicatore("ragionamento", False, disponibile=False)
        self.hud.imposta_agenda([("Avvio dei sistemi...", "nota")])
        self.root.bind("<Key>", self._tasto)
        self.root.bind("<Escape>", self._esc)
        self.root.bind("<F1>", lambda e: self._invia("/aiuto", mostra=False))
        self.root.bind("<F2>", lambda e: self._mostra_cronologia())
        self.root.bind("<F11>", lambda e: self.root.attributes("-fullscreen",
                                                              not self.root.attributes("-fullscreen")))
        self.hud.tela.focus_set()
        self._leggi_eventi()
        self.hud.anima()
        self._aggiorna_agenda()
        threading.Thread(target=self._avvia, daemon=True).start()
        threading.Thread(target=self._sorveglia_dintorni, daemon=True).start()

    # --- Stato del reattore e riga sotto di esso ---

    def _aggiorna_stato(self):
        if self.errore_avvio:
            stato = "errore"
        elif not self.pronto:
            stato = "avvio"
        elif self.parlando:
            stato = "parla"
        elif self.occupato:
            stato = "parla" if self.etichetta_scritta and not self.risposta_a_voce else "pensa"
        elif self.stato_ascolto.endswith("ascolto...") or self.valutando:
            stato = "ascolto"
        else:
            stato = "riposo"
        self.hud.imposta_stato(stato)
        self.hud.imposta_gioco(self.assistente.modalita_gioco)
        self.hud.imposta_indicatore("gioco", self.assistente.modalita_gioco)
        parti = []
        if self.stato_voce:
            parti.append(self.stato_voce)
        elif self.stato_ascolto and self.stato_ascolto != "in ascolto":
            parti.append(self.stato_ascolto)
        attivi = len(self.assistente.compiti_attivi())
        if attivi:
            parti.append(f"{attivi} {'compito' if attivi == 1 else 'compiti'} in background")
        self.hud.dettaglio("  ·  ".join(parti))

    def _registra(self, chi, testo):
        self.registro = (self.registro + [(chi, testo)])[-300:]

    def _info(self, testo, titolo="Informazioni"):
        """Le informazioni brevi passano sotto i sottotitoli; quelle lunghe si aprono in una scheda (se la prima
        riga è un titolo, come "Comandi:", diventa il titolo della scheda)."""
        testo = testo.strip()
        if "\n" not in testo and len(testo) <= LIMITE_RIGA:
            self.hud.log(testo)
            return
        prima, _, resto = testo.partition("\n")
        if prima.endswith(":") and len(prima) <= 50 and resto:
            titolo, testo = prima.rstrip(":"), resto
        self.hud.scheda(titolo, testo)

    def _annuncia(self, testo, tipo="jarvis"):
        """Una frase di Jarvis che non risponde a una domanda: la domanda di prima sparisce."""
        self.hud.domanda("")
        self.hud.sottotitolo(testo, tipo)

    def _mostra_cronologia(self):
        righe = []
        nomi = {"tu": "Tu", "jarvis": self.nome}
        for chi, testo in self.registro:
            if chi in nomi:
                righe += [(nomi[chi], chi), (testo, ())]
            else:  # avvisi ed errori
                righe.append((testo, chi))
        self.hud.scheda("Cronologia", righe or [("Non abbiamo ancora parlato.", "info")])

    # --- Tastiera e indicatori ---

    def _tasto(self, evento):
        if self.hud.campo_visibile or self.hud.scheda_aperta:
            return None
        if evento.char and evento.char.isprintable() and not evento.char.isspace() and not evento.state & 0x4:
            self.hud.mostra_campo(evento.char)
            return "break"
        if evento.keysym == "Return":
            self.hud.mostra_campo()
            return "break"
        return None

    def _esc(self, _evento=None):
        if self.hud.scheda_aperta:
            self.hud.chiudi_scheda()
        elif self.hud.campo_visibile:
            self.hud.nascondi_campo()
        else:
            self._ferma()
        return "break"

    def _clic_indicatore(self, nome):
        if nome == "microfono":
            self._cambia_microfono(not self.microfono)
        elif nome == "voce":
            self._cambia_voce(self.config["parla"] == "mai")
        elif nome == "gioco":
            self._cambia_gioco(not self.assistente.modalita_gioco)
        elif nome == "ragionamento" and self.assistente.supporta_ragionamento:
            self.assistente.ragionamento = not self.assistente.ragionamento
            self.hud.imposta_indicatore("ragionamento", self.assistente.ragionamento)
            self.hud.log("Ragionamento profondo " + ("attivo: risposte più accurate ma più lente." if
                                                     self.assistente.ragionamento else "spento."))

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
        try:  # la voce scelta in un'altra copia di Jarvis sul PC (vedi recupero.py)
            ritrovata = recupero.ritrova_voce(self.config, self.assistente.salva_impostazione)
        except Exception:  # cercarla è un aiuto in più: se non va, si parte con quella che c'è
            ritrovata = ""
        if ritrovata:
            self.eventi.put(("info", ritrovata))
        if self.config["parla"] != "mai":
            self._prepara_voce(saluta=True)
        else:
            self.eventi.put(("saluto", self._saluto()))

    def _prepara_voce(self, saluta=False, nuova=False):
        """Carica la voce (la prima volta la scarica) senza bloccare la finestra."""
        def avanzamento(nome, scaricati, totale):
            self.eventi.put(("stato_voce", scarica.descrivi_avanzamento(nome, scaricati, totale)))

        pronta = not self.voce.prepara(avanzamento)  # se non va, lo dice la voce stessa ("problema_voce")
        if saluta:
            self.eventi.put(("saluto", self._saluto()))
        elif pronta and nuova:
            self.eventi.put(("saluto", f"Ecco la mia nuova voce{self._t()}."))
        self.eventi.put(("stato_voce", ""))

    def _sorveglia_dintorni(self):
        """Un thread per i pannelli: sensori del PC ogni 3 secondi, meteo ogni 30 minuti, calendario ogni 15."""
        lettore = sensori.Sensori()
        ultimo_meteo = ultimo_calendario = -1e9
        while not self.chiuso.is_set():
            self.eventi.put(("sensori", lettore.leggi()))
            adesso = time.monotonic()
            if adesso - ultimo_meteo >= 1800 and self.config["internet"] and self.config["citta"]:
                ultimo_meteo = adesso
                try:
                    self.eventi.put(("meteo", *strumenti.meteo_breve(self.config["citta"])))
                except Exception:  # senza internet il pannello resta vuoto
                    ultimo_meteo = adesso - 1500  # si riprova tra cinque minuti
            if adesso - ultimo_calendario >= 900 and (self.config.get("calendario_ics") or "").strip():
                ultimo_calendario = adesso
                try:
                    oggi = datetime.combine(datetime.now().date(), datetime.min.time())
                    eventi = integrazioni.eventi_tra(integrazioni.scarica_calendario(self.config["calendario_ics"]),
                                                     oggi, oggi + timedelta(days=2))
                    self.eventi.put(("calendario", eventi))
                except Exception:
                    pass
            self.chiuso.wait(3)

    def _aggiorna_agenda(self):
        """Il pannello IN PROGRAMMA: compiti in background, promemoria e impegni dei prossimi giorni."""
        adesso = datetime.now()
        righe = [(f"Compito {c.numero} · {c.stato}: {c.descrizione}", "compito")
                 for c in self.assistente.compiti_attivi()]
        prossimi = [(quando, f"{promemoria.descrivi_quando(quando, adesso)} · {messaggio}", "promemoria")
                    for quando, messaggio in promemoria.in_attesa(adesso)[:5]]
        for inizio, titolo, _, tutto_il_giorno in self.eventi_calendario:
            momento = inizio if isinstance(inizio, datetime) else datetime.combine(inizio, datetime.min.time())
            if (tutto_il_giorno and momento.date() >= adesso.date()) or momento >= adesso:
                quando = ("oggi" if momento.date() == adesso.date() else "domani") + \
                    (", tutto il giorno" if tutto_il_giorno else f" alle {momento.hour}:{momento.minute:02d}")
                prossimi.append((momento, f"{quando} · {titolo}", "evento"))
        prossimi.sort(key=lambda p: p[0])
        righe += [(testo, tipo) for _, testo, tipo in prossimi]
        self.hud.imposta_agenda(righe or [("Niente in programma.", "nota")])
        self.root.after(20000, self._aggiorna_agenda)

    def _t(self):
        titolo = self.config["come_chiamarmi"]
        return f", {titolo}" if titolo else ""

    def _saluto(self):
        ora = datetime.now().hour
        saluto = "Buongiorno" if 5 <= ora < 13 else "Buon pomeriggio" if ora < 18 else "Buonasera"
        return f"{saluto}{self._t()}. Tutti i sistemi sono operativi."

    def _ferma(self):
        self.stop.set()
        self.voce.zitto()

    def _invia(self, testo, mostra=True, a_voce=False, spontaneo=False):
        testo = (testo or "").strip()
        if not testo:
            return
        if self.occupato:
            if self.pronto:  # una richiesta nuova interrompe quella in corso
                self.comando_in_attesa = (testo, a_voce)
                self.stop.set()
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
            self._cambia_microfono(not self.microfono)
            return
        if minuscolo == "/voce" or minuscolo.startswith("/voce "):
            self._comando_voce(testo[6:].strip().lower())
            return
        if minuscolo == "/cronologia":
            self._mostra_cronologia()
            return
        if mostra:
            self.hud.domanda(testo)
            self._registra("tu", ("(ti ho sentito) " if spontaneo else "") + testo)
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
            self._info(self.assistente.imposta_chiave(chiave))
            self.hud.imposta_indicatore("ragionamento", self.assistente.ragionamento,
                                        disponibile=self.assistente.supporta_ragionamento)

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
        self._aggiorna_stato()

    def _mostra_compito(self, compito):
        esito = {"completato": "completato", "errore": "non riuscito"}.get(compito.stato, compito.stato)
        self._registra("jarvis", f"Compito {compito.numero} {esito} ({compito.descrizione}):\n{compito.risultato}")
        self.hud.scheda(f"Compito {compito.numero} {esito}", [(compito.descrizione, "info"),
                                                              (compito.risultato, ())])
        self.hud.lampo("avviso" if compito.stato == "completato" else "errore", 2.5)
        self.root.bell()
        notifiche.mostra(f"{self.nome}: compito {compito.numero} {esito}", compito.risultato)
        self.sorvegliante.annota(f"Compito {compito.numero} {esito} ({compito.descrizione}): {compito.risultato}")
        if compito.stato == "completato":
            annuncio = f"Ho terminato il compito {compito.numero}{self._t()}. {compito.risultato}"
        else:
            annuncio = f"Non sono riuscito a completare il compito {compito.numero}{self._t()}."
        self._annuncia(annuncio)
        if self.config["parla"] != "mai":
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
            risposta = random.choice(risposte).format(t=self._t())
            self._annuncia(risposta)
            if self.config["parla"] != "mai":
                self.voce.di(risposta)
            self.orecchio.attendi_comando()
            self.stato_ascolto = f"{'la' if lei else 'ti'} ascolto..."
            self._aggiorna_stato()
            self.root.after(10000, self._fine_attesa)
            return
        self._fine_attesa()
        if self.occupato:  # interrompe la risposta in corso: il nuovo comando parte appena possibile
            self.comando_in_attesa = (testo, True)
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
        self._aggiorna_stato()

        def valuta():
            try:
                decisione = self.assistente.valuta_frase(testo, secondi)
            except ErroreOllama:
                decisione = "ignora"
            self.eventi.put(("decisione", testo, decisione))

        threading.Thread(target=valuta, daemon=True).start()

    def _decisione(self, testo, decisione):
        self.valutando = False
        self._aggiorna_stato()
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

    def _cambia_microfono(self, acceso):
        self.microfono = acceso
        self.hud.imposta_indicatore("microfono", acceso)
        avviso = self.assistente.salva_impostazione("ascolto", acceso)
        if acceso:
            self._avvia_orecchio()
        else:
            self.orecchio.pausa(True)
            self.stato_ascolto = ""
            self._aggiorna_stato()
        self._info(("Microfono acceso: chiamami dicendo \"" + self.nome + "\"." if acceso else
                    "Microfono spento: non ascolto più.") + avviso)

    def _cambia_voce(self, acceso):
        avviso = self.assistente.salva_impostazione("parla", "sempre" if acceso else "mai")
        self.hud.imposta_indicatore("voce", acceso)
        if acceso:
            threading.Thread(target=self._prepara_voce, daemon=True).start()
        else:
            self.voce.zitto()
        self._info(("Voce attiva." if acceso else "Voce spenta: rispondo solo con i sottotitoli.") + avviso)

    def _comando_voce(self, nome):
        if not nome:
            self._cambia_voce(self.config["parla"] == "mai")
            return
        if nome not in voce.VOCI:
            elenco = "\n".join(f"- {n}: {v['descrizione']}" for n, v in voce.VOCI.items())
            self._info(f"Le voci disponibili (per esempio /voce nicola):\n{elenco}", "Voci")
            return
        if nome == "elevenlabs" and not (self.config.get("voce_elevenlabs") or "").strip():
            threading.Thread(target=self._ritrova_elevenlabs, daemon=True).start()
            return
        avviso = self.assistente.salva_impostazione("voce", nome)
        self.voce.zitto()
        if self.config["parla"] == "mai":
            self.assistente.salva_impostazione("parla", "sempre")
        self.hud.imposta_indicatore("voce", True)
        self._info(f"Cambio voce: {voce.VOCI[nome]['descrizione']}.{avviso}")
        threading.Thread(target=self._prepara_voce, kwargs={"nuova": True}, daemon=True).start()

    def _ritrova_elevenlabs(self):
        """/voce elevenlabs senza una voce impostata: la cerca nelle altre copie di Jarvis e su ElevenLabs."""
        try:
            ritrovata = recupero.ritrova_voce(self.config, self.assistente.salva_impostazione, forza=True)
        except Exception:
            ritrovata = ""
        if not ritrovata:
            self.eventi.put(("info", "Non trovo la voce di ElevenLabs che avevi scelto: lancia  py -3.12 prova_voci.py "
                                     "e rispondi p per sceglierla tra quelle pronte."))
            return
        self.eventi.put(("info", ritrovata))
        if self.config["parla"] == "mai":
            self.assistente.salva_impostazione("parla", "sempre")
        self.voce.zitto()
        self._prepara_voce(nuova=True)

    def _cambia_gioco(self, attiva):
        def cambia():
            self.eventi.put(("info", self.assistente.imposta_modalita_gioco(attiva)))
            self.eventi.put(("stato_voce", self.stato_voce))  # ridisegna lo stato

        threading.Thread(target=cambia, daemon=True).start()

    def _gioco_automatico(self, attiva, gioco):
        """Un gioco si è aperto (o chiuso): la modalità gioco si accende (o si spegne) da sola."""
        self._cambia_gioco(attiva)
        nome_gioco = integrazioni.nome_del_gioco(gioco) if gioco else ""
        frase = (f"Vedo {nome_gioco}: modalità gioco attiva{self._t()}. Buona partita." if attiva and nome_gioco else
                 f"Modalità gioco attiva{self._t()}. Buona partita." if attiva else
                 f"Partita finita{self._t()}: torno a pieno regime.")
        self._annuncia(frase)
        if self.config["parla"] != "mai":
            self.voce.di(frase)

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
                self.etichetta_scritta = True
                self._aggiorna_stato()
            self.ultima_risposta += evento[1]
            self.hud.sottotitolo(self.ultima_risposta)
            if self.risposta_a_voce:
                self.voce.aggiungi(evento[1])
        elif tipo == "info":
            self._info(evento[1])
        elif tipo == "pensiero":
            self.hud.log("Sto ragionando...")
        elif tipo == "ritira":  # il modello aveva scritto il suo ragionamento: si toglie
            self.ultima_risposta = ""
            self.hud.sottotitolo("")
            if self.risposta_a_voce:
                self.voce.zitto()
                self.voce.inizia()
        elif tipo == "pulisci":
            self.registro.clear()
            self.hud.sottotitolo("")
            self.hud.domanda("")
        elif tipo == "riavvia":
            self.da_riavviare = True
        elif tipo == "errore":
            self._registra("errore", evento[1])
            self.hud.sottotitolo(evento[1], "errore")
            self.hud.lampo("errore", 2.5)
            if self.risposta_a_voce:
                self.voce.di(f"Mi dispiace{self._t()}, c'è un problema: i dettagli sono sullo schermo.")
        elif tipo == "avviso":
            self._registra("avviso", f"⏰ {evento[1]}")
            self._annuncia(f"⏰ {evento[1]}", "avviso")
            self.hud.lampo("avviso", 4)
            self.root.bell()
            notifiche.mostra(self.nome, evento[1])
            self.sorvegliante.annota(evento[1])
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
            if self.ultima_risposta.strip():
                self._registra("jarvis", self.ultima_risposta.strip())
            # Se Jarvis ha fatto una domanda a voce, la risposta dell'utente non ha bisogno del nome.
            if self.domanda_a_voce and self.ultima_risposta.rstrip().endswith("?"):
                self.orecchio.attendi_comando()
            self._occupa(False)
            for compito in self.compiti_da_mostrare:
                self._mostra_compito(compito)
            self.compiti_da_mostrare.clear()
            self.hud.imposta_indicatore("ragionamento", self.assistente.ragionamento,
                                        disponibile=self.assistente.supporta_ragionamento)
            if self.da_riavviare:
                self._riavvia_quando_ha_finito()
                return
            self._comando_rimasto()
        elif tipo == "pronto":
            self.pronto = True
            for messaggio in self.assistente.cronologia:
                testo = messaggio["content"].split(SEPARATORE_DATI)[0]
                self._registra("tu" if messaggio["role"] == "user" else "jarvis", testo)
            self.hud.imposta_indicatore("ragionamento", self.assistente.ragionamento,
                                        disponibile=self.assistente.supporta_ragionamento)
            self._occupa(False)
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
                self._info(f"Non posso ascoltare: {testo.partition(': ')[2]}{self._consiglio_python()}")
                self.microfono = False
                self.hud.imposta_indicatore("microfono", False)
                testo = ""
            elif testo == "in ascolto" and not self.assistente.voce_attiva:
                self.assistente.voce_attiva = True
                senza_nome = ("" if self.config["attenzione"] == "solo_nome" else
                              " Puoi anche parlarmi senza nome: capisco da solo quando ti rivolgi a me.")
                self.hud.log(f"Ti ascolto: chiamami dicendo \"{self.nome}\". Per interrompermi: \"{self.nome}, "
                             f"basta\".{senza_nome}")
            self.stato_ascolto = testo
            self._aggiorna_stato()
        elif tipo == "stato_voce":
            self.stato_voce = evento[1]
            self._aggiorna_stato()
        elif tipo == "problema_voce":  # resta sullo schermo finché non lo chiudi, e nella cronologia
            riserva = self.config.get("voce_di_riserva", "")
            intanto = (f"\n\nIntanto parlo con la voce di riserva ({riserva})." if riserva and
                       riserva != self.config["voce"] else "")
            self._registra("avviso", evento[1])
            self.hud.scheda("Problema con la voce", evento[1] + intanto + self._consiglio_python())
        elif tipo == "parlando":
            self.parlando = evento[1]
            self._aggiorna_stato()
        elif tipo == "gioco_automatico":
            self._gioco_automatico(evento[1], evento[2])
        elif tipo == "saluto":
            self._registra("jarvis", evento[1])
            self._annuncia(evento[1])
            if self.config["parla"] != "mai":
                self.voce.di(evento[1])
        elif tipo == "sensori":
            self.hud.imposta_sensori(evento[1])
        elif tipo == "meteo":
            _, gradi, condizioni, citta = evento
            self.hud.imposta_meteo(gradi, f"{citta} · {condizioni}" if condizioni else citta)
        elif tipo == "calendario":
            self.eventi_calendario = evento[1]
        elif tipo == "errore_avvio":
            self.errore_avvio = True
            self.occupato = False
            self._registra("errore", evento[1])
            self.hud.sottotitolo(evento[1].split("\n")[0], "errore")
            self.hud.scheda("Non riesco ad avviarmi", [(evento[1], "errore"),
                                                       (f"Sistema il problema e riapri {self.nome}.", "info")])
            self._aggiorna_stato()

    def _comando_rimasto(self):
        if self.comando_in_attesa and not self.occupato:
            (testo, a_voce), self.comando_in_attesa = self.comando_in_attesa, None
            self._invia(testo, a_voce=a_voce)

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
        self.chiuso.set()
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
