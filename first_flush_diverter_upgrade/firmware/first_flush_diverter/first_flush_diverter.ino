// first_flush_diverter.ino
//
// Adaptive First-Flush Diverter for Rainwater Harvesting - prototype
// firmware (report Section 6/7: Hardware Design & Implementation).
//
// Target: Arduino Uno by default; ESP32 remains available as an optional target.
// Libraries: ESP32 -> install "ESP32Servo" (Tools > Manage Libraries).
//            Arduino Uno -> built-in "Servo" library.
//
// This sketch is a state machine that implements the working principle
// from Section 4.3 end-to-end:
//   1. DRY_SPELL_TRACKING   - time since the last tick accumulates as the
//                             dry-spell duration (Section 5.1.1).
//   2. INTENSITY_MEASURING  - the first ~1-2 minutes of a new rain event
//                             are used to estimate initial intensity
//                             (Section 5.1.2). The actuator stays in the
//                             DIVERT position throughout, so no runoff is
//                             lost while intensity is being measured.
//   3. DIVERTING            - the calculated diversion volume (as a tick
//                             count, Section 5.1.4) is waited out.
//   4. TURBIDITY_CHECK      - optional safety fallback (Section 5.1.5):
//                             if the water is still cloudy, diversion is
//                             extended in fixed steps, capped at
//                             TURBIDITY_MAX_EXTENSIONS.
//   5. STORAGE              - actuator switched to the tank; the sketch
//                             waits for a long tick-free gap to conclude
//                             the rain event has ended, then resets.
//
// For a bench/viva demo (Section 7.2.1), rain-gauge ticks can be produced
// by manually pressing a button wired to PIN_RAIN_GAUGE_TIP at a chosen
// rate instead of an outdoor gauge - fast presses simulate heavy
// intensity, slow presses simulate light intensity, and simply waiting
// before the first press simulates a chosen dry-spell length.

#include "config.h"
#if HARDWARE_TARGET == TARGET_ESP32
  #include <ESP32Servo.h>
#else
  #include <Servo.h>
#endif
#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32
  #include <WiFi.h>
  #include <HTTPClient.h>
#endif

// DHT11 and FC-37 support is intentionally disabled: these parts are not
// available. Uncomment and implement these lines only after obtaining them.
// #include <DHT.h>
// #define PIN_DHT11 A1
// #define PIN_FC37 A2
// DHT dht(PIN_DHT11, DHT11);

#include "diverter_logic.h"
#include "fuzzy_controller.h"

// ---------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------
enum class SystemState {
  DRY_SPELL_TRACKING,
  INTENSITY_MEASURING,
  DIVERTING,
  TURBIDITY_CHECK,
  STORAGE,
};

static SystemState state = SystemState::DRY_SPELL_TRACKING;

// ---------------------------------------------------------------------
// Rain-gauge tip counting (ISR-driven)
// ---------------------------------------------------------------------
volatile unsigned long tipCount = 0;         // ticks since current event started
volatile unsigned long lastTipMillis = 0;     // for debounce and "rain ended" gap
volatile bool newTipSinceLoop = false;        // set by ISR, cleared by loop()

// ---------------------------------------------------------------------
// Event-scoped state
// ---------------------------------------------------------------------
unsigned long drySpellStartMillis = 0;     // reset at the end of each rain event
unsigned long eventStartMillis = 0;        // when the current rain event began
unsigned long intensityStartTipCount = 0;  // excludes the event-trigger tip
float pendingDrySpellHours = 0.0f;         // captured at event start, used once
                                            // the intensity window closes

DiversionPlan currentPlan;
unsigned long diversionTargetTicks = 0;
int turbidityExtensionsUsed = 0;
float lastIntensityMmPerHr = 0.0f;
float lastTurbidityNtu = -1.0f;
unsigned long lastTelemetryMillis = 0;
unsigned long lastTankLevelMillis = 0;
float lastTankDistanceCm = -1.0f;
bool tankFull = false;

Servo actuatorServo;

// ---------------------------------------------------------------------
// Forward declarations (helper functions defined below loop())
// ---------------------------------------------------------------------
void tipISR();
void setActuator(bool toStorage);
float readTurbidityNtu();
float readTankDistanceCm();
void updateAuxiliaryOutputs();
bool rainHasStopped();
unsigned long snapshotTipCount();
int stateCode();
void publishTelemetryIfDue();
#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32
void connectWiFi();
#endif

