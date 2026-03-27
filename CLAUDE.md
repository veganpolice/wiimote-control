# Wiimote Mac Control — Overnight Build Session

## Mode
build

## End Time
2026-03-26T03:00:00-07:00  (4 hours from ~11pm)

## Branch Budget
1 branch: veganpolice/wiimote-mac-control

## Task

Build out the full Wiimote Mac control daemon with rich features. The hardware (Freenove ESP32-WROVER) arrives tomorrow — the ESP32 firmware is already written (`esp32/wiimote_bridge.ino`). Focus on the **Mac-side daemon** (`wiimote_daemon.py`).

The daemon reads JSON lines from serial (ESP32) or stdin. Each line is one of:
```json
{"type":"button","id":"A","pressed":true}
{"type":"button","id":"A","pressed":false}
{"type":"stick","x":0.5,"y":-0.3}
{"type":"accel","x":0.1,"y":0.9,"z":0.2}
```

### What's Already Built
- `wiimote_daemon.py` — MVP daemon: reads JSON events, maps button A → Ctrl+Opt (Wispr Flow voice input) using kCGEventFlagsChanged events (Method C — confirmed working)
- `test_daemon.py` — 13 unit tests, all passing
- `test_keypress.py` — standalone keypress test (Methods A/B/C)
- `esp32/wiimote_bridge.ino` — ESP32 firmware (sends all buttons, nunchuk stick, nunchuk buttons)
- Python env via `uv`, deps: `pyobjc-framework-Quartz`, `pyobjc-framework-ApplicationServices`

### Key Technical Details
- **Keypress method:** Use `kCGEventFlagsChanged` events with `CGEventSetType` — this is what macOS generates when you physically press modifier keys. Method C in test_keypress.py. This is confirmed working with Wispr Flow.
- **Wispr Flow shortcut:** Ctrl+Opt (Control=0x3B, Option=0x3A)
- **Accessibility permission required** for CGEventPost
- **Input Monitoring permission** may be needed for reading HID
- **Virtual keycodes reference:** Control=0x3B, Option=0x3A, Command=0x37, Shift=0x38, Tab=0x30, Space=0x31, Escape=0x35, Return=0x24, Delete=0x33, Arrow keys: Up=0x7E, Down=0x7D, Left=0x7B, Right=0x7C, F18=0x4F

### Features to Build (in priority order)

**Cycle 1: App Switching & D-pad Navigation**
- D-pad Left/Right → Cmd+Tab / Cmd+Shift+Tab (switch apps)
- D-pad Up/Down → Ctrl+Up/Down (Mission Control / App Expose)
- Hold B + D-pad → move between Conductor workspaces (Cmd+1/2/3 etc.)

**Cycle 2: Nunchuk Cursor Control**
- Nunchuk analog stick → smooth cursor movement via CGEventCreateMouseEvent
- Configurable dead zone, acceleration curve (slow near center, fast at edges)
- Nunchuk Z button → left click
- Nunchuk C button → right click
- Nunchuk stick click (if detectable) → middle click / scroll mode

**Cycle 3: Smart Navigation & Field Selection**
- Tab key simulation for moving between form fields/UI elements
- Plus/Minus buttons → Tab / Shift+Tab (cycle through fields)
- Button 1 → Enter/Return
- Button 2 → Escape
- Home button → spotlight/alfred (Cmd+Space)

**Cycle 4: Scroll & Zoom**
- Hold Nunchuk C + stick up/down → scroll
- Hold Nunchuk C + stick left/right → horizontal scroll
- Pinch-to-zoom simulation via keyboard shortcuts (Cmd+Plus/Minus)

**Cycle 5: Mode System**
- Button combos define "modes" (e.g., hold B = Navigation mode, hold Home = System mode)
- Visual/audio feedback per mode (play different macOS system sounds)
- Mode indicator: log current mode to a status file the user can display
- Mode-specific button mappings (different maps per held modifier button)

**Cycle 6: Gesture Recognition (Accelerometer)**
- Wiimote flick left/right → switch apps
- Wiimote flick up → Mission Control
- Wiimote point down → momentary mute
- Basic gesture detection from accelerometer data (threshold + timing based)

**Cycle 7: YAML Config & Polish**
- `~/.config/wiimote-control/config.yaml` for all button mappings
- Hot-reload config on file change (watchdog or polling)
- Rumble feedback integration (write rumble commands back to serial)
- macOS notification on connect/disconnect

**Cycle 8: Conductor Integration**
- Study how Conductor windows/workspaces are organized
- Map button combos to Conductor-specific actions:
  - Switch between workspaces
  - Focus chat input
  - Send messages / approve tool calls
  - Navigate between agent outputs
- Use AppleScript or accessibility APIs to discover Conductor window state

### Testing Strategy
- Use `uv run python -m unittest test_daemon -v` to run tests
- Mock all Quartz/CGEvent calls in tests (see existing test_daemon.py pattern)
- Test each new feature: button mapping, cursor movement, scroll, modes
- For cursor movement: mock CGEventCreateMouseEvent
- For each cycle, write tests BEFORE implementing

### Important
- DO NOT modify test_keypress.py — it's a manual testing tool
- DO NOT change the keypress method — Method C (FlagsChanged) is confirmed working
- All new features should add to BUTTON_MAP or create new handler functions
- Keep wiimote_daemon.py as a single file until it exceeds ~500 lines, then split
- Run `uv run python -m unittest test_daemon -v` after EVERY change
