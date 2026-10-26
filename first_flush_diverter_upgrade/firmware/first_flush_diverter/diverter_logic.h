

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


DrySpellBand classifyDrySpell(float drySpellHours);


IntensityBand classifyIntensity(float intensityMmPerHr);


float getMultiplier(DrySpellBand dryBand, IntensityBand intensityBand);


float baseVolumeLiters(float roofAreaM2, float baseFlushDepthMm);

unsigned long volumeToTicks(float volumeLiters, float roofAreaM2, float mmPerTip);


DiversionPlan calculateDiversionPlan(float roofAreaM2, float drySpellHours,
                                      float intensityMmPerHr,
                                      float baseFlushDepthMm,
                                      float mmPerTip);

#endif
