"""
fuzzy_controller.py

Fuzzy logic controller (FLC) for the Adaptive First-Flush Diverter. It
replaces the hard-banded lookup of report Section 5.1.3 with a smooth,
rule-based inference, while reusing the SAME nine multipliers as its rule
base, so the expert knowledge in Table 2 is preserved.

Design (zero-order Sugeno / TSK):

  Inputs   dry-spell duration (hours)      -> {SHORT, MEDIUM, LONG}
           initial rain intensity (mm/hr)  -> {LIGHT, MODERATE, HEAVY}

  Fuzzification
           Each input is split into three overlapping sets forming a
           Ruspini partition (memberships always sum to 1). The outer sets
           are trapezoidal shoulders and the middle set is the complement.
           The 0.5 crossover of each pair sits exactly on the crisp band
           threshold of Sections 5.1.1 / 5.1.2, so the FLC agrees with the
           banded logic on which band is "more true"; it just blends
           smoothly across a transition zone instead of jumping.

  Rules    9 rules, one per cell of Table 2:
               IF dry IS <band> AND intensity IS <band> THEN multiplier = z_ij
           AND is the product t-norm.

  Output   weighted average of the rule consequents (Sugeno defuzzification):
               multiplier = sum(w_ij * z_ij) / sum(w_ij)

Why Sugeno rather than Mamdani: the output is a crisp number, so there is no
membership-function integration / centroid search, which makes the on-device
cost tiny (a handful of multiplies) and lets the consequents be tuned by
plain linear least squares (see ml_baseline.fit_tuned_flc).

This module has no third-party dependencies. firmware/.../fuzzy_controller.*
is a one-to-one C++ port; simulation/parity_check.py verifies they agree.
"""

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from diverter_logic import (
    BASE_FLUSH_DEPTH_MM,
    DIVERSION_MULTIPLIER_TABLE,
    DRY_SPELL_LONG_MIN_HOURS,
    DRY_SPELL_SHORT_MAX_HOURS,
    INTENSITY_LIGHT_MAX_MM_HR,
    INTENSITY_MODERATE_MAX_MM_HR,
    RAIN_GAUGE_MM_PER_TIP,
    DiversionPlan,
    DrySpellBand,
    IntensityBand,
    base_volume_liters,
    volume_to_ticks,
)

Table3x3 = Sequence[Sequence[float]]

DRY_ORDER = (DrySpellBand.SHORT, DrySpellBand.MEDIUM, DrySpellBand.LONG)
INT_ORDER = (IntensityBand.LIGHT, IntensityBand.MODERATE, IntensityBand.HEAVY)


@dataclass(frozen=True)
class FuzzyConfig:
    """Membership-function geometry. Each crossover is centred on the crisp
    threshold; `half_width` is how far the blend zone extends either side
    (a half-width of 24 h at the 48 h threshold blends over 24-72 h)."""

    dry_short_medium_center_h: float = DRY_SPELL_SHORT_MAX_HOURS
    dry_medium_long_center_h: float = DRY_SPELL_LONG_MIN_HOURS
    dry_short_medium_half_width_h: float = 24.0
    dry_medium_long_half_width_h: float = 240.0

    int_light_moderate_center: float = INTENSITY_LIGHT_MAX_MM_HR
    int_moderate_heavy_center: float = INTENSITY_MODERATE_MAX_MM_HR
    int_light_moderate_half_width: float = 1.0
    int_moderate_heavy_half_width: float = 1.1

    def validate(self) -> None:
        """The middle set is the complement of the outer two, which is only a
        valid partition if the two blend zones do not overlap each other."""
        if min(self.dry_short_medium_half_width_h, self.dry_medium_long_half_width_h,
               self.int_light_moderate_half_width, self.int_moderate_heavy_half_width) <= 0:
            raise ValueError("half-widths must be > 0 (use crisp logic for hard bands)")
        if (self.dry_short_medium_center_h + self.dry_short_medium_half_width_h
                > self.dry_medium_long_center_h - self.dry_medium_long_half_width_h):
            raise ValueError("dry-spell blend zones overlap")
        if (self.int_light_moderate_center + self.int_light_moderate_half_width
                > self.int_moderate_heavy_center - self.int_moderate_heavy_half_width):
            raise ValueError("intensity blend zones overlap")

    def scaled(self, factor: float) -> "FuzzyConfig":
        """Same centres, blend zones scaled by `factor` (for width studies)."""
        return replace(
            self,
            dry_short_medium_half_width_h=self.dry_short_medium_half_width_h * factor,
            dry_medium_long_half_width_h=self.dry_medium_long_half_width_h * factor,
            int_light_moderate_half_width=self.int_light_moderate_half_width * factor,
            int_moderate_heavy_half_width=self.int_moderate_heavy_half_width * factor,
        )


DEFAULT_CONFIG = FuzzyConfig()
DEFAULT_CONFIG.validate()


def default_table() -> List[List[float]]:
    """The Table 2 multipliers as a 3x3 list, rows = dry band, cols = intensity band."""
    return [[DIVERSION_MULTIPLIER_TABLE[d][i] for i in INT_ORDER] for d in DRY_ORDER]


# --------------------------------------------------------------------------
# Fuzzification
# --------------------------------------------------------------------------

def _ramp_up(x: float, a: float, b: float) -> float:
    """0 below a, 1 above b, linear in between."""
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    return (x - a) / (b - a)


