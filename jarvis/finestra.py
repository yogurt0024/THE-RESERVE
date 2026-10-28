"""La finestra grafica di Jarvis, fatta con tkinter (incluso in Python).

Il modello lavora in un thread separato e manda gli eventi alla finestra
attraverso una coda, così la finestra non si blocca mai.
"""

import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox

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


def _mescola(colore1, colore2, quota):
    """Colore a metà strada tra due colori #rrggbb (quota 0 = colore1, 1 = colore2)."""
    a = [int(colore1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(colore2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * quota):02x}" for x, y in zip(a, b))


class Finestra:
    def __init__(self, config):
        self.nome = config["nome"]
        self.eventi = queue.Queue()
        self.stop = threading.Event()
        self.occupato = True  # finché il modello non è pronto non si può scrivere
        self.a_capo = True
        self.etichetta_scritta = False
        self.fase = 0
        self.assistente = Assistente(config, avvisa=lambda messaggio: self.eventi.put(("avviso", messaggio)))

        self.root = tk.Tk()
        self.root.title(self.nome)
        self.root.geometry("780x660")
        self.root.minsize(480, 400)
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
        self.stato = tk.Label(testata, text="avvio in corso...", font=(CARATTERE, 10),
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
        self.campo.bind("<Escape>", lambda _: self.stop.set())
        self.pulsante = self._bottone(riga, "Invia", self._invia_o_ferma, principale=True)
        self.pulsante.pack(side="left", padx=(8, 0))

        comandi = tk.Frame(fondo, bg=c["sfondo"])
        comandi.pack(fill="x", pady=(8, 0))
        for testo, comando in (("Nuova conversazione", "/nuova"), ("Memoria", "/memoria"), ("Aiuto", "/aiuto")):
            self._bottone(comandi, testo, lambda comando=comando: self._invia(comando, mostra=False)).pack(
                side="left", padx=(0, 6))
        self.ragionamento = tk.BooleanVar(value=False)
        self.casella = tk.Checkbutton(
            comandi, text="Ragionamento profondo", variable=self.ragionamento, command=self._cambia_ragionamento,
            font=(CARATTERE, 10), bg=c["sfondo"], fg=c["attenuato"], selectcolor=c["pannello"],
            activebackground=c["sfondo"], activeforeground=c["testo"], highlightthickness=0, state="disabled")
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

    def _anima(self):
        """Il "reattore" in alto a sinistra pulsa mentre Jarvis lavora."""
        if self.occupato:
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
        else:
            self.eventi.put(("pronto",))

    def _invia_o_ferma(self):
        if self.occupato:
            self.stop.set()
        else:
            self._invia()

    def _invia(self, testo=None, mostra=True):
        if self.occupato:
            return
        if testo is None:
            testo = self.campo.get().strip()
            self.campo.delete(0, "end")
        if not testo:
            return
        if testo.lower() in ("/esci", "esci"):
            self._chiudi()
            return
        if mostra:
            self._messaggio("Tu", testo, "tu")
        self.etichetta_scritta = False
        self._occupa(True)
        threading.Thread(target=self._lavora, args=(testo,), daemon=True).start()

    def _lavora(self, testo):
        try:
            for evento in self.assistente.gestisci(testo, self.stop):
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
        self.pulsante.configure(text="Ferma" if occupato else "Invia")
        self.stato.configure(text="sto elaborando..." if occupato else "pronto")

    def _cambia_ragionamento(self):
        self.assistente.ragionamento = self.ragionamento.get()

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
                self.etichetta_scritta = True
            self._scrivi(evento[1], "grassetto" if evento[2] else ())
        elif tipo == "info":
            self._riga(evento[1], "info")
        elif tipo == "pensiero":
            self.stato.configure(text="sto ragionando...")
        elif tipo == "pulisci":
            self._pulisci()
        elif tipo == "errore":
            self._riga(evento[1], "errore")
        elif tipo == "avviso":
            self._riga(f"⏰ {evento[1]}", "avviso")
            self.root.bell()
            self._in_primo_piano()
        elif tipo == "fatto":
            self._occupa(False)
            self.ragionamento.set(self.assistente.ragionamento)
            if not self.a_capo:
                self._scrivi("\n")
        elif tipo == "pronto":
            self._mostra_cronologia()
            self._riga(self.assistente.stato(), "info")
            if self.assistente.supporta_ragionamento:
                self.casella.configure(state="normal")
                self.ragionamento.set(self.assistente.ragionamento)
            self._occupa(False)
            self.campo.focus_set()
        elif tipo == "errore_avvio":
            self._riga(f"{evento[1]}\n\nSistema il problema e riapri {self.nome}.", "errore")
            self.stato.configure(text="non disponibile")
            self.occupato = False  # ferma l'animazione; casella di testo e pulsante restano disattivati
            self.pulsante.configure(state="disabled")
            self.campo.configure(state="disabled")

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

    def _chiudi(self):
        self.stop.set()
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
