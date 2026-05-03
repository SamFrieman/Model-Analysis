"""
Premium reporting layer.
Renders: Best Plays banner → per-player prop tables → JSON + CSV exports.
All strings are ASCII-safe for Windows CP1252 compatibility.
"""
import json
import csv
import sys
import os
from typing import Dict, List
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.compat import CONSOLE as console, RICH as RICH_AVAILABLE

if RICH_AVAILABLE:
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel
    from rich.columns import Columns
    from rich import box

# ── Colour maps ───────────────────────────────────────────────────────────────
_CONF_STYLE = {"High": "bold green", "Medium": "yellow", "Low": "red"}
_VOL_STYLE  = {"Low":  "bold green", "Medium": "yellow", "High": "bold red"}
_TIER_STYLE = {
    "ELITE":    "bold green",
    "STRONG":   "green",
    "PLAYABLE": "yellow",
    "PASS":     "dim red",
}
_TIER_ICON = {
    "ELITE":    "[bold green]** ELITE **[/bold green]",
    "STRONG":   "[green]* STRONG[/green]",
    "PLAYABLE": "[yellow]PLAYABLE[/yellow]",
    "PASS":     "[dim red]PASS[/dim red]",
}


def _stat_name(stat: str) -> str:
    return {
        "kills":  "Kills",  "deaths":  "Deaths", "assists": "Assists",
        "acs":    "ACS",    "adr":     "ADR",    "kast":    "KAST %",
        "hs_pct": "HS %",   "kd":      "K/D",
    }.get(stat, stat.upper())


def _ev_style(ev: float) -> str:
    if ev > 0.06:
        return "bold green"
    if ev > 0.02:
        return "green"
    if ev > -0.02:
        return "yellow"
    return "red"


def _edge_style(edge: float) -> str:
    if edge > 8.0:
        return "bold green"
    if edge > 5.0:
        return "green"
    if edge > 3.0:
        return "yellow"
    return "dim red"


def _pct_style(p: float) -> str:
    if p > 60:
        return "bold green"
    if p > 55:
        return "green"
    if p > 45:
        return "white"
    return "bold red"


# ── Collect ranked plays ──────────────────────────────────────────────────────

def _rank_plays(results: List[Dict]) -> List[Dict]:
    plays = []
    for res in results:
        player = res["player"]
        for stat, d in res["stats"].items():
            if d["best_tier"] == "PASS":
                continue
            plays.append({
                "player":     player,
                "stat":       stat,
                "side":       d["best_side"].upper(),
                "line":       d["line"],
                "p_win":      d["p_over"] if d["best_side"] == "over" else d["p_under"],
                "ev":         d["best_ev"],
                "edge":       d["best_edge"],
                "kelly":      d["best_kelly"],
                "tier":       d["best_tier"],
                "confidence": d["confidence"],
                "volatility": d["volatility"],
            })
    plays.sort(key=lambda x: x["ev"], reverse=True)
    return plays


# ── Best Plays banner ─────────────────────────────────────────────────────────

def print_best_plays(results: List[Dict]):
    plays = _rank_plays(results)
    top   = plays[:5]

    if RICH_AVAILABLE:
        console.print()
        console.print(Panel(
            "[bold yellow]BEST PLAYS[/bold yellow]",
            style="bold yellow", expand=False
        ))

        if not top:
            console.print("[dim]  No plays above PASS threshold.[/dim]")
            return

        tbl = Table(
            box=box.SIMPLE_HEAVY,
            header_style="bold yellow",
            show_lines=False,
            expand=False,
        )
        tbl.add_column("#",          justify="right",  style="dim",        min_width=2,  no_wrap=True)
        tbl.add_column("Player",     justify="left",   style="bold white",  min_width=11, no_wrap=True)
        tbl.add_column("Bet",        justify="left",                        min_width=22, no_wrap=True)
        tbl.add_column("Edge",       justify="right",                       min_width=8,  no_wrap=True)
        tbl.add_column("EV",         justify="right",                       min_width=7,  no_wrap=True)
        tbl.add_column("Kelly",      justify="right",  style="dim",         min_width=7,  no_wrap=True)
        tbl.add_column("Win %",      justify="right",                       min_width=7,  no_wrap=True)
        tbl.add_column("Tier",       justify="center",                      min_width=10, no_wrap=True)
        tbl.add_column("Conf",       justify="center",                      min_width=8,  no_wrap=True)

        for rank, p in enumerate(top, 1):
            bet_str  = f"{_stat_name(p['stat'])} {p['side'].title()} {p['line']}"
            edge_str = f"+{p['edge']:.1f}%" if p["edge"] > 0 else f"{p['edge']:.1f}%"
            ev_str   = f"+{p['ev']:.3f}"    if p["ev"]   > 0 else f"{p['ev']:.3f}"
            tbl.add_row(
                str(rank),
                p["player"],
                bet_str,
                Text(edge_str,        style=_edge_style(p["edge"])),
                Text(ev_str,          style=_ev_style(p["ev"])),
                f"{p['kelly']:.3f}",
                Text(f"{p['p_win']:.1f}%", style=_pct_style(p["p_win"])),
                Text(p["tier"],       style=_TIER_STYLE.get(p["tier"], "white")),
                Text(p["confidence"], style=_CONF_STYLE.get(p["confidence"], "white")),
            )
        console.print(tbl)

    else:
        print("\n" + "=" * 60)
        print("  BEST PLAYS")
        print("=" * 60)
        if not top:
            print("  No plays above PASS threshold.")
            return
        for rank, p in enumerate(top, 1):
            edge_str = f"+{p['edge']:.1f}%" if p["edge"] > 0 else f"{p['edge']:.1f}%"
            ev_str   = f"+{p['ev']:.3f}"    if p["ev"]   > 0 else f"{p['ev']:.3f}"
            print(
                f"  #{rank}  {p['player']:<13} "
                f"{_stat_name(p['stat'])} {p['side'].title()} {p['line']}"
                f"   Edge: {edge_str}   EV: {ev_str}"
                f"   Tier: {p['tier']}   Conf: {p['confidence']}"
            )
        print("=" * 60)


