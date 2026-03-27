# Cycle 11 Plan Review

## Simplification
- Serial reconnection: simple retry loop, no exponential backoff needed for USB serial
- Click-and-drag: simpler approach — just track Z held state and stick movement while held
  - Don't need a timer threshold — if Z is held and stick moves, it's a drag
  - But we need to distinguish from "click then move cursor" — so use a small delay or just
    check if stick moved while Z was down

Actually, simplest approach:
- Z press → send mouse-down immediately
- Stick while Z held → send mouse-dragged events
- Z release → send mouse-up
- Double-tap detection still works because it fires on the second release

Wait, that changes the current behavior where Z press = left click (press+release).
Current: Z press → full click cycle (down+up).
New: Z press → just down. Z release → just up. Stick while held → drag.

This is actually cleaner. A "click" is just a quick press+release. A "drag" is press, move, release. The mouse down/up are separated.

## Impact on existing behavior
- Z single click: still works (press down, release up = click)
- Z double-tap: need to adjust — currently fires on second release
- Right click (C): same change needed? No, C is also scroll mode toggle, keep it as is.

## Verdict
Change Z from "instant full click" to "press=down, release=up". This enables drag naturally.
