"""
Vectorised Monte Carlo engine.
Generates N simulations per player for all stats simultaneously,
applying correlated draws and latent pop-off / slump variables.
"""
import numpy as np
from scipy import stats as scipy_stats
from typing import Dict, Tuple
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DEFAULT_SIMS, CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MED_THRESHOLD

STAT_TARGETS = ["kills", "deaths", "assists", "acs", "adr", "kast", "hs_pct", "kd"]

# ── Correlation matrix (kills, deaths, assists, acs, adr, kast, hs_pct, kd) ──
_CORR = np.array([
    #  kil    dea    ast    acs    adr    kast   hs     kd
    [1.000, -0.35,  0.30,  0.82,  0.74,  0.45,  0.30,  0.70],
    [-0.35,  1.000,  0.15, -0.35, -0.28, -0.40, -0.10, -0.72],
    [0.300,  0.15,  1.00,  0.35,  0.30,  0.50,  0.15,  0.20],
    [0.820, -0.35,  0.35,  1.00,  0.78,  0.42,  0.28,  0.65],
    [0.740, -0.28,  0.30,  0.78,  1.00,  0.38,  0.22,  0.58],
    [0.450, -0.40,  0.50,  0.42,  0.38,  1.00,  0.18,  0.40],
    [0.300, -0.10,  0.15,  0.28,  0.22,  0.18,  1.00,  0.25],
    [0.700, -0.72,  0.20,  0.65,  0.58,  0.40,  0.25,  1.00],
])
_CORR += np.eye(8) * 1e-6
_L = np.linalg.cholesky(_CORR)

# ── Edge engine constants ─────────────────────────────────────────────────────
_DEFAULT_AMERICAN_ODDS = -110
_PAYOUT_B = 100 / 110        # ≈ 0.9091  (win $100 risking $110)
_IMPLIED_PROB = 110 / 210    # ≈ 0.52381

# Edge tier thresholds (as fractions, not percentages)
TIER_ELITE    = 0.08
TIER_STRONG   = 0.05
TIER_PLAYABLE = 0.03


def _edge_tier(edge: float) -> str:
    if edge > TIER_ELITE:
        return "ELITE"
    if edge > TIER_STRONG:
        return "STRONG"
    if edge > TIER_PLAYABLE:
        return "PLAYABLE"
    return "PASS"


def _compute_edge(p_win: float) -> Dict:
    """Return edge, EV, Kelly, and tier for one side of a prop."""
    edge  = p_win - _IMPLIED_PROB
    p_loss = 1.0 - p_win
    ev    = (p_win * _PAYOUT_B) - p_loss
    kelly = (_PAYOUT_B * p_win - p_loss) / _PAYOUT_B
    return {
        "edge":  round(edge  * 100, 2),   # stored as percentage points
        "ev":    round(ev,           4),
        "kelly": round(max(kelly, 0.0), 4),
        "tier":  _edge_tier(edge),
    }


# ── Distribution sampler ──────────────────────────────────────────────────────

def _sample_stat(fit: Dict, n: int, rng: np.random.Generator,
                 z: np.ndarray) -> np.ndarray:
    dist  = fit["dist_type"]
    mu    = fit["mu"]
    sigma = fit["sigma"]

    if dist == "negbinom":
        shifted_mu = np.clip(mu + sigma * z, 0.0, None)
        var_       = np.maximum(shifted_mu * 1.15, shifted_mu + 0.1)
        r_         = np.maximum(shifted_mu ** 2 / np.maximum(var_ - shifted_mu, 0.01), 0.5)
        p_         = r_ / (r_ + np.maximum(shifted_mu, 0.01))
        u          = rng.uniform(0, 1, n)
        return np.maximum(scipy_stats.nbinom.ppf(u, r_, p_).astype(float), 0.0)

    elif dist == "student_t":
        df_t  = fit["params"]["df"]
        loc_t = fit["params"]["loc"]
        sc_t  = fit["params"]["scale"]
        return loc_t + sc_t * scipy_stats.t.ppf(
            np.clip(scipy_stats.norm.cdf(z), 1e-6, 1 - 1e-6), df_t
        )

    else:  # normal
        return mu + sigma * z


# ── Main simulation function ──────────────────────────────────────────────────