// ---------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_RAIN_GAUGE_TIP, INPUT_PULLUP);
  pinMode(PIN_TURBIDITY_SENSOR, INPUT);
  pinMode(PIN_TANK_LEVEL_TRIG, OUTPUT);
  pinMode(PIN_TANK_LEVEL_ECHO, INPUT);
  pinMode(PIN_ALERT_LED, OUTPUT);
  pinMode(PIN_STATUS_RED, OUTPUT);
  pinMode(PIN_STATUS_GREEN, OUTPUT);
  digitalWrite(PIN_TANK_LEVEL_TRIG, LOW);
  digitalWrite(PIN_STATUS_RED, LOW);
  digitalWrite(PIN_STATUS_GREEN, LOW);
  digitalWrite(PIN_ALERT_LED, LOW);
  // Take the first level reading immediately. Later readings use the normal
  // interval even if the HC-SR04 is disconnected and returns no echo.
  lastTankLevelMillis = millis() - TANK_LEVEL_SAMPLE_MS;

#if HARDWARE_TARGET == TARGET_ESP32
  // Match the 0-3.3 V ADC input range. A 5 V turbidity module MUST have
  // its analogue output divided down before it reaches GPIO34.
  analogSetPinAttenuation(PIN_TURBIDITY_SENSOR, ADC_11db);
#endif

  actuatorServo.attach(PIN_ACTUATOR);

  // Fail-safe default: hold the diverter open (away from the tank) until
  // a full predictive plan says otherwise - protects water quality if the
  // system resets mid-event.
  setActuator(false);

  attachInterrupt(digitalPinToInterrupt(PIN_RAIN_GAUGE_TIP), tipISR, FALLING);

  drySpellStartMillis = millis();
  state = SystemState::DRY_SPELL_TRACKING;

#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32
  connectWiFi();
#endif

  Serial.println(F("Adaptive First-Flush Diverter - ready. Tracking dry spell."));
}

