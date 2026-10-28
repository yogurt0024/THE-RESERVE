"""L'aspetto di Jarvis: un HUD in stile Iron Man disegnato su un Canvas di tkinter (incluso in Python).

Al centro il reattore: gira piano quando Jarvis aspetta, si illumina quando ascolta, accelera quando pensa e
pulsa con la voce quando parla; in modalità gioco diventa arancione. Sotto il reattore, la linea della voce.
Intorno: ora, meteo, stato del PC, promemoria, impegni e compiti. Sotto, i sottotitoli di quello che dice.
Niente chat: per scrivere basta iniziare a digitare, e la cronologia si apre solo se la chiedi.
"""

import math
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime

COLORI = {
    "sfondo": "#02060c",
    "esagoni": "#0b2533",
    "pannello": "#040d16",
    "bordo_pannello": "#0d2f3f",
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
# I caratteri preferiti, se ci sono sul PC: Bahnschrift è quello "tecnico" di Windows 10 e 11.
TECNICO = ("Bahnschrift", "Segoe UI", "DejaVu Sans")
SOTTILE = ("Bahnschrift Light", "Segoe UI Light", "Segoe UI", "DejaVu Sans")
TESTO = ("Segoe UI", "DejaVu Sans")
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
PUNTI_ONDA = 90  # la linea della voce
STRATI_ALONE = 24  # l'alone intorno al reattore (più strati = sfumatura più morbida)
DURATA_ACCENSIONE = 1.8  # secondi: gli anelli si "montano" all'avvio


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


def _famiglia(preferite):
    disponibili = set(tkfont.families())
    return next((f for f in preferite if f in disponibili), preferite[-1])


class Hud:
    def __init__(self, root, nome):
        self.root = root
        self.nome = nome
        c = COLORI
        self.tela = tk.Canvas(root, bg=c["sfondo"], highlightthickness=0, borderwidth=0)
        self.tela.pack(fill="both", expand=True)
        tecnico, sottile, testo = _famiglia(TECNICO), _famiglia(SOTTILE), _famiglia(TESTO)
        self._basi = {  # nome: (famiglia, grandezza, stile)
            "titolo": (tecnico, 13, "bold"), "orologio": (sottile, 40, ""), "secondi": (sottile, 18, ""),
            "data": (testo, 11, ""), "meteo": (sottile, 34, ""), "piccolo": (tecnico, 9, ""),
            "etichetta": (tecnico, 9, "bold"), "numero": (tecnico, 12, "bold"), "riga": (testo, 10, ""),
            "stato": (tecnico, 12, "bold"), "sottotitoli": (testo, 17, ""), "domanda": (testo, 12, "italic"),
            "campo": (testo, 13, ""), "gradi": (tecnico, 8, ""),
        }
        self.font = {}
        for nome_font, (famiglia, grandezza, stile) in self._basi.items():
            self.font[nome_font] = tkfont.Font(family=famiglia, size=grandezza,
                                               weight="bold" if stile == "bold" else "normal",
                                               slant="italic" if stile == "italic" else "roman")
        self.al_clic_indicatore = lambda nome: None
        self.al_invio = lambda testo: None
        self._stato = "avvio"
        self._gioco = False
        self._lampo = None  # (colore, fino a quando)
        self._angoli = [0.0, 0.0, 0.0, 0.0]
        self._velocita = list(STATI["avvio"][:3])
        self._luce = 0.3
        self._colore = c["accento"]
        self._colore_alone = None
        self._livello = 0.0  # quanto "forte" parla, per le barre e la linea della voce
        self._obiettivo = 0.0
        self._barre_altezze = [0.0] * 64
        self._ultimo = time.monotonic()
        self._inizio = self._ultimo
        self._sottotitolo = ("", "jarvis", 0.0)  # testo, tipo, quando
        self._domanda = ("", 0.0)
        self._log = ("", 0.0)
        self._sensori = {}
        self._agenda = []
        self._righe_disegnate = None
        self._indicatori = {nome: (False, True) for nome, _ in INDICATORI}
        self._larghezza = self._altezza = 0
        self._crea_dinamici()
        self._crea_campo()
        self._crea_scheda()
        self.tela.bind("<Configure>", lambda e: self._disponi(e.width, e.height))

    # --- Costruzione ---

    def _crea_dinamici(self):
        t, c = self.tela, COLORI
        self.alone_esterno = [t.create_oval(0, 0, 1, 1, fill=c["sfondo"], outline="", tags="alone_esterno")
                              for _ in range(STRATI_ALONE)]

        def arco(larghezza, ampiezza):
            return t.create_arc(0, 0, 1, 1, style="arc", width=larghezza, extent=ampiezza, outline=c["accento"])

        self.marcatori = [arco(4, 5) for _ in range(2)]
        self.spazzata = (arco(10, 46), arco(3, 46))  # (alone, linea)
        self.anelli_a = [(arco(20, 78), arco(7, 78)) for _ in range(3)]
        self.anelli_b = [arco(3, 34) for _ in range(6)]
        self.tratteggio = t.create_oval(0, 0, 1, 1, outline=c["linea"], width=2, dash=(2, 7))
        self.reattore = (t.create_oval(0, 0, 1, 1, outline=c["accento"], width=22),
                         t.create_oval(0, 0, 1, 1, outline=c["accento"], width=9))
        self.barre = [t.create_line(0, 0, 0, 0, fill=c["accento"], width=3, capstyle="round", state="hidden")
                      for _ in range(64)]
        self.alone = [t.create_oval(0, 0, 1, 1, fill=c["sfondo"], outline="") for _ in range(5)]
        self.nucleo = t.create_oval(0, 0, 1, 1, fill=c["chiaro"], outline="")
        punti = [0, 0] * PUNTI_ONDA
        self.onda = (t.create_line(*punti, fill=c["linea"], width=6, smooth=True, capstyle="round"),
                     t.create_line(*punti, fill=c["accento"], width=2, smooth=True, capstyle="round"))
        self.scritta_stato = t.create_text(0, 0, text="", fill=c["accento"], font=self.font["stato"])
        self.scritta_dettaglio = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["piccolo"])
        self.orologio = t.create_text(0, 0, text="", fill=c["testo"], font=self.font["orologio"], anchor="nw")
        self.secondi = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["secondi"], anchor="nw")
        self.data = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["data"], anchor="nw")
        self.gradi = t.create_text(0, 0, text="", fill=c["testo"], font=self.font["meteo"], anchor="ne")
        self.cielo = t.create_text(0, 0, text="", fill=c["attenuato"], font=self.font["data"], anchor="ne")
        self.domanda_testo = t.create_text(0, 0, text="", fill=c["utente"], font=self.font["domanda"],
                                           justify="center")
        self.sottotitoli = t.create_text(0, 0, text="", fill=c["testo"], font=self.font["sottotitoli"],
                                         justify="center", anchor="n")
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
                t.create_arc(0, 0, 1, 1, style="arc", width=12, start=90, extent=0, outline=c["linea"],
                             tags="pannello_sinistro"),
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
        fondo = "#03101a"
        self.scheda_cornice = tk.Frame(self.tela, bg=c["accento"], padx=1, pady=1)
        interno = tk.Frame(self.scheda_cornice, bg=fondo)
        interno.pack(fill="both", expand=True)
        testata = tk.Frame(interno, bg=fondo)
        testata.pack(fill="x", padx=16, pady=(12, 4))
        self.scheda_titolo = tk.Label(testata, text="", font=self.font["stato"], fg=c["accento"], bg=fondo)
        self.scheda_titolo.pack(side="left")
        chiudi = tk.Label(testata, text="✕  ESC", font=self.font["etichetta"], fg=c["attenuato"], bg=fondo,
                          cursor="hand2")
        chiudi.pack(side="right")
        chiudi.bind("<Button-1>", lambda e: self.chiudi_scheda())
        tk.Frame(interno, bg=c["linea"], height=1).pack(fill="x", padx=16, pady=(0, 8))
        corpo = tk.Frame(interno, bg=fondo)
        corpo.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.scheda_testo = tk.Text(corpo, wrap="word", font=self.font["riga"], bg=fondo, fg=c["testo"],
                                    relief="flat", borderwidth=0, highlightthickness=0, padx=4, pady=4,
                                    spacing1=2, spacing3=2, cursor="arrow")
        barra = tk.Scrollbar(corpo, command=self.scheda_testo.yview, bg=fondo, troughcolor=fondo,
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
        self.scala = scala = max(0.7, min(1.6, min(w / 1280, h / 800)))
        for nome, (_, grandezza, _) in self._basi.items():
            self.font[nome].configure(size=max(7, round(grandezza * scala)))
        t.delete("statico")
        self.cx, self.cy = w / 2, h * 0.38
        self.raggio = r = max(60, min(w * 0.18, h * 0.235))
        cx, cy = self.cx, self.cy
        self._esagoni(w, h, scala)
        for i, ovale in enumerate(self.alone_esterno):  # l'alone: cerchi sempre più piccoli e più chiari
            quota = 1.9 - i * (0.95 / STRATI_ALONE)
            t.coords(ovale, cx - r * quota, cy - r * quota, cx + r * quota, cy + r * quota)
        self._colore_alone = None
        # Le parti fisse del reattore: il bordo, le tacche e i gradi.
        t.create_oval(cx - r * 1.08, cy - r * 1.08, cx + r * 1.08, cy + r * 1.08, outline=c["linea"], width=1,
                      tags="statico")
        for i in range(96):
            angolo = math.radians(i * 3.75)
            lungo = 0.07 if i % 8 == 0 else 0.035
            x0, y0 = cx + math.cos(angolo) * r * 0.99, cy + math.sin(angolo) * r * 0.99
            x1, y1 = cx + math.cos(angolo) * r * (0.99 - lungo), cy + math.sin(angolo) * r * (0.99 - lungo)
            t.create_line(x0, y0, x1, y1, fill=c["linea"], width=2 if i % 8 == 0 else 1, tags="statico")
        for gradi in (45, 135, 225, 315):
            angolo = math.radians(gradi - 90)
            t.create_text(cx + math.cos(angolo) * r * 1.17, cy + math.sin(angolo) * r * 1.17, text=f"{gradi:03d}",
                          fill=c["linea"], font=self.font["gradi"], tags="statico")
        t.create_oval(cx - r * 0.58, cy - r * 0.58, cx + r * 0.58, cy + r * 0.58, outline=c["linea"], width=1,
                      tags="statico")

        def cerchio(item, quota):
            t.coords(item, cx - r * quota, cy - r * quota, cx + r * quota, cy + r * quota)

        for marcatore in self.marcatori:
            cerchio(marcatore, 1.08)
        for item in self.spazzata:
            cerchio(item, 0.95)
        for alone, arco in self.anelli_a:
            cerchio(alone, 0.84)
            cerchio(arco, 0.84)
            t.itemconfigure(arco, width=max(3, round(r * 0.045)))
            t.itemconfigure(alone, width=max(8, round(r * 0.12)))
        for arco in self.anelli_b:
            cerchio(arco, 0.72)
        cerchio(self.tratteggio, 0.64)
        for item in self.reattore:
            cerchio(item, 0.44)
        t.itemconfigure(self.reattore[1], width=max(4, round(r * 0.06)))
        t.itemconfigure(self.reattore[0], width=max(10, round(r * 0.15)))
        for i, alone in enumerate(self.alone):
            cerchio(alone, 0.36 - i * 0.05)
        cerchio(self.nucleo, 0.12)
        # Sotto il reattore: la linea della voce, lo stato e il dettaglio.
        self.y_onda = cy + r * 1.24
        y_stato = self.y_onda + r * 0.1 + self.font["stato"].metrics("linespace") * 0.6
        t.coords(self.scritta_stato, cx, y_stato)
        y_dettaglio = y_stato + self.font["stato"].metrics("linespace")
        t.coords(self.scritta_dettaglio, cx, y_dettaglio)
        # In alto: nome e ora a sinistra, meteo a destra.
        margine = max(18, round(28 * scala))
        alto_titolo = self.font["titolo"].metrics("linespace")
        t.create_text(margine, margine, text=".".join(self.nome.upper()) + ".", fill=c["accento"],
                      font=self.font["titolo"], anchor="nw", tags="statico")
        for x0, x1 in ((margine, margine + 200 * scala), (w - margine - 200 * scala, w - margine)):
            t.create_line(x0, margine + alto_titolo + 4, x1, margine + alto_titolo + 4, fill=c["linea"],
                          tags="statico")
        t.create_line(margine, margine + alto_titolo + 4, margine + 46 * scala, margine + alto_titolo + 4,
                      fill=c["accento"], width=2, tags="statico")
        y = margine + alto_titolo + 10
        self._posizione_orologio = (margine - 2, y)
        t.coords(self.orologio, margine - 2, y)
        t.coords(self.data, margine, y + self.font["orologio"].metrics("linespace"))
        t.coords(self.gradi, w - margine, y - 4)
        t.coords(self.cielo, w - margine, y - 4 + self.font["meteo"].metrics("linespace"))
        # Pannelli laterali (solo se c'è spazio).
        laterali = w >= 860
        t.itemconfigure("pannello_sinistro", state="normal" if laterali else "hidden")
        t.itemconfigure("pannello_destro", state="normal" if laterali else "hidden")
        self._laterali = laterali
        self._larghezza_pannello = min(w * 0.22, 300 * scala)
        self._y_pannelli = h * 0.27
        self._margine = margine
        if laterali:
            self._pannello_sistema(margine, self._y_pannelli, self._larghezza_pannello, scala)
        self._righe_disegnate = None
        self._pannello_agenda()
        # In basso: domanda, sottotitoli, campo per scrivere e indicatori.
        larghezza_testo = min(w * 0.72, 980 * scala)
        y_sotto = y_dettaglio + self.font["piccolo"].metrics("linespace") * 1.6
        t.coords(self.domanda_testo, cx, y_sotto)
        t.itemconfigure(self.domanda_testo, width=larghezza_testo)
        t.coords(self.sottotitoli, cx, y_sotto + self.font["domanda"].metrics("linespace") * 0.9)
        t.itemconfigure(self.sottotitoli, width=larghezza_testo)
        y_log = h - margine * 2.7
        t.coords(self.log_testo, cx, y_log)
        t.itemconfigure(self.log_testo, width=larghezza_testo)
        t.coords(self.finestra_campo, cx, y_log)
        t.itemconfigure(self.finestra_campo, width=min(w * 0.6, 760 * scala),
                        height=self.font["campo"].metrics("linespace") + 20)
        y = h - margine
        t.create_line(margine, y - margine * 0.9, w - margine, y - margine * 0.9, fill="#071a24", tags="statico")
        x = margine
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
        # Gli strati: l'alone in fondo, sopra gli esagoni, poi le parti fisse, poi tutto quello che si muove.
        t.tag_lower("statico")
        t.tag_lower("griglia")
        t.tag_lower("alone_esterno")
        if self.scheda_aperta:
            self._posiziona_scheda()
        self._ridisegna_indicatori()
        self._ridisegna_pannelli()

    def _esagoni(self, w, h, scala):
        """Lo sfondo a nido d'ape: più acceso vicino al reattore e più scuro verso i bordi, ma non dietro al
        reattore, che resta pulito."""
        t, c = self.tela, COLORI
        lato = 26 * scala
        larghezza, altezza = math.sqrt(3) * lato, 1.5 * lato
        lontano = max(w, h) * 0.75
        riga = 0
        y = 0.0
        while y < h + lato:
            x = (larghezza / 2 if riga % 2 else 0.0)
            while x < w + larghezza:
                distanza = math.hypot(x - self.cx, y - self.cy)
                vicino = (distanza - self.raggio * 1.2) / (self.raggio * 0.6)
                if vicino <= 0:
                    x += larghezza
                    continue
                colore = mescola(c["sfondo"], c["esagoni"], (0.3 + 0.7 * max(0.0, 1 - distanza / lontano))
                                 * min(1.0, vicino))
                punti = []
                for k in range(6):
                    angolo = math.radians(60 * k - 30)
                    punti += [x + math.cos(angolo) * lato * 0.94, y + math.sin(angolo) * lato * 0.94]
                t.create_polygon(*punti, fill="", outline=colore, tags=("statico", "griglia"))
                x += larghezza
            y += altezza
            riga += 1

    def _pannello(self, x0, y0, x1, y1, titolo, tag):
        """Un pannello con gli angoli tagliati, il titolo e una lineetta accesa."""
        t, c = self.tela, COLORI
        taglio = 12 * self.scala
        t.create_polygon(x0 + taglio, y0, x1, y0, x1, y1 - taglio, x1 - taglio, y1, x0, y1, x0, y0 + taglio,
                         fill=c["pannello"], outline=c["bordo_pannello"], tags=tag)
        t.create_line(x0, y0 + taglio, x0 + taglio, y0, fill=c["accento"], width=2, tags=tag)
        t.create_line(x1 - taglio, y1, x1, y1 - taglio, fill=c["accento"], width=2, tags=tag)
        alto = self.font["etichetta"].metrics("linespace")
        t.create_text(x0 + 16 * self.scala, y0 + 10 * self.scala, text=titolo, fill=c["accento"],
                      font=self.font["etichetta"], anchor="nw", tags=tag)
        t.create_line(x0 + 16 * self.scala, y0 + 10 * self.scala + alto + 3, x1 - 16 * self.scala,
                      y0 + 10 * self.scala + alto + 3, fill=c["bordo_pannello"], tags=tag)
        return y0 + 10 * self.scala + alto + 12 * self.scala  # dove comincia il contenuto

    def _pannello_sistema(self, x0, y0, larghezza, scala):
        t, c = self.tela, COLORI
        lato = larghezza / 2
        raggio = min(lato * 0.3, 40 * scala)
        alto_cella = raggio * 2 + self.font["etichetta"].metrics("linespace") + 24 * scala
        altezza_pannello = (10 * scala + self.font["etichetta"].metrics("linespace") + 12 * scala + alto_cella * 2
                            + self.font["riga"].metrics("linespace") * 2.4)
        inizio = self._pannello(x0, y0, x0 + larghezza, y0 + altezza_pannello, "SISTEMA", ("statico",
                                                                                        "pannello_sinistro"))
        for i, (chiave, _, _) in enumerate(SENSORI):
            cx = x0 + lato * (i % 2) + lato / 2
            cy = inizio + alto_cella * (i // 2) + raggio + 10 * scala
            anello, alone, arco, valore, etichetta = self.misuratori[chiave]
            for item in (anello, alone, arco):
                t.coords(item, cx - raggio, cy - raggio, cx + raggio, cy + raggio)
            t.coords(valore, cx, cy)
            t.coords(etichetta, cx, cy + raggio + 13 * scala)
            for k in range(24):  # le tacche intorno al misuratore
                angolo = math.radians(k * 15)
                r0, r1 = raggio * 1.16, raggio * (1.24 if k % 6 == 0 else 1.2)
                t.create_line(cx + math.cos(angolo) * r0, cy + math.sin(angolo) * r0, cx + math.cos(angolo) * r1,
                              cy + math.sin(angolo) * r1, fill=c["linea"], tags=("statico", "pannello_sinistro"))
        t.coords(self.extra_sistema, x0 + 16 * scala, inizio + alto_cella * 2)
        t.itemconfigure(self.extra_sistema, width=larghezza - 32 * scala)

    def _pannello_agenda(self):
        """Il pannello IN PROGRAMMA: alto quanto le righe che contiene."""
        t = self.tela
        t.delete("cornice_agenda")
        if not self._larghezza or not self._laterali:
            return
        larghezza = self._larghezza_pannello
        x0 = self._larghezza - self._margine - larghezza
        y0 = self._y_pannelli
        passo = self.font["riga"].metrics("linespace") * 2.4
        quante = max(1, min(len(self._agenda), len(self.righe_agenda)))
        alto_testa = 10 * self.scala + self.font["etichetta"].metrics("linespace") + 12 * self.scala
        inizio = self._pannello(x0, y0, x0 + larghezza, y0 + alto_testa + quante * passo + 6 * self.scala,
                                "IN PROGRAMMA", "cornice_agenda")
        t.tag_lower("cornice_agenda", self.righe_agenda[0])
        for i, riga in enumerate(self.righe_agenda):
            t.coords(riga, x0 + 16 * self.scala, inizio + i * passo)
            t.itemconfigure(riga, width=larghezza - 32 * self.scala)
        self._righe_disegnate = quante

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
        self.tela.itemconfigure(self.scritta_dettaglio, text=testo)

    def imposta_meteo(self, gradi, descrizione):
        self.tela.itemconfigure(self.gradi, text=f"{round(gradi)}°" if gradi is not None else "")
        self.tela.itemconfigure(self.cielo, text=descrizione)

    def imposta_sensori(self, dati):
        self._sensori = dati
        self._ridisegna_pannelli()

    def imposta_agenda(self, righe):
        """righe: [(testo, tipo)] con tipo "promemoria", "evento", "compito" o "nota"."""
        self._agenda = righe[:len(self.righe_agenda)]
        if self._larghezza and max(1, len(self._agenda)) != self._righe_disegnate:
            self._pannello_agenda()
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
            _, alone, arco, valore, _ = self.misuratori[chiave]
            numero = self._sensori.get(chiave)
            if numero is None:
                t.itemconfigure(valore, text="--")
                t.itemconfigure(arco, extent=0)
                t.itemconfigure(alone, extent=0)
                continue
            colore = c["errore"] if numero >= 92 else c["avviso"] if numero >= 80 else c["accento"]
            ampiezza = -max(1, min(359.9, numero * 3.6))
            t.itemconfigure(valore, text=f"{numero:.0f}{unita}")
            t.itemconfigure(arco, extent=ampiezza, outline=colore)
            t.itemconfigure(alone, extent=ampiezza, outline=mescola(c["sfondo"], colore, 0.22))
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
        *velocita, luce, scritta = STATI[self._stato]
        # Gli stati si passano il testimone piano: velocità, luce e colore cambiano in un attimo, non di colpo.
        morbido = min(1.0, dt * 3)
        for i in range(3):
            self._velocita[i] += (velocita[i] - self._velocita[i]) * morbido
        self._luce += (luce - self._luce) * morbido
        obiettivo = c["errore"] if self._stato == "errore" else c["gioco"] if self._gioco else c["accento"]
        self._colore = mescola(self._colore, obiettivo, min(1.0, dt * 5))
        colore = self._colore
        if self._lampo and adesso < self._lampo[1]:
            colore = mescola(c["sfondo"], self._lampo[0], 0.6 + 0.4 * abs(math.sin(adesso * 6)))
        elif self._lampo:
            self._lampo = None
        luce = self._luce
        respiro = (math.sin((adesso - self._inizio) * (5.5 if self._stato == "pensa" else 1.6)) + 1) / 2
        if self._stato == "parla":
            if random.random() < 0.25:
                self._obiettivo = random.uniform(0.25, 1.0)
            self._livello += (self._obiettivo - self._livello) * min(1.0, dt * 14)
        else:
            self._livello += (0 - self._livello) * min(1.0, dt * 6)
        for i, v in enumerate(self._velocita + [-self._velocita[2] * 0.25]):
            self._angoli[i] = (self._angoli[i] + v * dt) % 360
        # All'accensione gli anelli si "montano": crescono dal nulla fino alla loro lunghezza.
        montaggio = min(1.0, (adesso - self._inizio) / DURATA_ACCENSIONE)
        montaggio = 1 - (1 - montaggio) ** 3
        acceso = mescola(c["sfondo"], colore, luce * (0.75 + 0.25 * respiro))
        alone_anelli = mescola(c["sfondo"], colore, 0.16 * luce + 0.06 * respiro)
        if colore != self._colore_alone:  # l'alone grande cambia solo con il colore
            self._colore_alone = colore
            for i, ovale in enumerate(self.alone_esterno):
                t.itemconfigure(ovale, fill=mescola(c["sfondo"], colore, 0.11 * (i / STRATI_ALONE) ** 2))
        for i, marcatore in enumerate(self.marcatori):
            t.itemconfigure(marcatore, start=self._angoli[3] + i * 180, outline=mescola(c["sfondo"], colore, 0.7))
        t.itemconfigure(self.spazzata[0], start=self._angoli[2], extent=46 * montaggio, outline=alone_anelli)
        t.itemconfigure(self.spazzata[1], start=self._angoli[2], extent=46 * montaggio,
                        outline=mescola(c["sfondo"], colore, luce))
        for i, (alone, arco) in enumerate(self.anelli_a):
            inizio = self._angoli[0] + i * 120
            t.itemconfigure(alone, start=inizio, extent=78 * montaggio, outline=alone_anelli)
            t.itemconfigure(arco, start=inizio, extent=78 * montaggio, outline=acceso)
        for i, arco in enumerate(self.anelli_b):
            t.itemconfigure(arco, start=self._angoli[1] + i * 60, extent=34 * montaggio,
                            outline=mescola(c["sfondo"], colore, luce * 0.7))
        forza_reattore = 0.55 + 0.45 * max(respiro * luce, self._livello)
        t.itemconfigure(self.reattore[0], outline=mescola(c["sfondo"], colore, 0.12 + 0.1 * forza_reattore))
        t.itemconfigure(self.reattore[1], outline=mescola(c["sfondo"], colore, forza_reattore))
        # L'alone del nucleo: cerchi sempre più chiari verso il centro.
        forza = 0.35 + 0.35 * respiro * luce + 0.3 * self._livello
        for i, alone in enumerate(self.alone):
            t.itemconfigure(alone, fill=mescola(c["sfondo"], colore, forza * (0.18 + i * 0.17)))
        t.itemconfigure(self.nucleo, fill=mescola(colore, "#ffffff", 0.35 + 0.5 * forza))
        self._barre(adesso, dt, colore)
        self._onda(adesso, colore)
        if self._gioco and self._stato == "riposo":
            scritta = "MODALITÀ GIOCO"
        t.itemconfigure(self.scritta_stato, text="   ".join(" ".join(p) for p in scritta.split()), fill=colore)
        ora = datetime.now()
        t.itemconfigure(self.orologio, text=f"{ora:%H:%M}")
        x, y = self._posizione_orologio
        t.coords(self.secondi, x + self.font["orologio"].measure(f"{ora:%H:%M}") + 6,
                 y + (self.font["orologio"].metrics("ascent") - self.font["secondi"].metrics("ascent")))
        t.itemconfigure(self.secondi, text=f"{ora:%S}")
        t.itemconfigure(self.data, text=f"{GIORNI[ora.weekday()]} {ora.day} {MESI[ora.month - 1]} {ora.year}")
        self._spegni_testi(adesso)

    def _barre(self, adesso, dt, colore):
        """Le barre della voce intorno al nucleo."""
        t, c = self.tela, COLORI
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

    def _onda(self, adesso, colore):
        """La linea della voce sotto il reattore: quasi piatta quando tace, viva quando ascolta o parla."""
        t, c = self.tela, COLORI
        r, cx, y = self.raggio, self.cx, self.y_onda
        vivacita = 0.05 + (0.25 if self._stato == "ascolto" else 0.0) + 0.95 * self._livello
        ampiezza = r * 0.09 * vivacita
        punti = []
        for i in range(PUNTI_ONDA):
            quota = i / (PUNTI_ONDA - 1)
            busta = math.sin(math.pi * quota) ** 1.5  # alle estremità la linea si posa
            onda = (math.sin(quota * 23 + adesso * 9.1) * 0.55 + math.sin(quota * 41 - adesso * 13.7) * 0.3
                    + math.sin(quota * 7 + adesso * 4.3) * 0.35)
            punti += [cx - r * 0.85 + quota * r * 1.7, y - ampiezza * busta * onda]
        t.coords(self.onda[0], *punti)
        t.coords(self.onda[1], *punti)
        t.itemconfigure(self.onda[0], fill=mescola(c["sfondo"], colore, 0.12 + 0.25 * min(1.0, vivacita)))
        t.itemconfigure(self.onda[1], fill=mescola(c["sfondo"], colore, 0.45 + 0.55 * min(1.0, vivacita)))

    def _spegni_testi(self, adesso):
        """I sottotitoli si spengono piano quando nessuno parla più; le informazioni dopo qualche secondo."""
        t, c = self.tela, COLORI
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
