"""
run_comparison.py

Head-to-head evaluation of the fuzzy logic controller (FLC) against the
existing banded lookup, the fixed-volume baseline and machine-learning
baselines. Complements run_scenarios.py (which works the 9 Table 2 cases).

Experiments
  A  Sensor-noise sensitivity   - how much does each controller's output move
                                  when its inputs are noisy? (needs no ground
                                  truth, so it does not depend on any assumption)
  B  Accuracy vs reference      - error against the synthetic reference process
                                  (reference_process.py), in-distribution and
                                  out-of-distribution, plus model footprint
  C  Learning curve             - accuracy vs number of labelled examples
  D  Intensity estimator check  - can the firmware's trigger-excluded window
                                  actually distinguish the intensity bands?

Usage (from simulation/):
    python3 run_comparison.py                # full run (a few minutes)
    python3 run_comparison.py --quick        # fewer seeds / sizes (~1 min)
    python3 run_comparison.py --outdir out   # where CSVs and PNGs are written

Requires numpy and scikit-learn; matplotlib is optional (figures are skipped
with a notice if it is missing).
"""

import argparse
import csv
import os
import sys

import numpy as np

from diverter_logic import (
    DRY_SPELL_LONG_MIN_HOURS,
    DRY_SPELL_SHORT_MAX_HOURS,
    INTENSITY_LIGHT_MAX_MM_HR,
    INTENSITY_MODERATE_MAX_MM_HR,
    RAIN_GAUGE_MM_PER_TIP,
    classify_dry_spell,
    classify_intensity,
    get_multiplier,
    intensity_from_window,
)
from fuzzy_controller import DEFAULT_CONFIG, fuzzy_multiplier
from ml_baseline import (
    ML_MODEL_NAMES,
    banded_predictor,
    data_free_predictors,
    error_metrics,
    fit_all,
    flc_predictor,
    footprint_bytes,
)
from reference_process import (
    PRESETS,
    TRAIN_DRY_RANGE_H,
    TRAIN_INTENSITY_RANGE,
    make_labelled_dataset,
    make_test_sets,
    sample_conditions,
    true_multiplier,
)

BASE_SEED = 20240920
ALL_METHODS = ["Fixed volume", "Banded table (current)", "FLC (expert)", "FLC (data-tuned)"] + ML_MODEL_NAMES


def hr(title):
    print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)


def save_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  -> saved {path}")


# ---------------------------------------------------------------------------
# Experiment A - sensor-noise sensitivity (assumption-free)
# ---------------------------------------------------------------------------

def experiment_noise(outdir, n_points=4000, n_draws=5, sigma_dry=0.10, sigma_int=0.30):
    hr("A. Sensor-noise sensitivity (no ground truth needed)")
    print(f"Inputs perturbed by log-normal noise: dry-spell sigma={sigma_dry:.0%}, intensity sigma={sigma_int:.0%}.")
    print("Metric: |multiplier(noisy input) - multiplier(clean input)| for the SAME controller,")
    print(f"over {n_points} operating points sampled across the training box.\n")

    rng = np.random.default_rng(BASE_SEED)
    t, i = sample_conditions(n_points, rng)
    clean_in = np.column_stack([t, i])

    controllers = {"Banded table (current)": banded_predictor()}
    for scale in (0.5, 1.0, 2.0):
        controllers[f"FLC width x{scale:g}"] = flc_predictor(DEFAULT_CONFIG.scaled(scale))

    rows = []
    print(f"{'controller':26s} {'mean':>7s} {'p95':>7s} {'max':>7s}")
    for name, f in controllers.items():
        base = f(clean_in)
        deltas = []
        for _ in range(n_draws):
            noisy = np.column_stack([t * np.exp(rng.normal(0, sigma_dry, n_points)),
                                     i * np.exp(rng.normal(0, sigma_int, n_points))])
            deltas.append(np.abs(f(noisy) - base))
        d = np.concatenate(deltas)
        row = {"controller": name, "mean": d.mean(), "p95": np.percentile(d, 95), "max": d.max()}
        rows.append(row)
        print(f"{name:26s} {row['mean']:7.3f} {row['p95']:7.3f} {row['max']:7.3f}")

    # Largest one-step jump when an input moves only 1% across a crisp threshold.
    def worst_jump(fn):
        j = 0.0
        for h_c in (DRY_SPELL_SHORT_MAX_HOURS, DRY_SPELL_LONG_MIN_HOURS):
            for i_v in (1.0, 5.0, 12.0):
                j = max(j, abs(fn(h_c * 1.01, i_v) - fn(h_c * 0.99, i_v)))
        for i_c in (INTENSITY_LIGHT_MAX_MM_HR, INTENSITY_MODERATE_MAX_MM_HR):
            for h_v in (24.0, 240.0, 1080.0):
                j = max(j, abs(fn(h_v, i_c * 1.01) - fn(h_v, i_c * 0.99)))
        return j

    crisp = lambda h, i_: get_multiplier(classify_dry_spell(h), classify_intensity(i_))
    fuzzy = lambda h, i_: fuzzy_multiplier(h, i_)
    print(f"\nWorst multiplier change from a 1% input change straddling a band threshold:")
    print(f"  banded table {worst_jump(crisp):.3f}   |   FLC {worst_jump(fuzzy):.3f}")
    save_csv(os.path.join(outdir, "noise_sensitivity.csv"), rows)
    return rows


