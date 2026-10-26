

#include "fuzzy_controller.h"
#include "config.h"

static_assert(DRY_SPELL_SHORT_MAX_HOURS + FUZZY_DRY_SHORT_MEDIUM_HALF_WIDTH_H <=
              DRY_SPELL_LONG_MIN_HOURS - FUZZY_DRY_MEDIUM_LONG_HALF_WIDTH_H,
              "fuzzy dry-spell blend zones overlap");
static_assert(INTENSITY_LIGHT_MAX_MM_HR + FUZZY_INT_LIGHT_MODERATE_HALF_WIDTH <=
              INTENSITY_MODERATE_MAX_MM_HR - FUZZY_INT_MODERATE_HEAVY_HALF_WIDTH,
              "fuzzy intensity blend zones overlap");


static float rampUp(float x, float a, float b) {
  if (x <= a) return 0.0f;
  if (x >= b) return 1.0f;
  return (x - a) / (b - a);
}

FuzzyMemberships fuzzifyDrySpell(float drySpellHours) {
  float h = drySpellHours < 0.0f ? 0.0f : drySpellHours;
  float shortDeg = 1.0f - rampUp(h,
      DRY_SPELL_SHORT_MAX_HOURS - FUZZY_DRY_SHORT_MEDIUM_HALF_WIDTH_H,
      DRY_SPELL_SHORT_MAX_HOURS + FUZZY_DRY_SHORT_MEDIUM_HALF_WIDTH_H);
  float longDeg = rampUp(h,
      DRY_SPELL_LONG_MIN_HOURS - FUZZY_DRY_MEDIUM_LONG_HALF_WIDTH_H,
      DRY_SPELL_LONG_MIN_HOURS + FUZZY_DRY_MEDIUM_LONG_HALF_WIDTH_H);
  FuzzyMemberships m = {{shortDeg, 1.0f - shortDeg - longDeg, longDeg}};
  return m;
}

FuzzyMemberships fuzzifyIntensity(float intensityMmPerHr) {
  float i = intensityMmPerHr < 0.0f ? 0.0f : intensityMmPerHr;
  float lightDeg = 1.0f - rampUp(i,
      INTENSITY_LIGHT_MAX_MM_HR - FUZZY_INT_LIGHT_MODERATE_HALF_WIDTH,
      INTENSITY_LIGHT_MAX_MM_HR + FUZZY_INT_LIGHT_MODERATE_HALF_WIDTH);
  float heavyDeg = rampUp(i,
      INTENSITY_MODERATE_MAX_MM_HR - FUZZY_INT_MODERATE_HEAVY_HALF_WIDTH,
      INTENSITY_MODERATE_MAX_MM_HR + FUZZY_INT_MODERATE_HEAVY_HALF_WIDTH);
  FuzzyMemberships m = {{lightDeg, 1.0f - lightDeg - heavyDeg, heavyDeg}};
  return m;
}

float fuzzyMultiplier(float drySpellHours, float intensityMmPerHr) {
  FuzzyMemberships md = fuzzifyDrySpell(drySpellHours);
  FuzzyMemberships mi = fuzzifyIntensity(intensityMmPerHr);

  float weightedSum = 0.0f;
  float totalWeight = 0.0f;
  for (uint8_t d = 0; d < 3; d++) {
    for (uint8_t i = 0; i < 3; i++) {
      float w = md.degree[d] * mi.degree[i];   // product t-norm
      weightedSum += w * getMultiplier(static_cast<DrySpellBand>(d),
                                       static_cast<IntensityBand>(i));
      totalWeight += w;
    }
  }
  return weightedSum / totalWeight;
}


static uint8_t argmax3(const FuzzyMemberships& m) {
  uint8_t best = 0;
  for (uint8_t k = 1; k < 3; k++) {
    if (m.degree[k] > m.degree[best]) best = k;
  }
  return best;
}

DiversionPlan calculateFuzzyDiversionPlan(float roofAreaM2, float drySpellHours,
                                          float intensityMmPerHr,
                                          float baseFlushDepthMm,
                                          float mmPerTip) {
  DiversionPlan plan;
  plan.dryBand = static_cast<DrySpellBand>(argmax3(fuzzifyDrySpell(drySpellHours)));
  plan.intensityBand = static_cast<IntensityBand>(argmax3(fuzzifyIntensity(intensityMmPerHr)));
  plan.multiplier = fuzzyMultiplier(drySpellHours, intensityMmPerHr);
  plan.baseVolumeLiters = baseVolumeLiters(roofAreaM2, baseFlushDepthMm);
  plan.diversionVolumeLiters = plan.baseVolumeLiters * plan.multiplier;
  plan.diversionTicks = volumeToTicks(plan.diversionVolumeLiters, roofAreaM2, mmPerTip);
  return plan;
}
