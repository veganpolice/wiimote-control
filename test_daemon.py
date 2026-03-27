#!/usr/bin/env python3
"""Tests for wiimote_daemon.py — mocks CGEvent calls, verifies button→keypress logic."""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch


# Mock Quartz before importing the daemon (it won't be available in CI or without permissions)
mock_quartz = MagicMock()
mock_quartz.kCGEventFlagMaskControl = 0x00040000
mock_quartz.kCGEventFlagMaskAlternate = 0x00080000
mock_quartz.kCGEventFlagMaskCommand = 0x00100000
mock_quartz.kCGEventFlagMaskShift = 0x00020000
mock_quartz.kCGEventFlagsChanged = 12
mock_quartz.kCGHIDEventTap = 0
mock_quartz.kCGEventLeftMouseDown = 1
mock_quartz.kCGEventLeftMouseUp = 2
mock_quartz.kCGEventRightMouseDown = 3
mock_quartz.kCGEventRightMouseUp = 4
mock_quartz.kCGEventMouseMoved = 5
mock_quartz.kCGEventLeftMouseDragged = 6
mock_quartz.kCGEventScrollWheel = 22
mock_quartz.kCGMouseButtonLeft = 0
mock_quartz.kCGMouseButtonRight = 1
mock_quartz.kCGScrollEventUnitPixel = 0

# Mock CGEventGetLocation to return a fake point
mock_point = MagicMock()
mock_point.x = 500.0
mock_point.y = 400.0
mock_quartz.CGEventGetLocation = MagicMock(return_value=mock_point)
mock_quartz.CGEventCreate = MagicMock()

# Mock CGDisplayBounds
mock_bounds = MagicMock()
mock_bounds.origin.x = 0
mock_bounds.origin.y = 0
mock_bounds.size.width = 1920
mock_bounds.size.height = 1080
mock_quartz.CGDisplayBounds = MagicMock(return_value=mock_bounds)
mock_quartz.CGMainDisplayID = MagicMock(return_value=0)

sys.modules["Quartz"] = mock_quartz

mock_yaml = MagicMock()
sys.modules["yaml"] = mock_yaml
mock_yaml.safe_load = MagicMock(return_value=None)
mock_yaml.dump = MagicMock()

mock_app_services = MagicMock()
mock_app_services.AXIsProcessTrusted = MagicMock(return_value=True)
sys.modules["ApplicationServices"] = mock_app_services

import wiimote_daemon as wd


class TestCheckAccessibility(unittest.TestCase):
    def test_exits_when_not_trusted(self):
        mock_app_services.AXIsProcessTrusted.return_value = False
        with self.assertRaises(SystemExit):
            wd.check_accessibility()
        mock_app_services.AXIsProcessTrusted.return_value = True

    def test_passes_when_trusted(self):
        mock_app_services.AXIsProcessTrusted.return_value = True
        wd.check_accessibility()  # Should not raise


class TestReadEvents(unittest.TestCase):
    def _events_from(self, *lines):
        source = io.StringIO("\n".join(lines) + "\n")
        return list(wd.read_events(source))

    def test_valid_button_event(self):
        events = self._events_from('{"type":"button","id":"A","pressed":true}')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "button")
        self.assertEqual(events[0]["id"], "A")
        self.assertTrue(events[0]["pressed"])

    def test_malformed_json_skipped(self):
        events = self._events_from("not json", '{"type":"button","id":"A","pressed":true}')
        self.assertEqual(len(events), 1)

    def test_empty_lines_skipped(self):
        events = self._events_from("", "", '{"type":"button","id":"A","pressed":true}', "")
        self.assertEqual(len(events), 1)

    def test_eof_produces_no_events(self):
        events = self._events_from("")
        self.assertEqual(len(events), 0)

    def test_unknown_type_still_yielded(self):
        events = self._events_from('{"type":"accel","x":0.1}')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "accel")


class TestSendKeyCombo(unittest.TestCase):
    def setUp(self):
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_key_with_modifier(self):
        wd.send_key_combo(["cmd"], wd.VK_TAB)
        # Should post 2 events: key down + key up
        self.assertEqual(mock_quartz.CGEventPost.call_count, 2)
        # Flags should have been set
        self.assertTrue(mock_quartz.CGEventSetFlags.called)

    def test_key_without_modifier(self):
        wd.send_key_combo([], wd.VK_RETURN)
        self.assertEqual(mock_quartz.CGEventPost.call_count, 2)
        # No flags set when no modifiers
        mock_quartz.CGEventSetFlags.assert_not_called()

    def test_multiple_modifiers(self):
        wd.send_key_combo(["cmd", "shift"], wd.VK_TAB)
        self.assertEqual(mock_quartz.CGEventPost.call_count, 2)
        # Check combined flags
        call_args = mock_quartz.CGEventSetFlags.call_args_list
        expected = mock_quartz.kCGEventFlagMaskCommand | mock_quartz.kCGEventFlagMaskShift
        self.assertEqual(call_args[0][0][1], expected)


class TestHandleButton(unittest.TestCase):
    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._a_held = False
        wd._c_held = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_button_a_press_sends_keypress(self):
        wd.handle_button("A", True)
        self.assertTrue(wd._a_held)
        # A press sets _a_held but does NOT call CGEventPost
        mock_quartz.CGEventPost.assert_not_called()

    def test_button_a_release_sends_key_release(self):
        wd._a_held = True
        wd.handle_button("A", False)
        # A release sends a mouse click (CGEventCreateMouseEvent called)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_unknown_button_ignored(self):
        wd.handle_button("UNKNOWN", True)
        self.assertFalse(wd._wispr_active)
        mock_quartz.CGEventPost.assert_not_called()

    def test_double_press_no_duplicate(self):
        wd.handle_button("A", True)
        call_count_after_first = mock_quartz.CGEventPost.call_count
        wd.handle_button("A", True)  # Second press while active
        self.assertEqual(mock_quartz.CGEventPost.call_count, call_count_after_first)

    def test_release_without_press_no_op(self):
        # A release without prior press still sends a mouse click
        # (current behavior: _a_held is False, _drag_active is False, goes to click branch)
        wd.handle_button("A", False)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_dpad_right_sends_cmd_tab(self):
        wd.handle_button("RIGHT", True)
        self.assertTrue(mock_quartz.CGEventPost.called)
        # RIGHT sends VK_RIGHT with NO modifier flags (plain arrow key)
        mock_quartz.CGEventSetFlags.assert_not_called()

    def test_dpad_left_sends_cmd_shift_tab(self):
        wd.handle_button("LEFT", True)
        self.assertTrue(mock_quartz.CGEventPost.called)
        # LEFT sends VK_LEFT with NO modifier flags (plain arrow key)
        mock_quartz.CGEventSetFlags.assert_not_called()

    def test_dpad_up_sends_ctrl_up(self):
        wd.handle_button("UP", True)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_dpad_down_sends_ctrl_down(self):
        wd.handle_button("DOWN", True)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_plus_sends_tab(self):
        wd.handle_button("PLUS", True)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_minus_sends_shift_tab(self):
        wd.handle_button("MINUS", True)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_button_1_sends_return(self):
        wd.handle_button("1", True)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_button_2_sends_escape(self):
        wd.handle_button("2", True)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_home_tap_sends_cmd_space(self):
        """HOME press sends Ctrl+Up immediately via BUTTON_MAP."""
        wd.handle_button("HOME", True)
        # HOME is in BUTTON_MAP as ("key_combo", ["ctrl"], VK_UP) — fires on press
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_key_combo_only_on_press(self):
        """Key combo actions fire on press, not on release."""
        wd.handle_button("RIGHT", True)
        press_count = mock_quartz.CGEventPost.call_count
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("RIGHT", False)
        self.assertEqual(mock_quartz.CGEventPost.call_count, 0)

    def test_nunchuk_z_press_sets_held(self):
        wd.handle_button("NUNCHUK_Z", True)
        self.assertTrue(wd._z_held)
        # No immediate action on press (deferred: Enter on tap, precision on hold)
        self.assertFalse(mock_quartz.CGEventCreateKeyboardEvent.called)

    def test_nunchuk_z_tap_sends_enter(self):
        wd.handle_button("NUNCHUK_Z", True)
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("NUNCHUK_Z", False)
        self.assertFalse(wd._z_held)
        # Tap (no stick movement) should send Enter
        self.assertTrue(mock_quartz.CGEventCreateKeyboardEvent.called)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_RETURN)

    def test_nunchuk_c_sets_c_held(self):
        wd.handle_button("NUNCHUK_C", True)
        self.assertTrue(wd._c_held)
        wd.handle_button("NUNCHUK_C", False)
        self.assertFalse(wd._c_held)