// ---------------------------------------------------------------------
// Main loop (state machine)
// ---------------------------------------------------------------------
void loop() {
  publishTelemetryIfDue();
  updateAuxiliaryOutputs();
  switch (state) {

    case SystemState::DRY_SPELL_TRACKING: {
      if (newTipSinceLoop) {
        // NOTE: millis() is a 32-bit counter and overflows after ~49.7
        // days. A dry spell tracked purely on millis() cannot correctly
        // span longer than that - for a real deployment, back this with
        // an RTC module rather than millis() alone (Section 8.4 flags
        // that the timing/calibration assumptions need field hardening).
        unsigned long drySpellMs = millis() - drySpellStartMillis;
        pendingDrySpellHours = drySpellMs / 3600000.0f;

        eventStartMillis = millis();
        // Do NOT set this to 1 or include it in the rate. The initiating
        // tip occurred before the measurement window and is still retained
        // in tipCount for the diversion-volume calculation.
        intensityStartTipCount = snapshotTipCount();
        noInterrupts();
        newTipSinceLoop = false;
        interrupts();

        Serial.print(F("Rain event started. Dry spell was "));
        Serial.print(pendingDrySpellHours, 2);
        Serial.println(F(" hours. Measuring initial intensity..."));

        state = SystemState::INTENSITY_MEASURING;
      }
      break;
    }

    case SystemState::INTENSITY_MEASURING: {
      unsigned long elapsed = millis() - eventStartMillis;

      if (newTipSinceLoop) {
        newTipSinceLoop = false;  // just keep counting; window closes on time
      }

      if (rainHasStopped()) {
        Serial.println(F("Rain stopped during intensity measurement - ending event."));
        state = SystemState::STORAGE;
      } else if (elapsed >= INTENSITY_WINDOW_MS) {
        float elapsedMinutes = elapsed / 60000.0f;
        unsigned long tipsNow = snapshotTipCount();
        unsigned long intensityTips = tipsNow - intensityStartTipCount;
        float tipsPerMinute = intensityTips / elapsedMinutes;
        float intensityMmPerHr = tipsPerMinute * RAIN_GAUGE_MM_PER_TIP * 60.0f;
        lastIntensityMmPerHr = intensityMmPerHr;

#if USE_FUZZY_CONTROLLER
        currentPlan = calculateFuzzyDiversionPlan(
            ROOF_AREA_M2, pendingDrySpellHours, intensityMmPerHr,
            BASE_FLUSH_DEPTH_MM, RAIN_GAUGE_MM_PER_TIP);
#else
        currentPlan = calculateDiversionPlan(
            ROOF_AREA_M2, pendingDrySpellHours, intensityMmPerHr,
            BASE_FLUSH_DEPTH_MM, RAIN_GAUGE_MM_PER_TIP);
#endif
        diversionTargetTicks = currentPlan.diversionTicks;
        turbidityExtensionsUsed = 0;

        Serial.print(F("Estimated intensity: "));
        Serial.print(intensityMmPerHr, 2);
        Serial.print(F(" mm/hr. Diversion target: "));
        Serial.print(currentPlan.diversionVolumeLiters, 2);
        Serial.print(F(" L ("));
        Serial.print(diversionTargetTicks);
        Serial.print(F(" ticks), multiplier "));
        Serial.print(currentPlan.multiplier, 3);
        Serial.println(F("x."));

        setActuator(false);  // stay diverted while we wait out the volume
        state = SystemState::DIVERTING;
      }
      break;
    }

    case SystemState::DIVERTING: {
      if (snapshotTipCount() >= diversionTargetTicks) {
        Serial.println(F("Calculated diversion volume reached."));
        state = SystemState::TURBIDITY_CHECK;
      } else if (rainHasStopped()) {
        // Rain ended before the full calculated volume passed - nothing
        // more to divert; go straight to the end-of-event reset.
        Serial.println(F("Rain stopped before target volume - ending event."));
        state = SystemState::STORAGE;
      }
      break;
    }

    case SystemState::TURBIDITY_CHECK: {
      float ntu = readTurbidityNtu();
      lastTurbidityNtu = ntu;
      Serial.print(F("Turbidity check: "));
      Serial.print(ntu, 1);
      Serial.println(F(" NTU"));

      if (ntu > TURBIDITY_CLEAN_THRESHOLD_NTU &&
          turbidityExtensionsUsed < TURBIDITY_MAX_EXTENSIONS) {
        unsigned long extensionTicks = static_cast<unsigned long>(
            diversionTargetTicks * TURBIDITY_EXTENSION_FRACTION);
        if (extensionTicks < 1UL) extensionTicks = 1UL;
        diversionTargetTicks += extensionTicks;
        turbidityExtensionsUsed++;

        Serial.print(F("Still cloudy - extending diversion (extension #"));
        Serial.print(turbidityExtensionsUsed);
        Serial.println(F(")."));

        state = SystemState::DIVERTING;
      } else {
        if (turbidityExtensionsUsed >= TURBIDITY_MAX_EXTENSIONS) {
          Serial.println(F("Max turbidity extensions reached - switching to storage anyway."));
        } else {
          Serial.println(F("Water clean - switching to storage."));
        }
        setActuator(true);
        state = SystemState::STORAGE;
      }
      break;
    }

    case SystemState::STORAGE: {
      if (rainHasStopped()) {
        Serial.println(F("Rain event ended. Resetting for next dry spell."));
        setActuator(false);  // fail-safe default for the next event
        drySpellStartMillis = millis();
        noInterrupts();
        tipCount = 0;
        newTipSinceLoop = false;
        interrupts();
        state = SystemState::DRY_SPELL_TRACKING;
      }
      break;
    }
  }
}

// ---------------------------------------------------------------------
// Interrupt service routine
// ---------------------------------------------------------------------
void tipISR() {
  unsigned long now = millis();
  if (now - lastTipMillis < TIP_DEBOUNCE_MS) {
    return;  // debounce - ignore contact bounce / accidental double-trigger
  }
  lastTipMillis = now;
  tipCount++;
  newTipSinceLoop = true;
}

// ---------------------------------------------------------------------
// Actuator control
// ---------------------------------------------------------------------
void setActuator(bool toStorage) {
  // Servo-flap version:
  actuatorServo.write(toStorage ? SERVO_ANGLE_STORAGE : SERVO_ANGLE_DIVERT);

  // Solenoid-valve version (Section 6.1 alternative) - comment out the
  // line above and use this instead if PIN_ACTUATOR drives a relay/MOSFET:
  // digitalWrite(PIN_ACTUATOR, toStorage ? HIGH : LOW);
}

