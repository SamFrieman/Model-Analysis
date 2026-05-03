"""
Fits per-player probabilistic models for each stat.
Outputs: mean, variance, distribution type, and fitted parameters.
Supports Normal, NegativeBinomial, and Poisson families.
Uses Bayesian updating (conjugate priors) for count stats.
"""
import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import gammaln
from typing import Dict, Tuple
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PLAYER_PROFILES

# --------------------------------------------------------------------------- #
#  Negative-Binomial MLE via moment matching                                   #
# --------------------------------------------------------------------------- #

def _fit_negbinom(x: np.ndarray) -> Tuple[float, float]:
    """Return (r, p) for NegBinomial parameterisation used by scipy.
    p = mean / variance  (we invert to get the failure-prob form)
    r = mean^2 / (variance - mean)
    """
    mu = float(x.mean())
    var = float(x.var())
    if var <= mu or var <= 0:
        var = mu * 1.15  # force overdispersion
    r = max(mu ** 2 / (var - mu), 0.5)
    p = r / (r + mu)
    return r, p


def _bayesian_normal_update(x: np.ndarray, prior_mu: float, prior_sig: float,
                             known_sig: float = None) -> Tuple[float, float]:
    """
    Normal-Normal conjugate update.
    Returns posterior (mu, sigma).
    """
    n = len(x)
    if n == 0:
        return prior_mu, prior_sig
    if known_sig is None:
        known_sig = float(x.std()) if x.std() > 0 else prior_sig

    tau0 = 1.0 / (prior_sig ** 2)
    tau_l = n / (known_sig ** 2)
    tau_post = tau0 + tau_l
    mu_post = (tau0 * prior_mu + tau_l * float(x.mean())) / tau_post
    sig_post = np.sqrt(1.0 / tau_post)
    return float(mu_post), float(sig_post)


def _fit_stat(player: str, stat: str, values: np.ndarray,
              use_window: int = 20) -> Dict:
    """
    Fit a probabilistic model to the last `use_window` observations.
    Returns dict with keys: dist_type, mu, sigma, params, skew, kurt
    """
    if len(values) == 0:
        return {"dist_type": "normal", "mu": 0.0, "sigma": 1.0, "params": {}}

    x = values[-use_window:].astype(float)

    # Prior from player profile
    profile = PLAYER_PROFILES.get(player, {})
    prior_mu = profile.get(f"{stat}_mu", float(x.mean()))
    prior_sig = profile.get(f"{stat}_sig", float(x.std()) if x.std() > 0 else 1.0)

    sample_skew = float(stats.skew(x)) if len(x) >= 4 else 0.0
    sample_kurt = float(stats.kurtosis(x)) if len(x) >= 4 else 0.0

    # Count stats → NegBinomial (kills, deaths, assists)
    if stat in ("kills", "deaths", "assists") and x.min() >= 0:
        r, p = _fit_negbinom(x)
        nb_mu = r * (1 - p) / p
        nb_var = r * (1 - p) / (p ** 2)
        # Bayesian shrinkage of mean toward prior
        post_mu, _ = _bayesian_normal_update(x, prior_mu, prior_sig, known_sig=np.sqrt(nb_var))
        # Re-fit r given updated mean
        var_ = max(nb_var, post_mu * 1.05)
        r_up = max(post_mu ** 2 / (var_ - post_mu), 0.5)
        p_up = r_up / (r_up + post_mu)
        return {
            "dist_type": "negbinom",
            "mu": post_mu,
            "sigma": np.sqrt(var_),
            "params": {"r": r_up, "p": p_up},
            "skew": sample_skew,
            "kurt": sample_kurt,
        }

    # Continuous stats → Normal with Bayesian update
    post_mu, post_sig = _bayesian_normal_update(x, prior_mu, prior_sig)

    # Add tail-fattening for high kurtosis (use t-distribution internally)
    if abs(sample_kurt) > 1.5 and len(x) >= 8:
        df_t, loc_t, scale_t = stats.t.fit(x)
        return {
            "dist_type": "student_t",
            "mu": float(loc_t),
            "sigma": float(scale_t),
            "params": {"df": float(df_t), "loc": float(loc_t), "scale": float(scale_t)},
            "skew": sample_skew,
            "kurt": sample_kurt,
        }

    return {
        "dist_type": "normal",
        "mu": post_mu,
        "sigma": max(post_sig, 0.5),
        "params": {"loc": post_mu, "scale": max(post_sig, 0.5)},
        "skew": sample_skew,
        "kurt": sample_kurt,
    }


STAT_TARGETS = ["kills", "deaths", "assists", "acs", "adr", "kast", "hs_pct", "kd"]


def fit_player_models(df: pd.DataFrame) -> Dict[str, Dict[str, Dict]]:
    """
    Returns: { player: { stat: fit_dict } }
    fit_dict keys: dist_type, mu, sigma, params, skew, kurt
    """
    models = {}
    for player, grp in df.groupby("player"):
        grp_sorted = grp.sort_values("match_date")
        models[player] = {}
        for stat in STAT_TARGETS:
            if stat not in grp_sorted.columns:
                continue
            values = grp_sorted[stat].dropna().values
            models[player][stat] = _fit_stat(player, stat, values)
    return models
