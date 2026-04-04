"""
MikuTTS — ElevenLabs voice chat bot for Half-Life (GoldSrc)
MIT License — see LICENSE
"""

import time
import re
import requests
import sounddevice as sd
import soundfile as sf
import os
import sys
import threading
import psutil
import ctypes
import numpy as np
import soxr
import csv
import hashlib
import configparser
import platform
import keyboard

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

if IS_WINDOWS:
    import win32gui
    import win32con
    import win32api

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# --- Load config ---
cfg = configparser.ConfigParser()
cfg.read(os.path.join(os.path.dirname(__file__), "config.ini"), encoding="utf-8")

API_KEY        = cfg.get("elevenlabs", "api_key")
VOICE_ID       = cfg.get("elevenlabs", "voice_id")
MODEL          = cfg.get("elevenlabs", "model", fallback="eleven_multilingual_v2")
STABILITY      = cfg.getfloat("elevenlabs", "stability", fallback=0.5)
SIMILARITY     = cfg.getfloat("elevenlabs", "similarity_boost", fallback=0.75)

LOG_FILE       = cfg.get("game", "log_file")
HL_PROCESS     = cfg.get("game", "process_name", fallback="hl.exe")
TRIGGER        = cfg.get("game", "trigger", fallback="!miku")
PTT_KEY        = cfg.get("game", "ptt_key", fallback="k")
CHAT_KEY       = cfg.get("game", "chat_key", fallback="y")
CHAT_MAX_LEN   = cfg.getint("game", "chat_max_len", fallback=200)

COOLDOWN_EXTRA = cfg.getfloat("audio", "cooldown_extra", fallback=2.0)
SAMPLE_RATE    = cfg.getint("audio", "sample_rate", fallback=48000)

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR      = os.path.join(BASE_DIR, cfg.get("cache", "cache_dir", fallback="cache"))
CACHE_CSV      = os.path.join(BASE_DIR, cfg.get("cache", "cache_csv", fallback="cache/cache.csv"))
LOCK_FILE      = os.path.join(BASE_DIR, cfg.get("app", "lock_file", fallback="miku_tts.lock"))

os.makedirs(CACHE_DIR, exist_ok=True)

