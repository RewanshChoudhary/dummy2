# Arduino Uno setup, wiring, calibration, and viva demo

Use one **Arduino Uno**. The project is configured for the Uno by default: it runs the controller, reads both sensors, and drives the servo offline. Wi-Fi/ThingSpeak telemetry is not available on the Uno; use an ESP32 target if telemetry is required.

## Parts

| Part | Quantity | Purpose |
|---|---:|---|
| Arduino Uno | 1 | Controller |
| Tipping-bucket rain gauge or push button | 1 | Rain-event and rainfall-volume input |
| Analogue turbidity sensor | 1 | Water-quality safety check |
| SG90 servo and diverter flap | 1 | Routes water to waste or storage |
| 5 V, 2 A regulated supply | 1 | Servo and sensor supply |
| 10 kΩ resistor | 1 | Rain-gauge pull-up if the gauge does not include one |
| Jumper wires | as needed | Sensor, button, servo, and common ground connections |

## Wiring

The current bench wiring connects only the servo signal (orange/yellow) to D9. Leave the red and brown/black servo wires disconnected; the servo will not move until a suitable supply and common ground are added.

| Connection | Arduino Uno pin | Notes |
|---|---:|---|
| Rain gauge/button, one terminal | D2 | Interrupt input; other terminal to GND. `INPUT_PULLUP` is enabled in code. |
| Turbidity analogue output | A0 | Uno's 0–5 V, 10-bit ADC input. Do not exceed 5 V. |
| Servo signal | D9 | Orange/yellow wire only; red and brown/black remain disconnected for now. |
| HC-SR04 trigger / echo | D7 / D8 | Trigger and echo for tank air-gap measurement. Connect VCC to 5 V and GND to common GND. |
| Alert LED | D10 | Active while the tank-full threshold is detected; use a 220 Ω resistor. |
| Red / green LEDs | D11 / D12 | Use a 220 Ω resistor in series with each LED. Red = diverting/alert; green = storage/ready. |
| Turbidity VCC/GND | 5 V/GND | Follow the sensor module datasheet. |

If the turbidity module's output can exceed 5 V, add suitable voltage protection or a divider before connecting it to A0.

## Arduino IDE installation and upload

1. Install Arduino IDE and select the built-in **Arduino Uno** board.
2. The sketch uses the built-in `Servo` library; no ESP32 library is required.
3. Open `firmware/first_flush_diverter/first_flush_diverter.ino`.
4. Select **Tools > Board > Arduino AVR Boards > Arduino Uno**, choose the serial port, and upload.
5. Open Serial Monitor at **115200 baud**. Initially leave `ENABLE_IOT` as `0`; the whole controller works offline.

## IoT dashboard limitation

The Arduino Uno has no built-in Wi-Fi, so the ThingSpeak telemetry code is disabled for this target. The controller and all sensor/actuator logic continue to work normally offline. To use ThingSpeak, switch `HARDWARE_TARGET` back to `TARGET_ESP32` and use the ESP32 wiring and setup instructions.

Never submit real Wi-Fi credentials or API keys to Git/repositories. Use a private copy of `config.h` for your credentials.

## Calibration and safety

1. Measure roof area and set `ROOF_AREA_M2`; verify the rain gauge's mm-per-tip value and set `RAIN_GAUGE_MM_PER_TIP`.
2. With clear water, measure the sensor's output voltage at the sensor output and put it in `TURBIDITY_CLEAN_VOLTAGE`. The default Uno configuration assumes the sensor output is connected directly to A0, so `TURBIDITY_DIVIDER_RATIO` remains `1.0`. If you add a voltage divider, update that ratio in `config.h`. Test at least two known muddy samples to determine `TURBIDITY_NTU_PER_VOLT`. Until this is done, present turbidity as a prototype safety signal—not certified drinking-water quality.
3. Confirm servo angles physically send water to **waste** at `SERVO_ANGLE_DIVERT` and **tank** at `SERVO_ANGLE_STORAGE`. Reverse the angles if needed.
4. Test with a button before plumbing. A reset/failure must leave the servo in DIVERT, protecting the tank.

## 6-minute demonstration script

1. Show the wiring and Serial Monitor. Reset the Uno: servo must move to diversion/waste.
2. Press the rain button once after a chosen dry period; Serial Monitor reports a new rain event.
3. Make further presses during the 5-minute measurement window. Slow, medium, and rapid presses demonstrate light, moderate, and heavy estimates. The trigger press is excluded from the rate estimate but included in total diverted volume.
4. At the calculated tick target, show the turbidity reading. Present clean water to send flow to the tank, then muddy water to show an extension.
5. Show the serial event summary and explain that every planned diversion is based on dry spell, rainfall intensity, and the quality fallback.

## Mark-oriented evidence to include

Include a photo of the assembled circuit, the wiring table above, a screenshot of serial output, the 44-test automated output, and the simulation plots in `results/`. State clearly that the controller's decision logic has desktop/firmware parity, but roof, rain-gauge and turbidity values require site calibration.