# ── Per-player report ─────────────────────────────────────────────────────────

def print_player_report(result: Dict):
    player  = result["player"]
    n_sims  = result["n_sims"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if RICH_AVAILABLE:
        console.print()
        console.rule(f"[bold cyan] {player} [/bold cyan]")
        console.print(f"[dim]Simulations: {n_sims:,}  |  {now_str}  |  Implied prob: 52.38% (-110)[/dim]")

        tbl = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            title=f"[bold]{player}[/bold]",
            expand=False,
        )
        tbl.add_column("Stat",      style="bold white", justify="left",   min_width=9,  no_wrap=True)
        tbl.add_column("Line",      style="cyan",       justify="right",  min_width=6,  no_wrap=True)
        tbl.add_column("Expected",  style="white",      justify="right",  min_width=9,  no_wrap=True)
        tbl.add_column("Over %",                        justify="right",  min_width=7,  no_wrap=True)
        tbl.add_column("Under %",                       justify="right",  min_width=8,  no_wrap=True)
        tbl.add_column("Best Side",                     justify="center", min_width=9,  no_wrap=True)
        tbl.add_column("Edge",                          justify="right",  min_width=7,  no_wrap=True)
        tbl.add_column("EV",                            justify="right",  min_width=7,  no_wrap=True)
        tbl.add_column("Kelly",     style="dim",        justify="right",  min_width=6,  no_wrap=True)
        tbl.add_column("Tier",                          justify="center", min_width=10, no_wrap=True)
        tbl.add_column("Vol",                           justify="center", min_width=6,  no_wrap=True)
        tbl.add_column("Conf",                          justify="center", min_width=8,  no_wrap=True)

        for stat, d in result["stats"].items():
            side      = d["best_side"].upper()
            edge      = d["best_edge"]
            ev        = d["best_ev"]
            kelly     = d["best_kelly"]
            tier      = d["best_tier"]
            edge_str  = f"+{edge:.1f}%" if edge > 0 else f"{edge:.1f}%"
            ev_str    = f"+{ev:.3f}"    if ev   > 0 else f"{ev:.3f}"
            p_over_v  = d["p_over"]
            p_under_v = d["p_under"]

            tbl.add_row(
                _stat_name(stat),
                str(d["line"]),
                str(d["ev"]),
                Text(f"{p_over_v}%",  style=_pct_style(p_over_v)),
                Text(f"{p_under_v}%", style=_pct_style(p_under_v)),
                Text(side,            style="bold cyan" if side == "OVER" else "bold magenta"),
                Text(edge_str,        style=_edge_style(edge)),
                Text(ev_str,          style=_ev_style(ev)),
                f"{kelly:.3f}",
                Text(tier,            style=_TIER_STYLE.get(tier, "white")),
                Text(d["volatility"], style=_VOL_STYLE.get(d["volatility"], "white")),
                Text(d["confidence"], style=_CONF_STYLE.get(d["confidence"], "white")),
            )
        console.print(tbl)

    else:
        sep = "-" * 90
        print(f"\n{sep}")
        print(f"  PLAYER: {player}   |   Sims: {n_sims:,}   |   {now_str}")
        print(sep)
        hdr = (f"  {'Stat':<10} {'Line':>7} {'EV':>8} {'Over':>7} {'Under':>7}"
               f"  {'Side':<6} {'Edge':>8} {'EV_bet':>8} {'Kelly':>7}  {'Tier':<10} {'Vol':<8} {'Conf'}")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for stat, d in result["stats"].items():
            side     = d["best_side"].upper()
            edge     = d["best_edge"]
            ev       = d["best_ev"]
            kelly    = d["best_kelly"]
            edge_str = f"+{edge:.1f}%" if edge > 0 else f"{edge:.1f}%"
            ev_str   = f"+{ev:.3f}"    if ev   > 0 else f"{ev:.3f}"
            print(
                f"  {_stat_name(stat):<10} {d['line']:>7} {d['ev']:>8}"
                f" {d['p_over']:>6}% {d['p_under']:>6}%"
                f"  {side:<6} {edge_str:>8} {ev_str:>8} {kelly:>7.3f}"
                f"  {d['best_tier']:<10} {d['volatility']:<8} {d['confidence']}"
            )
        print(sep)


