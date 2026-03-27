# Cycle 12 Learning

## What worked well
- `x * abs(x)` is simpler and cleaner than `sign(x) * x**2` for quadratic curve
- Mtime polling is dead simple config hot-reload — no watchdog needed
- Checking every N events (not every event) avoids stat() overhead

## Reusable patterns
- Quadratic response curves for analog input: `output = input * abs(input)` — preserves sign, easy to understand
- File mtime polling: check every N iterations, compare with cached value
