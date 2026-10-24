"""
diverter_logic.py

Core decision-logic for the Adaptive First-Flush Diverter for Rainwater
Harvesting (see report Section 5.1: "Algorithm Design").

This module implements, in plain Python with no hardware dependencies:
  - dry-spell duration banding                 (Section 5.1.1)
  - initial rain-intensity banding              (Section 5.1.2)
  - the banded lookup-table diversion multiplier (Section 5.1.3)
  - the predictive diversion-volume / tick calculation (Sections 5.1.3-5.1.4)

It is deliberately hardware-free so it can be run, plotted, and unit
tested on a desktop machine. The firmware in
firmware/first_flush_diverter/diverter_logic.h / .cpp implements the same
banding logic and lookup table in C++ for the ESP32 / Arduino Uno
prototype described in Section 6 - keep the two in sync if either is
recalibrated.
"""

import math
from dataclasses import dataclass
from enum import Enum


class DrySpellBand(Enum):
    SHORT = "short"      # < 2 days
    MEDIUM = "medium"    # 2 days - 30 days ("~1-2 weeks" example in report)
    LONG = "long"         # > 30 days


class IntensityBand(Enum):
    LIGHT = "light"        # < 2.5 mm/hr
    MODERATE = "moderate"  # 2.5 - 7.6 mm/hr
    HEAVY = "heavy"        # > 7.6 mm/hr


# --------------------------------------------------------------------------
# Calibration constants (Section 6, revisit per Section 8.4 / 11.2 future
# work once real field data is available - these are first-pass, hand-tuned
# values, not statistically derived).
# --------------------------------------------------------------------------

DRY_SPELL_SHORT_MAX_HOURS = 48.0          # < 2 days -> SHORT
DRY_SPELL_LONG_MIN_HOURS = 30 * 24.0      # > 30 days -> LONG

# Intensity bands follow the standard light/moderate/heavy rainfall-rate
# classification used in meteorology (mm/hr).
INTENSITY_LIGHT_MAX_MM_HR = 2.5
INTENSITY_MODERATE_MAX_MM_HR = 7.6

RAIN_GAUGE_MM_PER_TIP = 0.2   # standard tipping-bucket rain-gauge resolution
BASE_FLUSH_DEPTH_MM = 1.0     # first-flush depth diverted at multiplier 1.0x

# Section 5.1.3 lookup table: multiplier[dry_spell_band][intensity_band].
# Monotonically non-decreasing along both axes, matching the qualitative
# behaviour laid out in Table 2 of the report (short+light is smallest,
# long+heavy is largest, short+heavy is only "slightly" larger than
# short+light, long+light is larger than the medium+moderate baseline).
DIVERSION_MULTIPLIER_TABLE = {
    DrySpellBand.SHORT: {
        IntensityBand.LIGHT: 0.70,
        IntensityBand.MODERATE: 0.80,
        IntensityBand.HEAVY: 0.90,
    },
    DrySpellBand.MEDIUM: {
        IntensityBand.LIGHT: 0.90,
        IntensityBand.MODERATE: 1.00,   # baseline case (Table 2)
        IntensityBand.HEAVY: 1.15,
    },
    DrySpellBand.LONG: {
        IntensityBand.LIGHT: 1.20,
        IntensityBand.MODERATE: 1.35,
        IntensityBand.HEAVY: 1.55,
    },
}

# Section 5.1.5 turbidity safety fallback.
TURBIDITY_CLEAN_THRESHOLD_NTU = 5.0
TURBIDITY_EXTENSION_FRACTION = 0.10
TURBIDITY_MAX_EXTENSIONS = 3


def intensity_from_window(tips_after_window_start: int, window_ms: int) -> float:
    """Rain intensity in mm/hr from tips observed *after* event start.

    Mirrors the ESP32 sketch. The first tip starts a rain event and belongs in
    the diversion-volume total, but must not be counted as if it occurred
    during the following measurement window.
    """
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")
    return max(0, tips_after_window_start) * RAIN_GAUGE_MM_PER_TIP * 3600000.0 / window_ms


def classify_dry_spell(dry_spell_hours: float) -> DrySpellBand:
    """Section 5.1.1 - map a dry-spell duration (hours) onto a band."""
    if dry_spell_hours < DRY_SPELL_SHORT_MAX_HOURS:
        return DrySpellBand.SHORT
    if dry_spell_hours > DRY_SPELL_LONG_MIN_HOURS:
        return DrySpellBand.LONG
    return DrySpellBand.MEDIUM


