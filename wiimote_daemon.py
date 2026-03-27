#!/usr/bin/env python3
"""Wiimote Mac Control daemon — reads JSON events from stdin or serial, sends keypresses."""

import json
import os
import subprocess
import sys
import time

import yaml

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventCreateMouseEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSetIntegerValueField,
    CGEventSetType,
    CGMainDisplayID,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventFlagsChanged,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGEventRightMouseDown,
    kCGEventRightMouseUp,
    kCGEventLeftMouseDragged,
    kCGEventScrollWheel,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGMouseButtonRight,
    kCGScrollEventUnitPixel,
)

from Quartz import (
    CGDisplayBounds,
    CGEventCreate,
    CGEventCreateScrollWheelEvent,
    CGEventGetLocation,
)

from ApplicationServices import AXIsProcessTrusted

# ---------- Virtual keycodes ----------
VK_CONTROL = 0x3B
VK_OPTION = 0x3A
VK_COMMAND = 0x37
VK_SHIFT = 0x38
VK_TAB = 0x30
VK_SPACE = 0x31
VK_ESCAPE = 0x35
VK_RETURN = 0x24
VK_DELETE = 0x33
VK_UP = 0x7E
VK_DOWN = 0x7D
VK_LEFT = 0x7B
VK_RIGHT = 0x7C
VK_F18 = 0x4F
VK_1 = 0x12  # Number row 1
VK_2 = 0x13  # Number row 2
VK_3 = 0x14  # Number row 3
VK_EQUAL = 0x18  # =/+ key
VK_MINUS_KEY = 0x1B  # -/_ key
VK_Z = 0x06
VK_C = 0x08
VK_V = 0x09
VK_A = 0x00
VK_Q = 0x0C
VK_W = 0x0D
VK_PAGE_UP = 0x74
VK_PAGE_DOWN = 0x79
VK_BRACKET_LEFT = 0x21   # [ key
VK_BRACKET_RIGHT = 0x1E  # ] key
VK_F = 0x03
VK_G = 0x05
VK_X = 0x07
VK_T = 0x11
VK_BACKTICK = 0x32  # ` key

# Modifier name → flag mapping
MODIFIER_FLAGS = {
    "cmd": kCGEventFlagMaskCommand,
    "ctrl": kCGEventFlagMaskControl,
    "opt": kCGEventFlagMaskAlternate,
    "shift": kCGEventFlagMaskShift,
}

# ---------- Button → action mapping ----------
# Actions are tuples: ("key_combo", [modifiers], keycode) or ("wispr_toggle",)
# or ("action_name",) for special actions
BUTTON_MAP = {
    # A and B handled specially in handle_button
    "LEFT": ("key_combo", [], VK_LEFT),                   # Arrow left
    "RIGHT": ("key_combo", [], VK_RIGHT),                 # Arrow right
    "UP": ("key_combo", [], VK_UP),                       # Arrow up
    "DOWN": ("key_combo", [], VK_DOWN),                   # Arrow down
    "PLUS": ("key_combo", [], VK_RETURN),                  # Enter/Return
    "MINUS": ("key_combo", [], VK_TAB),                   # Tab
    "HOME": ("key_combo", ["ctrl"], VK_UP),               # Mission Control
    "1": ("key_combo", [], VK_ESCAPE),                    # Escape
    "2": ("key_combo", ["cmd"], VK_SPACE),                # Cmd+Space (Siri/Spotlight)
    # NUNCHUK_C handled specially (click/drag)
    # NUNCHUK_Z handled specially (modifier)
}

# C-held mode: hold C + press another button for alternate actions
MODE_C_MAP = {
    "LEFT": ("key_combo", ["cmd", "shift"], VK_TAB),      # Previous app
    "RIGHT": ("key_combo", ["cmd"], VK_TAB),              # Next app
    "UP": ("key_combo", ["cmd"], VK_UP),                   # Scroll to top (Cmd+Up)
    "DOWN": ("key_combo", ["cmd"], VK_DOWN),              # Scroll to bottom (Cmd+Down)
    "PLUS": ("key_combo", ["cmd", "shift"], VK_Z),        # Redo
    "MINUS": ("key_combo", ["cmd"], VK_Z),                # Undo
    "1": ("key_combo", ["ctrl"], VK_C),                   # Ctrl+C (interrupt)
    "2": ("key_combo", ["cmd"], VK_W),                    # Close tab (Cmd+W)
    "A": ("key_combo", ["cmd"], VK_T),                    # New tab (Cmd+T)
    "HOME": ("key_combo", ["cmd"], VK_BACKTICK),          # Switch window (Cmd+`)
}

# B-held mode: hold B + press another button for alternate actions
MODE_B_MAP = {
    "LEFT": ("key_combo", ["cmd"], VK_1),                 # Workspace 1
    "RIGHT": ("key_combo", ["cmd"], VK_2),                # Workspace 2
    "UP": ("key_combo", ["cmd"], VK_3),                   # Workspace 3
    "DOWN": ("key_combo", ["ctrl"], VK_DOWN),             # App windows
    "PLUS": ("key_combo", ["cmd"], VK_EQUAL),             # Zoom in (Cmd+=)
    "MINUS": ("key_combo", ["cmd"], VK_MINUS_KEY),        # Zoom out (Cmd+-)
    "1": ("key_combo", ["cmd"], VK_Z),                    # Undo
    "2": ("key_combo", ["cmd", "shift"], VK_Z),           # Redo
    "HOME": ("key_combo", ["ctrl", "cmd"], VK_Q),         # Lock screen
    "A": ("sequence", [("key_combo", ["cmd"], VK_A), ("key_combo", ["cmd"], VK_C)]),  # Select All + Copy
    "NUNCHUK_Z": ("key_combo", ["cmd"], VK_V),            # Paste
    "NUNCHUK_C": ("key_combo", ["cmd"], VK_C),            # Copy
}

# B-tap action (press and release B without pressing anything else)
B_TAP_ACTION = ("key_combo", ["cmd"], VK_C)               # Copy

