# Adaptive First-Flush Diverter

## Faculty presentation guide

### One-line project summary

The **Adaptive First-Flush Diverter** is an intelligent rainwater-harvesting controller that automatically rejects the first, potentially contaminated runoff and sends water to storage only after the estimated first-flush volume has passed and the water-quality check is acceptable.

## Why this project matters

The first water flowing from a roof can carry dust, bird droppings, leaves, and other accumulated contaminants. A fixed-volume diverter treats every rainfall event in the same way, even though contamination depends on:

- how long the roof has been dry;
- how intensely it is raining; and
- whether the water is still cloudy after the initial diversion.

This prototype addresses those limitations by making the diversion decision from multiple real-time inputs instead of using a single fixed delay or fixed volume.

## What the system does

1. Tracks the dry period since the previous rain event.
2. Detects the beginning of rainfall from a tipping-bucket input or a temporary manual GPIO5-to-GND trigger.
3. Measures the initial rainfall intensity from the rate of rain tips.
4. Calculates an adaptive first-flush volume using dry-spell duration and rainfall intensity.
5. Keeps the diverter in the waste position until that calculated volume has passed.
6. Reads the turbidity sensor as a water-quality safety check.
7. Extends diversion when the water is still cloudy, up to a defined safety limit.
8. Moves the diverter toward storage when the water is sufficiently clear.
9. Monitors the storage tank with an HC-SR04 and lights the alert LED when the tank is nearly full.
10. Resets safely for the next rainfall event after a long tip-free interval.

## System architecture

```text
Rain tips ───────────────┐
                         │
Dry-spell timer ─────────┤
                         ├──> Adaptive decision logic ───> Servo diverter
Rainfall intensity ──────┤             │
                         │             ├──> Red/green status LEDs
Turbidity sensor ────────┘             └──> Serial monitoring

HC-SR04 tank-level sensor ───────────────> Alert LED + tank-full warning
```

The controller is implemented as a **finite-state machine**. This makes the operation easy to test, explain, and extend.

## Operating states

| State | What happens | Expected indication |
|---|---|---|
| Dry-spell tracking | Waits for the first rain tip and records the dry period | Green LED normally on |
| Intensity measuring | Counts additional rain tips for the configured measurement window | Red LED on; diverter remains at waste |
| Diverting | Waits until the calculated first-flush tip target is reached | Red LED on |
| Turbidity check | Reads the analogue turbidity sensor | Red LED on |
| Storage | Sends acceptable water toward the storage tank | Green LED on |

The GPIO9 alert LED is independent of the main state indication. It lights when the HC-SR04 detects an air gap of 10 cm or less, indicating that the tank is nearly full.

## How the adaptive decision is calculated

The controller first calculates a base volume:

```text
Base flush volume = roof area × base flush depth
```

For the current prototype configuration:

```text
Roof area       = 50 m²
Base flush depth = 1 mm
Base volume      = 50 litres
```

The base volume is then multiplied by a factor selected from the dry-spell and rainfall-intensity conditions. The current multiplier range is 0.70× to 1.55×.

The final volume is converted to rain-gauge tips:

```text
Litres per tip = roof area × rain-gauge resolution
Target tips    = calculated diversion volume ÷ litres per tip
```

The firmware uses **fuzzy interpolation** between neighbouring conditions. Therefore, a small change around a boundary does not cause an abrupt change in the diversion decision. This is more realistic than a rigid “if-else” controller.

### Current input bands

| Input | Prototype categories |
|---|---|
| Dry spell | Short: below 48 h; medium: 48 h to 30 days; long: above 30 days |
| Rainfall intensity | Light: below 2.5 mm/h; moderate: up to 7.6 mm/h; heavy: above 7.6 mm/h |
| Turbidity | Clean at or below 5 NTU; cloudy above 5 NTU |

If the turbidity reading remains above the threshold, the controller adds 10% diversion extensions, limited to three extensions. This gives the system a quality-based fallback after the prediction stage.

## Current hardware connections

| Component | ESP32-S3 connection | Function |
|---|---|---|
| Rain tip trigger | GPIO5 to GND momentarily | Simulates a rain-gauge tip; uses `INPUT_PULLUP` |
| Turbidity sensor output | GPIO4 / ADC1 through 10 kΩ / 10 kΩ divider | Analogue water-quality reading |
| HC-SR04 trigger | GPIO7 | Starts tank-distance measurement |
| HC-SR04 echo | GPIO8 through 5 V-to-3.3 V divider | Receives tank-distance measurement |
| SG90 signal | GPIO6 | Servo control signal |
| Alert LED | GPIO9 through 220 Ω | Tank-full warning; replaces the buzzer |
| Red LED | GPIO10 through 220 Ω | Diverting, turbidity-check, or warning status |
| Green LED | GPIO18 through 220 Ω | Dry-spell tracking or storage status |
| Sensor power | 5 V and GND rails | Shared electrical reference |