# ---------------------------------------------------------------------------
# Experiment B - accuracy vs reference process + footprint
# ---------------------------------------------------------------------------

def experiment_accuracy(outdir, n_train=200, seeds=10, noise_sigma=0.10):
    hr("B. Accuracy against the synthetic reference process")
    print("'predicted range' is the min/max multiplier each method emitted over all test points and seeds")
    print("(a bounded range is a safety property: the flush can never be planned absurdly small or large).")
    print(f"Trainable methods fit on {n_train} noisy labelled examples (label noise sigma={noise_sigma:.0%}),")
    print(f"mean over {seeds} training seeds. Test sets are noise-free. Errors are in multiplier units")
    print("(1.00 = the reference 10-day / 5 mm/hr flush). Shortfall = under-diverting, Excess = over-diverting.\n")

    all_rows = []
    for pname, p in PRESETS.items():
        print(f"--- reference preset '{pname}': {p.description}")
        in_dist, ood = make_test_sets(p, np.random.default_rng(BASE_SEED + 1))
        acc = {m: {"in": [], "ood": [], "short": [], "excess": [], "bytes": None,
                   "lo": np.inf, "hi": -np.inf} for m in ALL_METHODS}
        free = data_free_predictors()

        for s in range(seeds):
            rng = np.random.default_rng(BASE_SEED + 100 + s)
            X, y = make_labelled_dataset(n_train, p, rng, noise_sigma)
            trained = fit_all(X, y, seed=s)
            preds = {**free, **trained}
            for m in ALL_METHODS:
                a = error_metrics(preds[m](in_dist[0]), in_dist[1])
                b = error_metrics(preds[m](ood[0]), ood[1])
                acc[m]["in"].append(a["mae"])
                acc[m]["ood"].append(b["mae"])
                acc[m]["short"].append(a["shortfall"])
                acc[m]["excess"].append(a["excess"])
                both = np.concatenate([preds[m](in_dist[0]), preds[m](ood[0])])
                acc[m]["lo"] = min(acc[m]["lo"], both.min())   # worst case across seeds
                acc[m]["hi"] = max(acc[m]["hi"], both.max())
            if s == 0:
                # footprint needs the fitted sklearn objects, not just predict()
                from ml_baseline import make_ml_model, fit_tuned_flc  # noqa: F401
                fitted = {}
                for name in ML_MODEL_NAMES:
                    mdl = make_ml_model(name, 0)
                    mdl.fit(X, y)
                    fitted[name] = mdl
                for m in ALL_METHODS:
                    acc[m]["bytes"] = footprint_bytes(m, fitted)

        print(f"{'method':26s} {'in-dist MAE':>14s} {'OOD MAE':>10s} {'shortfall':>10s} {'excess':>8s} {'~bytes':>8s}  predicted range")
        for m in ALL_METHODS:
            a = acc[m]
            print(f"{m:26s} {np.mean(a['in']):8.3f}±{np.std(a['in']):.3f} {np.mean(a['ood']):10.3f}"
                  f" {np.mean(a['short']):10.3f} {np.mean(a['excess']):8.3f} {a['bytes']:8d}  [{a['lo']:.2f}, {a['hi']:.2f}]")
            all_rows.append({
                "preset": pname, "method": m, "n_train": n_train if m not in
                ("Fixed volume", "Banded table (current)", "FLC (expert)") else 0,
                "in_dist_mae": np.mean(a["in"]), "in_dist_mae_std": np.std(a["in"]),
                "ood_mae": np.mean(a["ood"]), "shortfall": np.mean(a["short"]),
                "excess": np.mean(a["excess"]), "approx_bytes": a["bytes"],
                "pred_min": a["lo"], "pred_max": a["hi"],
            })
        print()
    save_csv(os.path.join(outdir, "accuracy_table.csv"), all_rows)
    return all_rows