# Home-held mode: hold Home + press another button for system/app actions
MODE_HOME_MAP = {
    "LEFT": ("key_combo", ["cmd", "shift"], VK_BRACKET_LEFT),   # Prev tab (Cmd+Shift+[)
    "RIGHT": ("key_combo", ["cmd", "shift"], VK_BRACKET_RIGHT), # Next tab (Cmd+Shift+])
    "UP": ("key_combo", [], VK_PAGE_UP),                        # Page Up
    "DOWN": ("key_combo", [], VK_PAGE_DOWN),                    # Page Down
    "A": ("key_combo", ["cmd"], VK_TAB),                        # Quick app switch
    "1": ("key_combo", ["ctrl"], VK_C),                         # Ctrl+C (cancel/interrupt)
    "2": ("key_combo", ["cmd"], VK_W),                          # Close tab/window
    "PLUS": ("key_combo", ["cmd", "shift"], VK_EQUAL),          # Zoom in (Cmd+Shift+=)
    "MINUS": ("key_combo", ["cmd"], VK_MINUS_KEY),              # Zoom out
    "NUNCHUK_Z": ("key_combo", ["cmd"], VK_Z),                  # Undo (quick access)
    "NUNCHUK_C": ("sticky_scroll_toggle",),                     # Toggle sticky scroll
}

# Home-tap action (press and release Home without combo) — Spotlight
HOME_TAP_ACTION = ("key_combo", ["cmd"], VK_SPACE)

# ---------- State ----------
_wispr_active = False

# Cursor movement state
_cursor_speed = 0.0  # Current velocity (accelerates while stick is held)
CURSOR_BASE_SPEED = 8.0  # (unused — kept for config compat)
CURSOR_MAX_SPEED = 160.0  # Pixels per tick at full stick deflection
CURSOR_ACCEL = 1.5  # Acceleration multiplier applied each tick
CURSOR_CURVE = "quadratic"  # "linear" or "quadratic" — quadratic gives finer control near center
CURSOR_DEAD_ZONE = 0.1  # Stick values within this radius are treated as center
CURSOR_INVERT_Y = False  # Invert Y axis (stick up = cursor down)
CURSOR_SMOOTHING = 0.9  # Exponential smoothing factor (0=very smooth/laggy, 1=no smoothing)
_smooth_x = 0.0  # Smoothed stick X
_smooth_y = 0.0  # Smoothed stick Y

# Scroll state
_scroll_mode = False  # True when Nunchuk C is held (stick becomes scroll)
_sticky_scroll = False  # True when sticky scroll is toggled on (Home + C)

# Precision mode (C held)
_c_held = False  # True while Nunchuk C is physically held

# A+B combo for Wispr Flow
_a_held = False
_a_press_time = 0.0  # When A was pressed (for deferred click)
_a_click_sent = False  # True once the deferred click has been sent
_b_held_raw = False
_ab_wispr_triggered = False
AB_COMBO_WINDOW = 0.15  # Seconds to wait for B after A before committing to click
SCROLL_SPEED = 60.0  # Scroll speed multiplier

# Mode state
_b_held = False  # True while B button is held
_b_combo_used = False  # True if another button was pressed while B was held
_home_held = False  # True while Home button is held
_home_combo_used = False  # True if another button was pressed while Home was held

# Double-tap detection for Nunchuk Z
_z_last_release = 0.0  # Timestamp of last Z release
DOUBLE_TAP_WINDOW = 0.3  # Seconds within which two taps = double-tap

# Drag state (Z held + stick movement)
_z_held = False  # True while Nunchuk Z is physically held
_z_combo_used = False  # True if Z was used as modifier (stick moved while held)
_drag_active = False  # True once stick moves while Z is held

# Z-held mode: Z acts as Cmd modifier + precision cursor
# Also keeps text selection on D-pad (Shift+Arrow)
MODE_Z_MAP = {
    "A": ("key_combo", ["cmd"], VK_C),                    # Copy (Cmd+C)
    "B": ("key_combo", ["cmd"], VK_X),                    # Cut (Cmd+X)
    "PLUS": ("key_combo", ["cmd"], VK_V),                 # Paste (Cmd+V)
    "MINUS": ("key_combo", ["cmd"], VK_Z),                # Undo (Cmd+Z)
    "LEFT": ("key_combo", ["shift"], VK_LEFT),            # Select char left
    "RIGHT": ("key_combo", ["shift"], VK_RIGHT),          # Select char right
    "UP": ("key_combo", ["shift"], VK_UP),                # Select line up
    "DOWN": ("key_combo", ["shift"], VK_DOWN),            # Select line down
}

# Double-tap C state
_c_last_release = 0.0

# Arrow key mode state (Home + stick)
ARROW_STICK_THRESHOLD = 0.5  # Stick must exceed this to fire an arrow key
_arrow_last_dir = None  # Last arrow direction sent ("up"/"down"/"left"/"right" or None)

# Haptic feedback
_serial_source = None  # Set by run_event_loop for rumble access from handlers
RUMBLE_CLICK = 50      # Short pulse for click
RUMBLE_WISPR = 150     # Medium pulse for Wispr activate
RUMBLE_MODE = 80       # Pulse for mode change
RUMBLE_GESTURE = 300   # Long pulse for gesture

# Precision cursor multiplier (B held = slow mode)
PRECISION_MULTIPLIER = 6.0  # Divide speed by this when Z is held for precision

# Gesture detection state
_accel_buffer = []  # Rolling buffer of (x, y, z) readings
ACCEL_BUFFER_SIZE = 10  # Number of readings to keep
GESTURE_THRESHOLD = 1.5  # Minimum delta from avg to trigger a flick
GESTURE_COOLDOWN_SEC = 0.5  # Minimum time between gestures
_gesture_last_time = 0.0  # Timestamp of last gesture fired
SHAKE_REVERSAL_COUNT = 4  # Number of axis reversals to detect a shake
SHAKE_WINDOW = 0.3  # Seconds to look back for shake detection

# Gesture → action mapping
GESTURE_MAP = {
    "flick_left": ("key_combo", ["cmd", "shift"], VK_TAB),   # Prev app
    "flick_right": ("key_combo", ["cmd"], VK_TAB),            # Next app
    "flick_up": ("volume_up",),                                # Volume up
    "flick_down": ("volume_down",),                            # Volume down
    "shake": ("key_combo", ["cmd"], VK_Z),                    # Undo
}

# ---------- Config ----------
CONFIG_PATH = os.path.expanduser("~/.config/wiimote-control/config.yaml")

# All known keycodes by name (for YAML config)
KEYCODE_NAMES = {
    "tab": VK_TAB, "space": VK_SPACE, "escape": VK_ESCAPE, "return": VK_RETURN,
    "delete": VK_DELETE, "up": VK_UP, "down": VK_DOWN, "left": VK_LEFT,
    "right": VK_RIGHT, "f18": VK_F18, "1": VK_1, "2": VK_2, "3": VK_3,
    "equal": VK_EQUAL, "minus_key": VK_MINUS_KEY, "z": VK_Z, "c": VK_C,
    "v": VK_V, "a": VK_A, "q": VK_Q, "w": VK_W, "x": VK_X, "f": VK_F, "g": VK_G,
    "page_up": VK_PAGE_UP, "page_down": VK_PAGE_DOWN,
    "bracket_left": VK_BRACKET_LEFT, "bracket_right": VK_BRACKET_RIGHT,
}