// ---------------------------------------------------------------------
// Auxiliary hardware
// ---------------------------------------------------------------------
// HC-SR04: measures the air gap above the tank water. A short distance means
// the tank is nearly full. The Uno can read the 5 V echo signal directly.
float readTankDistanceCm() {
  digitalWrite(PIN_TANK_LEVEL_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TANK_LEVEL_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TANK_LEVEL_TRIG, LOW);

  unsigned long echoUs = pulseIn(PIN_TANK_LEVEL_ECHO, HIGH, 30000UL);
  if (echoUs == 0UL) return -1.0f;  // no echo / sensor not connected
  return echoUs / 58.0f;
}

// LEDs provide a local status display without changing the core diversion
// state machine: red means diverting/alert, green means storage, and the
// D10 alert LED means the tank-full distance threshold is detected.
void updateAuxiliaryOutputs() {
  if (millis() - lastTankLevelMillis >= TANK_LEVEL_SAMPLE_MS) {
    lastTankLevelMillis = millis();
    lastTankDistanceCm = readTankDistanceCm();
    tankFull = lastTankDistanceCm > 0.0f &&
               lastTankDistanceCm <= TANK_FULL_DISTANCE_CM;
  }

  bool diverting = state == SystemState::INTENSITY_MEASURING ||
                   state == SystemState::DIVERTING ||
                   state == SystemState::TURBIDITY_CHECK;
  digitalWrite(PIN_STATUS_RED, (diverting || tankFull) ? HIGH : LOW);
  digitalWrite(PIN_STATUS_GREEN, (!diverting && !tankFull) ? HIGH : LOW);

  digitalWrite(PIN_ALERT_LED, tankFull ? HIGH : LOW);
}

// ---------------------------------------------------------------------
// Turbidity sensor reading -> approximate NTU
// ---------------------------------------------------------------------
float readTurbidityNtu() {
  int raw = analogRead(PIN_TURBIDITY_SENSOR);
  float adcVoltage = raw * (ADC_REFERENCE_VOLTS / ADC_MAX_READING);
  // Undo the resistor divider so 'voltage' is what the sensor really outputs.
  float voltage = adcVoltage / TURBIDITY_DIVIDER_RATIO;
  // Calibration is deliberately explicit: record clean voltage and slope
  // from known samples instead of silently assuming an Uno's 5 V / 10-bit ADC.
  float ntu = (TURBIDITY_CLEAN_VOLTAGE - voltage) * TURBIDITY_NTU_PER_VOLT;
  return ntu < 0.0f ? 0.0f : ntu;
}

// ---------------------------------------------------------------------
// Has the rain stopped? (no tick for RAIN_END_GAP_MS)
// ---------------------------------------------------------------------
bool rainHasStopped() {
  noInterrupts();
  unsigned long lastTip = lastTipMillis;
  interrupts();
  return (millis() - lastTip) >= RAIN_END_GAP_MS;
}

unsigned long snapshotTipCount() {
  noInterrupts();
  unsigned long count = tipCount;
  interrupts();
  return count;
}

int stateCode() {
  return static_cast<int>(state);
}

void publishTelemetryIfDue() {
#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32
  if (millis() - lastTelemetryMillis < TELEMETRY_INTERVAL_MS) return;
  lastTelemetryMillis = millis();
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return;

  String url = String("http://api.thingspeak.com/update?api_key=") + THINGSPEAK_WRITE_API_KEY +
      "&field1=" + stateCode() + "&field2=" + String(lastIntensityMmPerHr, 2) +
      "&field3=" + String(pendingDrySpellHours, 2) +
      "&field4=" + String(currentPlan.diversionVolumeLiters, 2) +
      "&field5=" + String(lastTurbidityNtu, 2) + "&field6=" + WiFi.RSSI();
  HTTPClient http;
  http.begin(url);
  int status = http.GET();
  Serial.print(F("ThingSpeak status: "));
  Serial.println(status);
  http.end();
#endif
}

#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 10000UL) {
    delay(250);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("Wi-Fi connected. IP: "));
    Serial.println(WiFi.localIP());
  } else {
    Serial.println(F("Wi-Fi unavailable; continuing safely offline."));
  }
}
#endif