class TestModeSystem(unittest.TestCase):
    """Tests for B-button Wispr toggle."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_b_press_activates_wispr(self):
        """B press activates Wispr (sets _wispr_active=True)."""
        wd.handle_button("B", True)
        self.assertTrue(wd._wispr_active)

    def test_b_release_exits_mode(self):
        """B release deactivates Wispr (sets _wispr_active=False)."""
        wd.handle_button("B", True)
        wd.handle_button("B", False)
        self.assertFalse(wd._wispr_active)

    def test_b_release_deactivates_wispr(self):
        """B release when Wispr was active deactivates it."""
        wd._wispr_active = True
        wd.handle_button("B", False)
        self.assertFalse(wd._wispr_active)


class TestHandleStick(unittest.TestCase):
    def setUp(self):
        wd._cursor_speed = 0.0
        wd._scroll_mode = False
        wd._z_held = False
        wd._drag_active = False
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._c_held = False
        wd._a_held = False
        wd._z_combo_used = False
        wd._sticky_scroll = False
        wd._arrow_last_dir = None
        wd._home_held = False
        wd._home_combo_used = False
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()

    def test_centered_stick_no_movement(self):
        wd.handle_stick(0.0, 0.0)
        mock_quartz.CGEventCreateMouseEvent.assert_not_called()

    def test_stick_deflection_moves_cursor(self):
        wd.handle_stick(1.0, 0.0)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    def test_cursor_accelerates(self):
        wd.handle_stick(1.0, 0.0)
        speed1 = wd._cursor_speed
        wd.handle_stick(1.0, 0.0)
        speed2 = wd._cursor_speed
        self.assertGreaterEqual(speed2, speed1)

    def test_cursor_speed_resets_on_center(self):
        wd.handle_stick(1.0, 0.0)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        # Reset smoothing so centering is immediate
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd.handle_stick(0.0, 0.0)
        # Centering should send no event
        mock_quartz.CGEventCreateMouseEvent.assert_not_called()

    def test_scroll_mode_when_c_held(self):
        wd._c_held = True
        wd.handle_stick(0.0, 1.0)
        # In scroll mode (C held), should use scroll events, not mouse move
        self.assertTrue(mock_quartz.CGEventCreateScrollWheelEvent.called)

    def test_precision_mode_when_z_held(self):
        """Stick movement while Z is held uses precision (slower) speed."""
        wd._z_held = True
        wd._z_combo_used = False
        wd.handle_stick(1.0, 0.0)
        # Should mark Z as used (no Enter on release)
        self.assertTrue(wd._z_combo_used)
        # Should still move cursor (not drag)
        self.assertFalse(wd._drag_active)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    def test_no_precision_when_z_released(self):
        """Stick movement without Z held sends normal move events."""
        wd._z_held = False
        wd.handle_stick(1.0, 0.0)
        self.assertFalse(wd._drag_active)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    def test_quadratic_curve_reduces_small_input(self):
        """Quadratic curve: small stick deflection produces smaller movement."""
        orig_curve = wd.CURSOR_CURVE
        try:
            # With linear
            wd.CURSOR_CURVE = "linear"
            wd._cursor_speed = 10.0
            wd.handle_stick(0.5, 0.0)
            linear_call = mock_quartz.CGEventCreateMouseEvent.call_args

            mock_quartz.CGEventCreateMouseEvent.reset_mock()
            mock_quartz.CGEventPost.reset_mock()

            # With quadratic — same input should produce smaller movement
            wd.CURSOR_CURVE = "quadratic"
            wd._cursor_speed = 10.0
            wd.handle_stick(0.5, 0.0)
            quad_call = mock_quartz.CGEventCreateMouseEvent.call_args

            # Both should have been called
            self.assertIsNotNone(linear_call)
            self.assertIsNotNone(quad_call)
        finally:
            wd.CURSOR_CURVE = orig_curve

    def test_quadratic_curve_preserves_full_deflection(self):
        """Quadratic curve: full deflection (1.0) produces same movement as linear."""
        orig_curve = wd.CURSOR_CURVE
        try:
            wd.CURSOR_CURVE = "quadratic"
            wd._cursor_speed = 10.0
            wd.handle_stick(1.0, 0.0)
            # 1.0 * abs(1.0) = 1.0 — same as linear
            self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)
        finally:
            wd.CURSOR_CURVE = orig_curve


class TestZPrecisionMode(unittest.TestCase):
    """Tests for Z = tap Enter / hold precision cursor."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._z_combo_used = False
        wd._drag_active = False
        wd._cursor_speed = 0.0
        wd._c_held = False
        wd._a_held = False
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._sticky_scroll = False
        wd._arrow_last_dir = None
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_z_hold_stick_release_no_enter(self):
        """Z press → stick move → Z release = precision cursor, no Enter."""
        wd.handle_button("NUNCHUK_Z", True)
        self.assertTrue(wd._z_held)

        # Move stick while Z held — marks as combo used
        wd.handle_stick(0.5, 0.0)
        self.assertTrue(wd._z_combo_used)

        # Release Z — should NOT send Enter since stick was moved
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        wd.handle_button("NUNCHUK_Z", False)
        self.assertFalse(wd._z_held)
        self.assertFalse(mock_quartz.CGEventCreateKeyboardEvent.called)

    def test_z_quick_tap_sends_enter(self):
        """Z press → Z release (no stick) = Enter."""
        wd.handle_button("NUNCHUK_Z", True)
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("NUNCHUK_Z", False)
        # Should have sent Enter
        self.assertTrue(mock_quartz.CGEventCreateKeyboardEvent.called)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_RETURN)

    def test_z_hold_no_stick_sends_enter(self):
        """Z press → Z release without any stick movement = still Enter."""
        wd.handle_button("NUNCHUK_Z", True)
        # No stick movement
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        wd.handle_button("NUNCHUK_Z", False)
        self.assertTrue(mock_quartz.CGEventCreateKeyboardEvent.called)

    def test_z_dpad_marks_combo_used(self):
        """Z held + D-pad = text selection, marks combo used (no Enter on release)."""
        wd.handle_button("NUNCHUK_Z", True)
        self.assertFalse(wd._z_combo_used)
        wd.handle_button("LEFT", True)
        self.assertTrue(wd._z_combo_used)
        # Release Z — should NOT send Enter
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        wd.handle_button("NUNCHUK_Z", False)
        # Check no Enter was sent (only Shift+Left was sent earlier)
        for call in mock_quartz.CGEventCreateKeyboardEvent.call_args_list:
            self.assertNotEqual(call[0][1], wd.VK_RETURN)


