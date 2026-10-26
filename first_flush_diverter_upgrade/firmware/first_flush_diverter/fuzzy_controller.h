

#ifndef FUZZY_CONTROLLER_H
#define FUZZY_CONTROLLER_H

#include "diverter_logic.h"


struct FuzzyMemberships {
  float degree[3];
};

FuzzyMemberships fuzzifyDrySpell(float drySpellHours);
FuzzyMemberships fuzzifyIntensity(float intensityMmPerHr);


float fuzzyMultiplier(float drySpellHours, float intensityMmPerHr);


DiversionPlan calculateFuzzyDiversionPlan(float roofAreaM2, float drySpellHours,
                                          float intensityMmPerHr,
                                          float baseFlushDepthMm,
                                          float mmPerTip);

#endif
