import pyautogui
import keyboard
import threading
import time

executando = False

def pressionar_q():
    global executando
    while executando:
        pyautogui.press('q')
        time.sleep(0.05)  # ajustável conforme necessário

def monitorar_teclas():
    global executando
    while True:
        if keyboard.is_pressed('F8') and not executando:
            executando = True
            threading.Thread(target=pressionar_q, daemon=True).start()
            print("▶ Iniciado (F8)")
            time.sleep(0.5)  # evitar múltiplos gatilhos
        elif keyboard.is_pressed('F12') and executando:
            executando = False
            print("⏹ Parado (F12)")
            time.sleep(0.5)

if __name__ == "__main__":
    print("Aguardando F8 para iniciar e F12 para parar...")
    monitorar_teclas()