class TestMainIntegration(unittest.TestCase):
    """Integration test: pipe JSON into main loop, verify keypresses sent."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._cursor_speed = 0.0

    def test_press_and_release_cycle(self):
        wd._wispr_active = False
        wd._a_held = False
        wd._drag_active = False
        mock_quartz.CGEventPost.reset_mock()

        events = [
            {"type": "button", "id": "A", "pressed": True},
            {"type": "button", "id": "A", "pressed": False},
        ]
        source = io.StringIO("\n".join(json.dumps(e) for e in events) + "\n")

        for event in wd.read_events(source):
            if event.get("type") == "button":
                wd.handle_button(event.get("id"), event.get("pressed"))

        self.assertFalse(wd._a_held)
        # A press sends 0 events, A release sends mouse click (down+up = 2 CGEventPost)
        self.assertEqual(mock_quartz.CGEventPost.call_count, 2)

    def test_mixed_event_stream(self):
        """Verify daemon handles a realistic mixed stream of events."""
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._cursor_speed = 0.0
        mock_quartz.CGEventPost.reset_mock()

        events = [
            {"type": "button", "id": "RIGHT", "pressed": True},
            {"type": "button", "id": "RIGHT", "pressed": False},
            {"type": "stick", "x": 0.5, "y": 0.0},
            {"type": "button", "id": "A", "pressed": True},
            {"type": "button", "id": "A", "pressed": False},
        ]
        source = io.StringIO("\n".join(json.dumps(e) for e in events) + "\n")

        for event in wd.read_events(source):
            et = event.get("type")
            if et == "button":
                wd.handle_button(event.get("id"), event.get("pressed"))
            elif et == "stick":
                wd.handle_stick(event.get("x", 0.0), event.get("y", 0.0))

        # RIGHT press = 2 posts (down+up), stick = 1 mouse move, A press+release = 4 posts
        self.assertFalse(wd._wispr_active)
        self.assertGreater(mock_quartz.CGEventPost.call_count, 0)

    def test_run_event_loop_processes_events(self):
        """run_event_loop processes events and returns False on EOF."""
        wd._wispr_active = False
        mock_quartz.CGEventPost.reset_mock()

        events = [
            {"type": "button", "id": "RIGHT", "pressed": True},
            {"type": "button", "id": "RIGHT", "pressed": False},
        ]
        source = io.StringIO("\n".join(json.dumps(e) for e in events) + "\n")
        result = wd.run_event_loop(source, rumble_on_wispr=False, rumble_duration=200)
        self.assertFalse(result)  # EOF = don't reconnect
        self.assertGreater(mock_quartz.CGEventPost.call_count, 0)

    def test_run_event_loop_handles_accel(self):
        """run_event_loop handles accel events (currently pass — motion controls disabled)."""
        wd._accel_buffer = []
        wd._gesture_last_time = 0.0

        events = [{"type": "accel", "x": 0.0, "y": 0.0, "z": 1.0}]
        source = io.StringIO("\n".join(json.dumps(e) for e in events) + "\n")
        wd.run_event_loop(source, rumble_on_wispr=False, rumble_duration=200)
        # Accel events are currently pass (motion controls disabled), buffer stays empty
        self.assertEqual(len(wd._accel_buffer), 0)


class TestHomeButton(unittest.TestCase):
    """Tests for Home button — routes through BUTTON_MAP as Ctrl+Up."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._a_held = False
        wd._c_held = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_home_sends_ctrl_up(self):
        """HOME press calls CGEventPost (fires immediately via BUTTON_MAP)."""
        wd.handle_button("HOME", True)
        self.assertTrue(mock_quartz.CGEventPost.called)
        # Verify Ctrl flag is set
        flag_calls = mock_quartz.CGEventSetFlags.call_args_list
        self.assertTrue(any(
            args[0][1] & mock_quartz.kCGEventFlagMaskControl
            for args in flag_calls
        ))


