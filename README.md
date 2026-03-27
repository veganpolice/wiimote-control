# Wiimote Mac Control

Control your Mac with a Nintendo Wiimote + Nunchuk. Use the analog stick as a mouse, buttons for keyboard shortcuts, and the nunchuk buttons for clicking and scrolling.

## How It Works

```
Wiimote → ESP32 (Bluetooth) → USB Serial → Mac daemon → macOS inputs
```

The ESP32 pairs with the Wiimote via Bluetooth Classic, reads button/nunchuk/accelerometer data, and sends JSON events over USB serial. The Mac daemon reads those events and simulates mouse movement, clicks, keypresses, and scrolling.

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Grant accessibility permissions

System Settings > Privacy & Security > Accessibility > add Terminal (or your Python binary)

### 3. Flash the ESP32

Open `esp32/wiimote_bridge/wiimote_bridge.ino` in Arduino IDE. Install ESP32Wiimote and ArduinoJson libraries. Select ESP32 Wrover Module board. Set upload speed to 115200. Flash to your ESP32 board (hold BOOT button during upload if needed).

### 4. Run the daemon

```bash
uv run python wiimote_daemon.py /dev/tty.usbserial-*
```

### 5. Pair the Wiimote

Press 1+2 on the Wiimote. The ESP32 will pair and start sending events.

## Button Mapping

### Default Mode

| Button | Action |
|--------|--------|
| Stick | Move cursor |
| A | Click (hold for drag, double-tap for double-click) |
| B | Wispr Flow (voice input toggle) |
| Z | Enter |
| C held | Modifier (see C-mode below) |
| C + stick | Scroll |
| D-pad | Arrow keys |
| Plus | Tab |
| Minus | Delete/Backspace |
| 1 | Escape |
| 2 | Cmd+Space (Siri/Spotlight) |
| Home | Mission Control |

### C-Mode (hold C + press button)

| Combo | Action |
|-------|--------|
| C + Left | Previous app (Cmd+Shift+Tab) |
| C + Right | Next app (Cmd+Tab) |
| C + Up | Switch window in same app (Cmd+`) |
| C + Down | Switch apps (Cmd+Tab) |
| C + Plus | Redo (Cmd+Shift+Z) |
| C + Minus | Undo (Cmd+Z) |
| C + stick | Scroll (inverted, natural direction) |

## Hardware

- [Freenove ESP32-WROVER](https://www.amazon.ca/dp/B0C9THDPXP) (~$18 CAD)
- Nintendo Wiimote + Nunchuk

## Architecture

```
┌──────────┐     Bluetooth    ┌──────────┐     USB Serial     ┌──────────────┐
│  Wiimote  │ ──────────────→ │  ESP32   │ ─────────────────→ │  Mac Daemon  │
│ + Nunchuk │  Classic (HID)  │ (bridge) │  JSON lines 115200 │ (Python)     │
└──────────┘                  └──────────┘                    └──────┬───────┘
                                                                     │ CGEvent
                                                                     │ (mouse,
                                                                     │  keys,
                                                                     │  scroll)
                                                                     ↓
                                                              ┌──────────────┐
                                                              │    macOS     │
                                                              └──────────────┘
```

## License

MIT
