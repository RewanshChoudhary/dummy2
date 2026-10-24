"""
reference_process.py

A synthetic "reference process": given a dry-spell duration and an initial
rain intensity, how much flush depth does a roof actually need to shed before
runoff falls to the clean threshold? It supplies the labels for training the
ML baselines and the ground truth every method is scored against.

IMPORTANT - what this is and is not
-----------------------------------
This is a simulation stand-in, NOT field data. The project is TRL 1 and no
measured turbidity dataset exists, so any accuracy number computed against
this process measures "how well does a method reproduce these stated
assumptions", not "how well does it protect real tank water". The two presets
below encode DIFFERENT assumptions on purpose, so the conclusions can be
checked for sensitivity to them. Replace with logged data when available.

Model (same family as baselines.py's synthetic turbidity curve):

    C0(t, I) = C_BASE * (1 + t / T_BUILD) * (1 + m * I)   initial turbidity, NTU
    k(I)     = K_BASE * (1 + w * I)                       wash-off rate per unit depth
    depth*(t, I) = ln(C0 / C_CLEAN) / k                   depth to reach C_CLEAN

  t = dry-spell hours, I = initial intensity mm/hr. The 'washoff' preset uses
  exactly the constants in baselines.py (m = 0, w = 0.05) so it is the
  project's own existing assumption. The 'mobilisation' preset instead makes
  heavier rain mobilise more of the deposited load (m > 0, w = 0), which is
  the assumption Table 2's multipliers encode (heavier rain -> divert more).

Everything is expressed as a MULTIPLIER relative to a reference scenario
(10-day dry spell, 5 mm/hr), because that is what the controllers output. This
makes the absolute scale (K_BASE, roof size, depth units) cancel out, so only
the *shape* of the response is being compared.
"""

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

import baselines  # single source of truth for the 'washoff' constants

REF_DRY_SPELL_H = 240.0     # 10 days  (Table 2 medium representative)
REF_INTENSITY = 5.0         # mm/hr    (Table 2 moderate representative)

# Sampling box for labelled data (the "field conditions" the ML model can see).
TRAIN_DRY_RANGE_H = (1.0, 1080.0)      # up to 45 days
TRAIN_INTENSITY_RANGE = (0.5, 15.0)    # mm/hr
# Wider box used to probe extrapolation.
WIDE_DRY_RANGE_H = (1.0, 2160.0)       # up to 90 days
WIDE_INTENSITY_RANGE = (0.5, 30.0)


@dataclass(frozen=True)
class ProcessParams:
    name: str
    description: str
    base_ntu: float
    build_scale_h: float
    mobilisation_gain: float      # m: intensity raises initial turbidity
    washoff_base: float           # K_BASE
    washoff_intensity_gain: float  # w: intensity speeds wash-off per unit depth
    clean_ntu: float


PRESETS: Dict[str, ProcessParams] = {
    "washoff": ProcessParams(
        name="washoff",
        description="Project's own baselines.py assumption: heavier rain washes clean in LESS depth.",
        base_ntu=baselines.TURBIDITY_BASE_NTU,
        build_scale_h=baselines.TURBIDITY_DRY_SPELL_SCALE_HOURS,
        mobilisation_gain=0.0,
        washoff_base=baselines.TURBIDITY_DECAY_BASE_PER_LITER,
        washoff_intensity_gain=baselines.TURBIDITY_INTENSITY_WASH_GAIN,
        clean_ntu=baselines.CLEAN_THRESHOLD_NTU,
    ),
    "mobilisation": ProcessParams(
        name="mobilisation",
        description="Table 2's assumption: heavier rain mobilises more load, needing MORE depth.",
        base_ntu=baselines.TURBIDITY_BASE_NTU,
        build_scale_h=baselines.TURBIDITY_DRY_SPELL_SCALE_HOURS,
        mobilisation_gain=0.08,
        washoff_base=baselines.TURBIDITY_DECAY_BASE_PER_LITER,
        washoff_intensity_gain=0.0,
        clean_ntu=baselines.CLEAN_THRESHOLD_NTU,
    ),
}


def required_depth(dry_h, intensity, p: ProcessParams):
    """Flush depth (arbitrary units) to reach the clean threshold. Vectorised."""
    t = np.asarray(dry_h, dtype=float)
    i = np.asarray(intensity, dtype=float)
    c0 = p.base_ntu * (1.0 + t / p.build_scale_h) * (1.0 + p.mobilisation_gain * i)
    k = p.washoff_base * (1.0 + p.washoff_intensity_gain * i)
    return np.maximum(np.log(c0 / p.clean_ntu), 0.0) / k


def true_multiplier(dry_h, intensity, p: ProcessParams):
    """Required depth relative to the reference scenario (=1.0 there)."""
    return required_depth(dry_h, intensity, p) / required_depth(REF_DRY_SPELL_H, REF_INTENSITY, p)


def _log_uniform(rng, lo, hi, n):
    return np.exp(rng.uniform(np.log(lo), np.log(hi), n))


def sample_conditions(n: int, rng, dry_range=TRAIN_DRY_RANGE_H,
                      intensity_range=TRAIN_INTENSITY_RANGE) -> Tuple[np.ndarray, np.ndarray]:
    """Log-uniform draws: real dry spells and intensities are heavily skewed
    towards small values, so a linear-uniform draw would over-sample extremes."""
    return _log_uniform(rng, *dry_range, n), _log_uniform(rng, *intensity_range, n)


def make_labelled_dataset(n: int, p: ProcessParams, rng, noise_sigma: float = 0.10,
                          dry_range=TRAIN_DRY_RANGE_H, intensity_range=TRAIN_INTENSITY_RANGE):
    """(X, y) with X = [[dry_h, intensity], ...] and y = true multiplier with
    multiplicative log-normal label noise (field variability / sensor error)."""
    t, i = sample_conditions(n, rng, dry_range, intensity_range)
    y = true_multiplier(t, i, p) * np.exp(rng.normal(0.0, noise_sigma, n))
    return np.column_stack([t, i]), y


def make_test_sets(p: ProcessParams, rng, n: int = 4000):
    """Noise-free test sets: in-distribution, and out-of-distribution (at
    least one input beyond the training box)."""
    t, i = sample_conditions(n, rng)
    in_dist = (np.column_stack([t, i]), true_multiplier(t, i, p))

    t_w, i_w = sample_conditions(n * 4, rng, WIDE_DRY_RANGE_H, WIDE_INTENSITY_RANGE)
    outside = (t_w > TRAIN_DRY_RANGE_H[1]) | (i_w > TRAIN_INTENSITY_RANGE[1])
    t_w, i_w = t_w[outside][:n], i_w[outside][:n]
    ood = (np.column_stack([t_w, i_w]), true_multiplier(t_w, i_w, p))
    return in_dist, ood
