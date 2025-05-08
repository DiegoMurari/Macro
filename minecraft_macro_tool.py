import os
import subprocess
import sys
import time
import json
import threading
import keyboard
import ctypes
from ctypes import byref, sizeof, wintypes, c_uint
from pynput import mouse
from pynput.mouse import Controller, Button

# parameters from config.json will still be loaded, but GUI is skipped in autoplay:
AUTO_LOOP = "--autoplay" in sys.argv

def _do_exec_autoplay():
    python = sys.executable
    script = os.path.abspath(sys.argv[0])
    args = [f'"{python}"', f'"{script}"', "--autoplay"]
    os.execv(python, args)

# WinAPI for playback
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# -- Raw Input Recorder via pynput -------------------------------------------
class RawInputRecorder:
    """
    Captura dx/dy globalmente usando pynput.
    on_move(dx, dy) chamado a cada evento de movimento.
    """
    def __init__(self):
        self._listener = None
        self._last_pos = None

    def start(self, on_move):
        if self._listener:
            return
        self._last_pos = None

        def _on_move(x, y):
            if self._last_pos is None:
                self._last_pos = (x, y)
                return
            dx = x - self._last_pos[0]
            dy = y - self._last_pos[1]
            self._last_pos = (x, y)
            if dx or dy:
                on_move(dx, dy)

        self._listener = mouse.Listener(on_move=_on_move)
        self._listener.start()
        print("[RawInput] Listener pynput iniciado", flush=True)

    def stop(self):
        if not self._listener:
            return
        self._listener.stop()
        self._listener = None
        self._last_pos = None
        print("[RawInput] Listener pynput parado", flush=True)

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
segment_time      = config["auto_reset_time"]
mouse_sensitivity = config["mouse_sensitivity"]

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
    _do_exec_autoplay()

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
    raw_recorder.stop()
    keyboard.unhook(on_key_event)
    segment_timer.cancel()
    save_macro()
    print(f"Gravação parada. {len(events)} eventos registrados e salvos.", flush=True)

# -- Macro Loading -----------------------------------------------------------
def load_macro_file():
    global loaded_macro_file
    from tkinter import filedialog  # import só quando GUI existir
    fname = filedialog.askopenfilename(
        initialdir=os.getcwd(),
        title="Selecione um macro (.json)",
        filetypes=[("JSON files","*.json"),("All files","*.*")]
    )
    if fname:
        loaded_macro_file = fname
        print(f"Macro carregada: {fname}", flush=True)

# -- Periodic Actions --------------------------------------------------------
def _periodic_actions():
    mouse_ctrl = Controller()
    mouse_ctrl.press(Button.left)
    try:
        while playing:
            time.sleep(10)
            dx = int(180 * mouse_sensitivity)
            user32.mouse_event(0x0001, dx, 0, 0, 0)
            keyboard.press('3'); keyboard.release('3')
    finally:
        mouse_ctrl.release(Button.left)

# -- Playback -----------------------------------------------------------------
def _play_thread(macro_events):
    keyboard.block_key('esc')  # evita ESC tirando foco

    record_start = macro_events[0]["time"]
    play_start   = time.time()
    threading.Thread(target=_periodic_actions, daemon=True).start()

    for e in macro_events:
        if not playing:
            break
        rel    = e["time"] - record_start
        target = play_start + rel
        wait   = target - time.time()
        if wait > 0:
            time.sleep(wait)
        if e["type"] == "mouse":
            dx, dy = int(e["dx"]), -int(e["dy"])
            user32.mouse_event(0x0001, dx, dy, 0, 0)
        else:
            et, sc = e["event_type"], e["scan_code"]
            if et == "down":
                keyboard.press(sc)
            else:
                keyboard.release(sc)

    print("Reprodução concluída.", flush=True)
    keyboard.send("t"); time.sleep(0.1)
    keyboard.write("/mina reset"); keyboard.send("enter")
    time.sleep(0.1)
    keyboard.unblock_key('esc')  # restaura ESC
    _do_exec_autoplay()

def play_macro():
    global playing
    if recording or playing:
        return
    if loaded_macro_file:
        fname = loaded_macro_file
    else:
        files = [f for f in os.listdir() if f.startswith("mineracao") and f.endswith(".json")]
        files.sort(key=lambda f: int(f[len("mineracao"):-5]))
        fname = files[-1] if files else None
    if not fname:
        print("Nenhum macro encontrado.", flush=True)
        return
    with open(fname, "r", encoding="utf-8") as f:
        macro_events = json.load(f)
    playing = True
    threading.Thread(target=_play_thread, args=(macro_events,), daemon=True).start()
    print(f"Reproduzindo {fname}...", flush=True)

def stop_play():
    global playing
    if playing:
        playing = False
        # diagnóstico
        print("[DEBUG] stop_play() chamado – parando macro e fechando VSCode...", flush=True)

        # tenta fechar o VSCode (inclui /T para processos filhos)
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", "Code.exe"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("[DEBUG] taskkill executado com sucesso.", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"[DEBUG] taskkill falhou: {e}", flush=True)

        # sai deste script
        sys.exit(0)


# -- GUI (só se não for autoplay) -------------------------------------------
if not AUTO_LOOP:
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("Minecraft Macro Tool")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=10)
    frame.grid()

    btn_start      = ttk.Button(frame, text="Iniciar Gravação",  command=lambda: start_record(update_label))
    btn_stop       = ttk.Button(frame, text="Parar Gravação",    command=stop_record)
    btn_load_macro = ttk.Button(frame, text="Carregar Macro",    command=load_macro_file)
    btn_play       = ttk.Button(frame, text="Iniciar Reprodução",command=play_macro)
    btn_stop_play  = ttk.Button(frame, text="Parar Reprodução",  command=stop_play)

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

    keyboard.add_hotkey(config["record_start_hotkey"], lambda: start_record(update_label))
    keyboard.add_hotkey(config["record_stop_hotkey"],  stop_record)
    keyboard.add_hotkey(config["play_start_hotkey"],   play_macro)
    keyboard.add_hotkey(config["play_stop_hotkey"],    stop_play)

    root.mainloop()
else:
    # sem GUI em autoplay: inicia reprodução automaticamente
    threading.Timer(0.5, play_macro).start()
    # mantém o processo vivo até o execv
    while True:
        time.sleep(1)                                                                  