#ifndef CONFIG_H
#define CONFIG_H

// ---------------------------------------------------------------------
// Board and wiring. Default target: Arduino Uno.
// ---------------------------------------------------------------------
#define TARGET_ESP32 1
#define TARGET_ARDUINO_UNO 2
#define HARDWARE_TARGET TARGET_ARDUINO_UNO

#if HARDWARE_TARGET == TARGET_ESP32
  // GPIO34 is ADC-input-only; GPIO27 supports interrupts.
  #define PIN_RAIN_GAUGE_TIP 27
  #define PIN_TURBIDITY_SENSOR 34
  #define PIN_ACTUATOR 18
  #define PIN_TANK_LEVEL_TRIG 25
  #define PIN_TANK_LEVEL_ECHO 26
  #define PIN_ALERT_LED 19
  #define PIN_STATUS_RED 21
  #define PIN_STATUS_GREEN 22
  #define ADC_REFERENCE_VOLTS 3.3f
  #define ADC_MAX_READING 4095.0f
#elif HARDWARE_TARGET == TARGET_ARDUINO_UNO
  #define PIN_RAIN_GAUGE_TIP 2
  #define PIN_TURBIDITY_SENSOR A0
  #define PIN_ACTUATOR 9
  // Auxiliary hardware listed in README.md.
  #define PIN_TANK_LEVEL_TRIG 7
  #define PIN_TANK_LEVEL_ECHO 8
  #define PIN_ALERT_LED 10
  #define PIN_STATUS_RED 11
  #define PIN_STATUS_GREEN 12
  #define ADC_REFERENCE_VOLTS 5.0f
  #define ADC_MAX_READING 1023.0f
#else
  #error "Unsupported HARDWARE_TARGET"
#endif

// ---------------------------------------------------------------------
// Site calibration - MUST be re-checked per installation (Sec 6.2 / 8.4)
// ---------------------------------------------------------------------
#define ROOF_AREA_M2             50.0f   // catchment area feeding this diverter
#define RAIN_GAUGE_MM_PER_TIP    0.2f    // tipping-bucket resolution (mm per tip)
#define BASE_FLUSH_DEPTH_MM      1.0f    // first-flush depth diverted at 1.0x multiplier

// ---------------------------------------------------------------------
// Dry-spell / intensity band thresholds (Sections 5.1.1, 5.1.2)
// ---------------------------------------------------------------------
#define DRY_SPELL_SHORT_MAX_HOURS   48.0f          // < 2 days -> SHORT
#define DRY_SPELL_LONG_MIN_HOURS    (30.0f * 24.0f)  // > 30 days -> LONG

#define INTENSITY_LIGHT_MAX_MM_HR      2.5f
#define INTENSITY_MODERATE_MAX_MM_HR   7.6f

#define INTENSITY_WINDOW_MS (5UL * 60UL * 1000UL)
// The trigger tip is excluded from this window: it starts the event but is
// not an observation within the window. This permits light/moderate bands.

// How long a gap without a tip means "the rain event has ended" - used to
// reset the state machine and start tracking the next dry spell.
#define RAIN_END_GAP_MS   (30UL * 60UL * 1000UL)   // 30 minutes

// ---------------------------------------------------------------------
// Controller selection and fuzzy membership geometry (fuzzy_controller.*)
// ---------------------------------------------------------------------
// 1 = fuzzy logic controller (smooth blending between bands)
// 0 = original hard-banded lookup table (Section 5.1.3)
// Both use the same MULTIPLIER_TABLE, so switching never changes the
// nine rule values, only how inputs are blended between them.
#define USE_FUZZY_CONTROLLER   1

// Each band crossover (where two sets are both 0.5) sits exactly on the
// crisp thresholds above. The half-width is how far the blend extends on
// either side of it, e.g. 24 h around 48 h blends SHORT->MEDIUM over 24-72 h.
// Smaller = closer to the banded behaviour, larger = smoother.
#define FUZZY_DRY_SHORT_MEDIUM_HALF_WIDTH_H   24.0f
#define FUZZY_DRY_MEDIUM_LONG_HALF_WIDTH_H    240.0f
#define FUZZY_INT_LIGHT_MODERATE_HALF_WIDTH   1.0f
#define FUZZY_INT_MODERATE_HEAVY_HALF_WIDTH   1.1f

// ---------------------------------------------------------------------
// Turbidity safety fallback (Section 5.1.5)
// ---------------------------------------------------------------------
#define TURBIDITY_CLEAN_THRESHOLD_NTU   5.0f
#define TURBIDITY_EXTENSION_FRACTION    0.10f
#define TURBIDITY_MAX_EXTENSIONS        3

// Fraction of the sensor's output voltage that reaches the ADC pin.
// ESP32 build: 10k + 20k divider -> 20k / (10k + 20k) = 0.6667.
// Uno build: sensor wired straight to A0 -> 1.0.
// If you use different resistors, change this value to match.
#if HARDWARE_TARGET == TARGET_ESP32
  #define TURBIDITY_DIVIDER_RATIO       0.6667f
#else
  #define TURBIDITY_DIVIDER_RATIO       1.0f
#endif

// Calibrate these two values using docs/SETUP_AND_DEMO.md before trusting NTU.
// Both are in volts at the SENSOR OUTPUT (i.e. after the divider is undone in
// readTurbidityNtu()), not volts at the ADC pin.
// Defaults are placeholders: 4.125 V = clean water, 20 NTU per volt of drop.
#define TURBIDITY_CLEAN_VOLTAGE         4.125f
#define TURBIDITY_NTU_PER_VOLT          20.0f

// ---------------------------------------------------------------------
// Actuator positions
// ---------------------------------------------------------------------
#define SERVO_ANGLE_DIVERT    0     // flap routed to waste / diversion outlet
#define SERVO_ANGLE_STORAGE   90    // flap routed to storage tank outlet

// ---------------------------------------------------------------------
// Auxiliary tank-level and status outputs
// ---------------------------------------------------------------------
#define TANK_FULL_DISTANCE_CM       10.0f
#define TANK_LEVEL_SAMPLE_MS        5000UL

// DHT11 and FC-37 are intentionally not enabled because those parts are not
// currently available. Their future pin/library examples remain commented in
// first_flush_diverter.ino.

// ---------------------------------------------------------------------
// Debounce
// ---------------------------------------------------------------------
#define TIP_DEBOUNCE_MS   50UL

// ---------------------------------------------------------------------
// IoT: ThingSpeak HTTP telemetry (ESP32 only)
// Create fields: 1=state, 2=rain mm/hr, 3=dry spell h, 4=diverted L,
// 5=turbidity NTU, 6=Wi-Fi RSSI. Keep disabled until credentials are set.
// Never commit a real API key.
// ---------------------------------------------------------------------
#define ENABLE_IOT 0
#define WIFI_SSID "YOUR_WIFI_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define THINGSPEAK_WRITE_API_KEY "YOUR_THINGSPEAK_WRITE_KEY"
#define TELEMETRY_INTERVAL_MS 20000UL  // ThingSpeak minimum is 15 seconds

#endif  // CONFIG_H
