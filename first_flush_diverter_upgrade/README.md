# Adaptive First-Flush Diverter — Arduino Uno Guide

This project is a small automatic rainwater first-flush diverter. It sends the first, potentially dirty part of a rain event to waste and moves the flap to the storage tank after the calculated amount has passed.

For a faculty-ready explanation, demonstration script, and viva questions, see [FACULTY_PRESENTATION.md](FACULTY_PRESENTATION.md).

The Arduino Uno version is the active build. It works offline and uses:

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
6. Use a pushbutton on D2 instead of a rain gauge if the real gauge is not available. Each press represents one rain-gauge tip.
7. If water is unavailable, leave the turbidity sensor disconnected and use the fixed A0 test described below.
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
| USB cable | Programs and powers the Uno logic board |
| Regulated 5 V supply, preferably 1–2 A | Powers the servo and sensors |

No water pump is required. Pour water manually through the model for a safe tabletop demonstration. Keep the electronics above the water containers and wipe up spills immediately.

## 2. Parts currently used

| Part | Quantity | Status | Function |
|---|---:|---|---|
| Arduino Uno | 1 | Required | Main controller |
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
- **Wi-Fi/ThingSpeak:** the Uno has no built-in Wi-Fi.

## 3. Arduino Uno pin map

These pins are already defined in `firmware/first_flush_diverter/config.h`.

| Component connection | Uno pin | Connection |
|---|---:|---|
| Rain gauge or pushbutton signal | D2 | Other terminal to GND; internal pull-up is enabled |
| Servo signal | D9 | Servo orange/yellow signal wire |
| Turbidity analogue output | A0 | Sensor OUT |
| HC-SR04 trigger | D7 | `TRIG` |
| HC-SR04 echo | D8 | `ECHO` |
| Alert LED anode through 220 Ω | D10 | Tank-full warning LED |
| Red LED anode through 220 Ω | D11 | Red status LED |
| Green LED anode through 220 Ω | D12 | Green status LED |
| All sensor/actuator grounds | GND | One common ground is essential |

### Component power connections

- Uno: power by USB while programming and testing.
- HC-SR04: `VCC` to 5 V, `GND` to GND.
- Turbidity sensor: `VCC` and `GND` according to its module label; connect `OUT` to A0.
- Servo: orange/yellow signal wire to D9. Leave the red and brown/black wires disconnected for now; the servo will not move without power.
- LEDs: long leg/anode goes to the Uno pin through 220 Ω; short leg/cathode goes to GND.
- D10 alert LED: connect D10 through 220 Ω to the long leg; connect the short leg to GND. This LED replaces the buzzer and produces no sound.

Do not connect the servo's disconnected power wires until a suitable supply is available. Do not connect a sensor output above 5 V to an Uno input. If the turbidity module can output above 5 V, use a suitable divider or level-protection circuit.

## 4. Wiring procedure for a beginner

Switch off USB and the external supply before wiring.

1. Place the Uno and breadboard on a dry table.
2. Connect Uno GND to the breadboard's ground rail.
3. Connect the HC-SR04: `VCC → 5 V`, `GND → GND`, `TRIG → D7`, `ECHO → D8`.
4. Connect the turbidity sensor: `VCC → 5 V`, `GND → GND`, `OUT → A0`.
5. Connect the rain pushbutton between D2 and GND. Do not add an external pull-up; the sketch uses `INPUT_PULLUP`.
6. Connect the servo orange/yellow signal wire to D9. Leave the red and brown/black servo wires disconnected for now; the servo will not move without power.
7. Connect the D10 LED: D10 → 220 Ω resistor → LED long leg; LED short leg → GND.
8. Connect the red LED from D11 through 220 Ω to GND.
9. Connect the green LED from D12 through 220 Ω to GND.
10. Check every ground connection, then connect USB and the external 5 V supply.

The HC-SR04 echo is safe for the 5 V Arduino Uno. If this wiring is later moved to an ESP32, the echo signal must be reduced to 3.3 V with a divider.

## 5. Install and upload the firmware

1. Install the Arduino IDE.
2. Open `firmware/first_flush_diverter/first_flush_diverter.ino`.
3. Keep all files in the same sketch folder:
   - `first_flush_diverter.ino`
   - `config.h`
   - `diverter_logic.h` and `diverter_logic.cpp`
   - `fuzzy_controller.h` and `fuzzy_controller.cpp`
4. Select **Tools → Board → Arduino AVR Boards → Arduino Uno**.
5. Select the correct USB port under **Tools → Port**.
6. Click **Verify** first, then **Upload**.
7. Open **Tools → Serial Monitor** and select **115200 baud**.

The only library required by the Uno firmware is Arduino's built-in `Servo` library. Do not install DHT11 or FC-37 libraries for this build.

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
- D10 alert LED: lights when the HC-SR04 measures an air gap of 10 cm or less.
- HC-SR04: sampled every five seconds; it warns but does not automatically change the servo route.

## 7. First power-on test

Test the electronics before adding water.

