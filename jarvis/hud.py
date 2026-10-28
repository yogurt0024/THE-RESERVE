"""L'aspetto di Jarvis: un HUD in stile Iron Man disegnato su un Canvas di tkinter (incluso in Python).

Al centro il reattore: gira piano quando Jarvis aspetta, si illumina quando ascolta, accelera quando pensa e
pulsa con la voce quando parla; in modalità gioco diventa oro e rosso. Intorno: ora, meteo, stato del PC,
promemoria, impegni e compiti. Sotto, i sottotitoli di quello che dice. Niente chat: per scrivere basta
iniziare a digitare, e la cronologia si apre solo se la chiedi.
"""

import math
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime

COLORI = {
    "sfondo": "#02060c",
    "griglia": "#061019",
    "linea": "#0e3446",
    "attenuato": "#4b8aa3",
    "testo": "#d9f5ff",
    "accento": "#2ec8f5",
    "chiaro": "#a6ecff",
    "utente": "#8fb3c4",
    "avviso": "#ffd23f",
    "errore": "#ff3b4e",
    "gioco": "#ff8a3d",
}
CARATTERE = "Segoe UI"
CARATTERE_SOTTILE = "Segoe UI Light"
CARATTERE_NUMERI = "Consolas"
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre"]
# Per ogni stato: velocità degli anelli (gradi al secondo), luminosità e la scritta sotto il reattore.
STATI = {
    "avvio": (70, -110, 160, 0.55, "AVVIO DEI SISTEMI"),
    "riposo": (10, -16, 36, 0.75, "IN ATTESA"),
    "ascolto": (28, -44, 90, 1.0, "IN ASCOLTO"),
    "pensa": (130, -210, 260, 0.9, "ELABORAZIONE"),
    "parla": (22, -34, 60, 1.0, "IN COMUNICAZIONE"),
    "errore": (4, -6, 12, 0.8, "SISTEMI NON DISPONIBILI"),
}
INDICATORI = [("microfono", "MICROFONO"), ("voce", "VOCE"), ("gioco", "MODALITÀ GIOCO"),
              ("ragionamento", "RAGIONAMENTO")]
SENSORI = [("cpu", "CPU", "%"), ("ram", "MEMORIA", "%"), ("gpu", "GPU", "%"), ("disco", "DISCO", "%")]
DURATA_SOTTOTITOLI = 25  # secondi: poi i sottotitoli si spengono
LUNGHEZZA_SOTTOTITOLI = 240  # caratteri: di una risposta lunga si vede la parte finale