DEFAULT_CONFIG = {
    "cursor": {
        "base_speed": 3.0,
        "max_speed": 25.0,
        "acceleration": 1.5,
        "curve": "quadratic",
        "dead_zone": 0.1,
        "invert_y": False,
    },
    "scroll": {
        "speed": 5.0,
    },
    "rumble": {
        "on_wispr": True,
        "duration_ms": 200,
    },
    "buttons": {
        "A": {"action": "wispr_toggle"},
        "LEFT": {"action": "key_combo", "modifiers": ["cmd", "shift"], "key": "tab"},
        "RIGHT": {"action": "key_combo", "modifiers": ["cmd"], "key": "tab"},
        "UP": {"action": "key_combo", "modifiers": ["ctrl"], "key": "up"},
        "DOWN": {"action": "key_combo", "modifiers": ["ctrl"], "key": "down"},
        "PLUS": {"action": "key_combo", "modifiers": [], "key": "tab"},
        "MINUS": {"action": "key_combo", "modifiers": ["shift"], "key": "tab"},
        "1": {"action": "key_combo", "modifiers": [], "key": "return"},
        "2": {"action": "key_combo", "modifiers": [], "key": "escape"},
        "HOME": {"action": "key_combo", "modifiers": ["cmd"], "key": "space"},
        "NUNCHUK_C": {"action": "mouse_click", "button": "right"},
        # NUNCHUK_Z handled specially: press=down, release=up, drag+double-tap
    },
    "b_mode": {
        "tap": {"action": "key_combo", "modifiers": ["cmd"], "key": "c"},
        "LEFT": {"action": "key_combo", "modifiers": ["cmd"], "key": "1"},
        "RIGHT": {"action": "key_combo", "modifiers": ["cmd"], "key": "2"},
        "UP": {"action": "key_combo", "modifiers": ["cmd"], "key": "3"},
        "DOWN": {"action": "key_combo", "modifiers": ["ctrl"], "key": "down"},
        "PLUS": {"action": "key_combo", "modifiers": ["cmd"], "key": "equal"},
        "MINUS": {"action": "key_combo", "modifiers": ["cmd"], "key": "minus_key"},
        "1": {"action": "key_combo", "modifiers": ["cmd"], "key": "z"},
        "2": {"action": "key_combo", "modifiers": ["cmd", "shift"], "key": "z"},
        "HOME": {"action": "key_combo", "modifiers": ["ctrl", "cmd"], "key": "q"},
        "A": {"action": "sequence", "steps": [
            {"action": "key_combo", "modifiers": ["cmd"], "key": "a"},
            {"action": "key_combo", "modifiers": ["cmd"], "key": "c"},
        ]},
        "NUNCHUK_Z": {"action": "key_combo", "modifiers": ["cmd"], "key": "v"},
        "NUNCHUK_C": {"action": "key_combo", "modifiers": ["cmd"], "key": "c"},
    },
    "home_mode": {
        "tap": {"action": "key_combo", "modifiers": ["cmd"], "key": "space"},
        "LEFT": {"action": "key_combo", "modifiers": ["cmd", "shift"], "key": "bracket_left"},
        "RIGHT": {"action": "key_combo", "modifiers": ["cmd", "shift"], "key": "bracket_right"},
        "UP": {"action": "key_combo", "modifiers": [], "key": "page_up"},
        "DOWN": {"action": "key_combo", "modifiers": [], "key": "page_down"},
        "A": {"action": "key_combo", "modifiers": ["cmd"], "key": "tab"},
        "1": {"action": "key_combo", "modifiers": ["ctrl"], "key": "c"},
        "2": {"action": "key_combo", "modifiers": ["cmd"], "key": "w"},
        "PLUS": {"action": "key_combo", "modifiers": ["cmd", "shift"], "key": "equal"},
        "MINUS": {"action": "key_combo", "modifiers": ["cmd"], "key": "minus_key"},
        "NUNCHUK_Z": {"action": "key_combo", "modifiers": ["cmd"], "key": "z"},
    },
    "double_tap": {
        "window_seconds": 0.3,
    },
    "gestures": {
        "enabled": True,
        "threshold": 1.5,
        "cooldown_seconds": 0.5,
        "shake_reversals": 4,
        "flick_left": {"action": "key_combo", "modifiers": ["cmd", "shift"], "key": "tab"},
        "flick_right": {"action": "key_combo", "modifiers": ["cmd"], "key": "tab"},
        "flick_up": {"action": "volume_up"},
        "flick_down": {"action": "volume_down"},
        "shake": {"action": "key_combo", "modifiers": ["cmd"], "key": "z"},
    },
}


def parse_action(cfg):
    """Convert a config dict action entry to an action tuple."""
    action = cfg.get("action")
    if action == "wispr_toggle":
        return ("wispr_toggle",)
    elif action == "key_combo":
        mods = cfg.get("modifiers", [])
        key_name = cfg.get("key", "")
        keycode = KEYCODE_NAMES.get(key_name)
        if keycode is None:
            print(f"WARN: unknown key name '{key_name}', skipping", file=sys.stderr)
            return None
        return ("key_combo", mods, keycode)
    elif action == "mouse_click":
        return ("mouse_click", cfg.get("button", "left"))
    elif action == "type_char":
        return ("type_char", cfg.get("char", ""))
    elif action == "volume_up":
        return ("volume_up",)
    elif action == "volume_down":
        return ("volume_down",)
    elif action == "sticky_scroll_toggle":
        return ("sticky_scroll_toggle",)
    elif action == "sequence":
        steps = cfg.get("steps", [])
        parsed_steps = []
        for step in steps:
            parsed = parse_action(step)
            if parsed:
                parsed_steps.append(parsed)
        if parsed_steps:
            return ("sequence", parsed_steps)
        return None
    return None


