

#include "config.h"
#if HARDWARE_TARGET == TARGET_ESP32_S3
  #include <ESP32Servo.h>
#else
  #include <Servo.h>
#endif
#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32_S3
  #include <WiFi.h>
  #include <HTTPClient.h>
#endif


#include "diverter_logic.h"
#include "fuzzy_controller.h"


enum class SystemState {
  DRY_SPELL_TRACKING,
  INTENSITY_MEASURING,
  DIVERTING,
  TURBIDITY_CHECK,
  STORAGE,
};

static SystemState state = SystemState::DRY_SPELL_TRACKING;

volatile unsigned long tipCount = 0;
volatile unsigned long lastTipMillis = 0;
volatile bool newTipSinceLoop = false;


unsigned long drySpellStartMillis = 0;
unsigned long eventStartMillis = 0;
unsigned long intensityStartTipCount = 0;
float pendingDrySpellHours = 0.0f;


DiversionPlan currentPlan;
unsigned long diversionTargetTicks = 0;
int turbidityExtensionsUsed = 0;
float lastIntensityMmPerHr = 0.0f;
float lastTurbidityNtu = -1.0f;
unsigned long lastTelemetryMillis = 0;
unsigned long lastTankLevelMillis = 0;
unsigned long lastSimulatedTipMillis = 0;
float lastTankDistanceCm = -1.0f;
bool tankFull = false;

Servo actuatorServo;


void tipISR();
void setActuator(bool toStorage);
float readTurbidityNtu();
float readTankDistanceCm();
void updateAuxiliaryOutputs();
void updateSimulatedRain();
bool rainHasStopped();
unsigned long snapshotTipCount();
int stateCode();
void publishTelemetryIfDue();
#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32_S3
void connectWiFi();
#endif

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

  lastTankLevelMillis = millis() - TANK_LEVEL_SAMPLE_MS;

#if HARDWARE_TARGET == TARGET_ESP32_S3
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_TURBIDITY_SENSOR, ADC_11db);
#endif

  actuatorServo.attach(PIN_ACTUATOR);


  setActuator(false);

#if SIMULATE_RAIN_INPUT
  // GPIO5 is deliberately held LOW by the external GND-rail connection.
  // Do not attach an interrupt in simulation mode; tips are generated below.
  lastSimulatedTipMillis = millis() - SIMULATED_TIP_INTERVAL_MS;
#else
  attachInterrupt(digitalPinToInterrupt(PIN_RAIN_GAUGE_TIP), tipISR, FALLING);
#endif

  drySpellStartMillis = millis();
  state = SystemState::DRY_SPELL_TRACKING;

#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32_S3
  connectWiFi();
#endif

  Serial.println(F("Adaptive First-Flush Diverter - ready. Tracking dry spell."));
}


void loop() {
  updateSimulatedRain();
  publishTelemetryIfDue();
  updateAuxiliaryOutputs();
  switch (state) {

    case SystemState::DRY_SPELL_TRACKING: {
      if (newTipSinceLoop) {

        unsigned long drySpellMs = millis() - drySpellStartMillis;
        pendingDrySpellHours = drySpellMs / 3600000.0f;

        eventStartMillis = millis();

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
        newTipSinceLoop = false;
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

        setActuator(false);
        state = SystemState::DIVERTING;
      }
      break;
    }

    case SystemState::DIVERTING: {
      if (snapshotTipCount() >= diversionTargetTicks) {
        Serial.println(F("Calculated diversion volume reached."));
        state = SystemState::TURBIDITY_CHECK;
      } else if (rainHasStopped()) {

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
        setActuator(false);
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

void tipISR() {
  unsigned long now = millis();
  if (now - lastTipMillis < TIP_DEBOUNCE_MS) {
    return;
  }
  lastTipMillis = now;
  tipCount++;
  newTipSinceLoop = true;
}


void updateSimulatedRain() {
#if SIMULATE_RAIN_INPUT
  unsigned long now = millis();
  if (now - lastSimulatedTipMillis >= SIMULATED_TIP_INTERVAL_MS) {
    lastSimulatedTipMillis = now;
    tipISR();
  }
#endif
}


void setActuator(bool toStorage) {
  // Servo-flap version:
  int targetAngle = toStorage ? SERVO_ANGLE_STORAGE : SERVO_ANGLE_DIVERT;
  actuatorServo.write(targetAngle);

  Serial.print(F("SERVO_CMD: "));
  Serial.print(toStorage ? F("STORAGE") : F("WASTE/DIVERT"));
  Serial.print(F(" angle="));
  Serial.print(targetAngle);
  Serial.println(F(" deg; command sent (no position feedback)"));

}


float readTankDistanceCm() {
  digitalWrite(PIN_TANK_LEVEL_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TANK_LEVEL_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TANK_LEVEL_TRIG, LOW);

  unsigned long echoUs = pulseIn(PIN_TANK_LEVEL_ECHO, HIGH, 30000UL);
  if (echoUs == 0UL) {
    Serial.println(F("ULTRASONIC: no echo received; distance unavailable"));
    return -1.0f;  // no echo / sensor not connected
  }

  float distanceCm = echoUs / 58.0f;
  Serial.print(F("ULTRASONIC: distance measured = "));
  Serial.print(distanceCm, 1);
  Serial.print(F(" cm (echo "));
  Serial.print(echoUs);
  Serial.println(F(" us)"));
  return distanceCm;
}


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


float readTurbidityNtu() {
#if HARDWARE_TARGET == TARGET_ESP32_S3
  // analogReadMilliVolts() uses the ESP32-S3 ADC calibration data. The
  // divider is undone below so calibration remains expressed at sensor OUT.
  float adcVoltage = analogReadMilliVolts(PIN_TURBIDITY_SENSOR) / 1000.0f;
#else
  int raw = analogRead(PIN_TURBIDITY_SENSOR);
  float adcVoltage = raw * (ADC_REFERENCE_VOLTS / ADC_MAX_READING);
#endif

  float voltage = adcVoltage / TURBIDITY_DIVIDER_RATIO;

  float ntu = (TURBIDITY_CLEAN_VOLTAGE - voltage) * TURBIDITY_NTU_PER_VOLT;
  return ntu < 0.0f ? 0.0f : ntu;
}


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
#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32_S3
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

#if ENABLE_IOT && HARDWARE_TARGET == TARGET_ESP32_S3
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("Wi-Fi connected. IP: "));
    Serial.println(WiFi.localIP());
    return;
  }

  WiFi.disconnect(true, false);
  delay(500);

  WiFi.mode(WIFI_STA);
  delay(500);

  Serial.println(F("Connecting to Wi-Fi..."));
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long started = millis();

  while (WiFi.status() != WL_CONNECTED &&
         millis() - started < 15000UL) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("Wi-Fi connected. IP: "));
    Serial.println(WiFi.localIP());
  } else {
    Serial.print(F("Wi-Fi connection failed. Status: "));
    Serial.println(WiFi.status());
  }
}
#endif
