"""
baselines.py

Simplified models of the two existing first-flush diverter categories
described in report Section 3 ("Literature Review / Prior-Art Analysis"),
used purely so the predictive algorithm can be compared against them
across the scenario matrix (Sections 7.1.2 and 8.2).

These are illustrative simulation models, not measured data: the project
is scoped to TRL 1 (Section 2.5) and no field turbidity dataset was
available, so the turbidity-only baseline is built from a simple,
clearly-labelled synthetic decay curve rather than real sensor logs. This
should be replaced with real data if the analysis is ever pushed past
decision-logic simulation (see Section 11.2, future work item 1).
"""

import math

from diverter_logic import base_volume_liters, BASE_FLUSH_DEPTH_MM


def fixed_volume_diversion_liters(
    roof_area_m2: float,
    base_flush_depth_mm: float = BASE_FLUSH_DEPTH_MM,
) -> float:
    """Section 3.1 - mechanical float diverters divert the same volume
    every time, sized only from roof area. Dry-spell length and rain
    intensity are never taken into account."""
    return base_volume_liters(roof_area_m2, base_flush_depth_mm)


# --- Synthetic turbidity-only model (Section 3.2 / 7.1.2) -----------------
#
# Assumption: the longer the dry spell, the more pollutant has built up on
# the roof, so the initial washoff starts out more turbid. Heavier initial
# rain intensity washes the accumulated pollutant off faster (turbidity
# drops per litre passed more quickly), but a turbidity sensor can only
# react to what it measures, so a fixed reaction lag is added to represent
# water that has already flowed past before the sensor's reading catches
# up (Section 3.2's core weakness: "reactive rather than predictive").

TURBIDITY_BASE_NTU = 50.0          # initial turbidity after a ~1 day dry spell
TURBIDITY_DRY_SPELL_SCALE_HOURS = 720.0   # 30 days: roughly doubles build-up
TURBIDITY_DECAY_BASE_PER_LITER = 0.35     # how fast turbidity clears per litre
TURBIDITY_INTENSITY_WASH_GAIN = 0.05      # heavier rain washes off faster
TURBIDITY_REACTION_LAG_LITERS = 0.5 * 1  # water already flowing before sensor reacts
CLEAN_THRESHOLD_NTU = 5.0


def _initial_turbidity_ntu(dry_spell_hours: float) -> float:
    return TURBIDITY_BASE_NTU * (1.0 + dry_spell_hours / TURBIDITY_DRY_SPELL_SCALE_HOURS)


def _decay_rate_per_liter(intensity_mm_per_hr: float) -> float:
    return TURBIDITY_DECAY_BASE_PER_LITER * (1.0 + TURBIDITY_INTENSITY_WASH_GAIN * intensity_mm_per_hr)


def synthetic_turbidity_reading(
    volume_passed_liters: float,
    dry_spell_hours: float,
    intensity_mm_per_hr: float,
) -> float:
    """Modelled turbidity (NTU) after `volume_passed_liters` has flowed,
    for a given dry-spell/intensity scenario. Exponential decay from an
    initial value that scales with dry-spell length."""
    initial_ntu = _initial_turbidity_ntu(dry_spell_hours)
    k = _decay_rate_per_liter(intensity_mm_per_hr)
    return initial_ntu * math.exp(-k * volume_passed_liters)


def turbidity_only_diversion_liters(
    dry_spell_hours: float,
    intensity_mm_per_hr: float,
    clean_threshold_ntu: float = CLEAN_THRESHOLD_NTU,
    reaction_lag_liters: float = TURBIDITY_REACTION_LAG_LITERS,
) -> float:
    """Section 3.2 / 7.1.2 - volume a reactive turbidity-only diverter
    would end up diverting for this scenario: solve for the volume at
    which the modelled turbidity curve crosses the clean threshold, then
    add a fixed reaction-lag volume to represent water that has already
    flowed past before the sensor's reading catches up."""
    initial_ntu = _initial_turbidity_ntu(dry_spell_hours)
    k = _decay_rate_per_liter(intensity_mm_per_hr)

    if initial_ntu <= clean_threshold_ntu:
        # Water starts clean enough - a reactive system would divert
        # almost nothing, but still needs the reaction lag to register it.
        return reaction_lag_liters

    volume_to_clear = math.log(initial_ntu / clean_threshold_ntu) / k
    return volume_to_clear + reaction_lag_liters