# --- Colors ---
class C:
    RESET  = "\033[0m"
    GRAY   = "\033[90m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    PINK   = "\033[95m"
    BOLD   = "\033[1m"

def enable_ansi():
    if IS_WINDOWS:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

def log(tag, msg, color=C.GRAY):
    ts = time.strftime("%H:%M:%S")
    print(f"{C.GRAY}[{ts}]{C.RESET} {color}{C.BOLD}[{tag}]{C.RESET} {color}{msg}{C.RESET}", flush=True)

# --- VK map (Windows) ---
VK_MAP = {
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
    'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
    'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
    'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
    'z': 0x5A,
}

# --- Cooldown ---
cooldown_lock = threading.Lock()
cooldown_map = {}

def is_on_cooldown(text):
    with cooldown_lock:
        until = cooldown_map.get(text.lower(), 0)
        if time.time() < until:
            remaining = until - time.time()
            log("COOL", f"Skipping duplicate \"{text}\" — {remaining:.1f}s remaining", C.YELLOW)
            return True
    return False

def set_cooldown(text, duration):
    with cooldown_lock:
        cooldown_map[text.lower()] = time.time() + duration + COOLDOWN_EXTRA

# --- Cache ---
def load_cache():
    cache = {}
    if os.path.exists(CACHE_CSV):
        with open(CACHE_CSV, "r", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) == 2:
                    cache[row[0]] = row[1]
    return cache

def save_cache(text, mp3_path):
    with open(CACHE_CSV, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([text, mp3_path])

# --- TTS ---
def elevenlabs_tts(text):
    log("API", f"Requesting TTS: \"{text}\"", C.CYAN)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": API_KEY, "Content-Type": "application/json"}
    body = {
        "text": text,
        "model_id": MODEL,
        "voice_settings": {"stability": STABILITY, "similarity_boost": SIMILARITY}
    }
    r = requests.post(url, headers=headers, json=body)
    r.raise_for_status()
    log("API", f"Response received — {len(r.content)} bytes", C.GREEN)
    return r.content

def get_audio(text, cache):
    if text in cache:
        mp3_path = cache[text]
        if os.path.exists(mp3_path):
            log("CACHE", f"Using cached: {mp3_path}", C.GREEN)
            return mp3_path
    t = time.time()
    audio = elevenlabs_tts(text)
    log("TIMER", f"API took: {time.time()-t:.3f}s", C.YELLOW)
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    mp3_path = os.path.join(CACHE_DIR, f"{h}.mp3")
    with open(mp3_path, "wb") as f:
        f.write(audio)
    save_cache(text, mp3_path)
    cache[text] = mp3_path
    log("CACHE", f"Saved: {mp3_path}", C.GREEN)
    return mp3_path

# --- Audio ---
def prepare_audio(mp3_path):
    data, sr = sf.read(mp3_path)
    if len(data.shape) == 1:
        data = np.column_stack([data, data])
    if sr != SAMPLE_RATE:
        data = soxr.resample(data, sr, SAMPLE_RATE, quality='MQ')
        sr = SAMPLE_RATE
    data = (data * 32767).astype(np.int16)
    return data, sr

def find_vbaudio_device():
    devices = sd.query_devices()
    log("AUDIO", "Searching for VB-Audio Speakers (MME, hostapi=0):", C.YELLOW)
    for i, d in enumerate(devices):
        if "vb-audio" in d["name"].lower() or "cable" in d["name"].lower():
            print(f"         {C.GRAY}[{i}] IN:{d['max_input_channels']} OUT:{d['max_output_channels']} API:{d['hostapi']} — {d['name']}{C.RESET}", flush=True)
    for i, d in enumerate(devices):
        if ("speakers" in d["name"].lower() and "vb-audio" in d["name"].lower()
                and d["max_output_channels"] > 0 and d["hostapi"] == 0):
            return i, d["name"]
    for i, d in enumerate(devices):
        if "vb-audio" in d["name"].lower() and d["max_output_channels"] > 0 and d["hostapi"] == 0:
            return i, d["name"]
    return None, None

def find_vbaudio_device_linux():
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        name = d["name"].lower()
        if d["max_output_channels"] > 0 and ("virtual" in name or "virt" in name):
            return i, d["name"]
    return None, None

# --- Key press ---
def get_hl_window():
    if not IS_WINDOWS:
        return None
    results = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip() == "Half-Life":
                results.append(hwnd)
    win32gui.EnumWindows(callback, None)
    if results:
        log("INPUT", f"Found HL window: {win32gui.GetWindowText(results[0])}", C.GRAY)
    return results[0] if results else None

def send_key(key, down=True):
    if IS_WINDOWS:
        hwnd = get_hl_window()
        if not hwnd:
            log("INPUT", "HL window not found!", C.RED)
            return
        vk = VK_MAP.get(key.lower(), ord(key.upper()))
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        if down:
            lparam = (scan << 16) | 1
            win32api.SendMessage(hwnd, win32con.WM_KEYDOWN, vk, lparam)
            log("INPUT", f"WM_KEYDOWN sent: {key.upper()}", C.YELLOW)
        else:
            lparam = (scan << 16) | (1 | 0xC0000000)
            win32api.SendMessage(hwnd, win32con.WM_KEYUP, vk, lparam)
            log("INPUT", f"WM_KEYUP sent: {key.upper()}", C.YELLOW)
    elif IS_LINUX:
        import subprocess
        action = "keydown" if down else "keyup"
        try:
            subprocess.run(["xdotool", action, key], check=True)
            log("INPUT", f"xdotool {action}: {key}", C.YELLOW)
        except Exception as e:
            log("INPUT", f"xdotool error: {e}", C.RED)

# --- Playback ---
def play_to_virtual_mic(mp3_path, cable_idx, local_idx):
    data, sr = prepare_audio(mp3_path)
    duration = len(data) / sr
    log("AUDIO", f"Duration: {duration:.2f}s, {sr}Hz", C.YELLOW)

    send_key(PTT_KEY, down=True)
    time.sleep(0.3)

    def play_local():
        try:
            sd.play(data, sr, device=local_idx)
            sd.wait()
        except Exception as e:
            log("AUDIO", f"Local playback error: {e}", C.RED)

    local_thread = threading.Thread(target=play_local, daemon=True)
    local_thread.start()

    try:
        sd.play(data, sr, device=cable_idx)
        sd.wait()
    except Exception as e:
        log("AUDIO", f"Virtual mic playback error: {e}", C.RED)

    local_thread.join(timeout=duration + 1)
    time.sleep(0.2)
    send_key(PTT_KEY, down=False)
    log("AUDIO", f"Done ({duration:.2f}s), PTT released", C.GREEN)

    return duration

# --- Speak helper ---
def speak(text, cable_idx, local_idx, cache, source="LOG"):
    if not text:
        return
    if is_on_cooldown(text):
        return
    log("TRIGGER", f"[{source}] Triggered: \"{text}\"", C.PINK)
    update_status(f"Speaking: {text[:40]}...")
    try:
        mp3_path = get_audio(text, cache)
        duration = play_to_virtual_mic(mp3_path, cable_idx, local_idx)
        set_cooldown(text, duration)
        update_status("Listening to chat...")
    except Exception as e:
        log("ERR", f"Error: {e}", C.RED)
        update_status(f"Error: {e}")

# --- Keyboard hook ---
def start_keyboard_hook(cable_idx, local_idx, cache):
    """
    Intercepts chat key (default Y), captures typed text,
    and triggers TTS immediately on Enter — before the log is written.
    """
    state = {
        "active": False,
        "buffer": ""
    }

    def on_key(event):
        if event.event_type != "down":
            return

        # Chat key pressed — start capturing
        if event.name == CHAT_KEY and not state["active"]:
            state["active"] = True
            state["buffer"] = ""
            log("HOOK", f"Chat opened ({CHAT_KEY.upper()}), capturing input...", C.CYAN)
            return

        if not state["active"]:
            return

        if event.name == "enter":
            text = state["buffer"].strip()
            state["active"] = False
            state["buffer"] = ""
            log("HOOK", f"Chat submitted: \"{text}\"", C.CYAN)

            # Check trigger and length
            pattern = re.compile(re.escape(TRIGGER) + r'\s+(.*)', re.IGNORECASE)
            m = pattern.search(text)
            if m and len(text) <= CHAT_MAX_LEN:
                tts_text = m.group(1).strip()
                threading.Thread(
                    target=speak,
                    args=(tts_text, cable_idx, local_idx, cache, "HOOK"),
                    daemon=True
                ).start()

        elif event.name == "escape":
            state["active"] = False
            state["buffer"] = ""
            log("HOOK", "Chat cancelled (ESC)", C.GRAY)

        elif event.name == "backspace":
            state["buffer"] = state["buffer"][:-1]

        elif event.name == "space":
            state["buffer"] += " "

        elif len(event.name) == 1:
            # Regular character
            if keyboard.is_pressed("shift"):
                state["buffer"] += event.name.upper()
            else:
                state["buffer"] += event.name

    keyboard.hook(on_key)
    log("HOOK", f"Keyboard hook active — chat key: {CHAT_KEY.upper()}, max length: {CHAT_MAX_LEN}", C.GREEN)

# --- Single instance ---
def check_single_instance():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                show_error("MikuTTS is already running!\nClose the existing instance first.")
                sys.exit(0)
        except:
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def cleanup_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def is_hl_running():
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] and proc.info["name"].lower() == HL_PROCESS.lower():
            return True
    return False

def show_error(msg):
    if IS_WINDOWS:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("MikuTTS — Error", msg)
        root.destroy()
    else:
        print(f"\n[ERROR] {msg}\n", flush=True)

# --- Startup checks ---
def startup_checks():
    log("CHECK", "Running startup checks...", C.YELLOW)

    log("CHECK", "Checking Half-Life process...", C.YELLOW)
    if not is_hl_running():
        log("CHECK", f"Half-Life ({HL_PROCESS}) is not running!", C.RED)
        show_error("Half-Life is not running!\nPlease start the game first.")
        cleanup_lock()
        sys.exit(0)
    log("CHECK", "Half-Life is running — OK", C.GREEN)

    log("CHECK", "Checking log file...", C.YELLOW)
    if not os.path.exists(LOG_FILE):
        log("CHECK", f"Log file not found: {LOG_FILE}", C.RED)
        show_error(f"Log file not found!\n{LOG_FILE}\n\nAdd -condebug to game launch options.")
        cleanup_lock()
        sys.exit(0)
    log("CHECK", "Log file found — OK", C.GREEN)

    log("CHECK", "Checking audio device...", C.YELLOW)
    if IS_WINDOWS:
        cable_idx, cable_name = find_vbaudio_device()
    else:
        cable_idx, cable_name = find_vbaudio_device_linux()

    if cable_idx is None:
        log("CHECK", "Virtual audio device not found!", C.RED)
        if IS_WINDOWS:
            show_error("VB-Audio Speakers not found!\nInstall VB-Cable from https://vb-audio.com/Cable/\nand reboot your PC.")
        else:
            show_error("Virtual audio device not found!\nRun: pactl load-module module-virtual-source source_name=VirtualMic")
        cleanup_lock()
        sys.exit(0)
    log("CHECK", f"Virtual audio found: [{cable_idx}] {cable_name} — OK", C.GREEN)

    local_idx = sd.default.device[1]
    devices = sd.query_devices()
    log("CHECK", f"Local output: [{local_idx}] {devices[local_idx]['name']} — OK", C.GREEN)

    log("CHECK", "All checks passed!", C.GREEN)
    print(flush=True)
    return cable_idx, local_idx

# --- Tray ---
status_text = "Running..."

def update_status(text):
    global status_text
    status_text = text

def create_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(255, 105, 180))
    draw.text((22, 18), "M", fill=(255, 255, 255))
    return img

