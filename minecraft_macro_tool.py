#!/usr/bin/env python3
# minecraft_macro_tool.py

import os
import sys
import time
import json
import threading
import keyboard
import ctypes
from ctypes import byref, sizeof, wintypes
import tkinter as tk
from tkinter import ttk, filedialog

# -- WinAPI & ctypes setup ---------------------------------------------------

user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# CreateWindowExW signature (64-bit hInstance/lpParam)
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,    # dwExStyle
    ctypes.c_wchar_p,  # lpClassName
    ctypes.c_wchar_p,  # lpWindowName
    wintypes.DWORD,    # dwStyle
    ctypes.c_int,      # X
    ctypes.c_int,      # Y
    ctypes.c_int,      # nWidth
    ctypes.c_int,      # nHeight
    wintypes.HWND,     # hWndParent
    wintypes.HMENU,    # hMenu
    ctypes.c_void_p,   # hInstance
    ctypes.c_void_p    # lpParam
]
user32.CreateWindowExW.restype = wintypes.HWND

# DefWindowProcW signature (64-bit wParam/lParam)
user32.DefWindowProcW.argtypes = [
    ctypes.c_void_p,  # hWnd
    wintypes.UINT,    # Msg
    ctypes.c_void_p,  # wParam
    ctypes.c_void_p   # lParam
]
user32.DefWindowProcW.restype = ctypes.c_long

# Window procedure prototype
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,  # hWnd
    ctypes.c_uint,    # Msg
    ctypes.c_void_p,  # wParam
    ctypes.c_void_p   # lParam
)

# Structures for Raw Input
class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", ctypes.c_ushort),
        ("usUsage", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint),
        ("hwndTarget", ctypes.c_void_p),
    ]

class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", ctypes.c_uint),
        ("dwSize", ctypes.c_uint),
        ("hDevice", ctypes.c_void_p),
        ("wParam", ctypes.c_ulong),
    ]

class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", ctypes.c_ushort),
        ("ulButtons", ctypes.c_uint),
        ("usButtonFlags", ctypes.c_ushort),
        ("usButtonData", ctypes.c_ushort),
        ("ulRawButtons", ctypes.c_uint),
        ("lLastX", ctypes.c_long),
        ("lLastY", ctypes.c_long),
        ("ulExtraInformation", ctypes.c_uint),
    ]

class RAWINPUT_UNION(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE)]

class RAWINPUT(ctypes.Structure):
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("data", RAWINPUT_UNION),
    ]

# -- Raw Input Recorder -------------------------------------------------------

