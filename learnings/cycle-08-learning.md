# Cycle 8 Learning

## What worked well
- The B-mode pattern was easy to replicate for Home-mode — same state tracking, same combo/tap logic
- Double-tap detection is simple: just track last release timestamp
- CGEventSetIntegerValueField with clickState=2 correctly signals double-click to macOS

## What surprised me
- HOME as a modifier is more natural than expected — it's the "system" button on the Wiimote, so using it for system actions (page up/down, tab switching, Ctrl+C) feels right
- The B-priority-over-Home edge case needed explicit handling since HOME goes through B-mode first when B is held

## What I'd do differently
- If adding a third modifier, should extract a generic "modifier button" pattern rather than duplicating state tracking
- The double-tap timing (0.3s) might need tuning with real hardware — configurable via YAML

## Reusable patterns
- Modifier button pattern: `_X_held`, `_X_combo_used`, tap-on-release-if-no-combo
- Double-tap detection: timestamp of last release, compare with configurable window
- CGEventSetIntegerValueField for click count (double/triple click)

## Conductor-specific insights
- Most Conductor interactions are already covered by existing mappings:
  - A = Wispr (main input method)
  - 1 = Enter (approve tool calls)
  - 2 = Escape (dismiss)
  - B + D-pad = workspace switching
  - C + stick = scroll through output
- The new additions fill key gaps:
  - Home + 1 = Ctrl+C (cancel agent, interrupt process)
  - Home + UP/DOWN = Page Up/Down (fast scroll through long outputs)
  - Home + LEFT/RIGHT = Tab switching (multiple terminal sessions)
