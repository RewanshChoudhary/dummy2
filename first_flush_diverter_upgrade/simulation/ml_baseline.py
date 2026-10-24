"""
ml_baseline.py

Machine-learning baselines for the Adaptive First-Flush Diverter, and a
data-tuned variant of the fuzzy controller, all predicting the same quantity
the controllers output: the diversion MULTIPLIER as a function of
(dry-spell hours, initial intensity mm/hr).

Methods (all share the interface  predict(X) -> multipliers, X = [[hours, mm/hr], ...]):

  Fixed volume            multiplier = 1 (mechanical float diverter, Sec 3.1)
  Banded table            existing Section 5.1.3 lookup
  FLC (expert)            fuzzy_controller with the Table 2 consequents; needs NO data
  FLC (data-tuned)        same FLC, consequents refitted by ridge least squares
  Poly ridge (deg 2)     6-coefficient quadratic surface
  Decision tree (depth 5) embeddable as nested if/else
  MLP (8-8)               small neural network, ~100 weights
  Random forest (100)     high-accuracy but heavyweight reference

The ML models receive the raw two features with standard scaling and NO
domain knowledge; the FLC embeds domain knowledge in its membership
functions and rule structure. That asymmetry is the point of the comparison.

Needs numpy + scikit-learn (only for this module; the controllers themselves
have no third-party dependencies).
"""

import warnings
from typing import Callable, Dict, List, Sequence

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.tree import DecisionTreeRegressor

from diverter_logic import classify_dry_spell, classify_intensity, get_multiplier
from fuzzy_controller import (
    DEFAULT_CONFIG,
    FuzzyConfig,
    default_table,
    firing_strengths,
    fuzzy_multiplier,
)

# Safety bounds on any tuned consequent: never plan less than half or more
# than double the base flush, whatever a noisy fit suggests.
MULTIPLIER_BOUNDS = (0.5, 2.0)

ML_MODEL_NAMES = ["Poly ridge (deg 2)", "Decision tree (depth 5)", "MLP (8-8)", "Random forest (100)"]

Predictor = Callable[[np.ndarray], np.ndarray]


# --------------------------------------------------------------------------
# Data-tuned FLC
# --------------------------------------------------------------------------

def design_matrix(X: np.ndarray, cfg: FuzzyConfig = DEFAULT_CONFIG) -> np.ndarray:
    """N x 9 matrix of normalised rule firing strengths (row-major over the
    3x3 rule grid). Because Sugeno output = design_matrix @ consequents, the
    consequents are a LINEAR least-squares problem."""
    return np.array([np.ravel(firing_strengths(h, i, cfg)) for h, i in X])


def fit_tuned_flc(X: np.ndarray, y: np.ndarray, cfg: FuzzyConfig = DEFAULT_CONFIG,
                  prior_strength: float = 1.0) -> List[List[float]]:
    """Refit the nine rule consequents to labelled data.

    Solves  min_z ||Phi z - y||^2 + prior_strength * ||z - z0||^2  in closed form,
    where z0 is the expert Table 2. With little data the result stays close to
    the expert table; with plenty it follows the data. Result is clipped to
    MULTIPLIER_BOUNDS and returned as a 3x3 table usable anywhere a Table 2 is
    (fuzzy_multiplier(..., table=...), export_cpp_table(...))."""
    phi = design_matrix(X, cfg)
    z0 = np.ravel(default_table())
    a = phi.T @ phi + prior_strength * np.eye(9)
    b = phi.T @ y + prior_strength * z0
    z = np.clip(np.linalg.solve(a, b), *MULTIPLIER_BOUNDS)
    return z.reshape(3, 3).tolist()


# --------------------------------------------------------------------------
# Predictors
# --------------------------------------------------------------------------

def fixed_predictor() -> Predictor:
    return lambda X: np.ones(len(X))


def banded_predictor() -> Predictor:
    return lambda X: np.array([get_multiplier(classify_dry_spell(h), classify_intensity(i)) for h, i in X])


