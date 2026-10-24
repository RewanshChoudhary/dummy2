// fuzzy_controller.h
//
// Zero-order Sugeno fuzzy logic controller that replaces the hard-banded
// lookup of report Section 5.1.3. One-to-one C++ port of
// simulation/fuzzy_controller.py - see that file for the design rationale.
//
// The rule consequents are NOT duplicated here: they are read through
// getMultiplier() from MULTIPLIER_TABLE in diverter_logic.cpp, so the banded
// and fuzzy controllers always share one table.
//
// Like diverter_logic.*, this file uses no Arduino APIs, so it can be
// compiled and desk-checked on a PC (see simulation/parity_check.py).

#ifndef FUZZY_CONTROLLER_H
#define FUZZY_CONTROLLER_H

#include "diverter_logic.h"

// Membership degrees of one input in its three sets; always sums to 1.
struct FuzzyMemberships {
  float degree[3];   // [SHORT|LIGHT, MEDIUM|MODERATE, LONG|HEAVY]
};

FuzzyMemberships fuzzifyDrySpell(float drySpellHours);
FuzzyMemberships fuzzifyIntensity(float intensityMmPerHr);

// Blended (Sugeno-defuzzified) multiplier for the given inputs.
float fuzzyMultiplier(float drySpellHours, float intensityMmPerHr);

// Drop-in replacement for calculateDiversionPlan(). The dryBand/intensityBand
// fields hold the DOMINANT set, for logging only.
DiversionPlan calculateFuzzyDiversionPlan(float roofAreaM2, float drySpellHours,
                                          float intensityMmPerHr,
                                          float baseFlushDepthMm,
                                          float mmPerTip);

#endif  // FUZZY_CONTROLLER_H
