"""I numeri del pannello SISTEMA della finestra: processore, memoria, scheda video, disco e batteria."""

import ctypes
import shutil
import sys
import time
from pathlib import Path

import strumenti


class Sensori:
    def __init__(self):
        self._tempi_cpu = None
        self._ultima_scheda = 0.0
        self._scheda = None

    def _tempi(self):
        """(tempo inattivo, tempo totale) del processore da quando il PC è acceso."""
        if sys.platform == "win32":
            inattivo, nucleo, utente = (ctypes.c_ulonglong() for _ in range(3))
            if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(inattivo), ctypes.byref(nucleo),
                                                         ctypes.byref(utente)):
                return None
            return inattivo.value, nucleo.value + utente.value  # il tempo "nucleo" comprende quello inattivo
        try:
            valori = [int(v) for v in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        except (OSError, ValueError, IndexError):
            return None
        return valori[3] + (valori[4] if len(valori) > 4 else 0), sum(valori)

    def _processore(self):
        tempi = self._tempi()
        if tempi is None:
            return None
        precedenti, self._tempi_cpu = self._tempi_cpu, tempi
        if precedenti is None or tempi[1] <= precedenti[1]:
            return None
        return max(0.0, min(100.0, 100 * (1 - (tempi[0] - precedenti[0]) / (tempi[1] - precedenti[1]))))

    def leggi(self):
        """{"cpu", "ram", "gpu", "gpu_temp", "vram", "disco", "batteria", "in_carica"}: solo quelli che si leggono."""
        dati = {}
        try:
            cpu = self._processore()
            if cpu is not None:
                dati["cpu"] = cpu
            memoria = strumenti._memoria_ram()
            if memoria:
                dati["ram"] = memoria[0] / memoria[1] * 100
            if time.monotonic() - self._ultima_scheda >= 10:  # nvidia-smi è lento: basta ogni 10 secondi
                self._ultima_scheda = time.monotonic()
                self._scheda = strumenti._scheda_video()
            if self._scheda:
                _, usata, totale, temperatura, utilizzo = self._scheda
                dati.update(gpu=utilizzo, gpu_temp=temperatura, vram=usata / totale * 100 if totale else 0)
            disco = shutil.disk_usage(Path.home().anchor or "/")
            dati["disco"] = disco.used / disco.total * 100
            batteria = strumenti._batteria()
            if batteria:
                dati["batteria"], dati["in_carica"] = batteria
        except Exception:  # un sensore che non risponde non deve fermare la finestra
            pass
        return dati