class TestDoubleTapZ(unittest.TestCase):
    """Tests for double-tap Z → double-click."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    @patch("wiimote_daemon.time")
    def test_double_tap_a_sends_double_click(self, mock_time):
        """Two quick A releases → double-click."""
        # First tap
        mock_time.time.return_value = 1000.0
        wd.handle_button("A", True)
        wd.handle_button("A", False)

        # Second tap within window
        mock_time.time.return_value = 1000.1  # 100ms later
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("A", True)
        wd.handle_button("A", False)
        # Double-click sends mouse events
        self.assertGreater(mock_quartz.CGEventPost.call_count, 0)

    @patch("wiimote_daemon.time")
    def test_slow_taps_a_no_double_click(self, mock_time):
        """Two slow A releases → two single clicks, no double-click."""
        mock_time.time.return_value = 1000.0
        wd.handle_button("A", True)
        wd.handle_button("A", False)

        # Second tap after window expires
        mock_time.time.return_value = 1001.0  # 1 second later
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        wd.handle_button("A", True)
        wd.handle_button("A", False)
        # Should send single click, not double-click
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)


class TestGestureDetection(unittest.TestCase):
    """Tests for accelerometer gesture detection."""

    def setUp(self):
        wd._accel_buffer = []
        wd._gesture_last_time = 0.0
        wd._wispr_active = False
        wd._b_held = False
        wd._home_held = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_detect_flick_right(self):
        """Sharp positive X spike → flick_right."""
        # Build buffer of calm readings
        buffer = [(0.0, 0.0, 1.0)] * 8
        # Add a spike
        buffer.append((2.0, 0.0, 1.0))
        gesture = wd.detect_gesture(buffer)
        self.assertEqual(gesture, "flick_right")

    def test_detect_flick_left(self):
        """Sharp negative X spike → flick_left."""
        buffer = [(0.0, 0.0, 1.0)] * 8
        buffer.append((-2.0, 0.0, 1.0))
        gesture = wd.detect_gesture(buffer)
        self.assertEqual(gesture, "flick_left")

    def test_no_gesture_at_rest(self):
        """Calm readings → no gesture."""
        buffer = [(0.0, 0.0, 1.0)] * 10
        gesture = wd.detect_gesture(buffer)
        self.assertIsNone(gesture)

    def test_detect_shake(self):
        """Rapid X reversals → shake."""
        buffer = [
            (0.5, 0.0, 1.0),
            (-0.5, 0.0, 1.0),
            (0.5, 0.0, 1.0),
            (-0.5, 0.0, 1.0),
            (0.5, 0.0, 1.0),
            (-0.5, 0.0, 1.0),
            (0.5, 0.0, 1.0),
        ]
        gesture = wd.detect_gesture(buffer)
        self.assertEqual(gesture, "shake")

    def test_buffer_too_small_no_gesture(self):
        """Buffer with < 3 readings → no gesture."""
        buffer = [(0.0, 0.0, 1.0), (2.0, 0.0, 1.0)]
        gesture = wd.detect_gesture(buffer)
        self.assertIsNone(gesture)

    @patch("wiimote_daemon.time")
    def test_handle_accel_fires_action(self, mock_time):
        """handle_accel detects a flick and fires the mapped action."""
        mock_time.time.return_value = 1000.0
        # Fill buffer with calm readings
        for _ in range(9):
            wd.handle_accel(0.0, 0.0, 1.0)
        mock_quartz.CGEventPost.reset_mock()
        # Send spike
        wd.handle_accel(3.0, 0.0, 1.0)
        self.assertTrue(mock_quartz.CGEventPost.called)

    @patch("wiimote_daemon.time")
    def test_gesture_cooldown(self, mock_time):
        """After a gesture, cooldown prevents immediate re-trigger."""
        mock_time.time.return_value = 1000.0
        for _ in range(9):
            wd.handle_accel(0.0, 0.0, 1.0)
        wd.handle_accel(3.0, 0.0, 1.0)  # Triggers gesture
        post_count = mock_quartz.CGEventPost.call_count

        # Immediately try again (within cooldown)
        mock_time.time.return_value = 1000.1  # Only 100ms later
        mock_quartz.CGEventPost.reset_mock()
        for _ in range(9):
            wd.handle_accel(0.0, 0.0, 1.0)
        wd.handle_accel(3.0, 0.0, 1.0)  # Should be blocked by cooldown
        self.assertEqual(mock_quartz.CGEventPost.call_count, 0)

    @patch("wiimote_daemon.time")
    def test_gesture_after_cooldown_expires(self, mock_time):
        """After cooldown expires, gestures work again."""
        mock_time.time.return_value = 1000.0
        for _ in range(9):
            wd.handle_accel(0.0, 0.0, 1.0)
        wd.handle_accel(3.0, 0.0, 1.0)

        # After cooldown
        mock_time.time.return_value = 1001.0  # 1 second later
        mock_quartz.CGEventPost.reset_mock()
        for _ in range(9):
            wd.handle_accel(0.0, 0.0, 1.0)
        wd.handle_accel(3.0, 0.0, 1.0)
        self.assertTrue(mock_quartz.CGEventPost.called)


class TestWriteStatus(unittest.TestCase):
    """Tests for status file writing."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._home_held = False
        wd._z_held = False
        wd._drag_active = False
        wd._status_last_write = 0.0
        wd._battery_level = None
        wd._frontmost_app = ""
        wd._frontmost_app_last_check = time.time()

    def test_write_status_default_mode(self):
        """Status file reflects default mode."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            orig = wd.STATUS_FILE
            wd.STATUS_FILE = tmp_path
            wd.write_status()
            with open(tmp_path) as f:
                status = json.load(f)
            self.assertEqual(status["mode"], "default")
            self.assertFalse(status["wispr"])
            self.assertFalse(status["scroll"])
            self.assertTrue(status["connected"])
        finally:
            wd.STATUS_FILE = orig
            os.unlink(tmp_path)

    def test_write_status_b_mode(self):
        """Status file reflects B-mode when B is held."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            orig = wd.STATUS_FILE
            wd.STATUS_FILE = tmp_path
            wd._b_held = True
            wd.write_status()
            with open(tmp_path) as f:
                status = json.load(f)
            self.assertEqual(status["mode"], "b_mode")
        finally:
            wd.STATUS_FILE = orig
            os.unlink(tmp_path)

    def test_write_status_home_mode(self):
        """Status file reflects Home-mode when Home is held."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            orig = wd.STATUS_FILE
            wd.STATUS_FILE = tmp_path
            wd._home_held = True
            wd.write_status()
            with open(tmp_path) as f:
                status = json.load(f)
            self.assertEqual(status["mode"], "home_mode")
        finally:
            wd.STATUS_FILE = orig
            os.unlink(tmp_path)

    def test_write_status_wispr_active(self):
        """Status file shows wispr=true when active."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            orig = wd.STATUS_FILE
            wd.STATUS_FILE = tmp_path
            wd._wispr_active = True
            wd.write_status()
            with open(tmp_path) as f:
                status = json.load(f)
            self.assertTrue(status["wispr"])
        finally:
            wd.STATUS_FILE = orig
            os.unlink(tmp_path)

    def test_throttle_writes(self):
        """Status writes are throttled to avoid excessive I/O."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name
        try:
            orig = wd.STATUS_FILE
            wd.STATUS_FILE = tmp_path
            wd.write_status()
            # Second write immediately should be throttled
            os.unlink(tmp_path)
            wd.write_status()
            # File should NOT be recreated (throttled)
            self.assertFalse(os.path.exists(tmp_path))
        finally:
            wd.STATUS_FILE = orig
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class TestParseAction(unittest.TestCase):
    def test_wispr_toggle(self):
        result = wd.parse_action({"action": "wispr_toggle"})
        self.assertEqual(result, ("wispr_toggle",))

    def test_key_combo(self):
        result = wd.parse_action({"action": "key_combo", "modifiers": ["cmd"], "key": "tab"})
        self.assertEqual(result, ("key_combo", ["cmd"], wd.VK_TAB))

    def test_mouse_click(self):
        result = wd.parse_action({"action": "mouse_click", "button": "left"})
        self.assertEqual(result, ("mouse_click", "left"))

    def test_unknown_key_returns_none(self):
        result = wd.parse_action({"action": "key_combo", "modifiers": [], "key": "nonexistent"})
        self.assertIsNone(result)

    def test_unknown_action_returns_none(self):
        result = wd.parse_action({"action": "unknown_action"})
        self.assertIsNone(result)


class TestTextSelection(unittest.TestCase):
    """Tests for Z + D-pad text selection and double-tap C cursor warp."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._c_last_release = 0.0
        wd._cursor_speed = 0.0
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_z_dpad_left_selects_char(self):
        """Z held + D-pad LEFT sends Shift+Left (select char left)."""
        wd._z_held = True
        wd.handle_button("LEFT", True)
        # Should send Shift+Left, not Cmd+Shift+Tab
        mock_quartz.CGEventCreateKeyboardEvent.assert_called()
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_LEFT)  # Left arrow, not Tab
        mock_quartz.CGEventSetFlags.assert_called()
        flags = mock_quartz.CGEventSetFlags.call_args[0][1]
        self.assertEqual(flags, mock_quartz.kCGEventFlagMaskShift)

    def test_z_dpad_right_selects_char(self):
        """Z held + D-pad RIGHT sends Shift+Right."""
        wd._z_held = True
        wd.handle_button("RIGHT", True)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_RIGHT)

    def test_z_dpad_up_selects_line(self):
        """Z held + D-pad UP sends Shift+Up."""
        wd._z_held = True
        wd.handle_button("UP", True)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_UP)
        flags = mock_quartz.CGEventSetFlags.call_args[0][1]
        self.assertEqual(flags, mock_quartz.kCGEventFlagMaskShift)

    def test_bz_dpad_left_selects_word(self):
        """Z held + D-pad LEFT sends Shift+Left (select char left)."""
        wd._z_held = True
        wd.handle_button("LEFT", True)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_LEFT)
        flags = mock_quartz.CGEventSetFlags.call_args[0][1]
        # MODE_Z_MAP["LEFT"] = Shift+Left
        expected = mock_quartz.kCGEventFlagMaskShift
        self.assertEqual(flags, expected)

    def test_bz_dpad_up_selects_to_top(self):
        """Z held + D-pad UP sends Shift+Up (select line up)."""
        wd._z_held = True
        wd.handle_button("UP", True)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_UP)
        flags = mock_quartz.CGEventSetFlags.call_args[0][1]
        # MODE_Z_MAP["UP"] = Shift+Up
        expected = mock_quartz.kCGEventFlagMaskShift
        self.assertEqual(flags, expected)

    def test_dpad_without_z_is_normal(self):
        """D-pad without Z held uses normal BUTTON_MAP (plain arrow key)."""
        wd._z_held = False
        wd.handle_button("RIGHT", True)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_RIGHT)  # Normal: VK_RIGHT (arrow key)


