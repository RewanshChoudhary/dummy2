// diverter_logic.h
//
// Hardware-independent decision-logic for the Adaptive First-Flush
// Diverter (report Section 5.1: "Algorithm Design"). Deliberately kept
// free of any Arduino/ESP32-specific calls (no digitalRead, no Servo,
// no millis()) so it mirrors simulation/diverter_logic.py one-to-one and
// can be reasoned about / desk-checked on its own. All hardware I/O and
// timing live in first_flush_diverter.ino.
//
// If the lookup table in Section 5.1.3 is ever recalibrated, update the
// MULTIPLIER_TABLE in diverter_logic.cpp AND the DIVERSION_MULTIPLIER_TABLE
// in simulation/diverter_logic.py together so the simulation and the
// firmware stay consistent.

#ifndef DIVERTER_LOGIC_H
#define DIVERTER_LOGIC_H

#include <stdint.h>

enum class DrySpellBand : uint8_t { SHORT = 0, MEDIUM = 1, LONG = 2 };
enum class IntensityBand : uint8_t { LIGHT = 0, MODERATE = 1, HEAVY = 2 };

struct DiversionPlan {
  DrySpellBand dryBand;
  IntensityBand intensityBand;
  float multiplier;
  float baseVolumeLiters;
  float diversionVolumeLiters;
  unsigned long diversionTicks;
};

// Section 5.1.1 - map a dry-spell duration (hours) onto a band.
DrySpellBand classifyDrySpell(float drySpellHours);

// Section 5.1.2 - map an initial rain-intensity estimate (mm/hr) onto a band.
IntensityBand classifyIntensity(float intensityMmPerHr);

// Section 5.1.3 - look up the adjustment multiplier for a band pair.
float getMultiplier(DrySpellBand dryBand, IntensityBand intensityBand);

// Fixed base volume from roof area alone, in litres.
float baseVolumeLiters(float roofAreaM2, float baseFlushDepthMm);

// Section 5.1.4 - convert a diversion volume (litres) to a rain-gauge tick
// count, rounding to nearest (ties up) with a minimum of 1. Shared by the
// banded and fuzzy controllers so the two can never disagree on rounding.
unsigned long volumeToTicks(float volumeLiters, float roofAreaM2, float mmPerTip);

// Sections 5.1.3 + 5.1.4 - compute the full predictive diversion plan,
// including the equivalent tick count the actuation logic waits for.
DiversionPlan calculateDiversionPlan(float roofAreaM2, float drySpellHours,
                                      float intensityMmPerHr,
                                      float baseFlushDepthMm,
                                      float mmPerTip);

#endif  // DIVERTER_LOGIC_H