def load_config():
    """Load config from YAML file, falling back to defaults.
    Currently disabled — code defaults are the source of truth."""
    return {}
    global BUTTON_MAP, MODE_B_MAP, B_TAP_ACTION
    global MODE_HOME_MAP, HOME_TAP_ACTION, DOUBLE_TAP_WINDOW
    global CURSOR_BASE_SPEED, CURSOR_MAX_SPEED, CURSOR_ACCEL, CURSOR_CURVE
    global GESTURE_THRESHOLD, GESTURE_COOLDOWN_SEC, SHAKE_REVERSAL_COUNT, GESTURE_MAP
    global CURSOR_DEAD_ZONE, CURSOR_INVERT_Y, SCROLL_SPEED

    cfg = DEFAULT_CONFIG.copy()

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                user_cfg = yaml.safe_load(f)
            if user_cfg:
                # Merge user config over defaults (shallow per section)
                for section in user_cfg:
                    if section in cfg and isinstance(cfg[section], dict):
                        cfg[section].update(user_cfg[section])
                    else:
                        cfg[section] = user_cfg[section]
            print(f"Config loaded from {CONFIG_PATH}")
        except Exception as e:
            print(f"WARN: failed to load config: {e}. Using defaults.", file=sys.stderr)

    # Apply cursor settings
    cursor = cfg.get("cursor", {})
    CURSOR_BASE_SPEED = cursor.get("base_speed", 3.0)
    CURSOR_MAX_SPEED = cursor.get("max_speed", 25.0)
    CURSOR_ACCEL = cursor.get("acceleration", 1.5)
    CURSOR_CURVE = cursor.get("curve", "quadratic")
    CURSOR_DEAD_ZONE = cursor.get("dead_zone", 0.1)
    CURSOR_INVERT_Y = cursor.get("invert_y", False)

    # Apply scroll settings
    scroll = cfg.get("scroll", {})
    SCROLL_SPEED = scroll.get("speed", 5.0)

    # Build button maps from config
    new_map = {}
    for btn_id, btn_cfg in cfg.get("buttons", {}).items():
        action = parse_action(btn_cfg)
        if action:
            new_map[btn_id] = action
    if new_map:
        BUTTON_MAP = new_map

    new_b_map = {}
    b_mode = cfg.get("b_mode", {})
    for btn_id, btn_cfg in b_mode.items():
        if btn_id == "tap":
            tap = parse_action(btn_cfg)
            if tap:
                B_TAP_ACTION = tap
            continue
        action = parse_action(btn_cfg)
        if action:
            new_b_map[btn_id] = action
    if new_b_map:
        MODE_B_MAP = new_b_map

    # Build Home-mode map from config
    new_home_map = {}
    home_mode = cfg.get("home_mode", {})
    for btn_id, btn_cfg in home_mode.items():
        if btn_id == "tap":
            tap = parse_action(btn_cfg)
            if tap:
                HOME_TAP_ACTION = tap
            continue
        action = parse_action(btn_cfg)
        if action:
            new_home_map[btn_id] = action
    if new_home_map:
        MODE_HOME_MAP = new_home_map

    # Double-tap settings
    dt = cfg.get("double_tap", {})
    DOUBLE_TAP_WINDOW = dt.get("window_seconds", 0.3)

    # Gesture settings
    gestures = cfg.get("gestures", {})
    GESTURE_THRESHOLD = gestures.get("threshold", 1.5)
    GESTURE_COOLDOWN_SEC = gestures.get("cooldown_seconds", 0.5)
    SHAKE_REVERSAL_COUNT = gestures.get("shake_reversals", 4)
    new_gesture_map = {}
    for gesture_name in ("flick_left", "flick_right", "flick_up", "flick_down", "shake"):
        if gesture_name in gestures:
            action = parse_action(gestures[gesture_name])
            if action:
                new_gesture_map[gesture_name] = action
    if new_gesture_map:
        GESTURE_MAP = new_gesture_map

    return cfg


def write_default_config():
    """Write the default config file if it doesn't exist."""
    if os.path.exists(CONFIG_PATH):
        return
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
    print(f"Default config written to {CONFIG_PATH}")


def check_accessibility():
    """Check macOS accessibility permission. Exit with clear message if missing."""
    if not AXIsProcessTrusted():
        print("ERROR: No accessibility permission.", file=sys.stderr)
        print(
            "Grant access in: System Settings > Privacy & Security > Accessibility",
            file=sys.stderr,
        )
        sys.exit(1)


def send_ctrl_opt(pressed):
    """Send Ctrl+Opt via kCGEventFlagsChanged events (Method C).

    This matches what macOS generates when you physically press modifier keys.
    """
    if pressed:
        e = CGEventCreateKeyboardEvent(None, VK_CONTROL, True)
        CGEventSetType(e, kCGEventFlagsChanged)
        CGEventSetFlags(e, kCGEventFlagMaskControl)
        CGEventPost(kCGHIDEventTap, e)
        e = CGEventCreateKeyboardEvent(None, VK_OPTION, True)
        CGEventSetType(e, kCGEventFlagsChanged)
        CGEventSetFlags(e, kCGEventFlagMaskControl | kCGEventFlagMaskAlternate)
        CGEventPost(kCGHIDEventTap, e)
    else:
        e = CGEventCreateKeyboardEvent(None, VK_OPTION, True)
        CGEventSetType(e, kCGEventFlagsChanged)
        CGEventSetFlags(e, kCGEventFlagMaskControl)
        CGEventPost(kCGHIDEventTap, e)
        e = CGEventCreateKeyboardEvent(None, VK_CONTROL, True)
        CGEventSetType(e, kCGEventFlagsChanged)
        CGEventSetFlags(e, 0)
        CGEventPost(kCGHIDEventTap, e)


def send_key_combo(modifiers, keycode):
    """Send a key press with modifier flags.

    Args:
        modifiers: list of modifier names ("cmd", "ctrl", "opt", "shift")
        keycode: virtual keycode to press
    """
    flags = 0
    for mod in modifiers:
        flags |= MODIFIER_FLAGS.get(mod, 0)

    e = CGEventCreateKeyboardEvent(None, keycode, True)
    if flags:
        CGEventSetFlags(e, flags)
    CGEventPost(kCGHIDEventTap, e)

    e = CGEventCreateKeyboardEvent(None, keycode, False)
    if flags:
        CGEventSetFlags(e, flags)
    CGEventPost(kCGHIDEventTap, e)


def send_mouse_click(button="left"):
    """Click the mouse at its current position.

    Clears modifier flags so held modifiers (e.g. Wispr's Ctrl+Opt)
    don't cause Ctrl+Click = right-click. Small delay between down/up
    ensures macOS registers the click for window activation.
    """
    loc = CGEventGetLocation(CGEventCreate(None))

    if button == "left":
        down_type, up_type, btn = kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGMouseButtonLeft
    else:
        down_type, up_type, btn = kCGEventRightMouseDown, kCGEventRightMouseUp, kCGMouseButtonRight

    e = CGEventCreateMouseEvent(None, down_type, loc, btn)
    CGEventSetFlags(e, 0)
    CGEventPost(kCGHIDEventTap, e)
    time.sleep(0.02)  # Brief pause so macOS registers the click
    e = CGEventCreateMouseEvent(None, up_type, loc, btn)
    CGEventSetFlags(e, 0)
    CGEventPost(kCGHIDEventTap, e)