class RawInputRecorder:
    RIDEV_INPUTSINK = 0x00000100
    WM_INPUT        = 0x00FF

    def __init__(self):
        self.hwnd     = None
        self.thread   = None
        self.running  = False
        self.callback = None

    def start(self, on_move):
        """Begin capturing raw mouse movement; on_move(dx, dy) called each event."""
        self.callback = on_move
        self.running  = True
        self.thread   = threading.Thread(target=self._message_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop capturing and destroy the hidden window."""
        self.running = False
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    def _message_loop(self):
        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == RawInputRecorder.WM_INPUT:
                size = ctypes.c_uint(0)
                user32.GetRawInputData(
                    lparam, 0x10000003, None, byref(size), sizeof(RAWINPUTHEADER)
                )
                buf = ctypes.create_string_buffer(size.value)
                user32.GetRawInputData(
                    lparam, 0x10000003, buf, byref(size), sizeof(RAWINPUTHEADER)
                )
                raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
                if raw.header.dwType == 0:  # MOUSE
                    dx = raw.data.mouse.lLastX
                    dy = raw.data.mouse.lLastY
                    if self.callback:
                        self.callback(dx, dy)
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc = WNDPROC(wnd_proc)
        wc   = WNDCLASS()
        wc.style         = 0
        wc.lpfnWndProc   = proc
        wc.cbClsExtra    = wc.cbWndExtra = 0
        wc.hInstance     = kernel32.GetModuleHandleW(None)
        wc.hIcon = wc.hCursor = wc.hbrBackground = None
        wc.lpszMenuName  = None
        wc.lpszClassName = "RawInputListener"
        user32.RegisterClassW(byref(wc))

        self.hwnd = user32.CreateWindowExW(
            0,
            wc.lpszClassName,
            wc.lpszClassName,
            0, 0, 0, 0, 0,
            None, None,
            wc.hInstance,
            None
        )

        rid = RAWINPUTDEVICE(
            usUsagePage=1, usUsage=2,
            dwFlags=RawInputRecorder.RIDEV_INPUTSINK,
            hwndTarget=self.hwnd
        )
        user32.RegisterRawInputDevices((RAWINPUTDEVICE * 1)(rid), 1, sizeof(RAWINPUTDEVICE))

        msg = wintypes.MSG()
        PM_REMOVE = 0x0001
        while self.running:
            if user32.PeekMessageW(byref(msg), self.hwnd, 0, 0, PM_REMOVE):
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))

# -- Globals ------------------------------------------------------------------

events            = []
recording         = False
playing           = False
raw_recorder      = None
segment_timer     = None
segment_end_time  = 0
loaded_macro_file = None

# -- Configuration -----------------------------------------------------------

def load_config():
    default = {
        "record_start_hotkey": "F9",
        "record_stop_hotkey":  "F10",
        "play_start_hotkey":   "F11",
        "play_stop_hotkey":    "F12",
        "auto_reset_time":     130,
        "mouse_sensitivity":   10.0
    }
    if not os.path.exists("Config.json"):
        with open("Config.json", "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        print("Config.json criado com valores padrão.", flush=True)
        return default
    try:
        with open("Config.json", "r", encoding="utf-8") as f:
            conf = json.load(f)
        print("Config.json carregado.", flush=True)
        return conf
    except Exception as e:
        print("Erro ao carregar Config.json:", e, flush=True)
        return default

config            = load_config()
segment_time      = config.get("auto_reset_time", 130)
mouse_sensitivity = config.get("mouse_sensitivity", 10.0)

# -- Recording & Segmentation ------------------------------------------------

def on_key_event(event):
    if recording and event.event_type in ("down", "up"):
        events.append({
            "type":       "key",
            "scan_code":  event.scan_code,
            "event_type": event.event_type,
            "time":       time.time()
        })

def init_segment_timer(update_callback=None):
    global segment_timer, segment_end_time
    segment_end_time = time.time() + segment_time
    segment_timer    = threading.Timer(segment_time, on_segment)
    segment_timer.start()

    def countdown():
        while recording:
            rem = int(segment_end_time - time.time())
            if rem <= 0:
                break
            print(f"Tempo restante: {rem}s", flush=True)
            if update_callback:
                update_callback(rem)
            time.sleep(1)

    threading.Thread(target=countdown, daemon=True).start()

def save_macro():
    base     = "mineracao"
    existing = [f for f in os.listdir() if f.startswith(base) and f.endswith(".json")]
    nums     = [int(f[len(base):-5]) for f in existing if f[len(base):-5].isdigit()]
    version  = max(nums) + 1 if nums else 1
    fname    = f"{base}{version}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"Macro salva em {fname}", flush=True)

def auto_reset_script():
    keyboard.send("t"); time.sleep(0.1)
    keyboard.write("/mina reset"); keyboard.send("enter")
    time.sleep(0.1)
    print("Enviado /mina reset. Reiniciando script...", flush=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def on_segment():
    if recording:
        print("=== Segmentação automática ===", flush=True)
        save_macro()
        auto_reset_script()

def start_record(update_callback=None):
    global recording, events, raw_recorder
    if recording:
        return
    events.clear()
    recording    = True
    raw_recorder = RawInputRecorder()
    raw_recorder.start(lambda dx, dy: events.append({
        "type": "mouse", "dx": dx, "dy": dy, "time": time.time()
    }))
    keyboard.hook(on_key_event)
    init_segment_timer(update_callback)
    print("Gravação iniciada.", flush=True)

def stop_record():
    global recording, raw_recorder, segment_timer
    if not recording:
        return
    recording = False
    if raw_recorder:
        raw_recorder.stop()
    keyboard.unhook(on_key_event)
    if segment_timer:
        segment_timer.cancel()
    save_macro()  # always save on stop
    print(f"Gravação parada. {len(events)} eventos registrados e salvos.", flush=True)

# -- Macro Loading -----------------------------------------------------------

def load_macro_file():
    global loaded_macro_file
    fname = filedialog.askopenfilename(
        initialdir=os.getcwd(),
        title="Selecione um macro (.json)",
        filetypes=[("JSON files","*.json"),("All files","*.*")]
    )
    if fname:
        loaded_macro_file = fname
        print(f"Macro carregada: {fname}", flush=True)
        label_loaded.config(text=os.path.basename(fname))

# -- Playback -----------------------------------------------------------------

def _play_thread(macro_events):
    start_offset = time.time() - macro_events[0]["time"]
    for e in macro_events:
        if not playing:
            break
        wait = e["time"] + start_offset - time.time()
        if wait > 0:
            time.sleep(wait)
        if e.get("type") == "mouse":
            dx = int(e["dx"] * mouse_sensitivity)
            dy = -int(e["dy"] * mouse_sensitivity)
            user32.mouse_event(0x0001, dx, dy, 0, 0)
        elif e.get("type") == "key":
            et = e.get("event_type"); sc = e.get("scan_code")
            if et == "down":
                keyboard.press(sc)
            elif et == "up":
                keyboard.release(sc)
    print("Reprodução concluída." if playing else "Reprodução interrompida.", flush=True)

def play_macro():
    global playing
    if recording:
        print("Pare a gravação antes de reproduzir.", flush=True)
        return
    if playing:
        return
    if loaded_macro_file:
        fname = loaded_macro_file
    else:
        files = [f for f in os.listdir() if f.startswith("mineracao") and f.endswith(".json")]
        if not files:
            print("Nenhum macro encontrado.", flush=True)
            return
        files.sort(key=lambda f: int(f[len("mineracao"):-5]))
        fname = files[-1]
    with open(fname, "r", encoding="utf-8") as f:
        macro = json.load(f)
    playing = True
    threading.Thread(target=_play_thread, args=(macro,), daemon=True).start()
    print(f"Reproduzindo {fname}...", flush=True)

def stop_play():
    global playing
    if playing:
        playing = False
        print("Reprodução parada.", flush=True)

# -- GUI ----------------------------------------------------------------------

root = tk.Tk()
root.title("Minecraft Macro Tool")
root.resizable(False, False)

frame = ttk.Frame(root, padding=10)
frame.grid()

btn_start      = ttk.Button(frame, text="Iniciar Gravação",     command=lambda: start_record(update_label))
btn_stop       = ttk.Button(frame, text="Parar Gravação",        command=stop_record)
btn_load_macro = ttk.Button(frame, text="Carregar Macro",        command=load_macro_file)
btn_play       = ttk.Button(frame, text="Iniciar Reprodução",    command=play_macro)
btn_stop_play  = ttk.Button(frame, text="Parar Reprodução",      command=stop_play)

btn_start.grid     (row=0, column=0, padx=5, pady=5)
btn_stop.grid      (row=0, column=1, padx=5, pady=5)
btn_load_macro.grid(row=1, column=0, padx=5, pady=5)
btn_play.grid      (row=1, column=1, padx=5, pady=5)
btn_stop_play.grid (row=2, column=1, padx=5, pady=5)

label_count  = ttk.Label(frame, text=f"Próximo reset em: {segment_time}s")
label_count.grid   (row=2, column=0, pady=(10,0))

label_loaded = ttk.Label(frame, text="Nenhum macro carregado")
label_loaded.grid  (row=3, column=0, columnspan=2, pady=(5,0))

def update_label(remaining):
    label_count.config(text=f"Próximo reset em: {remaining}s")

# Hotkeys (work even when GUI is open)
keyboard.add_hotkey(config["record_start_hotkey"], lambda: start_record(update_label))
keyboard.add_hotkey(config["record_stop_hotkey"], stop_record)
keyboard.add_hotkey(config["play_start_hotkey"], play_macro)
keyboard.add_hotkey(config["play_stop_hotkey"], stop_play)

root.mainloop()
