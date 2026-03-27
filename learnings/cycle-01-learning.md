# Cycle 1-3 Learning

## What worked well
- Building `send_key_combo` as the first abstraction — it made every subsequent button mapping a one-liner in BUTTON_MAP
- Tuple-based action definitions: `("key_combo", ["cmd"], VK_TAB)` — data-driven, easy to extend, no new functions needed per button
- Testing with mocked Quartz — fast, no permissions needed, catches logic bugs

## What surprised me
- CGEventGetLocation requires creating a dummy event first (`CGEventCreate(None)`) to get current cursor position
- CGDisplayBounds returns a rect with origin — can't just clamp to width/height, need to account for origin offset (multi-monitor)
- Scroll needs `CGEventCreateScrollWheelEvent` not `CGEventCreateMouseEvent` with scroll type

## What I'd do differently
- Nothing yet — the approach is clean for this scale

## Reusable patterns
- `MODIFIER_FLAGS` dict for mapping modifier names to constants
- Tuple-based action map pattern: `BUTTON_MAP = {"id": ("action_type", ...args)}`
- Cursor acceleration: base speed → multiply by CURSOR_ACCEL each tick → cap at max
