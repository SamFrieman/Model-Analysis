#!/usr/bin/env python3
"""
Val Prop Engine — CLI
=====================
Commands:
    val auto        Run full pipeline (simulate + report + update tracker)
    val tracker     Rebuild Excel tracker from all saved JSON reports
    val results     Write actual outcomes into the tracker spreadsheet
"""

import argparse
import json as _json
import os
import sys
import time
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Patches stdout for UTF-8 on Windows BEFORE any other import touches it
from utils.compat import CONSOLE as console, RICH

try:
    from valorant_model.config import (PLAYERS, DEFAULT_BENCHMARKS, DEFAULT_SIMS, PLAYER_PROFILES)
    from valorant_model.data.ingestion import load_data
    from valorant_model.features.engineering import engineer_features
    from valorant_model.models.probabilistic import fit_player_models
    from valorant_model.simulation.monte_carlo import run_full_simulation
    from valorant_model.utils.reporting import (
        print_best_plays, print_player_report, print_summary_banner,
        export_json, export_csv
    )
    from valorant_model.utils.spreadsheet import (
        results_to_rows, append_to_tracker, generate_tracker,
        update_results, list_unresolved
    )
except ImportError:
    from config import (PLAYERS, DEFAULT_BENCHMARKS, DEFAULT_SIMS, PLAYER_PROFILES)
    from data.ingestion import load_data
    from features.engineering import engineer_features
    from models.probabilistic import fit_player_models
    from simulation.monte_carlo import run_full_simulation
    from utils.reporting import (
        print_best_plays, print_player_report, print_summary_banner,
        export_json, export_csv
    )
    from utils.spreadsheet import (
        results_to_rows, append_to_tracker, generate_tracker,
        update_results, list_unresolved
    )

if RICH:
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.table import Table
    from rich import box

OUTPUT_DIR   = os.path.join(_HERE, "output")
TRACKER_PATH = Path(OUTPUT_DIR) / "val_prop_tracker.xlsx"


# ── Shared helpers ────────────────────────────────────────────────────────────

def _banner():
    if RICH:
        console.print(Panel.fit(
            "[bold red]VAL[/bold red][bold white] /[/bold white][bold cyan]PROP ENGINE[/bold cyan]\n"
            "[dim]Probabilistic Valorant Performance Model  v2.0[/dim]",
            border_style="bright_blue",
        ))
    else:
        print("=" * 52)
        print("  VAL / PROP ENGINE -- Valorant Performance Model")
        print("=" * 52)


def _step(msg: str):
    if RICH:
        console.print(f"[bold yellow]>[/bold yellow]  {msg}")
    else:
        print(f">  {msg}")


def _ok(msg: str):
    if RICH:
        console.print(f"[bold green]OK[/bold green]  {msg}")
    else:
        print(f"OK  {msg}")


def _err(msg: str):
    if RICH:
        console.print(f"[bold red]ERR[/bold red] {msg}")
    else:
        print(f"ERR {msg}")


def build_benchmarks(stat: str = None, line: float = None) -> dict:
    bm = dict(DEFAULT_BENCHMARKS)
    if stat and line is not None:
        bm = {stat: line}
    elif stat:
        bm = {stat: DEFAULT_BENCHMARKS.get(stat, DEFAULT_BENCHMARKS["kills"])}
    return bm


# ── val auto ──────────────────────────────────────────────────────────────────

def run_pipeline(
    players: list,
    benchmarks: dict,
    n_sims: int,
    opp_strength: float,
    data_path: str = None,
    out_dir: str = OUTPUT_DIR,
) -> list:
    os.makedirs(out_dir, exist_ok=True)

    _step("Data ingestion ...")
    t0 = time.time()
    df = load_data(data_path)
    _step(f"  Loaded {len(df):,} records for {df['player'].nunique()} players  [{time.time()-t0:.1f}s]")

    _step("Feature engineering ...")
    t0 = time.time()
    df_feat = engineer_features(df)
    _step(f"  {len(df_feat.columns)} features built  [{time.time()-t0:.1f}s]")

    _step("Fitting probabilistic models ...")
    t0 = time.time()
    all_models = fit_player_models(df_feat)
    _step(f"  Models fitted for {len(all_models)} players  [{time.time()-t0:.1f}s]")

    _step(f"Running Monte Carlo  ({n_sims:,} sims / player) ...")
    t0 = time.time()
    results = []

    if RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as prog:
            task = prog.add_task("Simulating players", total=len(players))
            for i, player in enumerate(players):
                if player not in all_models:
                    prog.advance(task)
                    continue
                res = run_full_simulation(
                    player=player, models=all_models[player],
                    benchmarks=benchmarks, opp_strength=opp_strength,
                    n_sims=n_sims, seed=i * 7,
                )
                results.append(res)
                prog.advance(task)
    else:
        for i, player in enumerate(players):
            if player not in all_models:
                continue
            print(f"  Simulating {player} ...")
            res = run_full_simulation(
                player=player, models=all_models[player],
                benchmarks=benchmarks, opp_strength=opp_strength,
                n_sims=n_sims, seed=i * 7,
            )
            results.append(res)

    _step(f"  Simulation complete  [{time.time()-t0:.1f}s]")

    # Report
    _step("Generating premium report ...")
    print_best_plays(results)
    for res in results:
        print_player_report(res)
    if len(results) > 1:
        print_summary_banner(results)

    # JSON + CSV
    ts = time.strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"report_{ts}.json")
    export_json(results, json_path)
    export_csv(results,  os.path.join(out_dir, f"report_{ts}.csv"))

    # Spreadsheet tracker — append new rows, preserve existing actual/notes
    _step("Updating Excel tracker ...")
    try:
        run_date = time.strftime("%Y-%m-%d %H:%M")
        new_rows = results_to_rows(results, run_date)
        added    = append_to_tracker(TRACKER_PATH, new_rows)
        _ok(f"  Tracker updated (+{added} new rows) -> {TRACKER_PATH}")
    except Exception as exc:
        _err(f"  Tracker update failed: {exc}")

    return results


