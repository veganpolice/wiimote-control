# Cycle 8 Plan Review

## Does it match the task?
Yes — user wants better Conductor control. Conductor is terminal-based, so keyboard shortcuts are the interface.

## Simplification
- Drop click-and-drag for now — complex state, rare need
- Home-mode is good but keep it minimal: just app switching
- Double-tap Z: useful but adds timing state — include, it's simple enough

## What's already covered
Looking at existing mappings, Conductor use is well-served:
- A = Wispr (voice input) — the main interaction
- 1 = Enter (approve tool calls)
- 2 = Escape (dismiss)
- B + D-pad Left/Right = Cmd+1/2 (workspaces)
- C + stick = scroll
- Tab/Shift+Tab for field navigation

## Gaps to fill
1. **Ctrl+C** (cancel/interrupt) — critical for Conductor, no mapping exists
2. **Page Up/Down** — faster scrolling through long outputs
3. **Home-mode** for quick app switching without Spotlight
4. **Double-tap Z** for double-click (text selection)
5. **Cmd+W** (close tab) — useful

## Revised scope
- Add Home-mode (hold Home = modifier, like B)
- Add Ctrl+C mapping
- Add Page Up/Down
- Add double-tap Z detection
- Skip click-and-drag

## Verdict
Plan is good with simplification. Proceed.
