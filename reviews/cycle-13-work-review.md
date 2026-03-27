# Cycle 13 Work Review

## What was built
1. **Z + D-pad = text selection** — Shift+Arrow keys when Z is held
   - Z + LEFT/RIGHT = select char by char
   - Z + UP/DOWN = select line by line
   - Routing takes priority over B-mode and default D-pad mappings when Z held

2. **B + Z + D-pad = word/line-level selection**
   - B + Z + LEFT/RIGHT = Shift+Opt+Arrow (select word by word)
   - B + Z + UP/DOWN = Shift+Cmd+Arrow (select to top/bottom of document)
   - B combo marked as used to suppress B-tap

3. **Double-tap C = warp cursor to screen center**
   - Same double-tap pattern as Z (uses DOUBLE_TAP_WINDOW)
   - Reuses existing CGDisplayBounds for center calculation
   - Does not interfere with C's scroll-mode toggle

4. **warp_cursor_to_center()** function — moves cursor to center of main display

## Correctness
- Z-held D-pad check placed BEFORE B-mode routing to ensure it takes priority
- Fixed ordering bug caught by tests (B-mode was intercepting D-pad before Z check)
- Double-tap C resets _c_last_release correctly
- 8 new tests, all passing

## Verdict
Clean. The text selection is the most useful feature for real work — select, copy, paste all from Wiimote.