def simulate_player(player: str, models: Dict[str, Dict],
                    opp_strength: float = 1.0,
                    n_sims: int = DEFAULT_SIMS,
                    seed: int = None) -> Dict[str, np.ndarray]:

    rng = np.random.default_rng(seed)

    z_corr = rng.standard_normal((n_sims, 8)) @ _L.T

    # Latent pop-off / slump  (mixture of normals)
    pop_idx  = rng.choice(3, size=n_sims, p=[0.80, 0.12, 0.08])
    pop_vals = np.where(pop_idx == 0, 0.0,
               np.where(pop_idx == 1, rng.normal(0.22, 0.08, n_sims),
                                      rng.normal(-0.20, 0.10, n_sims)))

    # AR(1) streakiness
    streak   = np.zeros(n_sims)
    ar_coef  = 0.30
    noise    = rng.normal(0, 0.08, n_sims)
    for t in range(1, n_sims):
        streak[t] = ar_coef * streak[t-1] + (1 - ar_coef) * noise[t]

    latent = pop_vals + streak * 0.5

    results = {}
    for i, stat in enumerate(STAT_TARGETS):
        if stat not in models:
            continue
        raw = _sample_stat(models[stat], n_sims, rng, z_corr[:, i])

        sign = -1.0 if stat == "deaths" else 1.0
        raw  = raw * (1.0 + sign * latent)

        if stat in ("kills", "acs", "adr", "kd"):
            raw = raw * opp_strength
        elif stat == "deaths":
            raw = raw / np.maximum(opp_strength, 0.1)

        if stat in ("kills", "deaths", "assists"):
            raw = np.maximum(np.round(raw), 0.0)
        elif stat == "kast":
            raw = np.clip(raw, 0.0, 100.0)
        elif stat == "hs_pct":
            raw = np.clip(raw, 0.0, 80.0)
        elif stat == "kd":
            raw = np.maximum(raw, 0.0)

        results[stat] = raw

    if "kills" in results and "deaths" in results:
        results["kd"] = results["kills"] / np.maximum(results["deaths"], 1.0)

    return results


def evaluate_line(simulations: np.ndarray, line: float) -> Tuple[float, float, float, float]:
    p_over  = float(np.mean(simulations > line))
    p_under = float(np.mean(simulations <= line))
    ev_raw  = float(np.mean(simulations))
    vol_cv  = float(np.std(simulations) / np.maximum(np.abs(ev_raw), 1e-6))
    return p_over, p_under, ev_raw, vol_cv


def confidence_score(p_over: float, vol_cv: float) -> str:
    p_max = max(p_over, 1 - p_over)
    adj   = p_max - vol_cv * 0.05
    if adj >= CONFIDENCE_HIGH_THRESHOLD:
        return "High"
    if adj >= CONFIDENCE_MED_THRESHOLD:
        return "Medium"
    return "Low"


def volatility_label(vol_cv: float) -> str:
    if vol_cv < 0.18:
        return "Low"
    if vol_cv < 0.30:
        return "Medium"
    return "High"


def run_full_simulation(player: str, models: Dict[str, Dict],
                        benchmarks: Dict[str, float],
                        opp_strength: float = 1.0,
                        n_sims: int = DEFAULT_SIMS,
                        seed: int = 0) -> Dict:

    sims   = simulate_player(player, models, opp_strength, n_sims, seed)
    output = {"player": player, "n_sims": n_sims, "stats": {}}

    for stat, line in benchmarks.items():
        if stat not in sims:
            continue
        arr                  = sims[stat]
        p_over, p_under, ev, vol_cv = evaluate_line(arr, line)

        over_edge  = _compute_edge(p_over)
        under_edge = _compute_edge(p_under)

        # Best side = higher edge (could be negative on both, pick lesser evil)
        best_side  = "over" if over_edge["edge"] >= under_edge["edge"] else "under"

        output["stats"][stat] = {
            # ── raw probabilities ──────────────────────────────────────────
            "line":          line,
            "ev":            round(ev, 2),
            "p_over":        round(p_over  * 100, 1),
            "p_under":       round(p_under * 100, 1),
            "std":           round(float(np.std(arr)), 2),
            "p5":            round(float(np.percentile(arr, 5)),  2),
            "p95":           round(float(np.percentile(arr, 95)), 2),
            "volatility":    volatility_label(vol_cv),
            "confidence":    confidence_score(p_over, vol_cv),
            # ── edge engine ───────────────────────────────────────────────
            "implied_prob":  round(_IMPLIED_PROB * 100, 2),
            "edge_over":     over_edge["edge"],
            "ev_over":       over_edge["ev"],
            "kelly_over":    over_edge["kelly"],
            "tier_over":     over_edge["tier"],
            "edge_under":    under_edge["edge"],
            "ev_under":      under_edge["ev"],
            "kelly_under":   under_edge["kelly"],
            "tier_under":    under_edge["tier"],
            "best_side":     best_side,
            "best_edge":     over_edge["edge"] if best_side == "over" else under_edge["edge"],
            "best_ev":       over_edge["ev"]   if best_side == "over" else under_edge["ev"],
            "best_kelly":    over_edge["kelly"]if best_side == "over" else under_edge["kelly"],
            "best_tier":     over_edge["tier"] if best_side == "over" else under_edge["tier"],
        }

    return output
