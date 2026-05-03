import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    PLAYERS, AGENTS, MAPS, TIERS, PLAYER_PROFILES,
    N_HISTORY_MATCHES, MAP_AFFINITY
)


def _rounds_played() -> int:
    return int(np.clip(np.random.normal(22, 3), 13, 35))


def _correlated_match(player: str, rounds: int, opp_str: float,
                      map_name: str, tier: str, match_date: datetime,
                      rng: np.random.Generator) -> dict:
    profile = PLAYER_PROFILES[player]
    kills_mu = profile["kills_mu"]
    kills_sig = profile["kills_sig"]
    acs_mu = profile["acs_mu"]
    acs_sig = profile["acs_sig"]
    kd_mu = profile["kd_mu"]

    # map affinity
    map_offset = MAP_AFFINITY.get(player, {}).get(map_name, 0.0)
    kills_mu += map_offset
    acs_mu += map_offset * 8

    # opponent adjustment
    kills_mu *= opp_str
    acs_mu *= opp_str

    # tier adjustment (LAN slightly higher variance)
    if "LAN" in tier:
        kills_sig *= 1.15
        acs_sig *= 1.12

    # latent "form factor": captures hot/cold streaks
    form = rng.normal(0, 0.12)

    # latent "pop-off" (heavy-tailed bonus, rare)
    pop_off = rng.choice([0.0, 0.0, 0.0, 0.0, 0.0, 0.18, 0.28, -0.22],
                         p=[0.55, 0.12, 0.10, 0.08, 0.05, 0.04, 0.03, 0.03])

    scale = 1.0 + form + pop_off

    # Correlated draws via Cholesky
    corr_matrix = np.array([
        [1.00, 0.82, 0.65, 0.75, 0.45],
        [0.82, 1.00, 0.60, 0.78, 0.42],
        [0.65, 0.60, 1.00, 0.50, 0.38],
        [0.75, 0.78, 0.50, 1.00, 0.40],
        [0.45, 0.42, 0.38, 0.40, 1.00],
    ])
    L = np.linalg.cholesky(corr_matrix)
    z = rng.standard_normal(5)
    c = L @ z  # correlated normals

    kills = max(0, round(kills_mu * scale + kills_sig * c[0]))
    acs = max(0, round(acs_mu * scale + acs_sig * c[1]))
    deaths = max(1, round((kills / max(kd_mu * scale, 0.1)) + 1.5 * abs(c[2])))
    adr = max(0, round(acs * 0.65 + 15 * c[3] + rng.normal(0, 8)))
    assists = max(0, round(rng.poisson(lam=max(3.5 + 0.8 * c[4], 0.5))))
    kast = float(np.clip(rng.normal(72, 9), 30, 99))
    hs_pct = float(np.clip(rng.normal(24, 6), 5, 60))
    agent = rng.choice(AGENTS)

    return {
        "player": player,
        "match_date": match_date.strftime("%Y-%m-%d"),
        "map": map_name,
        "agent": agent,
        "tier": tier,
        "rounds": rounds,
        "kills": int(kills),
        "deaths": int(deaths),
        "assists": int(assists),
        "acs": int(acs),
        "adr": int(adr),
        "kast": round(kast, 1),
        "hs_pct": round(hs_pct, 1),
        "opp_strength": round(opp_str, 3),
        "team_rating": round(float(rng.uniform(800, 1300)), 1),
        "kd": round(kills / max(deaths, 1), 3),
    }


def generate_synthetic_data(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    records = []
    base_date = datetime(2024, 1, 1)

    for player in PLAYERS:
        for i in range(N_HISTORY_MATCHES):
            days_ago = N_HISTORY_MATCHES - i + rng.integers(0, 2)
            match_date = base_date + timedelta(days=int(days_ago))
            map_name = rng.choice(MAPS)
            tier = rng.choice(TIERS, p=[0.25, 0.20, 0.30, 0.25])

            opp_bucket = rng.choice(["strong", "medium", "weak"], p=[0.30, 0.45, 0.25])
            opp_str_base = {"strong": 0.88, "medium": 1.0, "weak": 1.10}[opp_bucket]
            opp_str = float(np.clip(rng.normal(opp_str_base, 0.04), 0.78, 1.20))

            rounds = _rounds_played()
            record = _correlated_match(player, rounds, opp_str, map_name, tier, match_date, rng)
            records.append(record)

    df = pd.DataFrame(records)
    df["match_date"] = pd.to_datetime(df["match_date"])
    df.sort_values(["player", "match_date"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def load_data(data_path: str = None) -> pd.DataFrame:
    if data_path and os.path.exists(data_path):
        df = pd.read_csv(data_path, parse_dates=["match_date"])
        df.sort_values(["player", "match_date"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
    return generate_synthetic_data()
