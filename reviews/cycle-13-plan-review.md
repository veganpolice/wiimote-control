# Cycle 13 Plan Review

## Does it match the task?
Yes — text selection and cursor warp are core usability features for controlling a Mac hands-free.

## Simplest approach?
- Z + D-pad is elegant: Z is already "mouse button" so D-pad while Z held = selection arrows
- Double-tap C reuses existing double-tap Z pattern
- B + Z + D-pad for word selection layers nicely on existing mode system

## Over-engineering?
No. Three focused features, all using existing patterns.

## Risks
- D-pad routing when Z is held needs careful ordering in handle_button — Z-held check must come before default BUTTON_MAP lookup for D-pad
- Double-tap C needs to not interfere with C's scroll-mode toggle
- B + Z + D-pad has three modifiers active — need to check all combinations route correctly

## Verdict
Good plan. Implement Feature 1 first (highest value), then 3 (simplest), then 2.
