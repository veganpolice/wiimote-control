# Cycle 14 Learning

## What worked well
- Sticky scroll is a natural extension — reusing _scroll_mode pattern with persistent flag
- "sticky_scroll_toggle" as a new action type in execute_action — clean extension point
- Status file enrichment is low-cost, high-value for debugging

## What surprised me
- Adding new state vars (_sticky_scroll) broke TestWriteStatus because setUp didn't reset it
- Pattern is consistent: every new global state var must be added to ALL setUp methods

## Reusable patterns
- Toggle actions: `global_flag = not global_flag` in execute_action for simple on/off features
- Status file as debugging aid: add every piece of state you might want to see