# ---------------------------------------------------------------------------
# Experiment C - learning curve
# ---------------------------------------------------------------------------

def experiment_learning_curve(outdir, sizes, seeds, noise_sigma=0.10):
    hr("C. Learning curve: in-distribution MAE vs number of labelled examples")
    rows = []
    for pname, p in PRESETS.items():
        in_dist, _ = make_test_sets(p, np.random.default_rng(BASE_SEED + 1))
        free = data_free_predictors()
        free_mae = {m: error_metrics(f(in_dist[0]), in_dist[1])["mae"] for m, f in free.items()}
        print(f"--- preset '{pname}' (data-free: " +
              ", ".join(f"{m} {v:.3f}" for m, v in free_mae.items()) + ")")
        trainable = ["FLC (data-tuned)"] + ML_MODEL_NAMES
        print(f"{'N':>6s} " + " ".join(f"{m[:14]:>14s}" for m in trainable))
        for n in sizes:
            maes = {m: [] for m in trainable}
            for s in range(seeds):
                rng = np.random.default_rng(BASE_SEED + 1000 * n + s)
                X, y = make_labelled_dataset(n, p, rng, noise_sigma)
                trained = fit_all(X, y, seed=s)
                for m in trainable:
                    maes[m].append(error_metrics(trained[m](in_dist[0]), in_dist[1])["mae"])
            print(f"{n:6d} " + " ".join(f"{np.mean(maes[m]):14.3f}" for m in trainable))
            for m in trainable:
                rows.append({"preset": pname, "n_train": n, "method": m,
                             "mae_mean": np.mean(maes[m]), "mae_std": np.std(maes[m])})
        for m, v in free_mae.items():
            rows.append({"preset": pname, "n_train": 0, "method": m, "mae_mean": v, "mae_std": 0.0})
        print()
    save_csv(os.path.join(outdir, "learning_curve.csv"), rows)
    return rows


# ---------------------------------------------------------------------------
# Experiment D - can the firmware estimator resolve the intensity bands?
# ---------------------------------------------------------------------------