def flc_predictor(cfg: FuzzyConfig = DEFAULT_CONFIG, table=None) -> Predictor:
    return lambda X: np.array([fuzzy_multiplier(h, i, cfg, table) for h, i in X])


def make_ml_model(name: str, seed: int):
    if name == "Poly ridge (deg 2)":
        return make_pipeline(StandardScaler(), PolynomialFeatures(2), Ridge(alpha=1e-3))
    if name == "Decision tree (depth 5)":
        return DecisionTreeRegressor(max_depth=5, min_samples_leaf=2, random_state=seed)
    if name == "MLP (8-8)":
        return make_pipeline(StandardScaler(), MLPRegressor(
            hidden_layer_sizes=(8, 8), activation="tanh", solver="lbfgs",
            max_iter=2000, random_state=seed))
    if name == "Random forest (100)":
        return RandomForestRegressor(n_estimators=100, min_samples_leaf=2, random_state=seed, n_jobs=1)
    raise ValueError(name)


def fit_all(X: np.ndarray, y: np.ndarray, seed: int = 0,
            models: Sequence[str] = ML_MODEL_NAMES) -> Dict[str, Predictor]:
    """Fit every trainable method on (X, y); return name -> predictor. The
    data-free methods (fixed, banded, expert FLC) are added by the caller."""
    out: Dict[str, Predictor] = {"FLC (data-tuned)": flc_predictor(table=fit_tuned_flc(X, y))}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        for name in models:
            model = make_ml_model(name, seed)
            model.fit(X, y)
            out[name] = model.predict
    return out


def data_free_predictors() -> Dict[str, Predictor]:
    return {
        "Fixed volume": fixed_predictor(),
        "Banded table (current)": banded_predictor(),
        "FLC (expert)": flc_predictor(),
    }


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def error_metrics(pred: np.ndarray, truth: np.ndarray) -> Dict[str, float]:
    """MAE/RMSE of the multiplier, plus the two operationally different error
    directions: SHORTFALL (diverted too little -> dirtier tank water) and
    EXCESS (diverted too much -> wasted water)."""
    err = pred - truth
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "shortfall": float(np.mean(np.maximum(-err, 0.0))),
        "excess": float(np.mean(np.maximum(err, 0.0))),
        "max_abs": float(np.max(np.abs(err))),
    }


# --------------------------------------------------------------------------
# Model footprint (rough, for the "can it run on the MCU?" discussion)
# --------------------------------------------------------------------------
# Byte estimates assume 4-byte floats; a tree node is ~12 B (float threshold,
# float value, two 16-bit child indices). These are order-of-magnitude
# figures for comparing methods, not measured flash usage.

ARDUINO_UNO_FLASH_BYTES = 32 * 1024


def _tree_nodes(model) -> int:
    return int(model.tree_.node_count)


def footprint_bytes(name: str, fitted: Dict[str, object]) -> int:
    if name in ("Fixed volume",):
        return 4
    if name in ("Banded table (current)",):
        return 9 * 4 + 4 * 4                       # table + 4 thresholds
    if name in ("FLC (expert)", "FLC (data-tuned)"):
        return 9 * 4 + 4 * 4 + 4 * 4               # consequents + thresholds + half-widths
    model = fitted[name]
    if name == "Poly ridge (deg 2)":
        ridge = model.steps[-1][1]
        return (ridge.coef_.size + 1 + 4) * 4      # coeffs + intercept + scaler mean/scale
    if name == "Decision tree (depth 5)":
        return _tree_nodes(model) * 12
    if name == "MLP (8-8)":
        mlp = model.steps[-1][1]
        n = sum(w.size for w in mlp.coefs_) + sum(b.size for b in mlp.intercepts_) + 4
        return n * 4
    if name == "Random forest (100)":
        return sum(_tree_nodes(t) for t in model.estimators_) * 12
    raise ValueError(name)
