"""Notifiche di Windows (il riquadro in basso a destra), usando solo componenti di Windows.

Funziona anche mentre si gioca, salvo quando Windows è in modalità "Non disturbare".
Su altri sistemi non fa niente.
"""

import ctypes
import sys
import threading
import time

NIM_ADD, NIM_DELETE = 0, 2
NIF_ICON, NIF_TIP, NIF_INFO = 0x2, 0x4, 0x10
NIIF_INFO = 0x1
IDI_APPLICATION = 32512


def mostra(titolo, testo):
    if sys.platform == "win32":
        threading.Thread(target=_mostra, args=(titolo, testo), daemon=True).start()


def _mostra(titolo, testo):
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]

    class DatiIcona(ctypes.Structure):  # NOTIFYICONDATAW
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                    ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD), ("guidItem", Guid),
                    ("hBalloonIcon", wintypes.HICON)]

    try:
        user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                           wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.LoadIconW.restype = wintypes.HICON
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
        # Una finestra invisibile a cui Windows collega l'icona della notifica.
        finestra = user32.CreateWindowExW(0, "STATIC", "Jarvis", 0, 0, 0, 0, 0, None, None, None, None)
        dati = DatiIcona()
        dati.cbSize = ctypes.sizeof(DatiIcona)
        dati.hWnd = finestra
        dati.uID = 1
        dati.uFlags = NIF_ICON | NIF_TIP | NIF_INFO
        dati.hIcon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        dati.szTip = "Jarvis"
        dati.szInfoTitle = titolo[:63]
        dati.szInfo = testo[:255]
        dati.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(dati))
        time.sleep(10)  # il tempo di leggerla; poi l'icona sparisce
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(dati))
        user32.DestroyWindow(finestra)
    except (AttributeError, OSError):
        pass
