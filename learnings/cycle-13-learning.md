# Cycle 13 Learning

## What worked well
- Z as "action modifier" for D-pad is intuitive — Z = mouse button = "I want to interact with what's under cursor"
- Double-tap pattern reuse from Z to C was trivial
- Test-first caught the B-mode priority bug immediately

## What surprised me
- Modifier routing order matters a LOT. Z-held D-pad must be checked before B-mode routing because B + Z + D-pad is a valid combo that Z-held should handle
- The fix was simple: move Z-held check before B-mode routing in handle_button

## Reusable patterns
- "Hold physical button to change D-pad meaning" — extremely flexible modifier system
- Three-modifier combos (B + Z + D-pad) work naturally by layering checks
