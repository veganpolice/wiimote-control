# Progress

## Completed Cycles
- [x] Cycles 1-3: App switching, cursor control, field navigation — 34 tests passing
  - D-pad: app switch (Cmd+Tab), Mission Control, App Expose
  - Nunchuk: cursor movement with acceleration, left/right click
  - Scroll: hold C + stick
  - Fields: Plus/Minus = Tab/Shift+Tab, 1=Enter, 2=Escape, Home=Spotlight
- [x] Cycle 5: Mode system — B button as modifier, B-tap = Copy, 9 new tests
  - B + D-pad → workspaces, B + 1/2 → undo/redo, B + A → select all
  - B + Nunchuk Z/C → paste/copy, B + Plus/Minus → zoom
  - B + Home → lock screen
- [x] Cycle 7: YAML config & rumble feedback — 7 new tests
  - Config at ~/.config/wiimote-control/config.yaml
  - Rumble feedback on Wispr activation
- [x] Cycle 8: Conductor integration & Home-mode — 14 new tests
  - Home button as second modifier
  - Home + UP/DOWN = Page Up/Down, Home + LEFT/RIGHT = Prev/Next tab
  - Home + 1 = Ctrl+C, Home + 2 = Cmd+W, Home-tap = Spotlight
  - Double-tap Z = double-click
- [x] Cycle 9: Gesture recognition — 8 new tests
  - Flick left/right → switch apps, Shake → undo
  - Cooldown prevents rapid-fire, all thresholds configurable
- [x] Cycle 10: Status display, ESP32 accel, README — 5 new tests
  - Status file at /tmp/wiimote-status.json
  - ESP32 firmware sends accelerometer at 10Hz
- [x] Cycle 11: Click-and-drag & serial reconnection — 8 new tests
  - Z press = mouse-down, Z release = mouse-up, Z + stick = drag
  - Serial reconnection on OSError, extracted run_event_loop
- [x] Cycle 12: Non-linear cursor & config hot-reload — 2 new tests
  - Quadratic cursor curve (x * abs(x)), configurable
  - Config mtime polling every 100 events, auto-reload
- [x] Cycle 13: Text selection & pointer warp — 8 new tests
  - Z + D-pad = Shift+Arrow (select char/line)
  - B + Z + D-pad = Shift+Opt/Cmd+Arrow (select word/to-top)
  - Double-tap C = warp cursor to screen center
- [x] Cycle 14: Sticky scroll & enhanced status — 5 new tests
  - Home + C = toggle sticky scroll mode
  - Status file shows z_held, drag, sticky_scroll
- [x] Cycle 15: Action sequences (macros) — 3 new tests
  - "sequence" action type executes multiple actions
  - B + A = Select All + Copy (sequence)
  - YAML config supports sequences via "steps" array
- [x] Cycle 16: Arrow key mode & haptic patterns — 5 new tests
  - Home + stick = arrow keys (for terminal/list navigation)
  - Debounced: only fires once per direction until center
  - Rumble feedback on click (50ms), mode change (80ms), gesture (300ms)
  - Global _serial_source for rumble from any handler
- [x] Cycle 17: Precision cursor — 2 new tests
  - Hold B + stick = 1/4 speed (fine positioning)
  - Also applies to drag mode
- [x] Cycle 18: macOS notifications & LaunchAgent — 4 new tests
  - Notification on connect/disconnect via osascript
  - --install / --uninstall flags for LaunchAgent plist
- [x] Cycle 19: Dead zone, Y-invert, type_char action — 3 new tests
  - Configurable dead zone (cursor.dead_zone)
  - Y-axis inversion (cursor.invert_y)
  - "type_char" action type for single character input
- [x] Cycle 20: Screen region cursor snap — 4 new tests + README update
  - Home + Z + stick = warp cursor to screen region (9 snap points)
  - warp_cursor_to_region() with margin

- [x] Cycle 21: Volume control gestures — 5 new tests
  - Flick up/down → volume up/down via osascript
  - X-axis flick priority over Y-axis
- [x] Cycle 22: Frontmost app detection — 3 new tests
  - Cached osascript call (1s interval) to detect active app
  - Status file includes "app" field
- [x] Cycle 23: Help overlay — 4 new tests
  - /tmp/wiimote-help.txt shows current mode's button mapping
  - Updates on mode change (B hold/release, Home hold/release)
- [x] Cycle 24: Event recording & playback — 2 new tests
  - --record FILE: write timestamped JSON events to file
  - --replay FILE: replay events with correct timing
  - Useful for testing without hardware, creating demos

## Current Cycle
Complete — session ended

## Pass
Build mode — compound engineering loop

## Stats
Cycles: 24 | Tests passing: 136 | ESP32 hardware connected