def mescola(colore1, colore2, quota):
    """Colore a metà strada tra due colori #rrggbb (quota 0 = colore1, 1 = colore2)."""
    quota = max(0.0, min(1.0, quota))
    a = [int(colore1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(colore2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * quota):02x}" for x, y in zip(a, b))


def coda_del_testo(testo, massimo=LUNGHEZZA_SOTTOTITOLI):
    """La parte finale di un testo lungo, cominciando da una frase o almeno da una parola intera."""
    testo = " ".join(testo.split())
    if len(testo) <= massimo:
        return testo
    coda = testo[-massimo:]
    for separatore in (". ", "! ", "? ", ": ", "; ", ", ", " "):
        posizione = coda.find(separatore)
        if 0 <= posizione < massimo // 2:
            return "… " + coda[posizione + len(separatore):]
    return "… " + coda


class Hud:
    def __init__(self, root, nome):
        self.root = root
        self.nome = nome
        c = COLORI
        self.tela = tk.Canvas(root, bg=c["sfondo"], highlightthickness=0, borderwidth=0)
        self.tela.pack(fill="both", expand=True)
        self.font = {
            "titolo": tkfont.Font(family=CARATTERE, size=13, weight="bold"),
            "orologio": tkfont.Font(family=CARATTERE_SOTTILE, size=34),
            "data": tkfont.Font(family=CARATTERE, size=11),
            "meteo": tkfont.Font(family=CARATTERE_SOTTILE, size=30),
            "piccolo": tkfont.Font(family=CARATTERE, size=9),
            "etichetta": tkfont.Font(family=CARATTERE, size=9, weight="bold"),
            "numero": tkfont.Font(family=CARATTERE_NUMERI, size=11, weight="bold"),
            "riga": tkfont.Font(family=CARATTERE, size=10),
            "stato": tkfont.Font(family=CARATTERE, size=11, weight="bold"),
            "sottotitoli": tkfont.Font(family=CARATTERE, size=17),
            "domanda": tkfont.Font(family=CARATTERE, size=12, slant="italic"),
            "campo": tkfont.Font(family=CARATTERE, size=13),
        }
        self.al_clic_indicatore = lambda nome: None
        self.al_invio = lambda testo: None
        self._stato = "avvio"
        self._gioco = False
        self._lampo = None  # (colore, fino a quando)
        self._angoli = [0.0, 0.0, 0.0]
        self._livello = 0.0  # quanto "forte" parla, per le barre intorno al nucleo
        self._obiettivo = 0.0
        self._barre_altezze = [0.0] * 64
        self._ultimo = time.monotonic()
        self._inizio = self._ultimo
        self._sottotitolo = ("", "jarvis", 0.0)  # testo, tipo, quando
        self._domanda = ("", 0.0)
        self._log = ("", 0.0)
        self._dettaglio = ""
        self._meteo = None
        self._sensori = {}
        self._agenda = []
        self._indicatori = {nome: (False, True) for nome, _ in INDICATORI}
        self._larghezza = self._altezza = 0
        self._crea_dinamici()
        self._crea_campo()
        self._crea_scheda()
        self.tela.bind("<Configure>", lambda e: self._disponi(e.width, e.height))

    # --- Costruzione ---

    def _crea_dinamici(self):
        t, c = self.tela, COLORI
        self.anelli = {
            "spazzata": t.create_arc(0, 0, 1, 1, style="arc", width=4, extent=46, outline=c["accento"]),
            "a": [t.create_arc(0, 0, 1, 1, style="arc", width=7, extent=78, outline=c["accento"]) for _ in range(3)],
            "b": [t.create_arc(0, 0, 1, 1, style="arc", width=3, extent=34, outline=c["accento"]) for _ in range(6)],
            "tratteggio": t.create_oval(0, 0, 1, 1, outline=c["linea"], width=2, dash=(2, 7)),
            "reattore": t.create_oval(0, 0, 1, 1, outline=c["accento"], width=9),
        }
        self.barre = [t.create_line(0, 0, 0, 0, fill=c["accento"], width=3, capstyle="round") for _ in range(64)]
        self.alone = [t.create_oval(0, 0, 1, 1, fill=c["sfondo"], outline="") for _ in range(5)]
        self.nucleo = t.create_oval(0, 0, 1, 1, fill=c["chiaro"], outline="")
        self.scritta_stato = t.create_text(0, 0, text="", fill=c["accento"], font=self.font["stato"])
        self.scritta_dettaglio = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["piccolo"])
        self.orologio = t.create_text(0, 0, text="", fill=c["testo"], font=self.font["orologio"], anchor="nw")
        self.data = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["data"], anchor="nw")
        self.gradi = t.create_text(0, 0, text="", fill=c["testo"], font=self.font["meteo"], anchor="ne")
        self.cielo = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["data"], anchor="ne")
        self.domanda_testo = t.create_text(0, 0, text="", fill=c["utente"], font=self.font["domanda"],
                                           justify="center")
        self.sottotitoli = t.create_text(0, 0, text="", fill=c["testo"], font=self.font["sottotitoli"],
                                         justify="center")
        self.log_testo = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["riga"], justify="center")
        self.indicatori = {}
        for nome, etichetta in INDICATORI:
            punto = t.create_oval(0, 0, 1, 1, outline=c["accento"], width=2, tags=("indicatore", nome))
            scritta = t.create_text(0, 0, text=etichetta, fill=c["attenuato"], font=self.font["etichetta"],
                                    anchor="w", tags=("indicatore", nome))
            self.indicatori[nome] = (punto, scritta)
            t.tag_bind(nome, "<Button-1>", lambda e, nome=nome: self.al_clic_indicatore(nome))
            t.tag_bind(nome, "<Enter>", lambda e: self.tela.configure(cursor="hand2"))
            t.tag_bind(nome, "<Leave>", lambda e: self.tela.configure(cursor=""))
        self.suggerimento = t.create_text(0, 0, text="", fill="#2a6a85", font=self.font["piccolo"], anchor="e")
        self.misuratori = {}
        for chiave, etichetta, _ in SENSORI:
            self.misuratori[chiave] = (
                t.create_oval(0, 0, 1, 1, outline=c["linea"], width=5, tags="pannello_sinistro"),
                t.create_arc(0, 0, 1, 1, style="arc", width=5, start=90, extent=0, outline=c["accento"],
                             tags="pannello_sinistro"),
                t.create_text(0, 0, text="--", fill=c["testo"], font=self.font["numero"], tags="pannello_sinistro"),
                t.create_text(0, 0, text=etichetta, fill=c["attenuato"], font=self.font["etichetta"],
                              tags="pannello_sinistro"))
        self.extra_sistema = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["riga"], anchor="nw",
                                           tags="pannello_sinistro")
        self.righe_agenda = [t.create_text(0, 0, text="", fill=c["testo"], font=self.font["riga"], anchor="nw",
                                           tags="pannello_destro") for _ in range(8)]

    def _crea_campo(self):
        c = COLORI
        self.cornice_campo = tk.Frame(self.tela, bg=c["accento"], padx=1, pady=1)
        self.campo = tk.Entry(self.cornice_campo, font=self.font["campo"], bg="#04111b", fg=c["testo"],
                              insertbackground=c["chiaro"], relief="flat", highlightthickness=0, borderwidth=8)
        self.campo.pack(fill="both", expand=True)
        self.campo.bind("<Return>", self._invio)
        self.finestra_campo = self.tela.create_window(0, 0, window=self.cornice_campo, state="hidden")

    def _crea_scheda(self):
        c = COLORI
        self.scheda_cornice = tk.Frame(self.tela, bg=c["accento"], padx=1, pady=1)
        interno = tk.Frame(self.scheda_cornice, bg="#03101a")
        interno.pack(fill="both", expand=True)
        testata = tk.Frame(interno, bg="#03101a")
        testata.pack(fill="x", padx=16, pady=(12, 4))
        self.scheda_titolo = tk.Label(testata, text="", font=self.font["stato"], fg=c["accento"], bg="#03101a")
        self.scheda_titolo.pack(side="left")
        chiudi = tk.Label(testata, text="✕  ESC", font=self.font["etichetta"], fg=c["attenuato"], bg="#03101a",
                          cursor="hand2")
        chiudi.pack(side="right")
        chiudi.bind("<Button-1>", lambda e: self.chiudi_scheda())
        corpo = tk.Frame(interno, bg="#03101a")
        corpo.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.scheda_testo = tk.Text(corpo, wrap="word", font=self.font["riga"], bg="#03101a", fg=c["testo"],
                                    relief="flat", borderwidth=0, highlightthickness=0, padx=4, pady=4,
                                    spacing1=2, spacing3=2, cursor="arrow")
        barra = tk.Scrollbar(corpo, command=self.scheda_testo.yview, bg="#03101a", troughcolor="#03101a",
                             relief="flat", borderwidth=0, width=10)
        self.scheda_testo.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.scheda_testo.pack(side="left", fill="both", expand=True)
        self.scheda_testo.tag_configure("tu", foreground=c["utente"], font=self.font["etichetta"], spacing1=10)
        self.scheda_testo.tag_configure("jarvis", foreground=c["accento"], font=self.font["etichetta"], spacing1=10)
        self.scheda_testo.tag_configure("info", foreground=c["attenuato"])
        self.scheda_testo.tag_configure("avviso", foreground=c["avviso"])
        self.scheda_testo.tag_configure("errore", foreground=c["errore"])
        self.scheda_aperta = False

    # --- Disposizione (a ogni cambio di grandezza della finestra) ---

    def _disponi(self, w, h):
        if (w, h) == (self._larghezza, self._altezza) or w < 50 or h < 50:
            return
        self._larghezza, self._altezza = w, h
        t, c = self.tela, COLORI
        scala = max(0.7, min(1.6, min(w / 1280, h / 800)))
        for nome, base in (("titolo", 13), ("orologio", 34), ("data", 11), ("meteo", 30), ("piccolo", 9),
                           ("etichetta", 9), ("numero", 11), ("riga", 10), ("stato", 11), ("sottotitoli", 17),
                           ("domanda", 12), ("campo", 13)):
            self.font[nome].configure(size=max(7, round(base * scala)))
        t.delete("statico")
        # Una griglia leggera sullo sfondo.
        passo = max(36, round(48 * scala))
        for x in range(0, w, passo):
            t.create_line(x, 0, x, h, fill=c["griglia"], tags=("statico", "griglia"))
        for y in range(0, h, passo):
            t.create_line(0, y, w, y, fill=c["griglia"], tags=("statico", "griglia"))
        self.cx, self.cy = w / 2, h * 0.40
        self.raggio = r = max(60, min(w * 0.19, h * 0.25))
        cx, cy = self.cx, self.cy
        # Anelli fissi: il bordo esterno e le tacche.
        t.create_oval(cx - r * 1.08, cy - r * 1.08, cx + r * 1.08, cy + r * 1.08, outline=c["linea"], width=1,
                      tags="statico")
        for i in range(96):
            angolo = math.radians(i * 3.75)
            lungo = 0.07 if i % 8 == 0 else 0.035
            x0, y0 = cx + math.cos(angolo) * r * 0.99, cy + math.sin(angolo) * r * 0.99
            x1, y1 = cx + math.cos(angolo) * r * (0.99 - lungo), cy + math.sin(angolo) * r * (0.99 - lungo)
            t.create_line(x0, y0, x1, y1, fill=c["linea"], width=2 if i % 8 == 0 else 1, tags="statico")
        t.create_oval(cx - r * 0.58, cy - r * 0.58, cx + r * 0.58, cy + r * 0.58, outline=c["linea"], width=1,
                      tags="statico")

        def cerchio(item, quota):
            t.coords(item, cx - r * quota, cy - r * quota, cx + r * quota, cy + r * quota)

        cerchio(self.anelli["spazzata"], 0.95)
        for arco in self.anelli["a"]:
            cerchio(arco, 0.84)
        for arco in self.anelli["b"]:
            cerchio(arco, 0.72)
        cerchio(self.anelli["tratteggio"], 0.64)
        cerchio(self.anelli["reattore"], 0.44)
        for i, alone in enumerate(self.alone):
            cerchio(alone, 0.36 - i * 0.05)
        cerchio(self.nucleo, 0.12)
        t.itemconfigure(self.anelli["reattore"], width=max(4, round(r * 0.06)))
        for arco in self.anelli["a"]:
            t.itemconfigure(arco, width=max(3, round(r * 0.045)))
        t.coords(self.scritta_stato, cx, cy + r * 1.2)
        t.coords(self.scritta_dettaglio, cx, cy + r * 1.2 + self.font["stato"].metrics("linespace") + 2)
        # In alto: nome e ora a sinistra, meteo a destra.
        margine = max(18, round(28 * scala))
        t.create_text(margine, margine, text=".".join(self.nome.upper()) + ".",
                      fill=c["accento"], font=self.font["titolo"], anchor="nw", tags="statico")
        t.create_line(margine, margine + self.font["titolo"].metrics("linespace") + 4, margine + 180 * scala,
                      margine + self.font["titolo"].metrics("linespace") + 4, fill=c["linea"], tags="statico")
        y = margine + self.font["titolo"].metrics("linespace") + 10
        t.coords(self.orologio, margine - 2, y)
        t.coords(self.data, margine, y + self.font["orologio"].metrics("linespace"))
        t.coords(self.gradi, w - margine, margine)
        t.coords(self.cielo, w - margine, margine + self.font["meteo"].metrics("linespace"))
        # Pannelli laterali (solo se c'è spazio).
        laterali = w >= 860
        t.itemconfigure("pannello_sinistro", state="normal" if laterali else "hidden")
        t.itemconfigure("pannello_destro", state="normal" if laterali else "hidden")
        larghezza_pannello = min(w * 0.22, 300 * scala)
        if laterali:
            self._pannello_sistema(margine, h * 0.30, larghezza_pannello, scala)
            self._pannello_agenda(w - margine - larghezza_pannello, h * 0.30, larghezza_pannello)
        # In basso: domanda, sottotitoli, campo per scrivere e indicatori.
        larghezza_testo = min(w * 0.72, 980 * scala)
        y_sotto = cy + r * 1.2 + self.font["stato"].metrics("linespace") * 2.6
        t.coords(self.domanda_testo, cx, y_sotto)
        t.itemconfigure(self.domanda_testo, width=larghezza_testo)
        t.coords(self.sottotitoli, cx, y_sotto + self.font["domanda"].metrics("linespace") * 1.4)
        t.itemconfigure(self.sottotitoli, width=larghezza_testo, anchor="n")
        t.coords(self.log_testo, cx, h - margine * 2.6)
        t.itemconfigure(self.log_testo, width=larghezza_testo)
        t.coords(self.finestra_campo, cx, h - margine * 2.6)
        t.itemconfigure(self.finestra_campo, width=min(w * 0.6, 760 * scala),
                        height=self.font["campo"].metrics("linespace") + 20)
        x = margine
        y = h - margine
        for nome, _ in INDICATORI:
            punto, scritta = self.indicatori[nome]
            d = max(8, round(10 * scala))
            t.coords(punto, x, y - d / 2, x + d, y + d / 2)
            t.coords(scritta, x + d + 7, y)
            x += d + 7 + self.font["etichetta"].measure(t.itemcget(scritta, "text")) + 26 * scala
        t.coords(self.suggerimento, w - margine, y)
        t.itemconfigure(self.suggerimento, text="Scrivi per parlarmi  ·  Esc interrompe  ·  F2 cronologia  ·  "
                                                "F1 aiuto  ·  F11 schermo intero" if w >= 1100 else
                        "Scrivi per parlarmi  ·  F2 cronologia")
        t.tag_lower("statico")
        t.tag_lower("griglia")
        if self.scheda_aperta:
            self._posiziona_scheda()
        self._ridisegna_indicatori()
        self._ridisegna_pannelli()

    def _cornice(self, x0, y0, x1, y1, titolo, tag):
        t, c = self.tela, COLORI
        lato = 14
        for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            t.create_line(x, y, x + dx * lato, y, fill=c["attenuato"], width=2, tags=("statico", tag))
            t.create_line(x, y, x, y + dy * lato, fill=c["attenuato"], width=2, tags=("statico", tag))
        t.create_text(x0 + 6, y0 - 6, text=titolo, fill=c["accento"], font=self.font["etichetta"], anchor="sw",
                      tags=("statico", tag))

    def _pannello_sistema(self, x0, y0, larghezza, scala):
        t = self.tela
        lato = larghezza / 2
        raggio = min(lato * 0.32, 42 * scala)
        altezza = lato * 2 + 4 + self.font["riga"].metrics("linespace") * 2.6
        self._cornice(x0, y0, x0 + larghezza, y0 + altezza, "SISTEMA", "pannello_sinistro")
        for i, (chiave, _, _) in enumerate(SENSORI):
            cx = x0 + lato * (i % 2) + lato / 2
            cy = y0 + lato * (i // 2) + lato / 2
            anello, arco, valore, etichetta = self.misuratori[chiave]
            t.coords(anello, cx - raggio, cy - raggio, cx + raggio, cy + raggio)
            t.coords(arco, cx - raggio, cy - raggio, cx + raggio, cy + raggio)
            t.coords(valore, cx, cy)
            t.coords(etichetta, cx, cy + raggio + 12 * scala)
        t.coords(self.extra_sistema, x0 + 8, y0 + lato * 2 + 4)
        t.itemconfigure(self.extra_sistema, width=larghezza - 16)

    def _pannello_agenda(self, x0, y0, larghezza):
        altezza = len(self.righe_agenda) * (self.font["riga"].metrics("linespace") * 2.3) + 16
        self._cornice(x0, y0, x0 + larghezza, y0 + altezza, "IN PROGRAMMA", "pannello_destro")
        passo = self.font["riga"].metrics("linespace") * 2.3
        for i, riga in enumerate(self.righe_agenda):
            self.tela.coords(riga, x0 + 10, y0 + 12 + i * passo)
            self.tela.itemconfigure(riga, width=larghezza - 20)

    # --- Quello che la finestra può cambiare ---

    def imposta_stato(self, stato):
        if stato in STATI:
            self._stato = stato

    @property
    def stato(self):
        return self._stato

    def imposta_gioco(self, attivo):
        self._gioco = attivo

    def lampo(self, tipo="avviso", secondi=3.0):
        self._lampo = (COLORI[tipo], time.monotonic() + secondi)

    def sottotitolo(self, testo, tipo="jarvis"):
        self._sottotitolo = (testo, tipo, time.monotonic())
        colore = {"jarvis": COLORI["testo"], "avviso": COLORI["avviso"], "errore": COLORI["errore"]}[tipo]
        self.tela.itemconfigure(self.sottotitoli, text=coda_del_testo(testo), fill=colore)

    def domanda(self, testo):
        self._domanda = (testo, time.monotonic())
        self.tela.itemconfigure(self.domanda_testo, text=f"« {coda_del_testo(testo, 160)} »" if testo else "",
                                fill=COLORI["utente"])

    def log(self, testo):
        self._log = (testo, time.monotonic())
        self.tela.itemconfigure(self.log_testo, text=coda_del_testo(testo, 260), fill=COLORI["attenuato"])

    def dettaglio(self, testo):
        self._dettaglio = testo
        self.tela.itemconfigure(self.scritta_dettaglio, text=testo)

    def imposta_meteo(self, gradi, descrizione):
        self._meteo = (gradi, descrizione)
        self.tela.itemconfigure(self.gradi, text=f"{round(gradi)}°" if gradi is not None else "")
        self.tela.itemconfigure(self.cielo, text=descrizione)

    def imposta_sensori(self, dati):
        self._sensori = dati
        self._ridisegna_pannelli()

    def imposta_agenda(self, righe):
        """righe: [(testo, tipo)] con tipo "promemoria", "evento", "compito" o "nota"."""
        self._agenda = righe[:len(self.righe_agenda)]
        self._ridisegna_pannelli()

    def imposta_indicatore(self, nome, acceso, disponibile=True):
        self._indicatori[nome] = (acceso, disponibile)
        self._ridisegna_indicatori()

    def _ridisegna_indicatori(self):
        c = COLORI
        for nome, (punto, scritta) in self.indicatori.items():
            acceso, disponibile = self._indicatori[nome]
            colore = c["gioco"] if nome == "gioco" and acceso else c["accento"]
            self.tela.itemconfigure(punto, fill=colore if acceso else c["sfondo"],
                                    outline=colore if disponibile else c["linea"])
            self.tela.itemconfigure(scritta, fill=c["testo"] if acceso else
                                    c["attenuato"] if disponibile else c["linea"])

    def _ridisegna_pannelli(self):
        t, c = self.tela, COLORI
        for chiave, _, unita in SENSORI:
            _, arco, valore, _ = self.misuratori[chiave]
            numero = self._sensori.get(chiave)
            if numero is None:
                t.itemconfigure(valore, text="--")
                t.itemconfigure(arco, extent=0)
                continue
            colore = c["errore"] if numero >= 92 else c["avviso"] if numero >= 80 else c["accento"]
            t.itemconfigure(valore, text=f"{numero:.0f}{unita}")
            t.itemconfigure(arco, extent=-max(1, min(359.9, numero * 3.6)), outline=colore)
        extra = []
        if self._sensori.get("gpu_temp") is not None:
            extra.append(f"Scheda video {self._sensori['gpu_temp']}°C · memoria video "
                         f"{self._sensori.get('vram', 0):.0f}%")
        if self._sensori.get("batteria") is not None:
            extra.append(f"Batteria {self._sensori['batteria']}%" + (" in carica" if self._sensori.get("in_carica")
                                                                       else ""))
        t.itemconfigure(self.extra_sistema, text="\n".join(extra))
        simboli = {"promemoria": "◷", "evento": "◆", "compito": "◌", "nota": "·"}
        colori = {"promemoria": c["testo"], "evento": c["chiaro"], "compito": c["accento"], "nota": c["attenuato"]}
        for i, riga in enumerate(self.righe_agenda):
            if i < len(self._agenda):
                testo, tipo = self._agenda[i]
                t.itemconfigure(riga, text=f"{simboli.get(tipo, '·')}  {testo}", fill=colori.get(tipo, c["testo"]))
            else:
                t.itemconfigure(riga, text="")

    # --- Il campo per scrivere ---

    def mostra_campo(self, testo=""):
        self.tela.itemconfigure(self.finestra_campo, state="normal")
        self.tela.itemconfigure(self.log_testo, state="hidden")
        if testo:
            self.campo.insert("end", testo)
        self.campo.focus_set()

    def nascondi_campo(self):
        self.campo.delete(0, "end")
        self.tela.itemconfigure(self.finestra_campo, state="hidden")
        self.tela.itemconfigure(self.log_testo, state="normal")
        self.tela.focus_set()

    @property
    def campo_visibile(self):
        return self.tela.itemcget(self.finestra_campo, "state") != "hidden"

    def _invio(self, _evento=None):
        testo = self.campo.get().strip()
        self.nascondi_campo()
        if testo:
            self.al_invio(testo)
        return "break"

    # --- Le schede (testi lunghi: aiuto, resoconti, cronologia) ---

    def scheda(self, titolo, righe):
        """righe: [(testo, tag)] oppure un testo semplice."""
        if isinstance(righe, str):
            righe = [(righe, ())]
        self.scheda_titolo.configure(text=titolo.upper())
        self.scheda_testo.configure(state="normal")
        self.scheda_testo.delete("1.0", "end")
        for testo, tag in righe:
            self.scheda_testo.insert("end", testo + "\n", tag)
        self.scheda_testo.configure(state="disabled")
        self.scheda_testo.see("end" if len(righe) > 1 else "1.0")
        self.scheda_aperta = True
        self._posiziona_scheda()

    def _posiziona_scheda(self):
        self.scheda_cornice.place(relx=0.5, rely=0.47, anchor="center", relwidth=0.7 if self._larghezza > 900 else
                                  0.92, relheight=0.62)
        self.scheda_cornice.lift()

    def chiudi_scheda(self):
        self.scheda_aperta = False
        self.scheda_cornice.place_forget()

    # --- Animazione ---

    def anima(self):
        adesso = time.monotonic()
        dt, self._ultimo = min(0.1, adesso - self._ultimo), adesso
        if self._larghezza:
            self._disegna(adesso, dt)
        self.root.after(33, self.anima)

    def _disegna(self, adesso, dt):
        t, c = self.tela, COLORI
        velocita_a, velocita_b, velocita_spazzata, luce, scritta = STATI[self._stato]
        colore = c["errore"] if self._stato == "errore" else c["gioco"] if self._gioco else c["accento"]
        if self._lampo and adesso < self._lampo[1]:
            colore = mescola(c["sfondo"], self._lampo[0], 0.6 + 0.4 * abs(math.sin(adesso * 6)))
        elif self._lampo:
            self._lampo = None
        respiro = (math.sin((adesso - self._inizio) * (5.5 if self._stato == "pensa" else 1.6)) + 1) / 2
        if self._stato == "parla":
            if random.random() < 0.25:
                self._obiettivo = random.uniform(0.25, 1.0)
            self._livello += (self._obiettivo - self._livello) * min(1.0, dt * 14)
        else:
            self._livello += (0 - self._livello) * min(1.0, dt * 6)
        self._angoli[0] = (self._angoli[0] + velocita_a * dt) % 360
        self._angoli[1] = (self._angoli[1] + velocita_b * dt) % 360
        self._angoli[2] = (self._angoli[2] - velocita_spazzata * dt) % 360
        acceso = mescola(c["sfondo"], colore, luce * (0.75 + 0.25 * respiro))
        t.itemconfigure(self.anelli["spazzata"], start=self._angoli[2], outline=mescola(c["sfondo"], colore, luce))
        for i, arco in enumerate(self.anelli["a"]):
            t.itemconfigure(arco, start=self._angoli[0] + i * 120, outline=acceso)
        for i, arco in enumerate(self.anelli["b"]):
            t.itemconfigure(arco, start=self._angoli[1] + i * 60, outline=mescola(c["sfondo"], colore, luce * 0.7))
        t.itemconfigure(self.anelli["reattore"], outline=mescola(c["sfondo"], colore, 0.55 + 0.45 * max(
            respiro * luce, self._livello)))
        # L'alone del nucleo: cerchi sempre più chiari verso il centro.
        forza = 0.35 + 0.35 * respiro * luce + 0.3 * self._livello
        for i, alone in enumerate(self.alone):
            t.itemconfigure(alone, fill=mescola(c["sfondo"], colore, forza * (0.18 + i * 0.17)))
        t.itemconfigure(self.nucleo, fill=mescola(colore, "#ffffff", 0.35 + 0.5 * forza))
        # Le barre della voce intorno al nucleo.
        r, cx, cy = self.raggio, self.cx, self.cy
        for i, barra in enumerate(self.barre):
            obiettivo = self._livello * (0.35 + 0.65 * abs(math.sin(i * 0.7 + adesso * 7.3) *
                                                          math.sin(i * 0.23 - adesso * 3.1)))
            self._barre_altezze[i] += (obiettivo - self._barre_altezze[i]) * min(1.0, dt * 18)
            altezza = self._barre_altezze[i]
            if altezza < 0.02:
                t.itemconfigure(barra, state="hidden")
                continue
            angolo = math.radians(i * 360 / len(self.barre) + self._angoli[0] * 0.3)
            r0, r1 = r * 0.50, r * (0.50 + 0.11 * altezza)
            t.coords(barra, cx + math.cos(angolo) * r0, cy + math.sin(angolo) * r0, cx + math.cos(angolo) * r1,
                     cy + math.sin(angolo) * r1)
            t.itemconfigure(barra, state="normal", fill=mescola(c["sfondo"], colore, 0.5 + 0.5 * altezza))
        if self._gioco and self._stato == "riposo":
            scritta = "MODALITÀ GIOCO"
        t.itemconfigure(self.scritta_stato, text="   ".join(" ".join(p) for p in scritta.split()), fill=colore)
        # Ora e data, una volta al secondo basta, ma costa poco.
        ora = datetime.now()
        t.itemconfigure(self.orologio, text=f"{ora:%H:%M:%S}")
        t.itemconfigure(self.data, text=f"{GIORNI[ora.weekday()]} {ora.day} {MESI[ora.month - 1]} {ora.year}")
        # I sottotitoli si spengono piano quando nessuno parla più.
        testo, tipo, quando = self._sottotitolo
        if testo and self._stato not in ("parla", "pensa"):
            passati = adesso - quando
            if passati > DURATA_SOTTOTITOLI + 3:
                self.sottotitolo("")
                self.domanda("")
            elif passati > DURATA_SOTTOTITOLI:
                quota = (passati - DURATA_SOTTOTITOLI) / 3
                base = {"jarvis": c["testo"], "avviso": c["avviso"], "errore": c["errore"]}[tipo]
                t.itemconfigure(self.sottotitoli, fill=mescola(base, c["sfondo"], quota))
                t.itemconfigure(self.domanda_testo, fill=mescola(c["utente"], c["sfondo"], quota))
        testo_log, quando_log = self._log
        if testo_log and adesso - quando_log > 12:
            self.log("")