def classify_intensity(intensity_mm_per_hr: float) -> IntensityBand:
    """Section 5.1.2 - map an initial rain-intensity estimate onto a band."""
    if intensity_mm_per_hr < INTENSITY_LIGHT_MAX_MM_HR:
        return IntensityBand.LIGHT
    if intensity_mm_per_hr <= INTENSITY_MODERATE_MAX_MM_HR:
        return IntensityBand.MODERATE
    return IntensityBand.HEAVY


def get_multiplier(dry_spell_band: DrySpellBand, intensity_band: IntensityBand) -> float:
    """Section 5.1.3 - look up the adjustment multiplier for a band pair."""
    return DIVERSION_MULTIPLIER_TABLE[dry_spell_band][intensity_band]


def base_volume_liters(roof_area_m2: float, base_flush_depth_mm: float = BASE_FLUSH_DEPTH_MM) -> float:
    """Fixed base volume from roof area alone (Section 5.1.3), in litres.
    1 mm of runoff depth over 1 sq. metre of roof == 1 litre of water."""
    return roof_area_m2 * base_flush_depth_mm


def round_half_up(x: float) -> int:
    """Round to the nearest integer, ties going UP (4.5 -> 5).

    Python's built-in round() uses banker's rounding (4.5 -> 4), whereas the
    firmware uses C's lroundf() (4.5 -> 5). Using this helper on the Python
    side keeps the simulation's tick counts identical to the firmware's."""
    return int(math.floor(x + 0.5))


def volume_to_ticks(
    volume_liters: float,
    roof_area_m2: float,
    mm_per_tip: float = RAIN_GAUGE_MM_PER_TIP,
) -> int:
    """Section 5.1.4 - convert a diversion volume (litres) into the number of
    rain-gauge tips the actuation logic waits for. Always at least 1."""
    liters_per_tick = roof_area_m2 * mm_per_tip
    if liters_per_tick <= 0:
        return 1
    return max(1, round_half_up(volume_liters / liters_per_tick))


@dataclass
class DiversionPlan:
    dry_spell_band: DrySpellBand
    intensity_band: IntensityBand
    multiplier: float
    base_volume_liters: float
    diversion_volume_liters: float
    diversion_ticks: int


def calculate_diversion_plan(
    roof_area_m2: float,
    dry_spell_hours: float,
    intensity_mm_per_hr: float,
    base_flush_depth_mm: float = BASE_FLUSH_DEPTH_MM,
    mm_per_tip: float = RAIN_GAUGE_MM_PER_TIP,
) -> DiversionPlan:
    """Sections 5.1.3 + 5.1.4 - compute the predictive diversion volume and
    the equivalent number of rain-gauge ticks the actuation logic should
    wait for (tick count is the on-device volume proxy, Section 5.1.4)."""
    dry_band = classify_dry_spell(dry_spell_hours)
    int_band = classify_intensity(intensity_mm_per_hr)
    multiplier = get_multiplier(dry_band, int_band)
    base_vol = base_volume_liters(roof_area_m2, base_flush_depth_mm)
    diversion_vol = base_vol * multiplier

    ticks = volume_to_ticks(diversion_vol, roof_area_m2, mm_per_tip)

    return DiversionPlan(
        dry_spell_band=dry_band,
        intensity_band=int_band,
        multiplier=multiplier,
        base_volume_liters=base_vol,
        diversion_volume_liters=diversion_vol,
        diversion_ticks=ticks,
    )


def apply_turbidity_fallback(
    diversion_volume_liters: float,
    turbidity_reader,
    extension_fraction: float = TURBIDITY_EXTENSION_FRACTION,
    clean_threshold_ntu: float = TURBIDITY_CLEAN_THRESHOLD_NTU,
    max_extensions: int = TURBIDITY_MAX_EXTENSIONS,
):
    """Section 5.1.5 - given the calculated diversion volume, repeatedly
    check turbidity and extend diversion in fixed fractional steps if the
    water is still not clean, capped at max_extensions checks.

    `turbidity_reader` is a callable: total_volume_diverted_liters -> NTU
    reading at that point (a real sensor read on hardware, or a synthetic
    model when simulating). Returns (final_volume_liters, extensions_used).
    """
    volume = diversion_volume_liters
    extension_step = diversion_volume_liters * extension_fraction
    extensions_used = 0

    while extensions_used < max_extensions:
        reading_ntu = turbidity_reader(volume)
        if reading_ntu <= clean_threshold_ntu:
            break
        volume += extension_step
        extensions_used += 1

    return volume, extensions_used