# --- Log monitor loop ---
def monitor_loop(cable_idx, local_idx, cache):
    pattern = re.compile(re.escape(TRIGGER) + r'\s+(.*)', re.IGNORECASE)

    while True:
        if not is_hl_running():
            log("HL", "Half-Life closed, waiting for restart...", C.GRAY)
            update_status("Waiting for HL...")
            while not is_hl_running():
                time.sleep(3)
            log("HL", "Half-Life started again!", C.GREEN)

        update_status("Listening to chat...")

        while not os.path.exists(LOG_FILE):
            if not is_hl_running():
                break
            time.sleep(1)

        if not os.path.exists(LOG_FILE):
            continue

        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, 2)
                log("FILE", "Listening for new lines...", C.GREEN)

                while True:
                    if not is_hl_running():
                        log("HL", "Half-Life closed", C.GRAY)
                        update_status("Half-Life closed")
                        break

                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    log("LOG", line.rstrip(), C.GRAY)

                    m = pattern.search(line)
                    if m:
                        text = m.group(1).strip()
                        if not text:
                            continue
                        # If already spoken via keyboard hook — skip
                        speak(text, cable_idx, local_idx, cache, source="LOG")

        except Exception as e:
            log("ERR", f"File error: {e}", C.RED)
            time.sleep(2)

