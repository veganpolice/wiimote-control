# Cycle 9 Learning

## What worked well
- Pure function `detect_gesture()` made testing trivial — no mocks needed, just pass buffer arrays
- Spike detection via "current value vs buffer average" is simple and effective
- Reversal counting for shake detection is elegant — just check sign changes of deltas

## What surprised me
- The threshold needs to be quite high (1.5g) to avoid false positives — small movements at rest can easily hit 0.5g
- Buffer clear after gesture is critical — without it, the spike stays in the buffer and re-triggers

## What I'd do differently
- Might want separate thresholds per axis (X for flick, all axes for shake)
- Consider exponential moving average instead of simple average for smoother detection
- Real hardware testing will probably require threshold adjustments

## Reusable patterns
- Rolling buffer + spike detection for any time-series event detection
- Cooldown timer pattern: `if now - last_time < cooldown: return`
- Reversal counting for oscillation/shake detection
