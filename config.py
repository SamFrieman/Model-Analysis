from dataclasses import dataclass, field
from typing import Dict, List

PLAYERS = [
    "TenZ", "Aspas", "Cryocells", "Derke", "Chronicle",
    "Zekken", "Less", "Yay", "Nats", "Shao"
]

AGENTS = [
    "Jett", "Reyna", "Raze", "Neon", "Yoru",
    "Sage", "Omen", "Brimstone", "Viper", "Astra",
    "Sova", "Fade", "Kay/O", "Skye", "Gekko"
]

MAPS = [
    "Ascent", "Bind", "Haven", "Split", "Fracture",
    "Pearl", "Lotus", "Sunset", "Abyss", "Icebox"
]

TIERS = ["LAN_PREMIER", "LAN_MAJOR", "ONLINE_QUALIFIER", "ONLINE_REGULAR"]

# Per-player realistic baselines (mean, std) for key stats
PLAYER_PROFILES: Dict[str, Dict] = {
    "TenZ":       {"kills_mu": 18.5, "kills_sig": 4.2, "acs_mu": 248, "acs_sig": 52, "kd_mu": 1.22, "kd_sig": 0.28},
    "Aspas":      {"kills_mu": 20.1, "kills_sig": 4.8, "acs_mu": 265, "acs_sig": 55, "kd_mu": 1.38, "kd_sig": 0.30},
    "Cryocells":  {"kills_mu": 17.8, "kills_sig": 4.0, "acs_mu": 238, "acs_sig": 48, "kd_mu": 1.18, "kd_sig": 0.26},
    "Derke":      {"kills_mu": 19.2, "kills_sig": 4.5, "acs_mu": 255, "acs_sig": 50, "kd_mu": 1.28, "kd_sig": 0.27},
    "Chronicle":  {"kills_mu": 16.4, "kills_sig": 3.8, "acs_mu": 222, "acs_sig": 44, "kd_mu": 1.10, "kd_sig": 0.24},
    "Zekken":     {"kills_mu": 17.5, "kills_sig": 4.1, "acs_mu": 232, "acs_sig": 46, "kd_mu": 1.15, "kd_sig": 0.25},
    "Less":       {"kills_mu": 16.8, "kills_sig": 3.9, "acs_mu": 228, "acs_sig": 45, "kd_mu": 1.12, "kd_sig": 0.24},
    "Yay":        {"kills_mu": 19.8, "kills_sig": 4.6, "acs_mu": 260, "acs_sig": 53, "kd_mu": 1.32, "kd_sig": 0.29},
    "Nats":       {"kills_mu": 18.0, "kills_sig": 4.3, "acs_mu": 242, "acs_sig": 49, "kd_mu": 1.20, "kd_sig": 0.27},
    "Shao":       {"kills_mu": 17.2, "kills_sig": 4.0, "acs_mu": 230, "acs_sig": 47, "kd_mu": 1.14, "kd_sig": 0.25},
}

DEFAULT_BENCHMARKS: Dict[str, float] = {
    "kills": 17.5,
    "acs": 220.0,
    "kd": 1.15,
    "adr": 140.0,
    "kast": 70.0,
    "hs_pct": 22.0,
    "assists": 4.5,
}

ROLLING_WINDOWS = [5, 10]
N_HISTORY_MATCHES = 60
DEFAULT_SIMS = 10_000
CONFIDENCE_HIGH_THRESHOLD = 0.70
CONFIDENCE_MED_THRESHOLD = 0.58

# Opponent adjustment multipliers (strong: 0.88, weak: 1.10)
OPP_STRENGTH_BUCKETS = {"strong": 0.88, "medium": 1.0, "weak": 1.10}

# Map affinity offsets (kills) for each player
MAP_AFFINITY: Dict[str, Dict[str, float]] = {
    "TenZ":      {"Ascent": 1.5, "Bind": -0.5, "Haven": 1.0, "Split": -1.0, "Fracture": 0.5,
                  "Pearl": 0.2, "Lotus": 0.8, "Sunset": -0.3, "Abyss": 0.6, "Icebox": -0.8},
    "Aspas":     {"Ascent": 2.0, "Bind": 1.0, "Haven": 0.5, "Split": -0.5, "Fracture": 1.2,
                  "Pearl": 0.8, "Lotus": -0.3, "Sunset": 1.5, "Abyss": 0.3, "Icebox": -0.6},
    "Cryocells": {"Ascent": 0.5, "Bind": 0.8, "Haven": 1.2, "Split": 0.3, "Fracture": -0.5,
                  "Pearl": -0.2, "Lotus": 0.5, "Sunset": 0.2, "Abyss": 1.0, "Icebox": 0.8},
    "Derke":     {"Ascent": 1.2, "Bind": 0.5, "Haven": 0.8, "Split": 1.5, "Fracture": -0.3,
                  "Pearl": 0.4, "Lotus": 0.6, "Sunset": -0.2, "Abyss": 0.9, "Icebox": 0.3},
    "Chronicle": {"Ascent": 0.3, "Bind": 1.0, "Haven": -0.5, "Split": 0.8, "Fracture": 1.2,
                  "Pearl": 0.5, "Lotus": -0.2, "Sunset": 0.6, "Abyss": -0.4, "Icebox": 1.1},
    "Zekken":    {"Ascent": 0.8, "Bind": -0.3, "Haven": 0.5, "Split": 1.0, "Fracture": 0.3,
                  "Pearl": 0.7, "Lotus": 1.1, "Sunset": 0.4, "Abyss": -0.5, "Icebox": 0.6},
    "Less":      {"Ascent": 0.4, "Bind": 0.9, "Haven": 0.6, "Split": -0.4, "Fracture": 0.8,
                  "Pearl": 0.3, "Lotus": 0.5, "Sunset": 1.0, "Abyss": 0.2, "Icebox": -0.7},
    "Yay":       {"Ascent": 1.8, "Bind": 0.6, "Haven": 1.3, "Split": -0.8, "Fracture": 0.9,
                  "Pearl": 0.5, "Lotus": 0.4, "Sunset": 1.2, "Abyss": 0.7, "Icebox": -0.5},
    "Nats":      {"Ascent": 0.9, "Bind": 0.4, "Haven": 1.1, "Split": 0.6, "Fracture": -0.3,
                  "Pearl": 0.8, "Lotus": 0.3, "Sunset": -0.5, "Abyss": 1.2, "Icebox": 0.7},
    "Shao":      {"Ascent": 0.6, "Bind": 0.7, "Haven": 0.3, "Split": 1.2, "Fracture": 0.5,
                  "Pearl": -0.4, "Lotus": 0.9, "Sunset": 0.3, "Abyss": 0.4, "Icebox": 1.0},
}