def on_quit(icon, item):
    log("SYS", "Exiting...", C.GRAY)
    cleanup_lock()
    icon.stop()
    os._exit(0)

def run_tray(cable_idx, local_idx, cache):
    thread = threading.Thread(target=monitor_loop, args=(cable_idx, local_idx, cache), daemon=True)
    thread.start()

    icon = pystray.Icon(
        "MikuTTS",
        create_icon(),
        "Miku TTS",
        menu=pystray.Menu(
            pystray.MenuItem(lambda text: status_text, lambda i, item: None),
            pystray.MenuItem("Quit", on_quit)
        )
    )
    icon.run()

def run_headless(cable_idx, local_idx, cache):
    log("SYS", "Running in headless mode (no tray)", C.YELLOW)
    try:
        monitor_loop(cable_idx, local_idx, cache)
    except KeyboardInterrupt:
        log("SYS", "Interrupted by user", C.GRAY)
        cleanup_lock()
        sys.exit(0)

def main():
    enable_ansi()
    check_single_instance()

    print(f"{C.PINK}{C.BOLD}")
    print("  ███╗   ███╗██╗██╗  ██╗██╗   ██╗    ████████╗████████╗███████╗")
    print("  ████╗ ████║██║██║ ██╔╝██║   ██║       ██╔══╝    ██╔══╝██╔════╝")
    print("  ██╔████╔██║██║█████╔╝ ██║   ██║       ██║       ██║   ███████╗")
    print("  ██║╚██╔╝██║██║██╔═██╗ ██║   ██║       ██║       ██║        ██╗")
    print("  ██║ ╚═╝ ██║██║██║  ██╗╚██████╔╝       ██║       ██║   ███████║")
    print("  ╚═╝     ╚═╝╚═╝╚═╝  ╚═╝ ╚═════╝        ╚═╝       ╚═╝   ╚══════╝")
    print(f"{C.RESET}", flush=True)

    log("SYS", f"Platform: {platform.system()}", C.CYAN)
    log("SYS", f"Trigger: {TRIGGER}", C.CYAN)
    log("SYS", f"PTT key: {PTT_KEY.upper()}", C.CYAN)
    log("SYS", f"Chat key: {CHAT_KEY.upper()}", C.CYAN)
    log("SYS", f"Cooldown: +{COOLDOWN_EXTRA}s", C.CYAN)

    cache = load_cache()
    log("CACHE", f"Loaded {len(cache)} cached entries", C.GREEN)

    cable_idx, local_idx = startup_checks()

    # Start keyboard hook for instant response
    start_keyboard_hook(cable_idx, local_idx, cache)

    log("SYS", "Starting monitor...", C.GREEN)

    if TRAY_AVAILABLE and IS_WINDOWS:
        run_tray(cable_idx, local_idx, cache)
    else:
        run_headless(cable_idx, local_idx, cache)

if __name__ == "__main__":
    main()