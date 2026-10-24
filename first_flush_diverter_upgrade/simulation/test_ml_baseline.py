"""
test_ml_baseline.py

Tests for reference_process.py and ml_baseline.py. Skipped automatically if
numpy / scikit-learn are not installed. Run with:
    python3 -m unittest test_ml_baseline.py -v
"""

import unittest

try:
    import numpy as np
    import sklearn  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

if HAVE_DEPS:
    from fuzzy_controller import default_table, fuzzy_multiplier
    from ml_baseline import (MULTIPLIER_BOUNDS, design_matrix, error_metrics, fit_all,
                             fit_tuned_flc, footprint_bytes)
    from reference_process import (PRESETS, REF_DRY_SPELL_H, REF_INTENSITY, TRAIN_DRY_RANGE_H,
                                   TRAIN_INTENSITY_RANGE, make_labelled_dataset, make_test_sets,
                                   true_multiplier)


@unittest.skipUnless(HAVE_DEPS, "numpy/scikit-learn not installed")
class TestReferenceProcess(unittest.TestCase):
    def test_reference_scenario_is_one(self):
        for p in PRESETS.values():
            self.assertAlmostEqual(float(true_multiplier(REF_DRY_SPELL_H, REF_INTENSITY, p)), 1.0)

    def test_longer_dry_spell_needs_more_in_both_presets(self):
        t = np.linspace(1, 2000, 200)
        for p in PRESETS.values():
            m = true_multiplier(t, 5.0, p)
            self.assertTrue(np.all(np.diff(m) > 0))

    def test_presets_disagree_on_intensity_direction_by_design(self):
        i = np.linspace(0.5, 30, 100)
        up = true_multiplier(240.0, i, PRESETS["mobilisation"])
        down = true_multiplier(240.0, i, PRESETS["washoff"])
        self.assertTrue(np.all(np.diff(up) > 0))
        self.assertTrue(np.all(np.diff(down) < 0))

    def test_datasets_are_reproducible_and_in_range(self):
        p = PRESETS["mobilisation"]
        X1, y1 = make_labelled_dataset(50, p, np.random.default_rng(3))
        X2, y2 = make_labelled_dataset(50, p, np.random.default_rng(3))
        np.testing.assert_array_equal(X1, X2)
        np.testing.assert_array_equal(y1, y2)
        self.assertTrue(np.all((X1[:, 0] >= TRAIN_DRY_RANGE_H[0]) & (X1[:, 0] <= TRAIN_DRY_RANGE_H[1])))
        self.assertTrue(np.all((X1[:, 1] >= TRAIN_INTENSITY_RANGE[0]) & (X1[:, 1] <= TRAIN_INTENSITY_RANGE[1])))

    def test_ood_set_really_is_outside_training_box(self):
        _, (Xo, _) = make_test_sets(PRESETS["washoff"], np.random.default_rng(0), n=300)
        outside = (Xo[:, 0] > TRAIN_DRY_RANGE_H[1]) | (Xo[:, 1] > TRAIN_INTENSITY_RANGE[1])
        self.assertTrue(np.all(outside))


@unittest.skipUnless(HAVE_DEPS, "numpy/scikit-learn not installed")
class TestTunedFLC(unittest.TestCase):
    def test_design_matrix_rows_sum_to_one(self):
        X = np.array([[10.0, 1.0], [48.0, 2.5], [900.0, 20.0]])
        np.testing.assert_allclose(design_matrix(X).sum(axis=1), 1.0)

    def test_recovers_known_table_from_noise_free_data(self):
        truth = [[0.9, 1.0, 1.1], [1.0, 1.2, 1.3], [1.1, 1.4, 1.8]]
        rng = np.random.default_rng(0)
        t = np.exp(rng.uniform(0, np.log(2000), 3000))
        i = np.exp(rng.uniform(np.log(0.3), np.log(30), 3000))
        y = np.array([fuzzy_multiplier(a, b, table=truth) for a, b in zip(t, i)])
        fitted = fit_tuned_flc(np.column_stack([t, i]), y, prior_strength=1e-6)
        np.testing.assert_allclose(fitted, truth, atol=1e-3)

    def test_no_data_falls_back_towards_expert_table(self):
        # With one example and a strong prior, the fit should barely move.
        fitted = fit_tuned_flc(np.array([[100.0, 5.0]]), np.array([1.4]), prior_strength=1e6)
        np.testing.assert_allclose(fitted, default_table(), atol=1e-3)

    def test_consequents_clipped_to_safety_bounds(self):
        X = np.array([[24.0, 1.0]] * 20)
        fitted = np.array(fit_tuned_flc(X, np.full(20, 50.0), prior_strength=1e-9))
        self.assertLessEqual(fitted.max(), MULTIPLIER_BOUNDS[1])
        self.assertGreaterEqual(fitted.min(), MULTIPLIER_BOUNDS[0])


@unittest.skipUnless(HAVE_DEPS, "numpy/scikit-learn not installed")
class TestModelsAndMetrics(unittest.TestCase):
    def test_all_models_fit_and_predict_finite_values(self):
        X, y = make_labelled_dataset(120, PRESETS["mobilisation"], np.random.default_rng(1))
        preds = fit_all(X, y, seed=0)
        self.assertEqual(len(preds), 5)
        for name, f in preds.items():
            out = f(X)
            self.assertEqual(out.shape, (120,), name)
            self.assertTrue(np.all(np.isfinite(out)), name)

    def test_error_metrics_split_shortfall_and_excess(self):
        m = error_metrics(np.array([0.8, 1.2]), np.array([1.0, 1.0]))
        self.assertAlmostEqual(m["mae"], 0.2)
        self.assertAlmostEqual(m["shortfall"], 0.1)   # (0.2 + 0) / 2
        self.assertAlmostEqual(m["excess"], 0.1)

    def test_forest_is_far_larger_than_flc(self):
        from ml_baseline import make_ml_model
        X, y = make_labelled_dataset(200, PRESETS["washoff"], np.random.default_rng(2))
        fitted = {}
        for n in ("Random forest (100)", "MLP (8-8)", "Decision tree (depth 5)", "Poly ridge (deg 2)"):
            fitted[n] = make_ml_model(n, 0).fit(X, y)
        flc = footprint_bytes("FLC (expert)", fitted)
        self.assertGreater(footprint_bytes("Random forest (100)", fitted), 100 * flc)


if __name__ == "__main__":
    unittest.main()
