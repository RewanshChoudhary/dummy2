"""
test_diverter_logic.py

Unit tests for diverter_logic.py. Run with:
    python3 -m unittest test_diverter_logic.py -v
"""

import unittest

from diverter_logic import (
    DIVERSION_MULTIPLIER_TABLE,
    DRY_SPELL_LONG_MIN_HOURS,
    DRY_SPELL_SHORT_MAX_HOURS,
    INTENSITY_LIGHT_MAX_MM_HR,
    INTENSITY_MODERATE_MAX_MM_HR,
    DrySpellBand,
    IntensityBand,
    apply_turbidity_fallback,
    base_volume_liters,
    calculate_diversion_plan,
    classify_dry_spell,
    classify_intensity,
    get_multiplier,
    intensity_from_window,
)


class TestBandClassification(unittest.TestCase):
    def test_dry_spell_bands(self):
        self.assertEqual(classify_dry_spell(0), DrySpellBand.SHORT)
        self.assertEqual(classify_dry_spell(DRY_SPELL_SHORT_MAX_HOURS - 1), DrySpellBand.SHORT)
        self.assertEqual(classify_dry_spell(DRY_SPELL_SHORT_MAX_HOURS), DrySpellBand.MEDIUM)
        self.assertEqual(classify_dry_spell(DRY_SPELL_LONG_MIN_HOURS), DrySpellBand.MEDIUM)
        self.assertEqual(classify_dry_spell(DRY_SPELL_LONG_MIN_HOURS + 1), DrySpellBand.LONG)

    def test_intensity_bands(self):
        self.assertEqual(classify_intensity(0), IntensityBand.LIGHT)
        self.assertEqual(classify_intensity(INTENSITY_LIGHT_MAX_MM_HR - 0.1), IntensityBand.LIGHT)
        self.assertEqual(classify_intensity(INTENSITY_LIGHT_MAX_MM_HR), IntensityBand.MODERATE)
        self.assertEqual(classify_intensity(INTENSITY_MODERATE_MAX_MM_HR), IntensityBand.MODERATE)
        self.assertEqual(classify_intensity(INTENSITY_MODERATE_MAX_MM_HR + 0.1), IntensityBand.HEAVY)


class TestLookupTable(unittest.TestCase):
    def test_monotonic_across_intensity(self):
        for dry_band in DrySpellBand:
            light = get_multiplier(dry_band, IntensityBand.LIGHT)
            moderate = get_multiplier(dry_band, IntensityBand.MODERATE)
            heavy = get_multiplier(dry_band, IntensityBand.HEAVY)
            self.assertLessEqual(light, moderate)
            self.assertLessEqual(moderate, heavy)

    def test_monotonic_across_dry_spell(self):
        for int_band in IntensityBand:
            short = get_multiplier(DrySpellBand.SHORT, int_band)
            medium = get_multiplier(DrySpellBand.MEDIUM, int_band)
            long_ = get_multiplier(DrySpellBand.LONG, int_band)
            self.assertLessEqual(short, medium)
            self.assertLessEqual(medium, long_)

    def test_baseline_case_is_one(self):
        # Medium dry spell + moderate intensity is called out as the
        # "baseline diverted volume" case in Table 2 of the report.
        self.assertEqual(
            DIVERSION_MULTIPLIER_TABLE[DrySpellBand.MEDIUM][IntensityBand.MODERATE], 1.0
        )

    def test_extremes(self):
        smallest = get_multiplier(DrySpellBand.SHORT, IntensityBand.LIGHT)
        largest = get_multiplier(DrySpellBand.LONG, IntensityBand.HEAVY)
        for dry_band in DrySpellBand:
            for int_band in IntensityBand:
                m = get_multiplier(dry_band, int_band)
                self.assertGreaterEqual(m, smallest)
                self.assertLessEqual(m, largest)


class TestDiversionPlan(unittest.TestCase):
    def test_base_volume_scales_with_roof_area(self):
        self.assertAlmostEqual(base_volume_liters(50.0, 1.0), 50.0)
        self.assertAlmostEqual(base_volume_liters(100.0, 1.0), 100.0)

    def test_plan_uses_correct_bands_and_volume(self):
        plan = calculate_diversion_plan(
            roof_area_m2=50.0, dry_spell_hours=10 * 24.0, intensity_mm_per_hr=5.0
        )
        self.assertEqual(plan.dry_spell_band, DrySpellBand.MEDIUM)
        self.assertEqual(plan.intensity_band, IntensityBand.MODERATE)
        self.assertAlmostEqual(plan.multiplier, 1.0)
        self.assertAlmostEqual(plan.base_volume_liters, 50.0)
        self.assertAlmostEqual(plan.diversion_volume_liters, 50.0)

    def test_plan_ticks_are_at_least_one(self):
        plan = calculate_diversion_plan(
            roof_area_m2=0.5, dry_spell_hours=1.0, intensity_mm_per_hr=0.1
        )
        self.assertGreaterEqual(plan.diversion_ticks, 1)

    def test_long_heavy_diverts_more_than_short_light(self):
        small = calculate_diversion_plan(50.0, dry_spell_hours=1.0, intensity_mm_per_hr=0.5)
        large = calculate_diversion_plan(50.0, dry_spell_hours=45 * 24.0, intensity_mm_per_hr=12.0)
        self.assertGreater(large.diversion_volume_liters, small.diversion_volume_liters)


class TestTickRounding(unittest.TestCase):
    def test_ties_round_up_to_match_firmware(self):
        # 45 L on a 50 m2 roof with 0.2 mm/tip = 4.5 ticks. The firmware's
        # lroundf() gives 5; Python's built-in round() would give 4.
        plan = calculate_diversion_plan(50.0, dry_spell_hours=24.0, intensity_mm_per_hr=12.0)
        self.assertAlmostEqual(plan.diversion_volume_liters, 45.0)
        self.assertEqual(plan.diversion_ticks, 5)


class TestIntensityMeasurement(unittest.TestCase):
    def test_trigger_excluded_from_window(self):
        # A single event-trigger tip must not force an 8 mm/hr estimate.
        self.assertEqual(intensity_from_window(0, 5 * 60 * 1000), 0.0)
        self.assertAlmostEqual(intensity_from_window(1, 5 * 60 * 1000), 2.4)
        self.assertEqual(classify_intensity(intensity_from_window(1, 5 * 60 * 1000)),
                         IntensityBand.LIGHT)

    def test_window_must_be_positive(self):
        with self.assertRaises(ValueError):
            intensity_from_window(1, 0)


class TestTurbidityFallback(unittest.TestCase):
    def test_no_extension_when_already_clean(self):
        volume, extensions = apply_turbidity_fallback(
            diversion_volume_liters=50.0,
            turbidity_reader=lambda v: 1.0,  # always reads clean
        )
        self.assertEqual(volume, 50.0)
        self.assertEqual(extensions, 0)

    def test_extends_until_clean_or_capped(self):
        # Reading only drops below threshold after the second extension.
        readings = iter([20.0, 10.0, 2.0])
        volume, extensions = apply_turbidity_fallback(
            diversion_volume_liters=50.0,
            turbidity_reader=lambda v: next(readings),
        )
        self.assertEqual(extensions, 2)
        self.assertGreater(volume, 50.0)

    def test_never_exceeds_max_extensions(self):
        volume, extensions = apply_turbidity_fallback(
            diversion_volume_liters=50.0,
            turbidity_reader=lambda v: 999.0,  # never clean
            max_extensions=3,
        )
        self.assertEqual(extensions, 3)


if __name__ == "__main__":
    unittest.main()
