# Cycle 11 Learning

## What worked well
- Splitting mouse click into down/up enables drag naturally — no special "drag mode" needed
- kCGEventLeftMouseDragged is the correct event type for drag (not MouseMoved while button held)
- Extracting `run_event_loop` makes main() testable and enables reconnection cleanly

## What surprised me
- CGEvent drag events require a different event type (kCGEventLeftMouseDragged = 6) not just MouseMoved
- Double-tap detection needs careful interaction with drag — solved by checking `_drag_active` flag

## Reusable patterns
- Press/release split for physical buttons (vs full click cycle) — more flexible
- Reconnection wrapper: extract the event loop into a function, wrap in while True + try/except OSError
