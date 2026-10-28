"""Gli occhi di Jarvis: una foto dello schermo (o della webcam) da far guardare al modello che vede.

La foto si fa con i componenti di Windows (niente librerie da installare oltre a numpy), si rimpicciolisce e
si passa al modello sul PC: non viene salvata né inviata a nessuno.
"""

import ctypes
import struct
import sys
import zlib

LATO_MASSIMO = 1280  # pixel: abbastanza per leggere, abbastanza poco per un modello piccolo


class ErroreSchermo(Exception):
    pass


def cattura_schermo():
    """La foto dello schermo principale come array numpy (altezza, larghezza, 3) in RGB."""
    if sys.platform != "win32":
        raise ErroreSchermo("guardare lo schermo funziona solo su Windows")
    import numpy as np
    from ctypes import wintypes

    class IntestazioneBitmap(ctypes.Structure):  # BITMAPINFOHEADER
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    for funzione in (user32.GetDC, gdi32.CreateCompatibleDC, gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
        funzione.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    larghezza, altezza = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    schermo = user32.GetDC(None)
    memoria = gdi32.CreateCompatibleDC(schermo)
    immagine = gdi32.CreateCompatibleBitmap(schermo, larghezza, altezza)
    try:
        gdi32.SelectObject(memoria, immagine)
        gdi32.BitBlt(memoria, 0, 0, larghezza, altezza, schermo, 0, 0, 0x00CC0020)  # SRCCOPY
        intestazione = IntestazioneBitmap(ctypes.sizeof(IntestazioneBitmap), larghezza, -altezza, 1, 32, 0)
        dati = ctypes.create_string_buffer(larghezza * altezza * 4)
        if not gdi32.GetDIBits(memoria, immagine, 0, altezza, dati, ctypes.byref(intestazione), 0):
            raise ErroreSchermo("Windows non mi ha dato la foto dello schermo")
    finally:
        gdi32.DeleteObject(immagine)
        gdi32.DeleteDC(memoria)
        user32.ReleaseDC(None, schermo)
    bgra = np.frombuffer(dati.raw, dtype=np.uint8).reshape(altezza, larghezza, 4)
    return bgra[:, :, 2::-1].copy()  # da BGRA a RGB


def cattura_webcam():
    """Una foto dalla webcam (serve opencv-python). Array numpy (altezza, larghezza, 3) in RGB."""
    try:
        import cv2
    except ImportError:
        raise ErroreSchermo("per la webcam serve la libreria opencv: py -3.12 -m pip install opencv-python") from None
    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(0)
    try:
        if not camera.isOpened():
            raise ErroreSchermo("non trovo la webcam (o la sta usando un altro programma)")
        for _ in range(5):  # le prime foto sono spesso scure: la webcam deve regolare la luce
            riuscita, foto = camera.read()
        if not riuscita:
            raise ErroreSchermo("la webcam non ha scattato la foto")
    finally:
        camera.release()
    return foto[:, :, ::-1].copy()  # da BGR a RGB


def rimpicciolisci(rgb, lato=LATO_MASSIMO):
    import numpy as np

    altezza, larghezza = rgb.shape[:2]
    passo = max(1, int(np.ceil(max(altezza, larghezza) / lato)))
    if passo == 1:
        return rgb
    # Media dei pixel a blocchi: più leggibile che saltarne qualcuno.
    altezza, larghezza = altezza // passo * passo, larghezza // passo * passo
    blocchi = rgb[:altezza, :larghezza].reshape(altezza // passo, passo, larghezza // passo, passo, 3)
    return blocchi.mean(axis=(1, 3)).astype(np.uint8)


def in_png(rgb):
    """Un'immagine RGB (array numpy uint8) come file PNG, solo con la libreria standard."""
    altezza, larghezza = rgb.shape[:2]
    righe = b"".join(b"\x00" + rgb[y].tobytes() for y in range(altezza))  # filtro 0 su ogni riga

    def blocco(tipo, dati):
        return struct.pack(">I", len(dati)) + tipo + dati + struct.pack(">I", zlib.crc32(tipo + dati) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + blocco(b"IHDR", struct.pack(">IIBBBBB", larghezza, altezza, 8, 2, 0, 0, 0))
            + blocco(b"IDAT", zlib.compress(righe, 6)) + blocco(b"IEND", b""))