def _clamp_to_screen(x, y):
    """Clamp coordinates to screen bounds."""
    bounds = CGDisplayBounds(CGMainDisplayID())
    x = max(bounds.origin.x, min(x, bounds.origin.x + bounds.size.width - 1))
    y = max(bounds.origin.y, min(y, bounds.origin.y + bounds.size.height - 1))
    return x, y


def move_cursor(dx, dy):
    """Move the cursor by (dx, dy) pixels from current position."""
    loc = CGEventGetLocation(CGEventCreate(None))
    new_x, new_y = _clamp_to_screen(loc.x + dx, loc.y + dy)

    e = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (new_x, new_y), kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, e)


def send_mouse_down(button="left"):
    """Press the mouse button down at current position (for drag start)."""
    loc = CGEventGetLocation(CGEventCreate(None))
    if button == "left":
        down_type, btn = kCGEventLeftMouseDown, kCGMouseButtonLeft
    else:
        down_type, btn = kCGEventRightMouseDown, kCGMouseButtonRight
    e = CGEventCreateMouseEvent(None, down_type, loc, btn)
    CGEventPost(kCGHIDEventTap, e)


def send_mouse_up(button="left"):
    """Release the mouse button at current position (for drag end)."""
    loc = CGEventGetLocation(CGEventCreate(None))
    if button == "left":
        up_type, btn = kCGEventLeftMouseUp, kCGMouseButtonLeft
    else:
        up_type, btn = kCGEventRightMouseUp, kCGMouseButtonRight
    e = CGEventCreateMouseEvent(None, up_type, loc, btn)
    CGEventPost(kCGHIDEventTap, e)


def move_cursor_dragged(dx, dy):
    """Move cursor while mouse button is held (drag)."""
    loc = CGEventGetLocation(CGEventCreate(None))
    new_x, new_y = _clamp_to_screen(loc.x + dx, loc.y + dy)

    e = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, (new_x, new_y), kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, e)


SNAP_MARGIN = 50  # Pixels from screen edge for snap targets


def warp_cursor_to_region(region):
    """Move cursor to a screen region. region is (rx, ry) where 0=left/top, 0.5=center, 1=right/bottom."""
    bounds = CGDisplayBounds(CGMainDisplayID())
    # Map (0,0)=top-left to (1,1)=bottom-right with margins
    x = bounds.origin.x + SNAP_MARGIN + (bounds.size.width - 2 * SNAP_MARGIN) * region[0]
    y = bounds.origin.y + SNAP_MARGIN + (bounds.size.height - 2 * SNAP_MARGIN) * region[1]
    e = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (x, y), kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, e)


def warp_cursor_to_center():
    """Move the cursor to the center of the main display."""
    bounds = CGDisplayBounds(CGMainDisplayID())
    cx = bounds.origin.x + bounds.size.width / 2
    cy = bounds.origin.y + bounds.size.height / 2
    e = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (cx, cy), kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, e)


def send_scroll(dx, dy):
    """Send a scroll event. dy>0 scrolls up, dy<0 scrolls down."""
    e = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 2, int(dy), int(dx))
    CGEventPost(kCGHIDEventTap, e)


def execute_action(action, pressed):
    """Execute a single action tuple."""
    global _wispr_active, _sticky_scroll

    action_type = action[0]

    if action_type == "wispr_toggle":
        if pressed and not _wispr_active:
            send_ctrl_opt(True)
            _wispr_active = True
        elif not pressed and _wispr_active:
            send_ctrl_opt(False)
            _wispr_active = False

    elif action_type == "key_combo":
        if pressed:
            _, modifiers, keycode = action
            send_key_combo(modifiers, keycode)

    elif action_type == "sequence":
        if pressed:
            for sub_action in action[1]:
                execute_action(sub_action, True)

    elif action_type == "sticky_scroll_toggle":
        if pressed:
            _sticky_scroll = not _sticky_scroll

    elif action_type == "volume_up":
        if pressed:
            _adjust_volume(6.25)  # ~1/16 of full range per flick

    elif action_type == "volume_down":
        if pressed:
            _adjust_volume(-6.25)

    elif action_type == "type_char":
        if pressed:
            _, char = action
            keycode = KEYCODE_NAMES.get(char.lower())
            if keycode is not None:
                send_key_combo([], keycode)

    elif action_type == "mouse_click":
        if pressed:
            _, button = action
            send_mouse_click(button)


def send_double_click():
    """Send a double-click at the current cursor position."""
    loc = CGEventGetLocation(CGEventCreate(None))
    for _ in range(2):
        e = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, loc, kCGMouseButtonLeft)
        CGEventSetIntegerValueField(e, 1, 2)  # clickState = 2 for double-click
        CGEventPost(kCGHIDEventTap, e)
        e = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, loc, kCGMouseButtonLeft)
        CGEventSetIntegerValueField(e, 1, 2)
        CGEventPost(kCGHIDEventTap, e)


def handle_button(button_id, pressed):
    """Map a button event to an action and execute it.

    B and Home buttons act as mode modifiers:
    - Hold B + press other buttons → uses MODE_B_MAP
    - Tap B alone (press + release without combo) → B_TAP_ACTION
    - Hold Home + press other buttons → uses MODE_HOME_MAP
    - Tap Home alone → HOME_TAP_ACTION (Spotlight)
    Double-tap Z → double-click
    """
    global _wispr_active, _scroll_mode, _b_held, _b_combo_used
    global _home_held, _home_combo_used, _z_last_release
    global _z_held, _z_combo_used, _drag_active, _c_last_release, _c_held
    global _a_held, _a_press_time, _a_click_sent, _b_held_raw, _ab_wispr_triggered

    # --- A = click/drag/double-tap ---
    # Mouse-down is deferred until stick moves (drag) to avoid
    # accidental micro-drags that prevent window activation.
    if button_id == "A":
        if pressed:
            _a_held = True
            _drag_active = False
            # Don't send mouse-down yet — wait for stick movement (drag)
            # or release (tap/click)
        else:
            _a_held = False
            if _drag_active:
                # Was dragging — release
                send_mouse_up("left")
            else:
                # Clean tap — send full click at current position
                now = time.time()
                if now - _z_last_release < DOUBLE_TAP_WINDOW:
                    send_double_click()
                    _z_last_release = 0.0
                else:
                    send_mouse_click("left")
                    _z_last_release = now
            _drag_active = False
        return

    # --- B = Wispr Flow toggle ---
    if button_id == "B":
        execute_action(("wispr_toggle",), pressed)
        return

    # --- Home = Mission Control (via BUTTON_MAP, no mode system) ---

    # --- Z-held = Cmd modifier mode (copy/paste/undo/cut + text selection) ---
    if _z_held and button_id in MODE_Z_MAP:
        _z_combo_used = True
        action = MODE_Z_MAP.get(button_id)
        if action:
            execute_action(action, pressed)
        return

    # --- Route through active modifier maps (B takes priority) ---
    if _b_held:
        action = MODE_B_MAP.get(button_id)
        if action is not None:
            _b_combo_used = True
            execute_action(action, pressed)
            return

    # --- Nunchuk C: modifier button ---
    if button_id == "NUNCHUK_C":
        _c_held = pressed
        return

    # --- Nunchuk Z: tap=Enter, hold=precision cursor ---
    if button_id == "NUNCHUK_Z":
        if pressed:
            _z_held = True
            _z_combo_used = False
        else:
            _z_held = False
            if not _z_combo_used:
                # Clean tap — send Enter
                send_key_combo([], VK_RETURN)
            _z_combo_used = False
        return

    # --- C-held mode routing ---
    if _c_held:
        action = MODE_C_MAP.get(button_id)
        if action is not None:
            execute_action(action, pressed)
            return

    # --- Default mode ---
    action = BUTTON_MAP.get(button_id)
    if action is not None:
        execute_action(action, pressed)