# ── Summary table (all players, best bet each) ────────────────────────────────

def print_summary_banner(results: List[Dict]):
    if RICH_AVAILABLE:
        console.print()
        tbl = Table(
            box=box.SIMPLE_HEAVY,
            title="[bold yellow]FULL MARKET OVERVIEW[/bold yellow]",
            header_style="bold yellow",
            expand=False,
        )
        tbl.add_column("Player",    style="bold white", min_width=12, no_wrap=True)
        tbl.add_column("Best Bet",  style="cyan",       min_width=22, no_wrap=True)
        tbl.add_column("Edge",      justify="right",    min_width=8,  no_wrap=True)
        tbl.add_column("EV",        justify="right",    min_width=7,  no_wrap=True)
        tbl.add_column("Win %",     justify="right",    min_width=7,  no_wrap=True)
        tbl.add_column("Tier",      justify="center",   min_width=10, no_wrap=True)
        tbl.add_column("Conf",      justify="center",   min_width=8,  no_wrap=True)

        for res in results:
            if not res["stats"]:
                continue
            best_stat = max(res["stats"], key=lambda s: res["stats"][s]["best_ev"])
            d    = res["stats"][best_stat]
            side = d["best_side"].upper()
            edge = d["best_edge"]
            ev   = d["best_ev"]
            p_win = d["p_over"] if side == "OVER" else d["p_under"]
            edge_str = f"+{edge:.1f}%" if edge > 0 else f"{edge:.1f}%"
            ev_str   = f"+{ev:.3f}"    if ev   > 0 else f"{ev:.3f}"
            bet_str  = f"{_stat_name(best_stat)} {side.title()} {d['line']}"
            tbl.add_row(
                res["player"],
                bet_str,
                Text(edge_str, style=_edge_style(edge)),
                Text(ev_str,   style=_ev_style(ev)),
                Text(f"{p_win:.1f}%", style=_pct_style(p_win)),
                Text(d["best_tier"],  style=_TIER_STYLE.get(d["best_tier"], "white")),
                Text(d["confidence"], style=_CONF_STYLE.get(d["confidence"], "white")),
            )
        console.print(tbl)

    else:
        print("\n=== FULL MARKET OVERVIEW ===")
        for res in results:
            if not res["stats"]:
                continue
            best_stat = max(res["stats"], key=lambda s: res["stats"][s]["best_ev"])
            d    = res["stats"][best_stat]
            side = d["best_side"].upper()
            edge = d["best_edge"]
            ev   = d["best_ev"]
            edge_str = f"+{edge:.1f}%" if edge > 0 else f"{edge:.1f}%"
            ev_str   = f"+{ev:.3f}"    if ev   > 0 else f"{ev:.3f}"
            print(
                f"  {res['player']:<13}  {_stat_name(best_stat)} {side.title()} {d['line']}"
                f"   Edge: {edge_str}   EV: {ev_str}   Tier: {d['best_tier']}"
            )


# ── Exports ───────────────────────────────────────────────────────────────────

def export_json(results: List[Dict], out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    msg = f"JSON exported -> {out_path}"
    if RICH_AVAILABLE:
        console.print(f"[green]{msg}[/green]")
    else:
        print(msg)


def export_csv(results: List[Dict], out_path: str):
    rows = []
    for res in results:
        for stat, d in res["stats"].items():
            rows.append({
                "player":       res["player"],
                "stat":         stat,
                "line":         d["line"],
                "ev":           d["ev"],
                "p_over":       d["p_over"],
                "p_under":      d["p_under"],
                "std":          d["std"],
                "p5":           d["p5"],
                "p95":          d["p95"],
                "implied_prob": d["implied_prob"],
                "edge_over":    d["edge_over"],
                "ev_over":      d["ev_over"],
                "kelly_over":   d["kelly_over"],
                "tier_over":    d["tier_over"],
                "edge_under":   d["edge_under"],
                "ev_under":     d["ev_under"],
                "kelly_under":  d["kelly_under"],
                "tier_under":   d["tier_under"],
                "best_side":    d["best_side"],
                "best_edge":    d["best_edge"],
                "best_ev":      d["best_ev"],
                "best_kelly":   d["best_kelly"],
                "best_tier":    d["best_tier"],
                "volatility":   d["volatility"],
                "confidence":   d["confidence"],
                "n_sims":       res["n_sims"],
            })
    if not rows:
        return
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    msg = f"CSV exported  -> {out_path}"
    if RICH_AVAILABLE:
        console.print(f"[green]{msg}[/green]")
    else:
        print(msg)