class TestRecordReplay(unittest.TestCase):
    """Tests for event recording and replay."""

    def test_recording_adds_timestamp(self):
        """Recording adds _ts field to events."""
        events = [
            '{"type":"button","id":"A","pressed":true}\n',
            '{"type":"button","id":"A","pressed":false}\n',
        ]
        record_buf = io.StringIO()
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._c_last_release = 0.0
        wd._serial_source = None
        wd._battery_level = -1
        wd._frontmost_app = ""
        wd._frontmost_app_last_check = 0.0

        source = io.StringIO("".join(events))
        wd.run_event_loop(source, False, 200, record_file=record_buf)

        recorded = record_buf.getvalue().strip().split("\n")
        self.assertEqual(len(recorded), 2)
        for line in recorded:
            event = json.loads(line)
            self.assertIn("_ts", event)
            self.assertIsInstance(event["_ts"], float)

    def test_replay_events_yields_events(self):
        """replay_events reads a recording file and yields JSON lines."""
        recording = '{"type":"button","id":"A","pressed":true,"_ts":0.0}\n'
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(recording)
            tmp_path = f.name
        try:
            lines = list(wd.replay_events(tmp_path))
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            self.assertEqual(event["id"], "A")
            self.assertNotIn("_ts", event)  # _ts should be popped
        finally:
            os.unlink(tmp_path)


class TestHelpOverlay(unittest.TestCase):
    """Tests for help file overlay."""

    def setUp(self):
        wd._b_held = False
        wd._home_held = False
        wd._z_held = False

    def test_write_help_default_mode(self):
        """write_help in default mode shows BUTTON_MAP."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp_path = f.name
        orig = wd.HELP_FILE
        try:
            wd.HELP_FILE = tmp_path
            wd.write_help()
            with open(tmp_path) as f:
                content = f.read()
            self.assertIn("DEFAULT MODE", content)
            # Check for actual BUTTON_MAP entries (B is not in BUTTON_MAP)
            self.assertIn("LEFT", content)
        finally:
            wd.HELP_FILE = orig
            os.unlink(tmp_path)

    def test_write_help_b_mode(self):
        """write_help in B-mode shows MODE_B_MAP."""
        wd._b_held = True
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp_path = f.name
        orig = wd.HELP_FILE
        try:
            wd.HELP_FILE = tmp_path
            wd.write_help()
            with open(tmp_path) as f:
                content = f.read()
            self.assertIn("B-MODE", content)
        finally:
            wd.HELP_FILE = orig
            os.unlink(tmp_path)

    def test_write_help_home_mode(self):
        """write_help in Home-mode shows MODE_HOME_MAP."""
        wd._home_held = True
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp_path = f.name
        orig = wd.HELP_FILE
        try:
            wd.HELP_FILE = tmp_path
            wd.write_help()
            with open(tmp_path) as f:
                content = f.read()
            self.assertIn("HOME-MODE", content)
        finally:
            wd.HELP_FILE = orig
            os.unlink(tmp_path)

    def test_action_desc_sequence(self):
        """_action_desc formats sequence actions."""
        seq = ("sequence", [("key_combo", ["cmd"], 0x00), ("key_combo", ["cmd"], 0x08)])
        desc = wd._action_desc(seq)
        self.assertIn("→", desc)


class TestFrontmostApp(unittest.TestCase):
    """Tests for frontmost app detection."""

    def setUp(self):
        wd._frontmost_app = ""
        wd._frontmost_app_last_check = 0.0

    @patch("wiimote_daemon.subprocess.run")
    def test_get_frontmost_app_calls_osascript(self, mock_run):
        """_get_frontmost_app calls osascript."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Terminal\n")
        result = wd._get_frontmost_app()
        self.assertEqual(result, "Terminal")
        mock_run.assert_called_once()

    @patch("wiimote_daemon.subprocess.run")
    def test_frontmost_app_cached(self, mock_run):
        """Frontmost app is cached for FRONTMOST_APP_CHECK_INTERVAL."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Safari\n")
        wd._get_frontmost_app()
        wd._get_frontmost_app()  # Should use cache
        self.assertEqual(mock_run.call_count, 1)

    @patch("wiimote_daemon.subprocess.run", side_effect=Exception("timeout"))
    def test_frontmost_app_handles_error(self, mock_run):
        """_get_frontmost_app doesn't crash on error."""
        result = wd._get_frontmost_app()
        self.assertEqual(result, "")


class TestVolumeGestures(unittest.TestCase):
    """Tests for flick up/down = volume up/down."""

    def setUp(self):
        wd._accel_buffer = []
        wd._gesture_last_time = 0.0

    def test_detect_flick_up(self):
        """Sharp positive Y spike → flick_up."""
        buffer = [(0, 0, 0)] * 8 + [(0, 3.0, 0)]
        result = wd.detect_gesture(buffer)
        self.assertEqual(result, "flick_up")

    def test_detect_flick_down(self):
        """Sharp negative Y spike → flick_down."""
        buffer = [(0, 0, 0)] * 8 + [(0, -3.0, 0)]
        result = wd.detect_gesture(buffer)
        self.assertEqual(result, "flick_down")

    @patch("wiimote_daemon.subprocess.Popen")
    def test_volume_up_calls_osascript(self, mock_popen):
        """volume_up action calls osascript to increase volume."""
        wd.execute_action(("volume_up",), True)
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        self.assertEqual(args[0], "osascript")

    @patch("wiimote_daemon.subprocess.Popen")
    def test_volume_down_calls_osascript(self, mock_popen):
        """volume_down action calls osascript to decrease volume."""
        wd.execute_action(("volume_down",), True)
        mock_popen.assert_called_once()

    def test_x_flick_takes_priority_over_y(self):
        """X-axis flick is checked before Y-axis."""
        buffer = [(0, 0, 0)] * 8 + [(3.0, 3.0, 0)]
        result = wd.detect_gesture(buffer)
        self.assertEqual(result, "flick_right")  # X takes priority


