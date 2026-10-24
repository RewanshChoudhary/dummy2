"""
test_fuzzy_controller.py

Unit tests for fuzzy_controller.py. Run with:
    python3 -m unittest test_fuzzy_controller.py -v
"""

import unittest

from diverter_logic import (
    DRY_SPELL_LONG_MIN_HOURS,
    DRY_SPELL_SHORT_MAX_HOURS,
    INTENSITY_LIGHT_MAX_MM_HR,
    INTENSITY_MODERATE_MAX_MM_HR,
    DrySpellBand,
    IntensityBand,
    calculate_diversion_plan,
    classify_dry_spell,
    classify_intensity,
    get_multiplier,
)
from fuzzy_controller import (
    DEFAULT_CONFIG,
    DRY_ORDER,
    INT_ORDER,
    FuzzyConfig,
    calculate_fuzzy_diversion_plan,
    default_table,
    dry_spell_memberships,
    export_cpp_table,
    firing_strengths,
    fuzzy_multiplier,
    intensity_memberships,
    rule_base_text,
)

# Representative points from run_scenarios.py, one per Table 2 cell.
DRY_REP = {DrySpellBand.SHORT: 24.0, DrySpellBand.MEDIUM: 240.0, DrySpellBand.LONG: 1080.0}
INT_REP = {IntensityBand.LIGHT: 1.0, IntensityBand.MODERATE: 5.0, IntensityBand.HEAVY: 12.0}


def frange(start, stop, step):
    x = start
    while x <= stop:
        yield x
        x += step


class TestMemberships(unittest.TestCase):
    def test_partition_of_unity_and_range(self):
        for h in list(frange(0, 3000, 7.3)) + [-5.0]:
            m = dry_spell_memberships(h)
            self.assertAlmostEqual(sum(m), 1.0, places=12)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in m))
        for i in list(frange(0, 60, 0.05)) + [-1.0]:
            m = intensity_memberships(i)
            self.assertAlmostEqual(sum(m), 1.0, places=12)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in m))

    def test_crossover_is_exactly_at_crisp_thresholds(self):
        s, m, _ = dry_spell_memberships(DRY_SPELL_SHORT_MAX_HOURS)
        self.assertAlmostEqual(s, 0.5)
        self.assertAlmostEqual(m, 0.5)
        _, m, l = dry_spell_memberships(DRY_SPELL_LONG_MIN_HOURS)
        self.assertAlmostEqual(m, 0.5)
        self.assertAlmostEqual(l, 0.5)
        li, mo, _ = intensity_memberships(INTENSITY_LIGHT_MAX_MM_HR)
        self.assertAlmostEqual(li, 0.5)
        self.assertAlmostEqual(mo, 0.5)
        _, mo, hv = intensity_memberships(INTENSITY_MODERATE_MAX_MM_HR)
        self.assertAlmostEqual(mo, 0.5)
        self.assertAlmostEqual(hv, 0.5)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            FuzzyConfig(dry_medium_long_half_width_h=5000.0).validate()
        with self.assertRaises(ValueError):
            FuzzyConfig(int_light_moderate_half_width=0.0).validate()


