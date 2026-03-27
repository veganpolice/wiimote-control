# Build Plan

## Cycle 24: Event Recording & Playback

### Goal
Record Wiimote input events to a file and replay them. Useful for:
- Testing the daemon without hardware
- Creating repeatable demos
- Sharing button sequences

### Approach
- `--record FILE` flag: write each incoming JSON event + timestamp to a file
- `--replay FILE` flag: read recorded events from file, feed to daemon with correct timing
- Recording format: original JSON + "ts" field (seconds since start)

### Implementation
1. In run_event_loop, if recording: write each event with timestamp
2. New replay_events() function: reads recording file, yields events with delays
3. CLI flags --record and --replay in main()

### Acceptance criteria
- --record captures events to file with timestamps
- --replay plays them back with correct timing
- All 134 tests pass + new tests

### Estimated scope
Small
