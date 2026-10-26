# Adaptive First-Flush Diverter — ESP32-S3 Guide

This project is a small automatic rainwater first-flush diverter. It sends the first, potentially dirty part of a rain event to waste and moves the flap to the storage tank after the calculated amount has passed.

For a faculty-ready explanation, demonstration script, and viva questions, see [FACULTY_PRESENTATION.md](FACULTY_PRESENTATION.md).

The ESP32-S3 version is the active build. It works offline by default and uses:

- an ESP32-S3 controller with native USB serial,
- a tipping-bucket rain gauge or pushbutton to represent rainfall,
- an analogue turbidity sensor to check water quality,
- an SG90 servo to move the diverter flap,
- an HC-SR04 to warn when the storage tank is nearly full,
- three LEDs for local status.

DHT11 and FC-37 are not available and are intentionally not used. Their example code is commented out in the sketch. No DHT11 or FC-37 library is needed.

The controller can also be demonstrated without water. A pushbutton simulates rain, a cardboard flap demonstrates the servo movement, and fixed 5 V/GND connections can simulate clean or dirty turbidity readings. A potentiometer is not required.

## 1. How to present the project

For a classroom demonstration, you do not need a complete rooftop plumbing system. Build a small tabletop water path:

1. Use a plastic funnel, bottle, or short pipe as the rainwater inlet.
2. Put a simple flap, PVC Y-junction, or two-outlet model below it as the diverter.
3. Label one outlet **WASTE / FIRST FLUSH** and the other **STORAGE TANK**.
4. Attach the SG90 servo horn to the flap.
5. Place a cup under each outlet to collect diverted and stored water.
6. Use a pushbutton on GPIO5 instead of a rain gauge if the real gauge is not available. Each press represents one rain-gauge tip.
7. If water is unavailable, leave the turbidity sensor disconnected and use the fixed GPIO4 test described below.
8. Put an empty bottle or small tank under the storage outlet. Mount the HC-SR04 above it and move an object within 10 cm to demonstrate the tank-full alarm.

The external objects needed for a convincing presentation are therefore:

| External object | Why it is used |
|---|---|
| Breadboard and jumper wires | Temporary electrical assembly |
| Plastic funnel, pipe, Y-junction, or cardboard flap | Small physical diverter model |
| Two cups or bottles | Waste and storage collection |
| Pushbutton or tipping-bucket rain gauge | Generates rain tips |
| Optional turbidity test wires | Simulates clean or dirty readings without water or a potentiometer |
| SG90 servo and horn | Moves the flap |
| Empty bottle/container | Demonstrates tank-level sensing |
| USB cable | Programs and powers the ESP32-S3 logic board |
| Regulated 5 V supply, preferably 1–2 A | Powers the servo and sensors |

No water pump is required. Pour water manually through the model for a safe tabletop demonstration. Keep the electronics above the water containers and wipe up spills immediately.

## 2. Parts currently used

| Part | Quantity | Status | Function |
|---|---:|---|---|
| ESP32-S3 DevKitC-compatible board | 1 | Required | Main controller |
| Tipping-bucket rain gauge or pushbutton | 1 | Required | Rain event, intensity, and volume input |
| Analogue turbidity sensor | 1 | Required | Checks whether diverted water is still cloudy |
| SG90 servo and flap | 1 | Required | Selects waste or storage outlet |
| HC-SR04 ultrasonic sensor | 1 | Auxiliary | Measures tank air gap and detects nearly full tank |
| Alert LED | 1 | Auxiliary | Replaces the buzzer for a tank-full warning |
| Red LED | 1 | Auxiliary | Diverting or alarm status |
| Green LED | 1 | Auxiliary | Storage/ready status |
| 220 Ω resistor | 3 | Required for LEDs | Limits LED current |
| Breadboard and jumper wires | as needed | Required | Connections |
| Regulated 5 V supply | 1 | Strongly recommended | Servo and sensor power |

Not used in the current build:

- **DHT11:** no temperature/humidity measurement is performed.
- **FC-37:** no separate rain-drop detection is performed; the tipping gauge or pushbutton starts the event.
- **Wi-Fi/ThingSpeak:** disabled by default; the ESP32-S3 can provide telemetry after credentials are configured.

## 3. ESP32-S3 pin map

These pins are already defined in `firmware/first_flush_diverter/config.h`.