def handle_stick(x, y):
    """Handle nunchuk analog stick input.

    In normal mode: move cursor. When Nunchuk C is held: scroll instead.
    When Nunchuk Z is held: precision cursor (slower movement).
    x/y range: -1.0 to 1.0 (0.0 = centered, already dead-zone filtered by ESP32).
    """
    global _cursor_speed, _drag_active, _arrow_last_dir, _home_combo_used
    global _smooth_x, _smooth_y, _z_combo_used

    # Apply dead zone
    if abs(x) < CURSOR_DEAD_ZONE:
        x = 0.0
    if abs(y) < CURSOR_DEAD_ZONE:
        y = 0.0

    # Exponential smoothing for fluid cursor movement
    _smooth_x = _smooth_x + CURSOR_SMOOTHING * (x - _smooth_x)
    _smooth_y = _smooth_y + CURSOR_SMOOTHING * (y - _smooth_y)

    # Snap to zero when stick is centered
    if x == 0.0 and y == 0.0 and abs(_smooth_x) < 0.01 and abs(_smooth_y) < 0.01:
        _smooth_x = 0.0
        _smooth_y = 0.0
        _cursor_speed = 0.0
        _arrow_last_dir = None
        return

    # Use smoothed values for cursor, raw values for discrete actions
    x_raw, y_raw = x, y
    x, y = _smooth_x, _smooth_y

    # Apply Y-axis inversion
    if CURSOR_INVERT_Y:
        y = -y

    # Home + Z + stick = snap cursor to screen region
    if _home_held and _z_held:
        threshold = ARROW_STICK_THRESHOLD
        rx = 0.5  # center
        ry = 0.5
        if x < -threshold:
            rx = 0.0  # left
        elif x > threshold:
            rx = 1.0  # right
        if y > threshold:
            ry = 0.0  # top (stick up = top)
        elif y < -threshold:
            ry = 1.0  # bottom
        if rx != 0.5 or ry != 0.5:
            warp_cursor_to_region((rx, ry))
            _home_combo_used = True
        return

    # Home + stick = arrow keys (for terminal navigation, list selection)
    if _home_held:
        direction = None
        if abs(x) > abs(y):
            if x < -ARROW_STICK_THRESHOLD:
                direction = "left"
            elif x > ARROW_STICK_THRESHOLD:
                direction = "right"
        else:
            if y > ARROW_STICK_THRESHOLD:
                direction = "up"
            elif y < -ARROW_STICK_THRESHOLD:
                direction = "down"

        if direction and direction != _arrow_last_dir:
            arrow_keys = {"up": VK_UP, "down": VK_DOWN, "left": VK_LEFT, "right": VK_RIGHT}
            send_key_combo([], arrow_keys[direction])
            _arrow_last_dir = direction
            _home_combo_used = True
        return

    # C held = scroll mode (inverted both axes for natural scrolling)
    if _c_held:
        send_scroll(-x_raw * SCROLL_SPEED, y_raw * SCROLL_SPEED)
        return

    # Direct proportional speed — stick deflection maps directly to cursor speed
    # Quadratic curve gives fine control near center, fast at edges
    cx = x * abs(x)
    cy = y * abs(y)

    speed = CURSOR_MAX_SPEED

    # Z held = precision mode (slower cursor)
    if _z_held:
        speed = speed / PRECISION_MULTIPLIER
        if cx != 0.0 or cy != 0.0:
            _z_combo_used = True

    if _sticky_scroll:
        send_scroll(cx * SCROLL_SPEED, -cy * SCROLL_SPEED)
    elif _a_held:
        # A held + stick = drag mode
        if not _drag_active:
            send_mouse_down("left")  # Start drag on first stick movement
            _drag_active = True
        move_cursor_dragged(cx * speed, -cy * speed)
    else:
        move_cursor(cx * speed, -cy * speed)


def detect_gesture(buffer):
    """Detect a gesture from the accelerometer buffer.

    Returns gesture name ("flick_left", "flick_right", "flick_up", "flick_down", "shake") or None.
    """
    if len(buffer) < 3:
        return None

    # Compute running averages
    avg_x = sum(r[0] for r in buffer) / len(buffer)
    avg_y = sum(r[1] for r in buffer) / len(buffer)

    # Check latest reading against average for flick
    latest = buffer[-1]
    delta_x = latest[0] - avg_x
    delta_y = latest[1] - avg_y

    # Check X-axis flicks first (left/right)
    if abs(delta_x) > GESTURE_THRESHOLD:
        if delta_x < 0:
            return "flick_left"
        else:
            return "flick_right"

    # Check Y-axis flicks (up/down)
    if abs(delta_y) > GESTURE_THRESHOLD:
        if delta_y > 0:
            return "flick_up"
        else:
            return "flick_down"

    # Shake detection: count x-axis direction reversals in buffer
    if len(buffer) >= 5:
        reversals = 0
        for i in range(2, len(buffer)):
            prev_delta = buffer[i - 1][0] - buffer[i - 2][0]
            curr_delta = buffer[i][0] - buffer[i - 1][0]
            if prev_delta * curr_delta < 0:  # Sign change = reversal
                reversals += 1
        if reversals >= SHAKE_REVERSAL_COUNT:
            return "shake"

    return None