def cmd_auto(args: argparse.Namespace):
    _banner()
    if getattr(args, "all_players", False) or args.player is None:
        players = PLAYERS
    else:
        if args.player not in PLAYER_PROFILES:
            _err(f"Unknown player: {args.player}. Available: {', '.join(PLAYERS)}")
            sys.exit(1)
        players = [args.player]
    run_pipeline(
        players=players,
        benchmarks=build_benchmarks(args.stat, args.line),
        n_sims=args.sims,
        opp_strength=args.opp,
        data_path=args.data,
        out_dir=args.out,
    )


# ── val tracker ───────────────────────────────────────────────────────────────

def cmd_tracker(args: argparse.Namespace):
    _banner()
    json_dir  = Path(getattr(args, "reports_dir", None) or OUTPUT_DIR)
    xlsx_path = Path(getattr(args, "out",          None) or str(TRACKER_PATH))

    _step(f"Scanning {json_dir} for report_*.json ...")
    n_reports, n_rows = generate_tracker(json_dir, xlsx_path)

    if n_reports == 0:
        _err("No report JSON files found. Run  val auto  first.")
        sys.exit(1)

    _ok(f"Rebuilt tracker from {n_reports} report(s), {n_rows} prop rows")
    _ok(f"Saved -> {xlsx_path}")


# ── val results ───────────────────────────────────────────────────────────────

def cmd_results(args: argparse.Namespace):
    _banner()
    xlsx_path = Path(getattr(args, "xlsx", None) or str(TRACKER_PATH))

    # ── --list ────────────────────────────────────────────────────────────────
    if getattr(args, "list_unfilled", False):
        try:
            pending = list_unresolved(xlsx_path)
        except FileNotFoundError:
            _err(f"Tracker not found: {xlsx_path}  (run  val auto  first)")
            sys.exit(1)

        if not pending:
            _ok("No unresolved props.")
            return

        if RICH:
            tbl = Table(box=box.ROUNDED, header_style="bold magenta",
                        title="[bold]Unresolved Props[/bold]")
            tbl.add_column("Player",   style="bold white", min_width=12)
            tbl.add_column("Stat",     min_width=9)
            tbl.add_column("Side",     justify="center", min_width=7)
            tbl.add_column("Line",     justify="right",  min_width=6)
            tbl.add_column("Tier",     justify="center", min_width=10)
            tbl.add_column("EV",       justify="right",  min_width=8)
            tbl.add_column("Run Date", style="dim",      min_width=16)
            for p in pending:
                tbl.add_row(
                    p["player"], p["stat"].title(), p["side"],
                    str(p["line"]), p["tier"],
                    f"+{p['ev']:.3f}" if p["ev"] > 0 else f"{p['ev']:.3f}",
                    p["run_date"],
                )
            console.print(tbl)
        else:
            print(f"\n{'Player':<14} {'Stat':<10} {'Side':<7} {'Line':>6}  {'Tier':<10}  {'EV':>8}  Run Date")
            print("-" * 75)
            for p in pending:
                ev_s = f"+{p['ev']:.3f}" if p["ev"] > 0 else f"{p['ev']:.3f}"
                print(f"{p['player']:<14} {p['stat']:<10} {p['side']:<7} {p['line']:>6}"
                      f"  {p['tier']:<10}  {ev_s:>8}  {p['run_date']}")
        return

    # ── build entries list ─────────────────────────────────────────────────
    entries: list[dict] = []

    # Single-play flags
    if getattr(args, "player", None) and getattr(args, "stat", None):
        result_val = getattr(args, "result", None)
        side_val   = getattr(args, "side",   None)
        if not result_val or not side_val:
            _err("--player/--stat requires --side and --result")
            sys.exit(1)
        entries.append({
            "player": args.player, "stat": args.stat,
            "side":   side_val,    "result": result_val,
        })

    # Inline JSON
    elif getattr(args, "json_str", None):
        try:
            entries = _json.loads(args.json_str)
        except _json.JSONDecodeError as e:
            _err(f"Invalid JSON: {e}")
            sys.exit(1)

    # JSON file
    elif getattr(args, "file", None):
        fp = Path(args.file)
        if not fp.exists():
            _err(f"File not found: {fp}")
            sys.exit(1)
        with open(fp, encoding="utf-8") as f:
            entries = _json.load(f)

    else:
        _err("Provide one of: --list | --player/--stat/--side/--result | --json | --file")
        sys.exit(1)

    if not entries:
        _err("No entries to update.")
        sys.exit(1)

    try:
        n_updated, unmatched = update_results(xlsx_path, entries)
    except FileNotFoundError:
        _err(f"Tracker not found: {xlsx_path}  (run  val auto  first)")
        sys.exit(1)

    _ok(f"{n_updated} result(s) written to {xlsx_path}")
    if unmatched:
        for u in unmatched:
            _err(f"  Unmatched: {u}")


