# Cycle 11 Work Review

## What was built
1. **Click-and-drag** — Z press = mouse-down, Z release = mouse-up, stick while Z held = drag events
   - Split `send_mouse_click` into `send_mouse_down` + `send_mouse_up`
   - Added `move_cursor_dragged` using kCGEventLeftMouseDragged
   - Extracted `_clamp_to_screen` helper
   - Drag interacts correctly with double-tap (drag suppresses double-tap detection)
   - B-mode Z still sends paste (Cmd+V) — bypasses drag logic

2. **Serial reconnection** — extracted `run_event_loop` from `main`, wrapped in reconnection loop
   - On OSError (serial disconnect): close, wait 2s, retry
   - Clean exit on EOF (stdin) or KeyboardInterrupt
   - Wispr state cleaned up on disconnect

3. **8 new tests**: Z press/release, drag mode, drag with stick, no drag without Z, drag suppresses double-tap, B+Z bypasses, run_event_loop, accel handling

## Correctness
- Z behavior change: from full click cycle to press/release split — more natural, enables drag
- Double-tap still works: fires on second release if no drag happened between taps
- Serial reconnection: simple retry loop, no complex state machine

## Verdict
Clean. The Z change is a behavioral improvement — press/release is more natural for a physical controller.