| Component connection | ESP32-S3 GPIO | Connection |
|---|---:|---|
| Rain gauge or pushbutton signal | GPIO5 | Other terminal to GND; internal pull-up is enabled |
| Turbidity analogue output | GPIO4 / ADC1 | Connect through the divider described below |
| Servo signal | GPIO6 | Servo orange/yellow signal wire |
| HC-SR04 trigger | GPIO7 | `TRIG` |
| HC-SR04 echo | GPIO8 | `ECHO` through a 5 V-to-3.3 V divider |
| Alert LED anode through 220 Ω | GPIO9 | Tank-full warning LED |
| Red LED anode through 220 Ω | GPIO10 | Red status LED |
| Green LED anode through 220 Ω | GPIO18 | Green status LED |
| All sensor/actuator grounds | GND | One common ground is essential |

### Component power connections

- ESP32-S3: power/program by USB. Use a separate regulated 5 V supply for the servo.
- HC-SR04: `VCC` to 5 V, `GND` to GND. Its `ECHO` must not connect directly to an ESP32-S3 GPIO.
- Turbidity sensor: `VCC` and `GND` according to its module label. Use a 10 kΩ / 10 kΩ divider from `OUT` to GPIO4.
- Servo: orange/yellow signal wire to GPIO6; red to the external 5 V supply and brown/black to common GND.
- LEDs: long leg/anode goes to its ESP32-S3 GPIO through 220 Ω; short leg/cathode goes to GND.
- GPIO9 alert LED: connect GPIO9 through 220 Ω to the long leg; connect the short leg to GND. This LED replaces the buzzer and produces no sound.

Do not connect a sensor output above 3.3 V directly to an ESP32-S3 GPIO. The equal-value turbidity divider makes the configured 0–5 V sensor range approximately 0–2.5 V at GPIO4. Use a voltage divider or logic-level shifter on the HC-SR04 `ECHO` line; a 10 kΩ upper resistor and 20 kΩ lower resistor produces about 3.3 V from a 5 V echo.

## 4. Wiring procedure for a beginner

Switch off USB and the external supply before wiring.

1. Place the ESP32-S3 and breadboard on a dry table.
2. Connect ESP32-S3 GND to the breadboard's ground rail.
3. Connect the HC-SR04: `VCC → 5 V`, `GND → GND`, `TRIG → GPIO7`, and `ECHO → GPIO8` through a level-shifting divider.
4. Connect the turbidity sensor: `VCC` and `GND` according to its module label, then connect `OUT → 10 kΩ → GPIO4`, with another 10 kΩ from GPIO4 to GND.
5. Connect the rain pushbutton between GPIO5 and GND. Do not add an external pull-up; the sketch uses `INPUT_PULLUP`.
6. Connect the servo orange/yellow signal wire to GPIO6. Power the servo from the external 5 V supply and connect its ground to ESP32-S3 GND.
7. Connect the alert LED from GPIO9 through 220 Ω to GND.
8. Connect the red LED from GPIO10 through 220 Ω to GND.
9. Connect the green LED from GPIO18 through 220 Ω to GND.
10. Check every ground connection, then connect USB and the external 5 V supply.

The ESP32-S3 GPIOs are 3.3 V logic. Never connect the 5 V HC-SR04 `ECHO` directly; use a divider such as 10 kΩ from `ECHO` to GPIO8 and 20 kΩ from GPIO8 to GND.

## 5. Install and upload the firmware

1. Install the Arduino IDE and the Espressif ESP32 board package.
2. Open `firmware/first_flush_diverter/first_flush_diverter.ino`.
3. Keep all files in the same sketch folder:
   - `first_flush_diverter.ino`
   - `config.h`
   - `diverter_logic.h` and `diverter_logic.cpp`
   - `fuzzy_controller.h` and `fuzzy_controller.cpp`
4. Select **Tools → Board → ESP32 Arduino → ESP32S3 Dev Module** (or the exact ESP32-S3 board variant).
5. Select the correct USB port under **Tools → Port**.
6. Click **Verify** first, then **Upload**.
7. Open **Tools → Serial Monitor** and select **115200 baud**.

Install the `ESP32Servo` library for the ESP32-S3 firmware. Do not install DHT11 or FC-37 libraries for this build. If using native USB, select the board's USB CDC serial option and keep GPIO19/GPIO20 free.

