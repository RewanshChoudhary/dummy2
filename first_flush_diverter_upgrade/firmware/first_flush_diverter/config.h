#ifndef CONFIG_H
#define CONFIG_H

#define TARGET_ESP32_S3 1
#define TARGET_ARDUINO_UNO 2
#define HARDWARE_TARGET TARGET_ESP32_S3

#if HARDWARE_TARGET == TARGET_ESP32_S3
  // ESP32-S3 DevKitC-compatible GPIO map. GPIO19/20 are reserved for the
  // native USB interface, and GPIO34 is not an ESP32-S3 ADC pin.
  #define PIN_RAIN_GAUGE_TIP 5
  #define PIN_TURBIDITY_SENSOR 4   // ADC1_CH3
  #define PIN_ACTUATOR 6
  #define PIN_TANK_LEVEL_TRIG 7
  #define PIN_TANK_LEVEL_ECHO 8
  #define PIN_ALERT_LED 9
  #define PIN_STATUS_RED 10
  #define PIN_STATUS_GREEN 18
  #define ADC_REFERENCE_VOLTS 3.3f
  #define ADC_MAX_READING 4095.0f
#elif HARDWARE_TARGET == TARGET_ARDUINO_UNO
  #define PIN_RAIN_GAUGE_TIP 2
  #define PIN_TURBIDITY_SENSOR A0
  #define PIN_ACTUATOR 9

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

// Bench/demo workaround: GPIO5 is tied to the breadboard GND (blue) rail
// because no rain gauge or push button is available. The firmware generates
// rain tips at a fixed interval while this is enabled. Set to 0 when a real
// rain gauge or push button is connected.
#define SIMULATE_RAIN_INPUT       1
#define SIMULATED_TIP_INTERVAL_MS 5000UL


#define ROOF_AREA_M2             50.0f
#define RAIN_GAUGE_MM_PER_TIP    0.2f
#define BASE_FLUSH_DEPTH_MM      1.0f


#define DRY_SPELL_SHORT_MAX_HOURS   48.0f
#define DRY_SPELL_LONG_MIN_HOURS    (30.0f * 24.0f)
#define INTENSITY_LIGHT_MAX_MM_HR      2.5f
#define INTENSITY_MODERATE_MAX_MM_HR   7.6f

#define INTENSITY_WINDOW_MS (15UL * 1000UL)

#define RAIN_END_GAP_MS   (15UL * 1000UL)

#define USE_FUZZY_CONTROLLER   1

#define FUZZY_DRY_SHORT_MEDIUM_HALF_WIDTH_H   24.0f
#define FUZZY_DRY_MEDIUM_LONG_HALF_WIDTH_H    240.0f
#define FUZZY_INT_LIGHT_MODERATE_HALF_WIDTH   1.0f
#define FUZZY_INT_MODERATE_HEAVY_HALF_WIDTH   1.1f

#define TURBIDITY_CLEAN_THRESHOLD_NTU   5.0f
#define TURBIDITY_EXTENSION_FRACTION    0.10f
#define TURBIDITY_MAX_EXTENSIONS        3


#if HARDWARE_TARGET == TARGET_ESP32_S3
  // Use equal-value resistors: sensor OUT -> 10k -> ADC4 -> 10k -> GND.
  // This keeps a 0-5 V sensor output within the S3 ADC input range.
  #define TURBIDITY_DIVIDER_RATIO       0.5f
#else
  #define TURBIDITY_DIVIDER_RATIO       1.0f
#endif


#define TURBIDITY_CLEAN_VOLTAGE         4.125f
#define TURBIDITY_NTU_PER_VOLT          20.0f

#define SERVO_ANGLE_DIVERT    0
#define SERVO_ANGLE_STORAGE   90


#define TANK_FULL_DISTANCE_CM       10.0f
#define TANK_LEVEL_SAMPLE_MS        5000UL


#define TIP_DEBOUNCE_MS   50UL


#define ENABLE_IOT 1
#define WIFI_SSID "Motorola"
#define WIFI_PASSWORD "67islame"
#define THINGSPEAK_WRITE_API_KEY "5LN0NL2DUIOCHMUD"
#define TELEMETRY_INTERVAL_MS 15000UL

#endif
