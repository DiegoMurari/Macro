#!/usr/bin/env python3
# detect_mouse_rawinput_fixed.py
# Detecta dx/dy em primeira-pessoa via Raw Input.
# F8 para iniciar, F9 para parar. Rode como Administrador.

import ctypes
from ctypes import (
    byref, sizeof, c_uint, c_ushort, c_ulong,
    c_void_p, c_long, wintypes
)
import threading
import keyboard
import time

user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Raw Input constants
RIDEV_INPUTSINK    = 0x00000100
RIDEV_CAPTUREMOUSE = 0x00000200
WM_INPUT           = 0x00FF

# Window‐proc prototype
WNDPROC = ctypes.WINFUNCTYPE(
    c_long,
    c_void_p,    # hwnd
    wintypes.UINT,   # msg
    wintypes.WPARAM, # wParam
    wintypes.LPARAM  # lParam
)

# -- Raw Input structures --------------------------------------------

class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style",        ctypes.c_uint),
        ("lpfnWndProc",  WNDPROC),
        ("cbClsExtra",   ctypes.c_int),
        ("cbWndExtra",   ctypes.c_int),
        ("hInstance",    c_void_p),
        ("hIcon",        c_void_p),
        ("hCursor",      c_void_p),
        ("hbrBackground",c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName",ctypes.c_wchar_p),
    ]

class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType",  c_uint),
        ("dwSize",  c_uint),
        ("hDevice", c_void_p),
        ("wParam",  c_ulong),
    ]

class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags",           c_ushort),
        ("ulButtons",         c_uint),
        ("usButtonFlags",     c_ushort),
        ("usButtonData",      c_ushort),
        ("ulRawButtons",      c_uint),
        ("lLastX",            c_long),
        ("lLastY",            c_long),
        ("ulExtraInformation",c_ulong),
    ]

class RAWINPUTUNION(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE)]

class RAWINPUT(ctypes.Structure):
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("data",   RAWINPUTUNION),
    ]

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", c_ushort),
        ("usUsage",     c_ushort),
        ("dwFlags",     c_uint),
        ("hwndTarget",  c_void_p),
    ]

# -- Detector via Raw Input -----------------------------------------

class RawInputDetector:
    def __init__(self):
        self.hwnd    = None
        self._proc   = None
        self._wc     = None
        self._thread = None
        self.running = False

    def start(self):
        if self.running:
            print("Já detectando.")
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("Detecção iniciada (F9 para parar).")

    def stop(self):
        if not self.running:
            print("Não detectando.")
            return
        self.running = False
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        print("Detecção parada.")

    def _loop(self):
        # define wnd_proc
        def wnd_proc(hwnd, msg, wParam, lParam):
            if msg == WM_INPUT:
                # obter tamanho
                size = c_uint(0)
                user32.GetRawInputData(
                    lParam, 0x10000003, None,
                    byref(size), sizeof(RAWINPUTHEADER)
                )
                buf = ctypes.create_string_buffer(size.value)
                user32.GetRawInputData(
                    lParam, 0x10000003, buf,
                    byref(size), sizeof(RAWINPUTHEADER)
                )
                raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
                if raw.header.dwType == 0:
                    dx = raw.data.mouse.lLastX
                    dy = raw.data.mouse.lLastY
                    if dx or dy:
                        print(f"dx={dx}, dy={dy}")
            return 0

        # register window class
        self._proc = WNDPROC(wnd_proc)
        self._wc   = WNDCLASS()
        self._wc.style        = 0
        self._wc.lpfnWndProc  = self._proc
        self._wc.cbClsExtra   = 0
        self._wc.cbWndExtra   = 0
        self._wc.hInstance    = kernel32.GetModuleHandleW(None)
        self._wc.hIcon        = None
        self._wc.hCursor      = None
        self._wc.hbrBackground= None
        self._wc.lpszMenuName = None
        self._wc.lpszClassName= "RawInputDetectClass"
        user32.RegisterClassW(byref(self._wc))

        # create hidden message-only window
        self.hwnd = user32.CreateWindowExW(
            0,
            self._wc.lpszClassName,
            self._wc.lpszClassName,
            0, 0,0,0,0,
            None, None,
            self._wc.hInstance,
            None
        )

        # register for raw mouse input
        rid = RAWINPUTDEVICE(
            usUsagePage=1,
            usUsage=2,
            dwFlags=RIDEV_INPUTSINK | RIDEV_CAPTUREMOUSE,
            hwndTarget=self.hwnd
        )
        devices = (RAWINPUTDEVICE * 1)(rid)
        if not user32.RegisterRawInputDevices(
            devices, 1, sizeof(RAWINPUTDEVICE)
        ):
            print("Falha no RegisterRawInputDevices")
            self.running = False
            return

        # message loop
        msg = wintypes.MSG()
        PM_REMOVE = 0x0001
        while self.running:
            if user32.PeekMessageW(byref(msg), self.hwnd, 0, 0, PM_REMOVE):
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))
            else:
                time.sleep(0.005)

# -- Main ------------------------------------------------------------

if __name__ == "__main__":
    det = RawInputDetector()
    keyboard.add_hotkey("F8", det.start)
    keyboard.add_hotkey("F9", det.stop)
    print("F8 → iniciar detecção")
    print("F9 → parar detecção")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        det.stop()
        print("Encerrado.")
