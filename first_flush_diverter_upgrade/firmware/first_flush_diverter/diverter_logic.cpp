// diverter_logic.cpp
//
// Implementation of the decision-logic declared in diverter_logic.h.
// See that file and report Section 5.1 for the rationale of each piece.

#include "diverter_logic.h"
#include "config.h"
#include <math.h>

DrySpellBand classifyDrySpell(float drySpellHours) {
  if (drySpellHours < DRY_SPELL_SHORT_MAX_HOURS) return DrySpellBand::SHORT;
  if (drySpellHours > DRY_SPELL_LONG_MIN_HOURS) return DrySpellBand::LONG;
  return DrySpellBand::MEDIUM;
}

IntensityBand classifyIntensity(float intensityMmPerHr) {
  if (intensityMmPerHr < INTENSITY_LIGHT_MAX_MM_HR) return IntensityBand::LIGHT;
  if (intensityMmPerHr <= INTENSITY_MODERATE_MAX_MM_HR) return IntensityBand::MODERATE;
  return IntensityBand::HEAVY;
}

// Section 5.1.3 lookup table: MULTIPLIER_TABLE[dry_band][intensity_band].
// Keep this numerically identical to DIVERSION_MULTIPLIER_TABLE in
// simulation/diverter_logic.py if either is recalibrated.
static const float MULTIPLIER_TABLE[3][3] = {
    // LIGHT   MODERATE  HEAVY
    {0.70f, 0.80f, 0.90f},  // SHORT
    {0.90f, 1.00f, 1.15f},  // MEDIUM
    {1.20f, 1.35f, 1.55f},  // LONG
};

float getMultiplier(DrySpellBand dryBand, IntensityBand intensityBand) {
  return MULTIPLIER_TABLE[static_cast<uint8_t>(dryBand)][static_cast<uint8_t>(intensityBand)];
}

float baseVolumeLiters(float roofAreaM2, float baseFlushDepthMm) {
  // 1 mm of runoff depth over 1 sq. metre of roof == 1 litre of water.
  return roofAreaM2 * baseFlushDepthMm;
}

unsigned long volumeToTicks(float volumeLiters, float roofAreaM2, float mmPerTip) {
  float litersPerTick = roofAreaM2 * mmPerTip;
  if (litersPerTick <= 0.0f) return 1UL;
  long rounded = lroundf(volumeLiters / litersPerTick);
  return (rounded < 1L) ? 1UL : static_cast<unsigned long>(rounded);
}

DiversionPlan calculateDiversionPlan(float roofAreaM2, float drySpellHours,
                                      float intensityMmPerHr,
                                      float baseFlushDepthMm,
                                      float mmPerTip) {
  DiversionPlan plan;
  plan.dryBand = classifyDrySpell(drySpellHours);
  plan.intensityBand = classifyIntensity(intensityMmPerHr);
  plan.multiplier = getMultiplier(plan.dryBand, plan.intensityBand);
  plan.baseVolumeLiters = baseVolumeLiters(roofAreaM2, baseFlushDepthMm);
  plan.diversionVolumeLiters = plan.baseVolumeLiters * plan.multiplier;

  plan.diversionTicks = volumeToTicks(plan.diversionVolumeLiters, roofAreaM2, mmPerTip);

  return plan;
}