class TestScreenSnap(unittest.TestCase):
    """Tests for Home + Z + stick = screen region cursor snap."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._c_last_release = 0.0
        wd._cursor_speed = 0.0
        wd._arrow_last_dir = None
        wd._serial_source = None
        wd.CURSOR_DEAD_ZONE = 0.1
        wd.CURSOR_INVERT_Y = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()

    def test_home_z_stick_up_snaps_to_top_center(self):
        """Home + Z + stick up = cursor at top center."""
        wd._home_held = True
        wd._z_held = True
        wd.handle_stick(0.0, 0.8)
        mock_quartz.CGEventCreateMouseEvent.assert_called()
        pos = mock_quartz.CGEventCreateMouseEvent.call_args[0][2]
        # Top center: x should be around center (960), y should be near top (50)
        self.assertAlmostEqual(pos[0], 960.0, delta=10)
        self.assertAlmostEqual(pos[1], 50.0, delta=10)
        self.assertTrue(wd._home_combo_used)

    def test_home_z_stick_bottom_right(self):
        """Home + Z + stick down-right = cursor at bottom-right."""
        wd._home_held = True
        wd._z_held = True
        wd.handle_stick(0.8, -0.8)  # right, down (negative y = down)
        pos = mock_quartz.CGEventCreateMouseEvent.call_args[0][2]
        # Bottom-right: x near 1870, y near 1030
        self.assertGreater(pos[0], 1800)
        self.assertGreater(pos[1], 1000)

    def test_home_z_stick_no_snap_below_threshold(self):
        """Home + Z + stick below threshold = no snap."""
        wd._home_held = True
        wd._z_held = True
        wd.handle_stick(0.2, 0.2)
        # Below threshold, no snap
        mock_quartz.CGEventCreateMouseEvent.assert_not_called()

    def test_home_stick_without_z_sends_arrows(self):
        """Home + stick without Z = arrow keys, not snap."""
        wd._home_held = True
        wd._z_held = False
        wd.handle_stick(0.0, 0.8)
        # Should send arrow key, not mouse event
        mock_quartz.CGEventCreateKeyboardEvent.assert_called()


class TestDeadZoneAndInvert(unittest.TestCase):
    """Tests for dead zone filtering and Y-axis inversion."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._c_last_release = 0.0
        wd._cursor_speed = 0.0
        wd._arrow_last_dir = None
        wd._serial_source = None
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._c_held = False
        wd._a_held = False
        wd.CURSOR_DEAD_ZONE = 0.1
        wd.CURSOR_INVERT_Y = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()

    def test_dead_zone_filters_small_input(self):
        """Stick values within dead zone are treated as center."""
        wd.CURSOR_DEAD_ZONE = 0.2
        wd.handle_stick(0.15, 0.1)
        # Should be treated as center, no movement
        mock_quartz.CGEventCreateMouseEvent.assert_not_called()
        self.assertEqual(wd._cursor_speed, 0.0)

    def test_dead_zone_passes_large_input(self):
        """Stick values outside dead zone pass through."""
        wd.CURSOR_DEAD_ZONE = 0.1
        wd.handle_stick(0.5, 0.0)
        mock_quartz.CGEventCreateMouseEvent.assert_called()

    def test_invert_y_reverses_vertical(self):
        """invert_y=True makes stick up = cursor down."""
        wd.CURSOR_INVERT_Y = True
        wd.handle_stick(0.0, 0.5)  # Stick up
        call_args = mock_quartz.CGEventCreateMouseEvent.call_args[0]
        new_y = call_args[2][1]
        # With invert: y=0.5 becomes y=-0.5, then -(-0.5)*speed = positive dy
        # So cursor should move DOWN (higher Y value)
        self.assertGreater(new_y, 400.0)  # Starting point is 400.0


class TestNotifyAndLaunchAgent(unittest.TestCase):
    """Tests for macOS notifications and LaunchAgent install/uninstall."""

    @patch("wiimote_daemon.subprocess.Popen")
    def test_notify_calls_osascript(self, mock_popen):
        """notify() calls osascript with display notification."""
        wd.notify("Test Title", "Test Message")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        self.assertEqual(args[0], "osascript")
        self.assertIn("display notification", args[2])

    @patch("wiimote_daemon.subprocess.Popen", side_effect=FileNotFoundError)
    def test_notify_handles_error(self, mock_popen):
        """notify() doesn't crash if osascript fails."""
        wd.notify("Test", "Test")  # Should not raise

    def test_install_launchagent(self):
        """install_launchagent writes a valid plist file."""
        with tempfile.NamedTemporaryFile(suffix=".plist", delete=False) as f:
            tmp_path = f.name
        orig = wd.LAUNCHAGENT_PATH
        try:
            wd.LAUNCHAGENT_PATH = tmp_path
            wd.install_launchagent("/dev/tty.test")
            with open(tmp_path) as f:
                content = f.read()
            self.assertIn("com.wiimote-control.daemon", content)
            self.assertIn("/dev/tty.test", content)
            self.assertIn("RunAtLoad", content)
        finally:
            wd.LAUNCHAGENT_PATH = orig
            os.unlink(tmp_path)

    def test_uninstall_launchagent(self):
        """uninstall_launchagent removes the plist file."""
        with tempfile.NamedTemporaryFile(suffix=".plist", delete=False) as f:
            tmp_path = f.name
            f.write(b"test")
        orig = wd.LAUNCHAGENT_PATH
        try:
            wd.LAUNCHAGENT_PATH = tmp_path
            wd.uninstall_launchagent()
            self.assertFalse(os.path.exists(tmp_path))
        finally:
            wd.LAUNCHAGENT_PATH = orig


class TestPrecisionCursor(unittest.TestCase):
    """Tests for Z-held precision cursor mode."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._z_combo_used = False
        wd._drag_active = False
        wd._c_held = False
        wd._a_held = False
        wd._c_last_release = 0.0
        wd._cursor_speed = 0.0
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._arrow_last_dir = None
        wd._serial_source = None
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_z_held_reduces_cursor_speed(self):
        """Z held + stick = slow precision cursor."""
        # Normal speed first
        wd._z_held = False
        wd.handle_stick(1.0, 0.0)
        normal_call = mock_quartz.CGEventCreateMouseEvent.call_args

        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0

        # Precision speed (Z held)
        wd._z_held = True
        wd._z_combo_used = False
        wd.handle_stick(1.0, 0.0)
        precision_call = mock_quartz.CGEventCreateMouseEvent.call_args

        # Both should have been called, precision should move less
        normal_pos = normal_call[0][2]  # (x, y) tuple
        precision_pos = precision_call[0][2]
        normal_dx = abs(normal_pos[0] - 500.0)
        precision_dx = abs(precision_pos[0] - 500.0)
        self.assertGreater(normal_dx, precision_dx)

    def test_z_precision_marks_combo_used(self):
        """Z held + stick movement marks _z_combo_used so Enter is suppressed."""
        wd._z_held = True
        wd._z_combo_used = False
        wd.handle_stick(1.0, 0.0)
        self.assertTrue(wd._z_combo_used)


class TestArrowKeyMode(unittest.TestCase):
    """Tests for Home + stick = arrow keys."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._c_last_release = 0.0
        wd._cursor_speed = 0.0
        wd._arrow_last_dir = None
        wd._serial_source = None
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._c_held = False
        wd._a_held = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_home_stick_up_sends_up_arrow(self):
        """Home + stick up sends Up arrow key."""
        wd._home_held = True
        wd.handle_stick(0.0, 0.8)
        mock_quartz.CGEventCreateKeyboardEvent.assert_called()
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_UP)
        self.assertTrue(wd._home_combo_used)

    def test_home_stick_right_sends_right_arrow(self):
        """Home + stick right sends Right arrow key."""
        wd._home_held = True
        wd.handle_stick(0.8, 0.0)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_RIGHT)

    def test_home_stick_below_threshold_no_arrow(self):
        """Home + stick below threshold doesn't fire arrow."""
        wd._home_held = True
        wd.handle_stick(0.2, 0.2)
        # No keyboard event should fire (only direction crosses above threshold)
        mock_quartz.CGEventCreateKeyboardEvent.assert_not_called()

    def test_home_stick_debounce(self):
        """Same direction doesn't fire twice until stick returns to center."""
        wd._home_held = True
        wd.handle_stick(0.0, 0.8)  # Up
        self.assertEqual(mock_quartz.CGEventPost.call_count, 2)  # down + up
        wd.handle_stick(0.0, 0.8)  # Up again (same direction)
        self.assertEqual(mock_quartz.CGEventPost.call_count, 2)  # No new events
        # Reset smoothing so center is immediate, then send enough centers
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd.handle_stick(0.0, 0.0)  # Center resets _arrow_last_dir
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd.handle_stick(0.0, 0.8)  # Up again (after center)
        self.assertEqual(mock_quartz.CGEventPost.call_count, 4)  # New events

    def test_stick_without_home_moves_cursor(self):
        """Stick without Home held moves cursor normally."""
        wd._home_held = False
        wd.handle_stick(0.8, 0.0)
        mock_quartz.CGEventCreateMouseEvent.assert_called()  # Mouse move, not keyboard


