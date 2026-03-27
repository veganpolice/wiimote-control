#!/usr/bin/env python3
"""Standalone keypress test — run this FIRST to verify permissions and find which method Wispr responds to."""

import sys
import time

import Quartz
from Quartz import (
    CGEventCreate,
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSetType,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskControl,
    kCGEventFlagsChanged,
    kCGHIDEventTap,
)

from ApplicationServices import AXIsProcessTrusted

# Virtual keycodes
VK_CONTROL = 0x3B
VK_OPTION = 0x3A
VK_F18 = 0x4F


def check_accessibility():
    if not AXIsProcessTrusted():
        print("ERROR: No accessibility permission.")
        print("Grant access in: System Settings > Privacy & Security > Accessibility")
        print("Add Terminal (or your Python binary) to the list.")
        sys.exit(1)
    print("OK: Accessibility permission granted.")


def method_a_raw_modifiers():
    """Press Control and Option keys directly via key-down events."""
    print("\n--- Method A: Raw modifier key down/up events ---")
    print("Pressing Control down...")
    e = CGEventCreateKeyboardEvent(None, VK_CONTROL, True)
    CGEventPost(kCGHIDEventTap, e)

    print("Pressing Option down...")
    e = CGEventCreateKeyboardEvent(None, VK_OPTION, True)
    CGEventSetFlags(e, kCGEventFlagMaskControl)
    CGEventPost(kCGHIDEventTap, e)

    time.sleep(0.5)

    print("Releasing Option...")
    e = CGEventCreateKeyboardEvent(None, VK_OPTION, False)
    CGEventPost(kCGHIDEventTap, e)

    print("Releasing Control...")
    e = CGEventCreateKeyboardEvent(None, VK_CONTROL, False)
    CGEventPost(kCGHIDEventTap, e)

    print("Method A done. Did Wispr activate?")


def method_b_dummy_key():
    """Press F18 with Ctrl+Opt flags."""
    print("\n--- Method B: F18 key with Ctrl+Opt flags ---")
    flags = kCGEventFlagMaskControl | kCGEventFlagMaskAlternate

    print("Pressing Ctrl+Opt+F18 down...")
    e = CGEventCreateKeyboardEvent(None, VK_F18, True)
    CGEventSetFlags(e, flags)
    CGEventPost(kCGHIDEventTap, e)

    time.sleep(0.5)

    print("Releasing Ctrl+Opt+F18...")
    e = CGEventCreateKeyboardEvent(None, VK_F18, False)
    CGEventSetFlags(e, flags)
    CGEventPost(kCGHIDEventTap, e)

    print("Method B done. Did Wispr activate?")


def method_c_flags_changed():
    """Send kCGEventFlagsChanged events — this is what macOS generates when you physically press modifier keys."""
    print("\n--- Method C: FlagsChanged events (physical modifier simulation) ---")

    # Press Control: send flagsChanged with Control flag + Control keycode
    print("Sending FlagsChanged: Control down...")
    e = CGEventCreateKeyboardEvent(None, VK_CONTROL, True)
    CGEventSetType(e, kCGEventFlagsChanged)
    CGEventSetFlags(e, kCGEventFlagMaskControl)
    CGEventPost(kCGHIDEventTap, e)

    time.sleep(0.05)

    # Press Option: send flagsChanged with Control+Option flags + Option keycode
    print("Sending FlagsChanged: Option down (Control held)...")
    e = CGEventCreateKeyboardEvent(None, VK_OPTION, True)
    CGEventSetType(e, kCGEventFlagsChanged)
    CGEventSetFlags(e, kCGEventFlagMaskControl | kCGEventFlagMaskAlternate)
    CGEventPost(kCGHIDEventTap, e)

    time.sleep(0.5)

    # Release Option: send flagsChanged with only Control flag + Option keycode
    print("Sending FlagsChanged: Option up...")
    e = CGEventCreateKeyboardEvent(None, VK_OPTION, True)
    CGEventSetType(e, kCGEventFlagsChanged)
    CGEventSetFlags(e, kCGEventFlagMaskControl)
    CGEventPost(kCGHIDEventTap, e)

    time.sleep(0.05)

    # Release Control: send flagsChanged with no flags + Control keycode
    print("Sending FlagsChanged: Control up...")
    e = CGEventCreateKeyboardEvent(None, VK_CONTROL, True)
    CGEventSetType(e, kCGEventFlagsChanged)
    CGEventSetFlags(e, 0)
    CGEventPost(kCGHIDEventTap, e)

    print("Method C done. Did Wispr activate?")


if __name__ == "__main__":
    check_accessibility()

    print("\nTesting three keypress methods. Watch for Wispr Flow activation.")
    print("Each method holds for 0.5 seconds.")

    print("\n" + "=" * 50)
    method_a_raw_modifiers()

    time.sleep(2)
    print("\n" + "=" * 50)
    method_b_dummy_key()

    time.sleep(2)
    print("\n" + "=" * 50)
    method_c_flags_changed()

    print("\n" + "=" * 50)
    print("\nWhich method activated Wispr?")
    print("  A = raw modifier key down/up")
    print("  B = F18 with flags")
    print("  C = FlagsChanged events (most likely)")
    print("  Neither = need further investigation")
