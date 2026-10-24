"""
parity_check.py

Verifies that the firmware C++ (diverter_logic.cpp, fuzzy_controller.cpp) and
the Python simulation produce the same results. The firmware sources are
compiled unchanged with g++ and run over a grid that deliberately includes
every band threshold and blend-zone edge.

Usage (from the simulation/ directory):
    python3 parity_check.py

Exit code 0 = parity, 1 = mismatch, 2 = no C++ compiler available.
Multipliers may differ by float32-vs-float64 rounding (tolerance 1e-4).
Tick counts must match exactly, except where the un-rounded value is within
1e-4 of (but not exactly on) a .5 boundary, where float32 rounding can
legitimately tip either way. Exact ties such as 4.5 are never exempted.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from diverter_logic import (
    RAIN_GAUGE_MM_PER_TIP,
    calculate_diversion_plan,
)
from fuzzy_controller import DRY_ORDER, INT_ORDER, calculate_fuzzy_diversion_plan

HERE = Path(__file__).resolve().parent
FIRMWARE = HERE.parent / "firmware" / "first_flush_diverter"
MULT_TOL = 1e-4


def build_grid():
    dry = [0, 1, 12, 23.9, 24, 24.1, 47.9, 48, 48.1, 60, 71.9, 72, 100, 240, 479, 480, 481,
           700, 719.9, 720, 720.1, 959, 960, 961, 1080, 2000, 5000]
    inten = [0, 0.3, 1.0, 1.49, 1.5, 1.51, 2.0, 2.49, 2.5, 2.51, 3.4, 3.5, 3.6, 5.0,
             6.4, 6.5, 6.6, 7.5, 7.6, 7.61, 8.0, 8.69, 8.7, 8.8, 12.0, 25.0, 60.0]
    return [(h, i, roof) for roof in (50.0, 120.0) for h in dry for i in inten]


def main() -> int:
    gxx = shutil.which("g++") or shutil.which("c++")
    if not gxx:
        print("No C++ compiler found; skipping parity check.")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "harness"
        cmd = [gxx, "-std=c++11", "-O0", f"-I{FIRMWARE}", str(HERE / "parity_harness.cpp"),
               str(FIRMWARE / "diverter_logic.cpp"), str(FIRMWARE / "fuzzy_controller.cpp"),
               "-o", str(exe)]
        build = subprocess.run(cmd, capture_output=True, text=True)
        if build.returncode != 0:
            print(build.stderr)
            return 1

        grid = build_grid()
        stdin = "\n".join(f"{h} {i} {r}" for h, i, r in grid) + "\n"
        run = subprocess.run([str(exe)], input=stdin, capture_output=True, text=True, check=True)

    lines = run.stdout.strip().splitlines()
    assert len(lines) == len(grid), "harness output length mismatch"

    problems = []
    for (h, i, roof), line in zip(grid, lines):
        cm, ct, fm, ft, fdb, fib = line.split()
        cm, fm, ct, ft, fdb, fib = float(cm), float(fm), int(ct), int(ft), int(fdb), int(fib)

        py_c = calculate_diversion_plan(roof, h, i)
        py_f = calculate_fuzzy_diversion_plan(roof, h, i)

        def near_tie(volume):
            # Only a value that is CLOSE to but not exactly on a .5 boundary may
            # legitimately round differently in float32. An EXACT tie (e.g. 4.5)
            # must round identically in both, so it is never exempted.
            x = volume / (roof * RAIN_GAUGE_MM_PER_TIP)
            gap = abs((x - int(x)) - 0.5)
            return 0.0 < gap < 1e-4

        if abs(cm - py_c.multiplier) > MULT_TOL:
            problems.append(f"crisp multiplier  h={h} i={i}: C++ {cm:.6f} vs Py {py_c.multiplier:.6f}")
        if ct != py_c.diversion_ticks and not near_tie(py_c.diversion_volume_liters):
            problems.append(f"crisp ticks       h={h} i={i}: C++ {ct} vs Py {py_c.diversion_ticks}")
        if abs(fm - py_f.multiplier) > MULT_TOL:
            problems.append(f"fuzzy multiplier  h={h} i={i}: C++ {fm:.6f} vs Py {py_f.multiplier:.6f}")
        if ft != py_f.diversion_ticks and not near_tie(py_f.diversion_volume_liters):
            problems.append(f"fuzzy ticks       h={h} i={i}: C++ {ft} vs Py {py_f.diversion_ticks}")
        if DRY_ORDER[fdb] != py_f.dry_spell_band or INT_ORDER[fib] != py_f.intensity_band:
            # Dominant band can legitimately differ only at an exact tie.
            problems.append(f"fuzzy dominant band h={h} i={i}: C++ ({fdb},{fib}) vs Py "
                            f"({py_f.dry_spell_band.name},{py_f.intensity_band.name})")

    print(f"Compared {len(grid)} operating points (crisp + fuzzy, multiplier / ticks / band).")
    if problems:
        print(f"{len(problems)} MISMATCH(ES):")
        for p in problems[:25]:
            print("  " + p)
        return 1
    print("Firmware C++ and Python agree on every point.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