def dry_spell_memberships(hours: float, cfg: FuzzyConfig = DEFAULT_CONFIG) -> Tuple[float, float, float]:
    """(SHORT, MEDIUM, LONG) membership degrees; always sums to 1."""
    h = max(hours, 0.0)
    short = 1.0 - _ramp_up(h, cfg.dry_short_medium_center_h - cfg.dry_short_medium_half_width_h,
                           cfg.dry_short_medium_center_h + cfg.dry_short_medium_half_width_h)
    long_ = _ramp_up(h, cfg.dry_medium_long_center_h - cfg.dry_medium_long_half_width_h,
                     cfg.dry_medium_long_center_h + cfg.dry_medium_long_half_width_h)
    return short, 1.0 - short - long_, long_


def intensity_memberships(mm_per_hr: float, cfg: FuzzyConfig = DEFAULT_CONFIG) -> Tuple[float, float, float]:
    """(LIGHT, MODERATE, HEAVY) membership degrees; always sums to 1."""
    i = max(mm_per_hr, 0.0)
    light = 1.0 - _ramp_up(i, cfg.int_light_moderate_center - cfg.int_light_moderate_half_width,
                           cfg.int_light_moderate_center + cfg.int_light_moderate_half_width)
    heavy = _ramp_up(i, cfg.int_moderate_heavy_center - cfg.int_moderate_heavy_half_width,
                     cfg.int_moderate_heavy_center + cfg.int_moderate_heavy_half_width)
    return light, 1.0 - light - heavy, heavy


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------

def firing_strengths(dry_spell_hours: float, intensity_mm_per_hr: float,
                     cfg: FuzzyConfig = DEFAULT_CONFIG) -> List[List[float]]:
    """Normalised rule firing strengths (3x3, sums to 1), product t-norm."""
    md = dry_spell_memberships(dry_spell_hours, cfg)
    mi = intensity_memberships(intensity_mm_per_hr, cfg)
    w = [[d * i for i in mi] for d in md]
    total = sum(sum(row) for row in w)
    return [[v / total for v in row] for row in w]


def fuzzy_multiplier(dry_spell_hours: float, intensity_mm_per_hr: float,
                     cfg: FuzzyConfig = DEFAULT_CONFIG,
                     table: Optional[Table3x3] = None) -> float:
    """Sugeno-defuzzified diversion multiplier. `table` overrides the rule
    consequents (used for data-tuned FLCs); default is the Table 2 values."""
    z = table if table is not None else default_table()
    w = firing_strengths(dry_spell_hours, intensity_mm_per_hr, cfg)
    return sum(w[i][j] * z[i][j] for i in range(3) for j in range(3))


def _argmax(values: Sequence[float]) -> int:
    best = 0
    for k in range(1, len(values)):
        if values[k] > values[best]:   # strict > : ties keep the lower band (matches C++)
            best = k
    return best


def calculate_fuzzy_diversion_plan(
    roof_area_m2: float,
    dry_spell_hours: float,
    intensity_mm_per_hr: float,
    base_flush_depth_mm: float = BASE_FLUSH_DEPTH_MM,
    mm_per_tip: float = RAIN_GAUGE_MM_PER_TIP,
    cfg: FuzzyConfig = DEFAULT_CONFIG,
    table: Optional[Table3x3] = None,
) -> DiversionPlan:
    """Drop-in replacement for diverter_logic.calculate_diversion_plan().

    The returned bands are the DOMINANT (highest-membership) sets, kept only
    for logging and comparison; the multiplier itself is the blended value."""
    multiplier = fuzzy_multiplier(dry_spell_hours, intensity_mm_per_hr, cfg, table)
    base_vol = base_volume_liters(roof_area_m2, base_flush_depth_mm)
    volume = base_vol * multiplier
    return DiversionPlan(
        dry_spell_band=DRY_ORDER[_argmax(dry_spell_memberships(dry_spell_hours, cfg))],
        intensity_band=INT_ORDER[_argmax(intensity_memberships(intensity_mm_per_hr, cfg))],
        multiplier=multiplier,
        base_volume_liters=base_vol,
        diversion_volume_liters=volume,
        diversion_ticks=volume_to_ticks(volume, roof_area_m2, mm_per_tip),
    )


# --------------------------------------------------------------------------
# Reporting helpers
# --------------------------------------------------------------------------

def rule_base_text(table: Optional[Table3x3] = None) -> List[str]:
    """Human-readable rule base, e.g. for pasting into the report."""
    z = table if table is not None else default_table()
    return [
        f"R{3 * i + j + 1}: IF dry-spell IS {DRY_ORDER[i].name} AND intensity IS "
        f"{INT_ORDER[j].name} THEN multiplier = {z[i][j]:.2f}"
        for i in range(3) for j in range(3)
    ]


def export_cpp_table(table: Table3x3) -> str:
    """C++ initialiser for MULTIPLIER_TABLE in diverter_logic.cpp, so a
    table tuned offline can be flashed to the device unchanged."""
    lines = ["static const float MULTIPLIER_TABLE[3][3] = {"]
    for name, row in zip(("SHORT", "MEDIUM", "LONG"), table):
        lines.append("    {" + ", ".join(f"{v:.2f}f" for v in row) + f"}},  // {name}")
    lines.append("};")
    return "\n".join(lines)