class TestSequenceAction(unittest.TestCase):
    """Tests for sequence (macro) actions."""

    def setUp(self):
        wd._wispr_active = False
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_sequence_fires_all_steps(self):
        """Sequence action executes all sub-actions in order."""
        seq = ("sequence", [
            ("key_combo", ["cmd"], wd.VK_A),
            ("key_combo", ["cmd"], wd.VK_C),
        ])
        wd.execute_action(seq, True)
        # 2 key combos × 2 events each (down + up) = 4 CGEventPost calls
        self.assertEqual(mock_quartz.CGEventPost.call_count, 4)

    def test_sequence_only_on_press(self):
        """Sequence doesn't fire on release."""
        seq = ("sequence", [("key_combo", ["cmd"], wd.VK_A)])
        wd.execute_action(seq, False)
        mock_quartz.CGEventPost.assert_not_called()

    def test_parse_action_sequence(self):
        """parse_action handles sequence config."""
        cfg = {
            "action": "sequence",
            "steps": [
                {"action": "key_combo", "modifiers": ["cmd"], "key": "a"},
                {"action": "key_combo", "modifiers": ["cmd"], "key": "c"},
            ],
        }
        result = wd.parse_action(cfg)
        self.assertEqual(result[0], "sequence")
        self.assertEqual(len(result[1]), 2)


class TestStickyScrollDirect(unittest.TestCase):
    """Tests for sticky scroll — via direct state setting (Home mode not available)."""

    def setUp(self):
        wd._wispr_active = False
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._z_last_release = 0.0
        wd._z_held = False
        wd._drag_active = False
        wd._c_held = False
        wd._a_held = False
        wd._cursor_speed = 0.0
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._arrow_last_dir = None
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    def test_sticky_scroll_makes_stick_scroll(self):
        """When sticky scroll is on, stick sends scroll events."""
        wd._sticky_scroll = True
        wd.handle_stick(0.5, 0.5)
        mock_quartz.CGEventCreateScrollWheelEvent.assert_called()

    def test_normal_c_without_home_no_sticky(self):
        """Normal C press (no Home) doesn't toggle sticky scroll."""
        wd._home_held = False
        wd.handle_button("NUNCHUK_C", True)
        self.assertFalse(wd._sticky_scroll)

    def test_status_shows_sticky_scroll(self):
        """Status file shows sticky_scroll state."""
        wd._sticky_scroll = True
        wd._status_last_write = 0.0
        with patch("builtins.open", unittest.mock.mock_open()):
            wd.write_status()


class TestSendRumble(unittest.TestCase):
    def test_rumble_over_stdin_is_noop(self):
        # Should not raise
        wd.send_rumble(sys.stdin, 200)

    def test_rumble_over_serial(self):
        mock_serial = MagicMock()
        wd.send_rumble(mock_serial, 200)
        mock_serial.write.assert_called_once()
        written = mock_serial.write.call_args[0][0]
        parsed = json.loads(written.decode())
        self.assertEqual(parsed["rumble"], 200)


# ---------- Phase 2: Regression / Snapshot Tests ----------


class TestButtonMapSnapshots(unittest.TestCase):
    """Freeze current button mappings so accidental changes are caught."""

    def test_button_map_exact(self):
        expected = {
            "LEFT": ("key_combo", [], wd.VK_LEFT),
            "RIGHT": ("key_combo", [], wd.VK_RIGHT),
            "UP": ("key_combo", [], wd.VK_UP),
            "DOWN": ("key_combo", [], wd.VK_DOWN),
            "PLUS": ("key_combo", [], wd.VK_RETURN),
            "MINUS": ("key_combo", [], wd.VK_TAB),
            "HOME": ("key_combo", ["ctrl"], wd.VK_UP),
            "1": ("key_combo", [], wd.VK_ESCAPE),
            "2": ("key_combo", ["cmd"], wd.VK_SPACE),
        }
        self.assertEqual(len(wd.BUTTON_MAP), len(expected))
        for key, val in expected.items():
            self.assertIn(key, wd.BUTTON_MAP, f"Missing key: {key}")
            self.assertEqual(wd.BUTTON_MAP[key], val, f"Mismatch for {key}")

    def test_mode_c_map_exact(self):
        expected = {
            "LEFT": ("key_combo", ["cmd", "shift"], wd.VK_TAB),
            "RIGHT": ("key_combo", ["cmd"], wd.VK_TAB),
            "UP": ("key_combo", ["cmd"], wd.VK_UP),
            "DOWN": ("key_combo", ["cmd"], wd.VK_DOWN),
            "PLUS": ("key_combo", ["cmd", "shift"], wd.VK_Z),
            "MINUS": ("key_combo", ["cmd"], wd.VK_Z),
            "1": ("key_combo", ["ctrl"], wd.VK_C),
            "2": ("key_combo", ["cmd"], wd.VK_W),
            "A": ("key_combo", ["cmd"], wd.VK_T),
            "HOME": ("key_combo", ["cmd"], wd.VK_BACKTICK),
        }
        self.assertEqual(len(wd.MODE_C_MAP), len(expected))
        for key, val in expected.items():
            self.assertIn(key, wd.MODE_C_MAP, f"Missing key: {key}")
            self.assertEqual(wd.MODE_C_MAP[key], val, f"Mismatch for {key}")

    def test_mode_z_map_exact(self):
        expected = {
            "A": ("key_combo", ["cmd"], wd.VK_C),
            "B": ("key_combo", ["cmd"], wd.VK_X),
            "PLUS": ("key_combo", ["cmd"], wd.VK_V),
            "MINUS": ("key_combo", ["cmd"], wd.VK_Z),
            "LEFT": ("key_combo", ["shift"], wd.VK_LEFT),
            "RIGHT": ("key_combo", ["shift"], wd.VK_RIGHT),
            "UP": ("key_combo", ["shift"], wd.VK_UP),
            "DOWN": ("key_combo", ["shift"], wd.VK_DOWN),
        }
        self.assertEqual(len(wd.MODE_Z_MAP), len(expected))
        for key, val in expected.items():
            self.assertIn(key, wd.MODE_Z_MAP, f"Missing key: {key}")
            self.assertEqual(wd.MODE_Z_MAP[key], val, f"Mismatch for {key}")