For ThingSpeak credentials, copy [`.env.example`](.env.example) to [`.env`](.env), fill in the Wi-Fi and API-key values, and copy them into the matching macros in `firmware/first_flush_diverter/config.h`. The Arduino firmware cannot read a dotenv file directly. Set `ENABLE_IOT` to `1` only after the values are configured.

If the IDE reports that a file is missing, confirm that the `.h` and `.cpp` files are beside the `.ino` file, not only in the repository's parent folder.

## 6. What the firmware does

The controller has five states:

1. **Dry-spell tracking:** waits for the first rain tip and measures time since the previous event.
2. **Intensity measuring:** the first five minutes after the first tip estimate rainfall intensity. The servo stays at WASTE.
3. **Diverting:** fuzzy logic calculates the first-flush volume from dry-spell duration and intensity. Further rain tips count toward that target.
4. **Turbidity check:** after the target volume, the sensor is read. Cloudy water extends diversion by 10%, up to three times.
5. **Storage:** when water is sufficiently clean, the servo moves to the STORAGE outlet.

The auxiliary outputs work independently:

- Red LED: intensity measurement, diverting, turbidity checking, or tank-full warning.
- Green LED: dry-spell tracking or storage, when the tank is not full.
- GPIO9 alert LED: lights when the HC-SR04 measures an air gap of 10 cm or less.
- HC-SR04: sampled every five seconds; it warns but does not automatically change the servo route.

## 7. First power-on test

Test the electronics before adding water.

1. Upload the sketch and open Serial Monitor at 115200 baud.
2. Reset the ESP32-S3. You should see a ready message.
3. The servo should move to the DIVERT/WASTE position. Adjust the mechanical linkage if necessary.
4. The green LED should normally be on during dry-spell tracking.
5. Put an object less than 10 cm from the HC-SR04. Within about five seconds, the GPIO9 alert LED and red LED should turn on. No sound is produced because the buzzer has been replaced by an LED.
6. Move the object away. The tank-full alert should clear at the next level sample.
7. Press the rain button once. The Serial Monitor should report that a rain event started and the red LED should turn on.

If the servo moves in the wrong direction, change these values in `config.h`:

```cpp
#define SERVO_ANGLE_DIVERT    0
#define SERVO_ANGLE_STORAGE   90
```

Use only the angles that are mechanically safe for your flap.

## 8. Dry-run turbidity test without water or a potentiometer

If you do not have water or a potentiometer, temporarily simulate the turbidity sensor with a jumper wire. Disconnect the turbidity sensor's `OUT` wire from the GPIO4 divider first.

For the clean-water simulation, connect the sensor-side input of the divider to 5 V:

```text
5 V → 10 kΩ → GPIO4 → 10 kΩ → GND
```

For the dirty-water simulation:

```text
GND → sensor-side input of the divider
```

Power off the ESP32-S3 before changing between these two connections. A 5 V signal through the documented divider produces a clean reading; the divider input connected to GND produces a high turbidity reading. Run the demonstration twice to show both outcomes.

Never connect the divider input to 5 V and GND at the same time. Do not leave the turbidity sensor's output connected while forcing the divider input to 5 V or GND. Do not operate a normal turbidity probe dry; use this fixed-voltage method only for a dry electronics demonstration.

## 9. Short classroom demonstration

The normal firmware uses a five-minute intensity window and a 30-minute rain-end gap. That is suitable for the intended control logic but long for a short presentation. For a temporary bench demonstration, you may change these values in `config.h`:

```cpp
#define INTENSITY_WINDOW_MS (60UL * 1000UL)  // temporary 1-minute demo
#define RAIN_END_GAP_MS     (60UL * 1000UL)  // temporary 1-minute demo
```

Restore the original values before treating the system as a real installation.

Demonstration sequence:

1. Show the physical flap, the WASTE and STORAGE labels, the two collection cups, and the ESP32-S3 wiring.
2. Reset the ESP32-S3 and explain that the fail-safe position is WASTE.
3. Leave the system waiting for a short period, then press the rain button once. Explain that this starts the event and records the dry spell.
4. Press the button slowly, moderately, or quickly during the measurement window. Explain that the press rate represents light, moderate, or heavy rain.
5. After the measurement window, read the Serial Monitor. It reports intensity, target litres, target tips, and the fuzzy multiplier.
6. Continue pressing the button until the target is reached. The controller then reads turbidity.
7. For a dry demonstration, connect the divider input to 5 V to simulate clean water and repeat the target-volume test. Then power off, connect it to GND, and repeat it to simulate dirty water and an extended diversion.
8. Move an object close to the HC-SR04 to demonstrate the independent tank-full GPIO9 alert LED and red LED warning.
9. Explain that DHT11 and FC-37 are not part of this demonstration because they are unavailable.

