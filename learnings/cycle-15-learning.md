# Cycle 15 Learning

## What worked well
- "sequence" action type is a clean generic pattern for macros
- B + A = Select All + Copy is the perfect first macro — most common workflow

## Reusable patterns
- Action sequences: `("sequence", [action1, action2, ...])` — execute_action recurses naturally
- parse_action recursion for YAML config of sequences works cleanly with "steps" array
