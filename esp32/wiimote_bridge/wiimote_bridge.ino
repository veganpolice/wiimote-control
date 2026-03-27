/*
 * Wiimote Bridge — ESP32 firmware
 *
 * Pairs with a Nintendo Wiimote via Bluetooth Classic, reads button/nunchuk/accelerometer
 * data, and sends JSON lines over USB serial to the Mac daemon (wiimote_daemon.py).
 *
 * Also reads commands from serial (e.g., rumble) and sends them back to the Wiimote.
 *
 * Hardware: Freenove ESP32-WROVER (or any ESP32 with Bluetooth Classic)
 * Library:  ESP32Wiimote (install via Arduino Library Manager)
 *
 * Serial protocol (115200 baud):
 *   ESP32 → Mac:  {"type":"button","id":"A","pressed":true}
 *   Mac → ESP32:  {"rumble":200}
 */

#include <ESP32Wiimote.h>
#include <ArduinoJson.h>

ESP32Wiimote wiimote;

// Track previous button state to send only changes (press/release events)
ButtonState prev_buttons = ButtonState::None;

// Nunchuk previous state
int prev_stick_x = 128;
int prev_stick_y = 128;

// Deadzone for nunchuk stick (0-255 range, center is ~128)
const int STICK_DEADZONE = 15;
// Only send stick updates every N ms to avoid flooding serial
const unsigned long STICK_INTERVAL_MS = 16;  // ~60fps for smooth cursor
unsigned long last_stick_send = 0;

// Accelerometer sending rate (lower than buttons/stick to avoid flooding)
const unsigned long ACCEL_INTERVAL_MS = 100;  // 10Hz
unsigned long last_accel_send = 0;

// Battery reporting (every 30 seconds)
const unsigned long BATTERY_INTERVAL_MS = 30000;
unsigned long last_battery_send = 0;

void send_button(const char* id, bool pressed) {
    Serial.print("{\"type\":\"button\",\"id\":\"");
    Serial.print(id);
    Serial.print("\",\"pressed\":");
    Serial.print(pressed ? "true" : "false");
    Serial.println("}");
}

void send_stick(float x, float y) {
    Serial.print("{\"type\":\"stick\",\"x\":");
    Serial.print(x, 2);
    Serial.print(",\"y\":");
    Serial.print(y, 2);
    Serial.println("}");
}

void send_accel(float x, float y, float z) {
    Serial.print("{\"type\":\"accel\",\"x\":");
    Serial.print(x, 2);
    Serial.print(",\"y\":");
    Serial.print(y, 2);
    Serial.print(",\"z\":");
    Serial.print(z, 2);
    Serial.println("}");
}

void check_button_state(ButtonState current, ButtonState prev, ButtonState mask, const char* id) {
    bool was_pressed = buttonStateHas(prev, mask);
    bool is_pressed = buttonStateHas(current, mask);
    if (is_pressed != was_pressed) {
        send_button(id, is_pressed);
    }
}

// Rumble via Wiimote output report 0x11 (LED + Rumble)
// Byte 0 of payload: bit 0 = rumble, bits 4-7 = LED mask
void set_rumble(bool on) {
    uint8_t data = on ? 0x01 : 0x00;
    // Output report 0x11 sets LEDs and rumble
    // Write to register space 0x04 (output report)
    // For simplicity, just use LED report with rumble bit
    // The Wiimote output report for LEDs+rumble is sent via HCI
    // ESP32Wiimote doesn't expose rumble directly, so we skip it for now
}

void check_serial_commands() {
    if (Serial.available()) {
        String line = Serial.readStringUntil('\n');
        line.trim();
        if (line.length() == 0) return;

        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, line);
        if (err) return;

        if (doc.containsKey("rumble")) {
            // Rumble not directly supported by this library version
            // TODO: implement via writeMemory when API is confirmed
        }
    }
}

float normalize_stick(int raw) {
    // Convert 0-255 range to -1.0 to 1.0, with deadzone
    float centered = (raw - 128.0f) / 128.0f;
    if (abs(centered) < (float)STICK_DEADZONE / 128.0f) {
        return 0.0f;
    }
    return centered;
}

bool reporting_mode_set = false;
bool was_connected = false;

// Re-send reporting mode periodically to recover from nunchuk flakiness
const unsigned long REPORTING_MODE_INTERVAL_MS = 5000;
unsigned long last_reporting_mode_send = 0;

