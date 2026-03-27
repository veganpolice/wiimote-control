# Cycle 16 Learning

## What worked well
- Arrow key mode with debounce: only fire once per direction until stick returns to center
- Global _serial_source for rumble from anywhere — simple and effective
- rumble() convenience wrapper keeps handler code clean

## Reusable patterns
- Debounced directional input: track _arrow_last_dir, only fire on direction change, reset on center
- Global source reference for bidirectional serial communication