# ── Parser ────────────────────────────────────────────────────────────────────

def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="val",
        description="Valorant Prop Engine -- Monte Carlo Performance Model",
    )
    sub = parser.add_subparsers(dest="command")

    # ── auto ──────────────────────────────────────────────────────────────────
    auto = sub.add_parser("auto",
        help="Run full pipeline: simulate -> report -> update tracker")
    auto.add_argument("--player",      type=str,   default=None,
        help="Player name  (default: all players)")
    auto.add_argument("--stat",        type=str,   default=None,
        choices=list(DEFAULT_BENCHMARKS.keys()),
        help="Stat to analyse  (default: all stats)")
    auto.add_argument("--line",        type=float, default=None,
        help="Prop line to evaluate  (used with --stat)")
    auto.add_argument("--sims",        type=int,   default=DEFAULT_SIMS,
        help=f"Monte Carlo iterations  (default: {DEFAULT_SIMS:,})")
    auto.add_argument("--opp",         type=float, default=1.0,
        help="Opponent strength multiplier 0.8-1.2  (default: 1.0)")
    auto.add_argument("--data",        type=str,   default=None,
        help="Path to CSV data file  (default: synthetic)")
    auto.add_argument("--out",         type=str,   default=OUTPUT_DIR,
        help="Output directory for reports")
    auto.add_argument("--all-players", action="store_true",
        help="Run for all players regardless of --player")

    # ── tracker ───────────────────────────────────────────────────────────────
    tracker = sub.add_parser("tracker",
        help="Rebuild Excel tracker from all saved JSON reports")
    tracker.add_argument("--reports-dir", type=str, default=None,
        help=f"Directory of report_*.json files  (default: {OUTPUT_DIR})")
    tracker.add_argument("--out",         type=str, default=None,
        help=f"Output .xlsx path  (default: {TRACKER_PATH})")

    # ── results ───────────────────────────────────────────────────────────────
    results = sub.add_parser("results",
        help="Write actual prop outcomes into the tracker spreadsheet")
    results.add_argument("--list",    dest="list_unfilled", action="store_true",
        help="Show all props with no result yet")
    results.add_argument("--player",  type=str, default=None,
        help="Player name  (use with --stat --side --result)")
    results.add_argument("--stat",    type=str, default=None,
        help="Stat name: kills | acs | adr | kd | kast | hs_pct | assists")
    results.add_argument("--side",    type=str, default=None, choices=["over","under","OVER","UNDER"],
        help="over | under")
    results.add_argument("--result",  type=str, default=None, choices=["over","under","OVER","UNDER","hit","miss"],
        help="Actual outcome: over | under  (or hit | miss)")
    results.add_argument("--json",    dest="json_str", type=str, default=None,
        help='Inline JSON array: \'[{"player":"TenZ","stat":"kills","side":"over","result":"over"}]\'')
    results.add_argument("--file",    type=str, default=None,
        help="Path to JSON file with result entries")
    results.add_argument("--xlsx",    type=str, default=None,
        help=f"Tracker .xlsx path  (default: {TRACKER_PATH})")

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = make_parser()
    args   = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Normalise result value: hit/miss → over/under based on side
    if args.command == "results" and getattr(args, "result", None):
        r = args.result.lower()
        if r == "hit" and getattr(args, "side", None):
            args.result = args.side.upper()
        elif r == "miss" and getattr(args, "side", None):
            args.result = "UNDER" if args.side.upper() == "OVER" else "OVER"
        else:
            args.result = r.upper()

    dispatch = {
        "auto":    cmd_auto,
        "tracker": cmd_tracker,
        "results": cmd_results,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
