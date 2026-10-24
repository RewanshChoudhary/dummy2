"""
run_scenarios.py

Decision-logic simulation described in report Section 7.1: works the
dry-spell x intensity scenario matrix (Table 2) through the predictive
algorithm and through the two baselines (fixed-volume, turbidity-only),
then prints and saves a comparison table (feeds Sections 8.1 and 8.2).

Usage:
    python3 run_scenarios.py [--roof-area 50] [--controller crisp|fuzzy] [--csv results.csv] [--plot]

--controller selects which predictive controller is tabulated: the original
banded lookup (default, reproduces the numbers already reported) or the fuzzy
logic controller. At the nine representative Table 2 points the two agree by
construction (each sits in the pure core of its bands); they differ only in
the blend zones near band thresholds - see run_comparison.py for those.

No third-party dependencies are required for the table/CSV output.
--plot needs matplotlib; if it isn't installed the script says so and
skips the chart rather than failing.
"""

import argparse
import csv as csv_module

from baselines import (
    fixed_volume_diversion_liters,
    turbidity_only_diversion_liters,
)
from diverter_logic import (
    DrySpellBand,
    IntensityBand,
    calculate_diversion_plan,
)
from fuzzy_controller import calculate_fuzzy_diversion_plan

CONTROLLERS = {
    "crisp": calculate_diversion_plan,
    "fuzzy": calculate_fuzzy_diversion_plan,
}

# Representative hours/intensity used for each band, chosen from the
# example values given alongside Table 2 in the report.
DRY_SPELL_REPRESENTATIVE_HOURS = {
    DrySpellBand.SHORT: 24.0,       # "< 2 days" -> 1 day
    DrySpellBand.MEDIUM: 10 * 24.0,  # "~1-2 weeks" -> 10 days
    DrySpellBand.LONG: 45 * 24.0,    # "> 1 month" -> 45 days
}

INTENSITY_REPRESENTATIVE_MM_HR = {
    IntensityBand.LIGHT: 1.0,
    IntensityBand.MODERATE: 5.0,
    IntensityBand.HEAVY: 12.0,
}


def build_scenario_matrix():
    """Returns the 9 (dry_spell_band, intensity_band) scenarios of Table 2,
    each with its representative numeric inputs."""
    scenarios = []
    for dry_band in (DrySpellBand.SHORT, DrySpellBand.MEDIUM, DrySpellBand.LONG):
        for int_band in (IntensityBand.LIGHT, IntensityBand.MODERATE, IntensityBand.HEAVY):
            scenarios.append({
                "dry_spell_band": dry_band,
                "intensity_band": int_band,
                "dry_spell_hours": DRY_SPELL_REPRESENTATIVE_HOURS[dry_band],
                "intensity_mm_per_hr": INTENSITY_REPRESENTATIVE_MM_HR[int_band],
            })
    return scenarios


def run(roof_area_m2: float, controller: str = "crisp"):
    plan_fn = CONTROLLERS[controller]
    rows = []
    for scenario in build_scenario_matrix():
        plan = plan_fn(
            roof_area_m2=roof_area_m2,
            dry_spell_hours=scenario["dry_spell_hours"],
            intensity_mm_per_hr=scenario["intensity_mm_per_hr"],
        )
        fixed_liters = fixed_volume_diversion_liters(roof_area_m2)
        turbidity_liters = turbidity_only_diversion_liters(
            dry_spell_hours=scenario["dry_spell_hours"],
            intensity_mm_per_hr=scenario["intensity_mm_per_hr"],
        )

        rows.append({
            "dry_spell_band": scenario["dry_spell_band"].value,
            "intensity_band": scenario["intensity_band"].value,
            "dry_spell_hours": scenario["dry_spell_hours"],
            "intensity_mm_hr": scenario["intensity_mm_per_hr"],
            "predictive_liters": round(plan.diversion_volume_liters, 2),
            "predictive_ticks": plan.diversion_ticks,
            "fixed_volume_liters": round(fixed_liters, 2),
            "turbidity_only_liters": round(turbidity_liters, 2),
            "vs_fixed_pct": round(
                100.0 * (plan.diversion_volume_liters - fixed_liters) / fixed_liters, 1
            ),
        })
    return rows


def print_table(rows):
    headers = [
        "Dry spell", "Intensity", "Predictive (L)", "Predictive (ticks)",
        "Fixed-vol (L)", "Turbidity-only (L)", "Predictive vs fixed",
    ]
    widths = [10, 10, 15, 18, 14, 19, 20]

    def fmt_row(cells):
        return " | ".join(str(c).ljust(w) for c, w in zip(cells, widths))

    print(fmt_row(headers))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(fmt_row([
            r["dry_spell_band"],
            r["intensity_band"],
            r["predictive_liters"],
            r["predictive_ticks"],
            r["fixed_volume_liters"],
            r["turbidity_only_liters"],
            f"{r['vs_fixed_pct']:+.1f}%",
        ]))


def save_csv(rows, path):
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv_module.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} rows to {path}")


def maybe_plot(rows):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed - skipping --plot chart)")
        return

    labels = [f"{r['dry_spell_band']}\n{r['intensity_band']}" for r in rows]
    predictive = [r["predictive_liters"] for r in rows]
    fixed = [r["fixed_volume_liters"] for r in rows]
    turbidity = [r["turbidity_only_liters"] for r in rows]

    x = range(len(rows))
    width = 0.27
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([i - width for i in x], fixed, width, label="Fixed-volume")
    ax.bar(x, predictive, width, label="Predictive (proposed)")
    ax.bar([i + width for i in x], turbidity, width, label="Turbidity-only")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Diverted volume (litres)")
    ax.set_title("Diversion volume by scenario: predictive vs. baselines")
    ax.legend()
    fig.tight_layout()
    out_path = "scenario_comparison.png"
    fig.savefig(out_path, dpi=150)
    print(f"\nSaved chart to {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roof-area", type=float, default=50.0,
                         help="Roof catchment area in square metres (default: 50)")
    parser.add_argument("--controller", choices=sorted(CONTROLLERS), default="crisp",
                         help="Predictive controller to tabulate (default: crisp banded lookup)")
    parser.add_argument("--csv", type=str, default=None,
                         help="Optional path to save results as CSV")
    parser.add_argument("--plot", action="store_true",
                         help="Also save a bar-chart comparison (needs matplotlib)")
    args = parser.parse_args()

    rows = run(args.roof_area, args.controller)

    print(f"Decision-logic simulation - roof area {args.roof_area} sq. m - {args.controller} controller")
    print("=" * 90)
    print_table(rows)

    print(
        "\nReading: 'Predictive vs fixed' is how much more (+) or less (-) the "
        "proposed method diverts compared with a fixed-volume diverter sized "
        "for the same roof. Expect negative values for short dry spells "
        "(avoids wasting water) and positive values for long dry spells "
        "(avoids under-protecting the tank) - see report Section 8.2."
    )

    if args.csv:
        save_csv(rows, args.csv)
    if args.plot:
        maybe_plot(rows)


if __name__ == "__main__":
    main()