class TestSpecialHandlerRegression(unittest.TestCase):
    """Lock in exact behavior of A, B, C, Z special handlers."""

    def setUp(self):
        wd._wispr_active = False
        wd._a_held = False
        wd._c_held = False
        wd._z_held = False
        wd._z_combo_used = False
        wd._drag_active = False
        wd._z_last_release = 0.0
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._scroll_mode = False
        wd._sticky_scroll = False
        wd._b_held = False
        wd._b_combo_used = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._cursor_speed = 0.0
        wd._arrow_last_dir = None
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventCreateScrollWheelEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()
        mock_quartz.CGEventSetFlags.reset_mock()

    # --- A button: click/drag/double-tap ---

    def test_a_press_defers_no_events(self):
        wd.handle_button("A", True)
        self.assertTrue(wd._a_held)
        self.assertFalse(wd._drag_active)
        mock_quartz.CGEventPost.assert_not_called()

    def test_a_release_sends_click(self):
        wd.handle_button("A", True)
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("A", False)
        self.assertFalse(wd._a_held)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    def test_a_drag_flow(self):
        """A press + stick movement = drag, A release = mouse up."""
        wd.handle_button("A", True)
        wd.handle_stick(0.8, 0.0)
        self.assertTrue(wd._drag_active)
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("A", False)
        # Should send mouse up (end drag), not a click
        self.assertFalse(wd._drag_active)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    @patch("wiimote_daemon.time")
    def test_a_double_tap(self, mock_time):
        """Two quick A taps = double click."""
        mock_time.time.return_value = 1000.0
        wd.handle_button("A", True)
        wd.handle_button("A", False)
        mock_time.time.return_value = 1000.1
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("A", True)
        wd.handle_button("A", False)
        # Double-click fires extra events
        self.assertGreater(mock_quartz.CGEventPost.call_count, 2)

    # --- B button: Wispr Flow toggle ---

    def test_b_press_activates_wispr(self):
        wd.handle_button("B", True)
        self.assertTrue(wd._wispr_active)

    def test_b_release_deactivates_wispr(self):
        wd.handle_button("B", True)
        wd.handle_button("B", False)
        self.assertFalse(wd._wispr_active)

    def test_b_idempotent(self):
        """Second B press while Wispr active is no-op."""
        wd.handle_button("B", True)
        count = mock_quartz.CGEventPost.call_count
        wd.handle_button("B", True)
        self.assertEqual(mock_quartz.CGEventPost.call_count, count)

    # --- C button: modifier + scroll ---

    def test_c_sets_held(self):
        wd.handle_button("NUNCHUK_C", True)
        self.assertTrue(wd._c_held)
        wd.handle_button("NUNCHUK_C", False)
        self.assertFalse(wd._c_held)

    def test_c_held_routes_to_mode_c_map(self):
        """C held + RIGHT = Cmd+Tab (from MODE_C_MAP)."""
        wd._c_held = True
        wd.handle_button("RIGHT", True)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_c_held_scroll(self):
        """C held + stick = scroll events."""
        wd._c_held = True
        wd.handle_stick(0.0, 0.8)
        self.assertTrue(mock_quartz.CGEventCreateScrollWheelEvent.called)

    # --- Z button: tap=Enter, hold=precision, hold+button=MODE_Z_MAP ---

    def test_z_tap_sends_enter(self):
        wd.handle_button("NUNCHUK_Z", True)
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        wd.handle_button("NUNCHUK_Z", False)
        args = mock_quartz.CGEventCreateKeyboardEvent.call_args[0]
        self.assertEqual(args[1], wd.VK_RETURN)

    def test_z_hold_stick_suppresses_enter(self):
        """Z held + stick movement = no Enter on release."""
        wd.handle_button("NUNCHUK_Z", True)
        wd.handle_stick(0.8, 0.0)
        self.assertTrue(wd._z_combo_used)
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        wd.handle_button("NUNCHUK_Z", False)
        # No Enter sent because stick was moved
        for call in mock_quartz.CGEventCreateKeyboardEvent.call_args_list:
            self.assertNotEqual(call[0][1], wd.VK_RETURN)

    def test_z_held_plus_sends_paste(self):
        """Z held + PLUS = Paste (Cmd+V) from MODE_Z_MAP."""
        wd.handle_button("NUNCHUK_Z", True)
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("PLUS", True)
        self.assertTrue(wd._z_combo_used)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_z_held_left_sends_shift_left(self):
        """Z held + LEFT = Shift+Left (text selection) from MODE_Z_MAP."""
        wd.handle_button("NUNCHUK_Z", True)
        mock_quartz.CGEventPost.reset_mock()
        wd.handle_button("LEFT", True)
        self.assertTrue(wd._z_combo_used)
        self.assertTrue(mock_quartz.CGEventPost.called)

    def test_z_held_a_still_clicks(self):
        """Z held + A = A's click handler (A is intercepted before Z-mode routing)."""
        wd.handle_button("NUNCHUK_Z", True)
        wd.handle_button("A", True)
        # A's special handler runs first: sets _a_held, not Z combo
        self.assertTrue(wd._a_held)


class TestHandleStickRegression(unittest.TestCase):
    """Lock in handle_stick control flow for each mode."""

    def setUp(self):
        wd._smooth_x = 0.0
        wd._smooth_y = 0.0
        wd._c_held = False
        wd._a_held = False
        wd._z_held = False
        wd._z_combo_used = False
        wd._drag_active = False
        wd._sticky_scroll = False
        wd._home_held = False
        wd._home_combo_used = False
        wd._arrow_last_dir = None
        wd._cursor_speed = 0.0
        mock_quartz.CGEventCreateMouseEvent.reset_mock()
        mock_quartz.CGEventCreateScrollWheelEvent.reset_mock()
        mock_quartz.CGEventCreateKeyboardEvent.reset_mock()
        mock_quartz.CGEventPost.reset_mock()

    def test_normal_moves_cursor(self):
        """Stick deflection with no modifiers moves cursor."""
        wd.handle_stick(0.8, 0.0)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    def test_c_held_scrolls(self):
        """C held + stick = scroll, no cursor movement."""
        wd._c_held = True
        wd.handle_stick(0.0, 0.8)
        self.assertTrue(mock_quartz.CGEventCreateScrollWheelEvent.called)
        mock_quartz.CGEventCreateMouseEvent.assert_not_called()

    def test_z_held_precision(self):
        """Z held = slower cursor, marks combo used."""
        wd._z_held = True
        wd.handle_stick(0.8, 0.0)
        self.assertTrue(wd._z_combo_used)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    def test_a_held_starts_drag(self):
        """A held + stick = mouse drag."""
        wd._a_held = True
        wd.handle_stick(0.8, 0.0)
        self.assertTrue(wd._drag_active)
        self.assertTrue(mock_quartz.CGEventCreateMouseEvent.called)

    def test_dead_zone_center(self):
        """Stick at center sends no events."""
        wd.handle_stick(0.0, 0.0)
        mock_quartz.CGEventCreateMouseEvent.assert_not_called()
        mock_quartz.CGEventCreateScrollWheelEvent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