### Important current prototype limitation

The SG90 orange/yellow signal wire connects to GPIO6. The servo must be powered from a separate regulated 5 V supply, with its brown/black ground connected to ESP32-S3 GND. The HC-SR04 echo also requires a resistor divider because ESP32-S3 GPIOs are 3.3 V logic.

## What makes the project impressive

### 1. It is adaptive rather than fixed

The system does not discard the same amount of water for every storm. It changes the target according to environmental history and rainfall behaviour.

### 2. It combines prediction with feedback

The dry-spell and intensity inputs predict how much runoff should be diverted. The turbidity sensor then checks the result and can extend diversion if the prediction is not sufficient.

### 3. It uses a structured control architecture

The finite-state machine separates detection, measurement, diversion, verification, and storage. This makes the behaviour traceable and reduces unsafe transitions.

### 4. It contains fail-safe behaviour

At startup and after an event, the diverter defaults away from the storage tank. If the system resets during uncertain conditions, potentially contaminated water is not immediately sent to the tank.

### 5. It is designed for calibration and expansion

Roof area, rain-gauge resolution, turbidity calibration, servo angles, and thresholds are kept in `config.h`. The same architecture can later accept a real tipping-bucket gauge, data logging, or enabled ESP32-S3 Wi-Fi telemetry.

## Suggested faculty demonstration

### Before the demonstration

1. Upload the firmware to the ESP32-S3 DevKitC-compatible board.
2. Open the Serial Monitor at **115200 baud**.
3. Confirm that the green LED is on after reset.
4. Power the servo from the external regulated 5 V supply and connect its ground to ESP32-S3 GND.
5. Use a jumper to touch GPIO5 to GND briefly whenever a rain tip is required.

### Demonstration sequence

1. **Introduce the problem:** explain roof contamination and why a fixed first-flush volume is unreliable.
2. **Show the sensor inputs:** point out the GPIO5 rain trigger, GPIO4 turbidity input, and GPIO7/GPIO8 tank-level sensor.
3. **Start a rain event:** touch GPIO5 to GND. The Serial Monitor reports the stored dry-spell duration.
4. **Explain intensity measurement:** produce slow or rapid GPIO5 triggers to represent light or heavy rainfall.
5. **Explain the adaptive calculation:** show the calculated intensity, multiplier, target volume, and target tips in the Serial Monitor.
6. **Show the diversion state:** the red LED indicates that the first flush is still being rejected.
7. **Show quality feedback:** present a clean or simulated clean analogue value at GPIO4 through its divider. The controller changes to storage after the target is reached.
8. **Show tank protection:** place an object within approximately 10 cm of the HC-SR04. The red LED and GPIO9 alert LED turn on.
9. **Conclude with the key message:** the system uses prediction first and sensor feedback second, which is the central idea of adaptive automation.

## A concise presentation script

> “This project is an adaptive first-flush diverter for rainwater harvesting. Instead of rejecting a fixed amount of water during every rainfall event, it estimates the required diversion using the roof’s dry period and the initial rainfall intensity. It then verifies the water using a turbidity sensor. If the water is still cloudy, the diversion is extended automatically. An ultrasonic sensor independently monitors the storage tank, while LEDs provide local status and warning indications. The controller is implemented as a finite-state machine with a fail-safe diversion default, making the system suitable as a prototype for intelligent and sustainable water management.”

## Likely faculty questions and strong answers

### Why is the first flush important?

The first runoff washes accumulated contaminants from the roof and collection surface. Diverting it improves the quality of water entering the storage tank.

### Why not use only the turbidity sensor?

Turbidity is a reactive measurement. The dry-spell and intensity inputs allow the system to reject a likely contaminated volume before relying on the sensor. The turbidity check then acts as a safety fallback.

### Why use fuzzy logic?

Rainfall and contamination do not change in perfect categories. Fuzzy interpolation avoids abrupt decisions when a measurement is close to a category boundary.

### Why use a state machine?

It gives every stage a defined purpose and transition. This makes the control logic easier to test, explain, debug, and protect against unsafe actuator behaviour.

### Is the turbidity value certified water quality?

No. In this prototype it is a calibrated safety indicator. A field-ready system would require sensor calibration against known samples and validation for the intended water use.

### What would be improved next?

The next practical improvements are a powered servo with an external regulated supply, a real tipping-bucket gauge, an RTC for long-term dry-spell tracking, data logging, enclosure and weather protection, and field calibration using actual roof runoff.

## Honest project conclusion

This prototype demonstrates the complete decision-making concept: **sense → estimate → divert → verify → store**. Its main contribution is the integration of environmental history, rainfall behaviour, water-quality feedback, and tank-level protection into one explainable embedded-control system.