void setup() {
    Serial.begin(115200);
    Serial.println("{\"type\":\"status\",\"msg\":\"Wiimote bridge starting...\"}");

    wiimote.init();

    Serial.println("{\"type\":\"status\",\"msg\":\"Waiting for Wiimote. Press 1+2 on Wiimote to pair.\"}");
}

void loop() {
    wiimote.task();

    bool connected = wiimote.isConnected();

    // Detect reconnection — reset state so reporting mode gets re-sent
    if (connected && !was_connected) {
        reporting_mode_set = false;
        prev_buttons = ButtonState::None;
        prev_stick_x = 128;
        prev_stick_y = 128;
        Serial.println("{\"type\":\"status\",\"msg\":\"Wiimote connected.\"}");
    }
    if (!connected && was_connected) {
        reporting_mode_set = false;
        Serial.println("{\"type\":\"status\",\"msg\":\"Wiimote disconnected.\"}");
    }
    was_connected = connected;

    // Set reporting mode after connection, and re-send periodically
    // to recover from nunchuk extension resets
    if (connected) {
        unsigned long now_rm = millis();
        if (!reporting_mode_set || (now_rm - last_reporting_mode_send >= REPORTING_MODE_INTERVAL_MS)) {
            wiimote.setReportingMode(ReportingMode::CoreButtonsAccelExt, true);
            if (!reporting_mode_set) {
                Serial.println("{\"type\":\"status\",\"msg\":\"Nunchuk+accel mode enabled.\"}");
            }
            reporting_mode_set = true;
            last_reporting_mode_send = now_rm;
        }
    }

    if (wiimote.available() > 0) {
        // --- Buttons (includes nunchuk C and Z) ---
        ButtonState buttons = wiimote.getButtonState();

        if (static_cast<uint32_t>(buttons) != static_cast<uint32_t>(prev_buttons)) {
            check_button_state(buttons, prev_buttons, kButtonA, "A");
            check_button_state(buttons, prev_buttons, kButtonB, "B");
            check_button_state(buttons, prev_buttons, kButtonOne, "1");
            check_button_state(buttons, prev_buttons, kButtonTwo, "2");
            check_button_state(buttons, prev_buttons, kButtonPlus, "PLUS");
            check_button_state(buttons, prev_buttons, kButtonMinus, "MINUS");
            check_button_state(buttons, prev_buttons, kButtonHome, "HOME");
            check_button_state(buttons, prev_buttons, kButtonUp, "UP");
            check_button_state(buttons, prev_buttons, kButtonDown, "DOWN");
            check_button_state(buttons, prev_buttons, kButtonLeft, "LEFT");
            check_button_state(buttons, prev_buttons, kButtonRight, "RIGHT");
            // Nunchuk buttons are part of ButtonState in this library
            check_button_state(buttons, prev_buttons, kButtonC, "NUNCHUK_C");
            check_button_state(buttons, prev_buttons, kButtonZ, "NUNCHUK_Z");
            prev_buttons = buttons;
        }

        // --- Nunchuk stick (throttled) ---
        NunchukState nunchuk = wiimote.getNunchukState();
        unsigned long now = millis();
        if (now - last_stick_send >= STICK_INTERVAL_MS) {
            float nx = normalize_stick(nunchuk.xStick);
            float ny = normalize_stick(nunchuk.yStick);
            float px = normalize_stick(prev_stick_x);
            float py = normalize_stick(prev_stick_y);

            if (nx != px || ny != py) {
                send_stick(nx, ny);
                prev_stick_x = nunchuk.xStick;
                prev_stick_y = nunchuk.yStick;
                last_stick_send = now;
            }
        }

        // --- Accelerometer (from Wiimote, throttled at 10Hz) ---
        if (now - last_accel_send >= ACCEL_INTERVAL_MS) {
            // Wiimote accelerometer: raw 0-255 (uint8_t), center ~128
            AccelState accel = wiimote.getAccelState();
            float ax = (accel.xAxis - 128.0f) / 50.0f;
            float ay = (accel.yAxis - 128.0f) / 50.0f;
            float az = (accel.zAxis - 128.0f) / 50.0f;
            send_accel(ax, ay, az);
            last_accel_send = now;
        }

        // --- Battery level (throttled, every 30s) ---
        if (now - last_battery_send >= BATTERY_INTERVAL_MS) {
            uint8_t battery = wiimote.getBatteryLevel();
            Serial.print("{\"type\":\"battery\",\"level\":");
            Serial.print(battery);
            Serial.println("}");
            last_battery_send = now;
        }
    }

    // Check for commands from Mac (rumble, etc.)
    check_serial_commands();

    delay(10);  // 100Hz polling — matches daemon's read rate
}