1. Upload the sketch and open Serial Monitor at 115200 baud.
2. Reset the Uno. You should see a ready message.
3. The servo should move to the DIVERT/WASTE position. Adjust the mechanical linkage if necessary.
4. The green LED should normally be on during dry-spell tracking.
5. Put an object less than 10 cm from the HC-SR04. Within about five seconds, the D10 alert LED and red LED should turn on. No sound is produced because the buzzer has been replaced by an LED.
6. Move the object away. The tank-full alert should clear at the next level sample.
7. Press the rain button once. The Serial Monitor should report that a rain event started and the red LED should turn on.

If the servo moves in the wrong direction, change these values in `config.h`:

```cpp
#define SERVO_ANGLE_DIVERT    0
#define SERVO_ANGLE_STORAGE   90
```

Use only the angles that are mechanically safe for your flap.

## 8. Dry-run turbidity test without water or a potentiometer

If you do not have water or a potentiometer, temporarily simulate the turbidity sensor with a jumper wire. Disconnect the turbidity sensor's `OUT` wire from A0 first.

For the clean-water simulation:

```text
A0 → Uno 5 V
```

For the dirty-water simulation:

```text
A0 → Uno GND
```

Power off the Uno before changing between these two connections. A0 connected to 5 V produces a clean reading; A0 connected to GND produces a high turbidity reading. Run the demonstration twice to show both outcomes.

Never connect A0 to 5 V and GND at the same time. Do not leave the turbidity sensor's output connected while forcing A0 to 5 V or GND. Do not operate a normal turbidity probe dry; use this fixed-voltage method only for a dry electronics demonstration.

## 9. Short classroom demonstration

The normal firmware uses a five-minute intensity window and a 30-minute rain-end gap. That is suitable for the intended control logic but long for a short presentation. For a temporary bench demonstration, you may change these values in `config.h`:

```cpp
#define INTENSITY_WINDOW_MS (60UL * 1000UL)  // temporary 1-minute demo
#define RAIN_END_GAP_MS     (60UL * 1000UL)  // temporary 1-minute demo
```

Restore the original values before treating the system as a real installation.

Demonstration sequence:

1. Show the physical flap, the WASTE and STORAGE labels, the two collection cups, and the Uno wiring.
2. Reset the Uno and explain that the fail-safe position is WASTE.
3. Leave the system waiting for a short period, then press the rain button once. Explain that this starts the event and records the dry spell.
4. Press the button slowly, moderately, or quickly during the measurement window. Explain that the press rate represents light, moderate, or heavy rain.
5. After the measurement window, read the Serial Monitor. It reports intensity, target litres, target tips, and the fuzzy multiplier.
6. Continue pressing the button until the target is reached. The controller then reads turbidity.
7. For a dry demonstration, connect A0 to 5 V to simulate clean water and repeat the target-volume test. Then power off, connect A0 to GND, and repeat it to simulate dirty water and an extended diversion.
8. Move an object close to the HC-SR04 to demonstrate the independent tank-full D10 alert LED and red LED warning.
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
4. Keep `TURBIDITY_DIVIDER_RATIO` at `1.0` when the Uno reads the sensor directly. Change it only if a voltage divider is installed.
5. Treat this as a prototype safety signal, not certified drinking-water testing.

The servo angles, rain-gauge resolution, roof area, and turbidity values must be verified at the installation site.

## 11. Common problems

| Problem | Likely cause | Fix |
|---|---|---|
| Uno resets when servo moves | Servo draws too much current | Use the external 5 V supply and connect its GND to Uno GND |
| Servo does not move | Servo power is intentionally disconnected | This is expected with the current wiring; only D9 is connected |
| No rain event starts | Button is not connected to GND or is on the wrong pin | Connect the button between D2 and GND |
| Turbidity always reads zero or an extreme value | Wrong sensor voltage or calibration | Check OUT to A0 and calibrate the two turbidity constants |
| HC-SR04 alarm never changes | TRIG/ECHO reversed or no common ground | Check D7, D8, VCC, GND, and the five-second sample interval |
| LEDs do not light | LED polarity or missing resistor | Long leg through 220 Ω to D11/D12; short leg to GND |
| D10 alert LED is off | Wrong polarity or tank is not within threshold | Check LED polarity/resistor and test with an object within 10 cm of the HC-SR04 |
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
| `firmware/first_flush_diverter/config.h` | Uno pins, calibration, thresholds, and controller settings |
| `firmware/first_flush_diverter/diverter_logic.*` | Core banded diversion calculations |
| `firmware/first_flush_diverter/fuzzy_controller.*` | Fuzzy controller implementation |
| `simulation/` | Python models, tests, scenarios, and parity check |
| `results/` | Generated comparison tables and plots |
| `docs/SETUP_AND_DEMO.md` | Additional setup and calibration notes |

## 14. Project limitations

- The Uno build is offline; it has no built-in Wi-Fi.
- DHT11 and FC-37 are not installed or active.
- The HC-SR04 only gives a local tank-full warning; it does not stop the inlet or move the servo automatically.
- A button simulates rain tips but does not measure real rainfall.
- `millis()` is used for dry-spell timing; long-term installations should use an RTC and field-tested calibration.
- The system is a prototype and does not certify water as safe to drink.