The first button press starts the event but is excluded from the intensity-rate calculation. It is still retained for diversion-volume counting.

## 10. Calibration before real use

Edit `firmware/first_flush_diverter/config.h` for the actual installation:

```cpp
#define ROOF_AREA_M2          50.0f  // actual catchment area
#define RAIN_GAUGE_MM_PER_TIP 0.2f   // gauge specification
```

For the turbidity sensor:

1. Measure the clean-water output voltage at the sensor output.
2. Set `TURBIDITY_CLEAN_VOLTAGE` to that voltage.
3. Test known clean and muddy samples and estimate `TURBIDITY_NTU_PER_VOLT`.
4. Keep `TURBIDITY_DIVIDER_RATIO` at `0.5` for the documented ESP32-S3 10 kΩ / 10 kΩ divider. Change it only if a different divider is installed.
5. Treat this as a prototype safety signal, not certified drinking-water testing.

The servo angles, rain-gauge resolution, roof area, and turbidity values must be verified at the installation site.

## 11. Common problems

| Problem | Likely cause | Fix |
|---|---|---|
| ESP32-S3 resets when servo moves | Servo draws too much current or grounds are separate | Use the external 5 V supply and connect its GND to ESP32-S3 GND |
| Servo does not move | Servo power is disconnected or grounds are separate | Power the servo from an external 5 V supply and connect its ground to ESP32-S3 GND |
| No rain event starts | Button is not connected to GND or is on the wrong pin | Connect the button between GPIO5 and GND |
| Turbidity always reads zero or an extreme value | Wrong divider, sensor voltage, or calibration | Check the 10 kΩ / 10 kΩ divider at GPIO4 and calibrate the two turbidity constants |
| HC-SR04 alarm never changes | TRIG/ECHO reversed, no level shifting, or no common ground | Check GPIO7, GPIO8, the echo divider, VCC, GND, and the five-second sample interval |
| LEDs do not light | LED polarity or missing resistor | Long legs through 220 Ω to GPIO9/GPIO10/GPIO18; short legs to GND |
| Alert LED is off | Wrong polarity or tank is not within threshold | Check LED polarity/resistor and test with an object within 10 cm of the HC-SR04 |
| IDE cannot find a header file | Files are not beside the `.ino` file | Put all firmware files in the same sketch folder |

## 12. Run the desktop simulations and tests

From the `simulation` directory:

```bash
python3 -m unittest test_diverter_logic test_fuzzy_controller test_ml_baseline
python3 parity_check.py
python3 run_scenarios.py --controller fuzzy
python3 run_comparison.py --outdir ../results --quick
```

The parity check compiles the controller C++ files with `g++` and compares them with the Python implementation. It does not require an Arduino connected.

## 13. Project structure

| Path | Purpose |
|---|---|
| `firmware/first_flush_diverter/first_flush_diverter.ino` | Arduino state machine and hardware I/O |
| `firmware/first_flush_diverter/config.h` | ESP32-S3 pins, calibration, thresholds, and controller settings |
| `firmware/first_flush_diverter/diverter_logic.*` | Core banded diversion calculations |
| `firmware/first_flush_diverter/fuzzy_controller.*` | Fuzzy controller implementation |
| `simulation/` | Python models, tests, scenarios, and parity check |
| `results/` | Generated comparison tables and plots |
| `docs/SETUP_AND_DEMO.md` | Additional setup and calibration notes |

## 14. Project limitations

- The ESP32-S3 build is offline by default; set `ENABLE_IOT` to `1` only after adding private Wi-Fi and ThingSpeak credentials.
- DHT11 and FC-37 are not installed or active.
- The HC-SR04 only gives a local tank-full warning; it does not stop the inlet or move the servo automatically.
- A button simulates rain tips but does not measure real rainfall.
- `millis()` is used for dry-spell timing; long-term installations should use an RTC and field-tested calibration.
- The system is a prototype and does not certify water as safe to drink.