def experiment_estimator(window_s=300.0, trials=20000):
    hr("D. Firmware intensity-estimator check (5 min window, trigger tip excluded)")
    print(f"Poisson tip arrivals at the true intensity, gauge resolution {RAIN_GAUGE_MM_PER_TIP} mm/tip.")
    print("Estimate = tips arriving AFTER event start / window * mm_per_tip * 60, exactly as firmware computes it.\n")
    rng = np.random.default_rng(BASE_SEED)
    print(f"{'true mm/hr':>10s} {'true band':>10s} {'mean est':>9s} {'P(LIGHT)':>9s} {'P(MOD)':>8s} {'P(HEAVY)':>9s}")
    for true in (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0):
        lam = true / (RAIN_GAUGE_MM_PER_TIP * 3600.0) * window_s
        est = np.array([intensity_from_window(tips, int(window_s * 1000))
                        for tips in rng.poisson(lam, trials)])
        bands = np.array([classify_intensity(v).value for v in est])
        print(f"{true:10.1f} {classify_intensity(true).value:>10s} {est.mean():9.1f} "
              f"{(bands == 'light').mean():9.2f} {(bands == 'moderate').mean():8.2f} {(bands == 'heavy').mean():9.2f}")
    print("\nThe initiating tip is retained for diversion-volume counting but excluded from the rate window.")
    print("At 5 minutes each observed tip equals 2.4 mm/hr, so all three controller bands are reachable.")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def make_figures(outdir, lc_rows):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed - skipping figures)")
        return

    # 1. Response surfaces
    ts = np.exp(np.linspace(np.log(1), np.log(2160), 120))
    is_ = np.exp(np.linspace(np.log(0.5), np.log(30), 120))
    T, I = np.meshgrid(ts, is_)
    grid = np.column_stack([T.ravel(), I.ravel()])
    panels = [
        ("Banded table (current)", banded_predictor()(grid)),
        ("FLC (expert)", flc_predictor()(grid)),
        ("Reference: 'mobilisation'", true_multiplier(grid[:, 0], grid[:, 1], PRESETS["mobilisation"])),
        ("Reference: 'washoff' (baselines.py)", true_multiplier(grid[:, 0], grid[:, 1], PRESETS["washoff"])),
    ]
    vmin = min(p[1].min() for p in panels)
    vmax = max(p[1].max() for p in panels)
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True, sharey=True)
    for ax, (title, z) in zip(axes.ravel(), panels):
        im = ax.pcolormesh(T, I, z.reshape(T.shape), shading="auto", vmin=vmin, vmax=vmax, cmap="viridis")
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_title(title, fontsize=10)
    for ax in axes[1]:
        ax.set_xlabel("dry-spell (hours)")
    for ax in axes[:, 0]:
        ax.set_ylabel("initial intensity (mm/hr)")
    fig.colorbar(im, ax=axes, label="diversion multiplier", shrink=0.85)
    fig.suptitle("Diversion multiplier surfaces")
    p1 = os.path.join(outdir, "surfaces.png")
    fig.savefig(p1, dpi=150); plt.close(fig); print(f"  -> saved {p1}")

    # 2. 1-D slices: staircase vs smooth
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    for ax, sweep, fixed, xlabel, which in (
        (a1, ts, 5.0, "dry-spell (hours), intensity fixed at 5 mm/hr", "dry"),
        (a2, is_, 240.0, "intensity (mm/hr), dry-spell fixed at 240 h", "int"),
    ):
        pts = [(x, fixed) if which == "dry" else (fixed, x) for x in sweep]
        ax.plot(sweep, banded_predictor()(np.array(pts)), drawstyle="steps-post", label="Banded table", lw=2)
        ax.plot(sweep, flc_predictor()(np.array(pts)), label="FLC (expert)", lw=2)
        for pname, style in (("mobilisation", "--"), ("washoff", ":")):
            xs = np.array(pts)
            ax.plot(sweep, true_multiplier(xs[:, 0], xs[:, 1], PRESETS[pname]), style, color="gray",
                    label=f"Reference '{pname}'")
        ax.set_xscale("log"); ax.set_xlabel(xlabel); ax.set_ylabel("multiplier"); ax.grid(alpha=0.3)
    a1.legend(fontsize=8)
    p2 = os.path.join(outdir, "slices.png")
    fig.tight_layout(); fig.savefig(p2, dpi=150); plt.close(fig); print(f"  -> saved {p2}")

    # 3. Learning curves
    if lc_rows:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
        for ax, pname in zip(axes, PRESETS):
            rows = [r for r in lc_rows if r["preset"] == pname]
            for m in ["FLC (data-tuned)"] + ML_MODEL_NAMES:
                pts = sorted((r["n_train"], r["mae_mean"]) for r in rows if r["method"] == m)
                ax.plot(*zip(*pts), marker="o", ms=3, label=m)
            for m, style in (("Fixed volume", ":"), ("Banded table (current)", "--"), ("FLC (expert)", "-.")):
                v = next(r["mae_mean"] for r in rows if r["method"] == m)
                ax.axhline(v, linestyle=style, color="black", alpha=0.6, lw=1, label=m + " (no data)")
            ax.set_xscale("log"); ax.set_yscale("log"); ax.grid(alpha=0.3, which="both")
            ax.set_xlabel("labelled training examples"); ax.set_title(f"reference '{pname}'", fontsize=10)
        axes[0].set_ylabel("in-distribution MAE (multiplier)")
        axes[1].legend(fontsize=7, loc="upper right")
        p3 = os.path.join(outdir, "learning_curve.png")
        fig.tight_layout(); fig.savefig(p3, dpi=150); plt.close(fig); print(f"  -> saved {p3}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", default="results")
    ap.add_argument("--quick", action="store_true", help="fewer seeds and sizes")
    ap.add_argument("--seeds", type=int, default=None)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    seeds = args.seeds or (3 if args.quick else 10)
    sizes = [8, 20, 50, 120, 250] if args.quick else [8, 15, 30, 60, 120, 250, 500, 1000]

    experiment_noise(args.outdir)
    experiment_accuracy(args.outdir, seeds=seeds)
    lc = experiment_learning_curve(args.outdir, sizes, seeds)
    experiment_estimator()
    hr("Figures")
    make_figures(args.outdir, lc)
    print("\nCaveat: experiments B and C score methods against a SYNTHETIC reference process, not field data.")
    print("They test sensitivity to stated assumptions; see reference_process.py.")


if __name__ == "__main__":
    sys.exit(main())