def handle_accel(x, y, z):
    """Handle accelerometer data — detect gestures from motion patterns."""
    global _accel_buffer, _gesture_last_time

    _accel_buffer.append((x, y, z))
    if len(_accel_buffer) > ACCEL_BUFFER_SIZE:
        _accel_buffer = _accel_buffer[-ACCEL_BUFFER_SIZE:]

    # Check cooldown
    now = time.time()
    if now - _gesture_last_time < GESTURE_COOLDOWN_SEC:
        return

    gesture = detect_gesture(_accel_buffer)
    if gesture is not None:
        action = GESTURE_MAP.get(gesture)
        if action is not None:
            execute_action(action, True)
            rumble(RUMBLE_GESTURE)
            _gesture_last_time = now
            _accel_buffer.clear()  # Reset buffer after gesture


STATUS_FILE = "/tmp/wiimote-status.json"
_status_last_write = 0.0
STATUS_WRITE_INTERVAL = 0.1  # Max 10 writes per second
_frontmost_app = ""
_frontmost_app_last_check = 0.0
FRONTMOST_APP_CHECK_INTERVAL = 1.0  # Check frontmost app every N seconds

# Help overlay
HELP_FILE = "/tmp/wiimote-help.txt"

# Battery state
_battery_level = -1  # -1 = unknown


def _action_desc(action):
    """Human-readable description of an action tuple."""
    if action is None:
        return "—"
    atype = action[0]
    if atype == "wispr_toggle":
        return "Wispr Flow (voice input)"
    elif atype == "key_combo":
        mods = "+".join(m.capitalize() for m in action[1]) if action[1] else ""
        key = next((name for name, code in KEYCODE_NAMES.items() if code == action[2]), f"0x{action[2]:02x}")
        return f"{mods}+{key}" if mods else key
    elif atype == "mouse_click":
        return f"{action[1]} click"
    elif atype == "sequence":
        return " → ".join(_action_desc(s) for s in action[1])
    elif atype == "sticky_scroll_toggle":
        return "toggle sticky scroll"
    elif atype == "volume_up":
        return "volume up"
    elif atype == "volume_down":
        return "volume down"
    return str(action)


def write_help():
    """Write current mode's button mapping to the help file."""
    try:
        lines = []
        if _b_held:
            lines.append("=== B-MODE ===")
            for btn, action in sorted(MODE_B_MAP.items()):
                lines.append(f"  B + {btn:12s} → {_action_desc(action)}")
            lines.append(f"  B tap        → {_action_desc(B_TAP_ACTION)}")
        elif _home_held:
            lines.append("=== HOME-MODE ===")
            for btn, action in sorted(MODE_HOME_MAP.items()):
                lines.append(f"  Home + {btn:12s} → {_action_desc(action)}")
            lines.append(f"  Home tap     → {_action_desc(HOME_TAP_ACTION)}")
            lines.append(f"  Home + stick → arrow keys")
            lines.append(f"  Home + Z + stick → screen snap")
        else:
            lines.append("=== DEFAULT MODE ===")
            for btn, action in sorted(BUTTON_MAP.items()):
                lines.append(f"  {btn:16s} → {_action_desc(action)}")
            lines.append(f"  Z (held)       → click/drag")
            lines.append(f"  C (held)       → scroll mode")
            lines.append(f"  Double-tap Z   → double-click")
            lines.append(f"  Double-tap C   → center cursor")
            if _z_held:
                lines.append("")
                lines.append("=== Z-HELD (text selection) ===")
                for btn, action in sorted(MODE_Z_MAP.items()):
                    lines.append(f"  Z + {btn:12s} → {_action_desc(action)}")

        with open(HELP_FILE, "w") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass  # Best-effort


def _get_frontmost_app():
    """Get the name of the frontmost application (cached)."""
    global _frontmost_app, _frontmost_app_last_check
    now = time.time()
    if now - _frontmost_app_last_check < FRONTMOST_APP_CHECK_INTERVAL:
        return _frontmost_app
    _frontmost_app_last_check = now
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first application process whose frontmost is true'],
            capture_output=True, text=True, timeout=1
        )
        if result.returncode == 0:
            _frontmost_app = result.stdout.strip()
    except Exception:
        pass
    return _frontmost_app


def write_status():
    """Write current state to the status file for external tools."""
    global _status_last_write

    now = time.time()
    if now - _status_last_write < STATUS_WRITE_INTERVAL:
        return
    _status_last_write = now

    mode = "default"
    if _b_held:
        mode = "b_mode"
    elif _home_held:
        mode = "home_mode"

    status = {
        "mode": mode,
        "wispr": _wispr_active,
        "scroll": _scroll_mode or _sticky_scroll,
        "sticky_scroll": _sticky_scroll,
        "z_held": _z_held,
        "drag": _drag_active,
        "connected": True,
        "battery": _battery_level,
        "app": _get_frontmost_app(),
    }
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f)
    except Exception:
        pass  # Best-effort


def read_events(source):
    """Yield parsed JSON events from a line-oriented source.

    Silently skips blank lines and malformed JSON.
    For serial ports (with timeout), uses readline() in a loop so that
    empty reads (timeout) don't terminate the generator.
    For stdin/file sources, iterates normally and stops on EOF.
    """
    if hasattr(source, 'in_waiting'):
        # Serial port — use readline loop (iter stops on empty timeout reads)
        while True:
            raw = source.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f"WARN: bad JSON: {line!r}", file=sys.stderr)
                continue
            yield event
    else:
        # stdin or file — iterate normally, EOF terminates
        for line in source:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f"WARN: bad JSON: {line!r}", file=sys.stderr)
                continue
            yield event


def replay_events(filepath):
    """Generator that yields recorded events with correct timing."""
    with open(filepath) as f:
        last_ts = 0.0
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = event.pop("_ts", 0.0)
            delay = ts - last_ts
            if delay > 0:
                time.sleep(delay)
            last_ts = ts
            yield json.dumps(event) + "\n"


def open_source(path=None):
    """Open the input source — serial port or stdin."""
    if path is None:
        return sys.stdin

    import serial

    return serial.Serial(path, 115200, timeout=0.1)


def rumble(duration_ms):
    """Send rumble using the global serial source (convenience wrapper)."""
    if _serial_source is not None:
        send_rumble(_serial_source, duration_ms)


def send_rumble(source, duration_ms):
    """Send a rumble command back to the ESP32 over serial."""
    if source is sys.stdin:
        return  # Can't send rumble over stdin
    try:
        cmd = json.dumps({"rumble": duration_ms}) + "\n"
        source.write(cmd.encode())
        source.flush()
    except Exception:
        pass  # Best-effort — don't crash if serial write fails


