import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ROLLING_WINDOWS

STAT_COLS = ["kills", "deaths", "assists", "acs", "adr", "kast", "hs_pct", "kd"]


def _rolling_for_group(grp: pd.DataFrame, window: int) -> pd.DataFrame:
    out = {}
    for col in STAT_COLS:
        shifted = grp[col].shift(1)  # no leakage: exclude current match
        out[f"{col}_roll{window}_mean"] = shifted.rolling(window, min_periods=2).mean()
        out[f"{col}_roll{window}_std"]  = shifted.rolling(window, min_periods=2).std()
    return pd.DataFrame(out, index=grp.index)


def _fatigue_proxy(grp: pd.DataFrame) -> pd.Series:
    """Count matches played in the previous 7 days as a fatigue proxy."""
    dates = grp["match_date"]
    fatigue = []
    for i, (idx, d) in enumerate(dates.items()):
        window_start = d - pd.Timedelta(days=7)
        cnt = ((dates < d) & (dates >= window_start)).sum()
        fatigue.append(cnt)
    return pd.Series(fatigue, index=grp.index, name="fatigue_7d")


def _opponent_adjusted(grp: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for col in ["kills", "acs", "adr", "kd"]:
        # divide raw stat by opponent multiplier to normalise difficulty
        out[f"{col}_opp_adj"] = grp[col] / grp["opp_strength"].replace(0, np.nan)
    return pd.DataFrame(out, index=grp.index)


def _map_agent_means(df: pd.DataFrame) -> pd.DataFrame:
    """Global mean per (player, map) and (player, agent) — computed on all history."""
    map_means = (
        df.groupby(["player", "map"])[STAT_COLS]
        .mean()
        .add_prefix("map_avg_")
        .reset_index()
    )
    agent_means = (
        df.groupby(["player", "agent"])[STAT_COLS]
        .mean()
        .add_prefix("agent_avg_")
        .reset_index()
    )
    df = df.merge(map_means, on=["player", "map"], how="left")
    df = df.merge(agent_means, on=["player", "agent"], how="left")
    return df


def _regression_to_mean(df: pd.DataFrame, alpha: float = 0.25) -> pd.DataFrame:
    """Bayesian shrinkage: pull rolling mean toward global mean."""
    global_means = df.groupby("player")[STAT_COLS].transform("mean")
    for w in ROLLING_WINDOWS:
        for col in STAT_COLS:
            roll_col = f"{col}_roll{w}_mean"
            if roll_col in df.columns:
                df[f"{col}_roll{w}_shrunk"] = (
                    (1 - alpha) * df[roll_col].fillna(global_means[col])
                    + alpha * global_means[col]
                )
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.sort_values(["player", "match_date"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    # rolling stats per player
    rolling_parts = []
    fatigue_parts = []
    opp_adj_parts = []

    for player, grp in df.groupby("player"):
        for w in ROLLING_WINDOWS:
            part = _rolling_for_group(grp, w)
            rolling_parts.append(part)
        fatigue_parts.append(_fatigue_proxy(grp))
        opp_adj_parts.append(_opponent_adjusted(grp))

    roll_df = pd.concat(rolling_parts, axis=0).groupby(level=0).last()
    # deduplicate duplicated rolling windows: concat may produce duplicate cols per player
    # safer: build column-wise
    roll_df2 = pd.concat(rolling_parts)
    # the loop above produces one rolling part per (player, window) combo; we need to join them all
    # Rebuild cleanly
    all_roll_dfs = []
    for player, grp in df.groupby("player"):
        parts = []
        for w in ROLLING_WINDOWS:
            parts.append(_rolling_for_group(grp, w))
        combined = pd.concat(parts, axis=1)
        all_roll_dfs.append(combined)

    roll_final = pd.concat(all_roll_dfs)
    df = df.join(roll_final, rsuffix="_dup")
    df.drop(columns=[c for c in df.columns if c.endswith("_dup")], inplace=True)

    # fatigue
    fatigue_series = pd.concat(fatigue_parts)
    df["fatigue_7d"] = fatigue_series.values

    # opponent-adjusted stats
    opp_adj_df = pd.concat(opp_adj_parts)
    for col in opp_adj_df.columns:
        df[col] = opp_adj_df[col].values

    # map / agent means
    df = _map_agent_means(df)

    # regression to mean
    df = _regression_to_mean(df)

    # volatility flag
    for col in ["kills", "acs"]:
        std_col = f"{col}_roll10_std"
        if std_col in df.columns:
            mean_col = f"{col}_roll10_mean"
            df[f"{col}_cv"] = df[std_col] / df[mean_col].replace(0, np.nan)

    df = df.bfill().ffill()
    df.reset_index(drop=True, inplace=True)
    return df