class TestInference(unittest.TestCase):
    def test_reproduces_table_2_at_band_cores(self):
        for d in DrySpellBand:
            for i in IntensityBand:
                got = fuzzy_multiplier(DRY_REP[d], INT_REP[i])
                self.assertAlmostEqual(got, get_multiplier(d, i), places=12, msg=f"{d} {i}")

    def test_agrees_with_crisp_wherever_memberships_are_pure(self):
        # Away from every blend zone the FLC must be identical to the banded logic.
        for h in list(frange(0, 20, 1)) + list(frange(80, 470, 30)) + list(frange(1000, 3000, 100)):
            for i in list(frange(0, 1.4, 0.1)) + list(frange(3.6, 6.4, 0.2)) + list(frange(8.8, 40, 1.0)):
                expected = get_multiplier(classify_dry_spell(h), classify_intensity(i))
                self.assertAlmostEqual(fuzzy_multiplier(h, i), expected, places=12, msg=f"{h} {i}")

    def test_midpoint_blends_neighbouring_rules(self):
        # At the 48 h threshold with moderate rain the output is the mean of
        # SHORT+MODERATE (0.80) and MEDIUM+MODERATE (1.00).
        self.assertAlmostEqual(fuzzy_multiplier(48.0, 5.0), 0.90)
        # At 7.6 mm/hr in a medium dry spell: mean of MEDIUM+MODERATE and MEDIUM+HEAVY.
        self.assertAlmostEqual(fuzzy_multiplier(240.0, 7.6), (1.00 + 1.15) / 2)

    def test_output_stays_within_table_range(self):
        lo = min(min(r) for r in default_table())
        hi = max(max(r) for r in default_table())
        for h in frange(0, 3000, 13.7):
            for i in frange(0, 40, 0.37):
                v = fuzzy_multiplier(h, i)
                self.assertGreaterEqual(v, lo - 1e-12)
                self.assertLessEqual(v, hi + 1e-12)

    def test_monotone_in_each_input(self):
        for i in (0.5, 2.5, 5.0, 7.6, 12.0):
            prev = -1.0
            for h in frange(0, 3000, 5.0):
                v = fuzzy_multiplier(h, i)
                self.assertGreaterEqual(v, prev - 1e-12)
                prev = v
        for h in (10.0, 48.0, 240.0, 720.0, 1500.0):
            prev = -1.0
            for i in frange(0, 40, 0.05):
                v = fuzzy_multiplier(h, i)
                self.assertGreaterEqual(v, prev - 1e-12)
                prev = v

    def test_no_jump_across_old_band_boundaries(self):
        # The banded lookup jumps by up to 0.2 at each threshold; the FLC must not.
        eps = 1e-3
        crisp_jump = abs(get_multiplier(DrySpellBand.MEDIUM, IntensityBand.LIGHT)
                         - get_multiplier(DrySpellBand.SHORT, IntensityBand.LIGHT))
        self.assertGreaterEqual(crisp_jump, 0.19)  # sanity: crisp really does jump
        for i in (1.0, 5.0, 12.0):
            for centre in (DRY_SPELL_SHORT_MAX_HOURS, DRY_SPELL_LONG_MIN_HOURS):
                jump = abs(fuzzy_multiplier(centre + eps, i) - fuzzy_multiplier(centre - eps, i))
                self.assertLess(jump, 1e-3)
        for h in (24.0, 240.0, 1080.0):
            for centre in (INTENSITY_LIGHT_MAX_MM_HR, INTENSITY_MODERATE_MAX_MM_HR):
                jump = abs(fuzzy_multiplier(h, centre + eps) - fuzzy_multiplier(h, centre - eps))
                self.assertLess(jump, 1e-3)

    def test_firing_strengths_normalised(self):
        for h, i in [(0, 0), (48, 2.5), (100, 7.0), (720, 7.6), (5000, 99)]:
            w = firing_strengths(h, i)
            self.assertAlmostEqual(sum(sum(r) for r in w), 1.0, places=12)

    def test_custom_table_is_used(self):
        flat = [[2.0] * 3 for _ in range(3)]
        self.assertAlmostEqual(fuzzy_multiplier(100.0, 4.0, table=flat), 2.0)


class TestPlan(unittest.TestCase):
    def test_matches_crisp_plan_at_band_cores(self):
        for d in DrySpellBand:
            for i in IntensityBand:
                a = calculate_diversion_plan(50.0, DRY_REP[d], INT_REP[i])
                b = calculate_fuzzy_diversion_plan(50.0, DRY_REP[d], INT_REP[i])
                self.assertAlmostEqual(a.diversion_volume_liters, b.diversion_volume_liters, places=9)
                self.assertEqual(a.diversion_ticks, b.diversion_ticks)
                self.assertEqual(a.dry_spell_band, b.dry_spell_band)
                self.assertEqual(a.intensity_band, b.intensity_band)

    def test_ticks_at_least_one(self):
        plan = calculate_fuzzy_diversion_plan(0.5, 1.0, 0.1)
        self.assertGreaterEqual(plan.diversion_ticks, 1)

    def test_dominant_band_flips_at_threshold(self):
        below = calculate_fuzzy_diversion_plan(50.0, 47.0, 5.0)
        above = calculate_fuzzy_diversion_plan(50.0, 49.0, 5.0)
        self.assertEqual(below.dry_spell_band, DrySpellBand.SHORT)
        self.assertEqual(above.dry_spell_band, DrySpellBand.MEDIUM)


class TestReporting(unittest.TestCase):
    def test_rule_base_lists_nine_rules(self):
        rules = rule_base_text()
        self.assertEqual(len(rules), 9)
        self.assertIn("IF dry-spell IS LONG AND intensity IS HEAVY THEN multiplier = 1.55", rules[8])

    def test_cpp_export_round_trips_default_table(self):
        text = export_cpp_table(default_table())
        self.assertIn("{0.70f, 0.80f, 0.90f},  // SHORT", text)
        self.assertIn("{1.20f, 1.35f, 1.55f},  // LONG", text)


if __name__ == "__main__":
    unittest.main()
