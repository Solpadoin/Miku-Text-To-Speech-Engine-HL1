# 🎤 MikuTTS — ElevenLabs Voice Chat Bot for Half-Life

[![License: MIT](https://img.shields.io/badge/License-MIT-pink.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey.svg)]()

MikuTTS is an open-source voice bot that monitors the in-game chat of **Half-Life (GoldSrc engine)**, detects a configurable trigger keyword (default: `!miku`), sends the text to **ElevenLabs Text-to-Speech API**, and plays the generated audio through a **virtual microphone** — so other players on the server hear the voice in real time.

---

## 🎯 How It Works

```
You type in HL1 chat:   !miku hello everyone
        ↓
Script reads game log:  qconsole.log (via -condebug)
        ↓
ElevenLabs API:         generates audio with your custom voice
        ↓
Audio plays through:    VB-Audio Virtual Cable (Windows)
                        PulseAudio virtual sink (Linux)
        ↓
PTT key is simulated:   K key sent to Half-Life window
        ↓
Other players hear:     your custom AI voice in voice chat
```

Audio is also played locally through your default speakers so you can hear what was spoken.

---

## ✅ Requirements

### System

| Platform | Requirements |
|----------|-------------|
| Windows 10/11 | VB-Audio Virtual Cable, Python 3.10+ |
| Linux (Ubuntu/Debian) | PulseAudio or PipeWire, xdotool, Python 3.10+ |

### Python Version

**Python 3.10 or higher** is required.

Check your version:
```bash
python --version
```

### Python Libraries

Install all dependencies:
```bash
pip install -r requirements.txt
```

**requirements.txt:**
```
requests>=2.31.0
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.24.0
soxr>=0.3.7
psutil>=5.9.0
pywin32>=306          # Windows only
pystray>=0.19.5       # Windows only (system tray)
Pillow>=10.0.0        # Windows only (tray icon)
```

> **Linux users:** Skip `pywin32`, `pystray`, and `Pillow`. Install `xdotool` via your package manager instead.

---

## 🔧 Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/yourusername/MikuTTS.git
cd MikuTTS
```

### Step 2 — Install Python dependencies

**Windows:**
```bash
pip install -r requirements.txt
```

**Linux:**
```bash
pip install requests sounddevice soundfile numpy soxr psutil
sudo apt install xdotool   # Ubuntu/Debian
# or
sudo pacman -S xdotool     # Arch
```

### Step 3 — Install virtual audio driver

**Windows — VB-Audio Virtual Cable:**
1. Download from https://vb-audio.com/Cable/
2. Extract and run `VBCABLE_Setup_x64.exe` as Administrator
3. Click **Install Driver**
4. **Reboot your PC**
5. Go to Windows Sound settings → Recording → set **CABLE Output** as default microphone

**Linux — PulseAudio virtual sink:**
```bash
# Load virtual sink (acts as a virtual speaker → microphone loopback)
pactl load-module module-null-sink sink_name=VirtualMic sink_properties=device.description=VirtualMic
pactl load-module module-virtual-source source_name=VirtualMicSource master=VirtualMic.monitor

# Set as default microphone
pactl set-default-source VirtualMicSource
```

To make it permanent, add to `/etc/pulse/default.pa`:
```
load-module module-null-sink sink_name=VirtualMic sink_properties=device.description=VirtualMic
load-module module-virtual-source source_name=VirtualMicSource master=VirtualMic.monitor
```

### Step 4 — Configure Half-Life

Add `-condebug` to your Half-Life launch options in Steam:
1. Steam → Right-click Half-Life → Properties
2. **Launch Options** → add `-condebug`
3. Launch the game — `qconsole.log` will appear in the game root folder

### Step 5 — Get ElevenLabs API key and Voice ID

1. Sign up at https://elevenlabs.io (free tier available)
2. Go to **Profile** → copy your **API Key**
3. Go to **Voices** → select or create a voice → copy the **Voice ID**

### Step 6 — Configure MikuTTS

Edit `config.ini`:

```ini
[elevenlabs]
api_key = YOUR_ELEVENLABS_API_KEY_HERE
voice_id = YOUR_VOICE_ID_HERE

[game]
log_file = C:\Program Files (x86)\Steam\steamapps\common\Half-Life\qconsole.log
process_name = hl.exe
trigger = !miku
ptt_key = k

[audio]
cooldown_extra = 2.0
sample_rate = 48000
```

> **Linux users:** Change `log_file` to your actual path, e.g.:
> `~/.steam/steam/steamapps/common/Half-Life/qconsole.log`
> Change `process_name` to `hl_linux`

### Step 7 — Set your PTT key

In Half-Life, go to **Options → Keyboard** and check what key is bound to **Use Voice Communication**. Set the same key in `config.ini` under `ptt_key`.

### Step 8 — Run MikuTTS

**Windows (with system tray):**
```bash
python miku_tts.py
```

Or use the included `start.bat`:
```bat
@echo off
chcp 65001
cd /d %~dp0
python miku_tts.py
pause
```

**Linux (headless):**
```bash
python3 miku_tts.py
```

---

## 🎮 Usage

Once running, type in the Half-Life chat:
```
!miku Hello everyone, this is my anime voice!
```

The bot will:
1. Detect `!miku` in the chat log
2. Request audio from ElevenLabs
3. Play it through the virtual microphone (other players hear it)
4. Play it locally through your speakers (you hear it too)

### Changing the trigger keyword

Edit `config.ini`:
```ini
[game]
trigger = !voice
```

Now use `!voice Hello!` in chat instead.

---

## 🗂 Audio Cache

Generated audio files are cached in the `cache/` folder. If you type the same text again, the cached `.mp3` is reused — **no API call is made**, saving your ElevenLabs quota.

Cache is stored as:
- `cache/*.mp3` — audio files
- `cache/cache.csv` — text → file mapping

To clear the cache, simply delete the `cache/` folder.

---

## 🛡 Duplicate Protection

If the same text is triggered multiple times (e.g. due to server-side translation bots), MikuTTS will ignore duplicates for the duration of the audio + configurable extra cooldown.

Configure in `config.ini`:
```ini
[audio]
cooldown_extra = 2.0   # seconds added after audio finishes
```

---

## 📁 Project Structure

```
MikuTTS/
├── miku_tts.py       # Main script
├── config.ini        # Configuration file
├── requirements.txt  # Python dependencies
├── start.bat         # Windows launcher
├── cache/            # Cached audio files (auto-created)
│   └── cache.csv     # Cache index
├── README.md
└── LICENSE
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `Log file not found` | Add `-condebug` to Steam launch options |
| `Virtual audio device not found` | Install VB-Cable (Windows) or set up PulseAudio virtual sink (Linux) |
| `Half-Life is not running` | Start the game before running MikuTTS |
| PTT key not working | Make sure `ptt_key` in config matches your in-game voice key |
| No sound heard by others | Check that CABLE Output is set as default microphone in Windows Sound settings |
| API error 401 | Check your ElevenLabs API key in `config.ini` |
| Slow first playback | Normal — first request hits ElevenLabs API (~1-2s). Subsequent same texts use cache instantly |

---

## 🖥 Platform Notes

### Windows
- Uses `win32api` to send key events directly to the Half-Life window — game does not need to be in focus
- System tray icon with status display
- VB-Audio Virtual Cable for virtual microphone

### Linux
- Uses `xdotool` to simulate keypresses
- PulseAudio/PipeWire virtual sink for virtual microphone
- Runs in headless mode (no tray) — use `Ctrl+C` to stop
- Game window must be in focus for xdotool keypresses to work (limitation of X11)

---

## 📜 License

MIT License — see [LICENSE](LICENSE)

```
Copyright (c) 2025 MikuTTS Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss what you would like to change.

---

## ⚠️ Disclaimer

This project uses the ElevenLabs API. You are responsible for complying with ElevenLabs' [Terms of Service](https://elevenlabs.io/terms) and usage policies. API usage may incur costs depending on your subscription plan.