RECONNECT_DELAY_SEC = 2.0  # Seconds to wait before reconnecting
CONFIG_CHECK_INTERVAL = 100  # Check config every N events


def _get_config_mtime():
    """Get the mtime of the config file, or 0 if it doesn't exist."""
    try:
        return os.path.getmtime(CONFIG_PATH)
    except OSError:
        return 0


def run_event_loop(source, rumble_on_wispr, rumble_duration, record_file=None):
    """Process events from a source. Returns True if should reconnect, False to exit."""
    global _serial_source, _battery_level, _a_click_sent
    _serial_source = source
    prev_wispr = False
    event_count = 0
    config_mtime = _get_config_mtime()
    start_time = time.time()

    for event in read_events(source):
        # Record event with timestamp if recording
        if record_file is not None:
            event["_ts"] = round(time.time() - start_time, 3)
            record_file.write(json.dumps(event) + "\n")
            record_file.flush()
        # Hot-reload config check
        event_count += 1
        if event_count % CONFIG_CHECK_INTERVAL == 0:
            new_mtime = _get_config_mtime()
            if new_mtime != config_mtime:
                config_mtime = new_mtime
                load_config()
                print("Config reloaded.")
        event_type = event.get("type")
        if event_type == "button":
            handle_button(event.get("id"), event.get("pressed"))
            write_status()
            if rumble_on_wispr and _wispr_active and not prev_wispr:
                send_rumble(source, rumble_duration)
            prev_wispr = _wispr_active
        elif event_type == "stick":
            handle_stick(event.get("x", 0.0), event.get("y", 0.0))
        elif event_type == "accel":
            pass  # Motion controls disabled
        elif event_type == "battery":
            _battery_level = event.get("level", -1)
            write_status()
        elif event_type == "status":
            print(f"ESP32: {event.get('msg', '')}")
    return False  # EOF — don't reconnect for stdin


LAUNCHAGENT_LABEL = "com.wiimote-control.daemon"
LAUNCHAGENT_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCHAGENT_LABEL}.plist")


def _adjust_volume(delta):
    """Adjust system volume by delta (0-100 scale). Uses osascript."""
    try:
        script = (
            f'set curVol to output volume of (get volume settings)\n'
            f'set volume output volume (curVol + {delta})'
        )
        subprocess.Popen(["osascript", "-e", script],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # Best-effort


def notify(title, message):
    """Show a macOS notification."""
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.Popen(["osascript", "-e", script],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # Best-effort


def install_launchagent(serial_path):
    """Install a LaunchAgent plist for auto-start on login."""
    python_path = sys.executable
    script_path = os.path.abspath(__file__)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHAGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>{serial_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/wiimote-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/wiimote-daemon.log</string>
</dict>
</plist>
"""
    os.makedirs(os.path.dirname(LAUNCHAGENT_PATH), exist_ok=True)
    with open(LAUNCHAGENT_PATH, "w") as f:
        f.write(plist)
    print(f"LaunchAgent installed at {LAUNCHAGENT_PATH}")
    print(f"Load with: launchctl load {LAUNCHAGENT_PATH}")


def uninstall_launchagent():
    """Remove the LaunchAgent plist."""
    if os.path.exists(LAUNCHAGENT_PATH):
        os.remove(LAUNCHAGENT_PATH)
        print(f"LaunchAgent removed: {LAUNCHAGENT_PATH}")
        print(f"Unload with: launchctl unload {LAUNCHAGENT_PATH}")
    else:
        print("No LaunchAgent found.")


def main():
    # Handle --install / --uninstall flags
    if "--install" in sys.argv:
        idx = sys.argv.index("--install")
        serial_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if not serial_path:
            print("Usage: wiimote_daemon.py --install /dev/tty.usbserial-XXX", file=sys.stderr)
            sys.exit(1)
        install_launchagent(serial_path)
        return
    if "--uninstall" in sys.argv:
        uninstall_launchagent()
        return

    check_accessibility()
    cfg = load_config()
    write_default_config()

    rumble_cfg = cfg.get("rumble", {})
    rumble_on_wispr = rumble_cfg.get("on_wispr", True)
    rumble_duration = rumble_cfg.get("duration_ms", 200)

    # Handle --record and --replay flags
    record_path = None
    replay_path = None
    remaining_args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if "--record" in sys.argv:
        idx = sys.argv.index("--record")
        record_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
    if "--replay" in sys.argv:
        idx = sys.argv.index("--replay")
        replay_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    serial_path = remaining_args[0] if remaining_args else None
    source_name = replay_path or serial_path or "stdin"
    print(f"Wiimote daemon listening on {source_name}. Ctrl+C to quit.")
    gestures_enabled = cfg.get("gestures", {}).get("enabled", True)
    print(f"Button map: {len(BUTTON_MAP)} buttons, B-mode: {len(MODE_B_MAP)} combos, "
          f"Home-mode: {len(MODE_HOME_MAP)} combos, gestures: {'on' if gestures_enabled else 'off'}")

    record_file = open(record_path, "w") if record_path else None
    if record_path:
        print(f"Recording events to {record_path}")

    try:
        if replay_path:
            # Replay mode: read from recorded file
            source = replay_events(replay_path)
            print(f"Replaying events from {replay_path}")
            run_event_loop(source, rumble_on_wispr, rumble_duration)
            print("Replay complete.")
            return

        while True:
            source = open_source(serial_path)
            if serial_path:
                notify("Wiimote Control", "Connected to ESP32")
            try:
                run_event_loop(source, rumble_on_wispr, rumble_duration, record_file=record_file)
                break  # Clean EOF (stdin) — exit
            except OSError as e:
                # Serial disconnect — reconnect
                if serial_path is None:
                    raise  # Don't reconnect stdin errors
                notify("Wiimote Control", "Disconnected — reconnecting...")
                print(f"\nSerial error: {e}. Reconnecting in {RECONNECT_DELAY_SEC}s...")
                try:
                    source.close()
                except Exception:
                    pass
                if _wispr_active:
                    send_ctrl_opt(False)
                time.sleep(RECONNECT_DELAY_SEC)
                print(f"Reconnecting to {serial_path}...")
            except KeyboardInterrupt:
                raise
            finally:
                if source is not sys.stdin:
                    try:
                        source.close()
                    except Exception:
                        pass
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        if _wispr_active:
            send_ctrl_opt(False)
        if record_file:
            record_file.close()
            print(f"Recording saved to {record_path}")


if __name__ == "__main__":
    main()
