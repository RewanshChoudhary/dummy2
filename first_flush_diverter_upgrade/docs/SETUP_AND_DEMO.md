# ESP32-S3 setup, wiring, calibration, and viva demo

Use an **ESP32-S3 DevKitC-compatible board**. The firmware is configured for the ESP32-S3 by default and uses native USB serial, an interrupt-driven rain input, a calibrated ADC turbidity reading, a servo, an HC-SR04 tank-level warning, and three status LEDs. Wi-Fi/ThingSpeak telemetry remains disabled until credentials are added.

## Parts

| Part | Quantity | Purpose |
|---|---:|---|
| ESP32-S3 DevKitC-compatible board | 1 | Controller |
| Tipping-bucket rain gauge or push button | 1 | Rain-event and rainfall-volume input |
| Analogue turbidity sensor | 1 | Water-quality safety check |
| SG90 servo and diverter flap | 1 | Routes water to waste or storage |
| HC-SR04 ultrasonic sensor | 1 | Tank air-gap measurement |
| 5 V, 2 A regulated supply | 1 | Servo and 5 V sensor supply |
| 10 kΩ resistors | 3 | Turbidity divider and HC-SR04 echo divider |
| 20 kΩ resistor | 1 | HC-SR04 echo divider |
| 220 Ω resistors | 3 | LED current limiting |
| Jumper wires and breadboard | as needed | Connections |

## Wiring

The active pins are defined in `firmware/first_flush_diverter/config.h`:

| Connection | ESP32-S3 GPIO | Notes |
|---|---:|---|
| Rain gauge/button, one terminal | GPIO5 | Other terminal to GND; `INPUT_PULLUP` is enabled |
| Turbidity sensor output | GPIO4 / ADC1 | Use the 10 kΩ / 10 kΩ divider below |
| Servo signal | GPIO6 | Orange/yellow wire; power servo from external 5 V |
| HC-SR04 trigger / echo | GPIO7 / GPIO8 | Echo must use the 5 V-to-3.3 V divider |
| Alert LED | GPIO9 | Use a 220 Ω resistor |
| Red / green LEDs | GPIO10 / GPIO18 | Use a 220 Ω resistor for each |

All grounds must be common. Connect the HC-SR04 `VCC` to 5 V, but never connect its 5 V `ECHO` directly to the ESP32-S3. Use 10 kΩ from `ECHO` to GPIO8 and 20 kΩ from GPIO8 to GND; this reduces the high level to approximately 3.3 V.

For the turbidity input, connect the sensor output through 10 kΩ to GPIO4 and connect another 10 kΩ from GPIO4 to GND. The firmware uses `TURBIDITY_DIVIDER_RATIO 0.5` and reads the S3 ADC with 11 dB attenuation and calibrated millivolts. Do not apply more than 3.3 V to any ESP32-S3 GPIO.

Power the board by USB while programming. Power the servo from a separate regulated 5 V supply and connect that supply's GND to ESP32-S3 GND. A reset or power failure leaves the servo command at the WASTE/DIVERT position after startup.

## Arduino IDE installation and upload

1. Install Arduino IDE and the Espressif ESP32 board package.
2. Install the `ESP32Servo` library from Library Manager.
3. Open `firmware/first_flush_diverter/first_flush_diverter.ino` and keep all companion `.h` and `.cpp` files in the same sketch folder.
4. Select **Tools > Board > ESP32 Arduino > ESP32S3 Dev Module** or the exact board variant.
5. Select the board's USB port and upload.
6. Open Serial Monitor at **115200 baud**. If native USB is used, enable USB CDC on boot in the board options and keep GPIO19/GPIO20 unused.

Keep credentials in the local [`.env`](../.env) file and never commit it. The Arduino firmware does not load dotenv files automatically, so copy the values into the matching macros in `firmware/first_flush_diverter/config.h`, then set `ENABLE_IOT` to `1` before uploading. Keep it at `0` for an offline demonstration.

## Calibration and safety

1. Measure the roof area and set `ROOF_AREA_M2`; verify the rain gauge's mm-per-tip value and set `RAIN_GAUGE_MM_PER_TIP`.
2. Measure the clean-water sensor output at the sensor side of the turbidity divider and set `TURBIDITY_CLEAN_VOLTAGE`. The default `4.125 V` is only a placeholder.
3. Test known clean and muddy samples and estimate `TURBIDITY_NTU_PER_VOLT`.
4. Keep `TURBIDITY_DIVIDER_RATIO` at `0.5` for the documented equal-value resistor divider. Change it if a different divider is installed.
5. Confirm the servo angles physically send water to **waste** at `SERVO_ANGLE_DIVERT` and **tank** at `SERVO_ANGLE_STORAGE`.
6. Treat turbidity as a prototype safety indicator, not certified drinking-water testing.

## 6-minute demonstration script

1. Show the diverter, collection cups, ESP32-S3, and the GPIO wiring.
2. Reset the board: the servo must move to diversion/waste and the green LED should be on.
3. Press the rain button on GPIO5 once after a chosen dry period; the Serial Monitor reports the event.
4. Make further slow, medium, or rapid presses during the intensity window to represent different rainfall rates.
5. At the calculated target, show a clean turbidity input. The servo changes to storage.
6. Repeat with the divider input connected to GND to simulate dirty water and demonstrate the extension logic.
7. Place an object within approximately 10 cm of the HC-SR04. The GPIO9 alert LED and red LED should turn on at the next level sample.

The normal firmware uses a five-minute intensity window and a 30-minute rain-end gap. For a temporary bench demonstration, these can be shortened in `config.h`; restore the original values afterward.

## Desktop verification

From the `simulation` directory:

```bash
python3 -m unittest test_diverter_logic test_fuzzy_controller test_ml_baseline
python3 parity_check.py
```

The desktop tests validate the controller calculations; they do not replace voltage, grounding, level-shifting, or servo safety checks on the physical ESP32-S3 setup.
