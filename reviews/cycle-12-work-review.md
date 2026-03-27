# Cycle 12 Work Review

## What was built
1. **Non-linear cursor acceleration** — quadratic curve `cx = x * abs(x)` for finer control near center
   - Half deflection (0.5) → 0.25 multiplier (4x more precise near center)
   - Full deflection (1.0) → unchanged (same top speed)
   - Configurable via `cursor.curve` config: "quadratic" (default) or "linear"

2. **Config hot-reload** — daemon checks config file mtime every 100 events
   - No external dependencies (no watchdog)
   - Prints "Config reloaded." when changes detected
   - Handles missing config file gracefully

## Correctness
- Quadratic curve preserves sign via `x * abs(x)` — works for both positive and negative stick values
- Config reload only triggers on actual mtime change, not on every check
- Both features have dedicated tests

## Verdict
Clean. Small, focused cycle. 88 tests passing.
