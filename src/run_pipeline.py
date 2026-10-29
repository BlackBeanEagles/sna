"""End-to-end runner. Every stage is a function so the null model can replay
stages 3-5 on permuted data (Build Guide, Step 6).

    python -m src.run_pipeline --simulate            # synthetic validation run
    python -m src.run_pipeline --pgn data/raw/x.pgn  # real archive slice
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import (animate, config, curve, events, matching, nulls, parse,
               predict, simulate, structure)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", default=None,
                    help="PGN / .pgn.zst path, or a database.lichess.org URL")
    ap.add_argument("--month", default=None,
                    help="YYYY-MM: stream that Lichess month directly, no download")
    ap.add_argument("--simulate", action="store_true",
                    help="generate synthetic data with a known contagion rule")
    ap.add_argument("--sim-players", type=int, default=2000)
    ap.add_argument("--sim-games", type=int, default=80000)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--null-reps", type=int, default=config.N_NULL_REPLICATES)
    ap.add_argument("--null-kind", default="shuffle",
                    choices=["shuffle", "rewire"],
                    help="timestamp shuffling, or degree-preserving rewiring")
    ap.add_argument("--no-animation", action="store_true")
    a = ap.parse_args()

    t_start = time.time()
    report: dict = {}

    if a.month:
        from .fetch import BASE
        a.pgn = BASE.format(month=a.month)

    if a.simulate or not a.pgn:
        print("[1/8] simulating games with a planted complex-contagion rule ...")
        info = simulate.simulate(n_players=a.sim_players, n_games=a.sim_games)
        pgn = Path(info["path"])
        report["simulation"] = {k: str(v) for k, v in info.items()}
    else:
        pgn = a.pgn if str(a.pgn).startswith("http") else Path(a.pgn)

    # Simulated runs write to their own filename so that games.parquet always
    # means real data -- a stale synthetic table there gets analysed silently.
    games_path = config.INTERIM / (
        "simulated_games.parquet" if (a.simulate or not a.pgn) else "games.parquet")

    label = str(pgn).rsplit("/", 1)[-1]
    print(f"[2/8] parsing {label} ...")
    games = parse.run(pgn, games_path, limit=a.limit,
                      progress=250000)
    report["parse"] = {
        "games": len(games), "skipped": games.attrs["skipped"],
        "players": len(set(games.white) | set(games.black)),
        "span": [str(games.ts.min()), str(games.ts.max())],
        "openings": int(games.eco.nunique()),
    }
    print("      ", report["parse"])
    if len(games) < 100:
        print("!! too few games survived the filters -- widen the sample")
        return

    print("[3/8] building exposure/adoption trials ...")
    trials = events.run(games_path,
                        config.PROCESSED / "trials.parquet")
    report["trials"] = {"n": len(trials), "adoptions": int(trials.adopted.sum()),
                        "rate": round(float(trials.adopted.mean()), 4)}
    print("      ", report["trials"])

    print("[4/8] network structure and early adopters ...")
    _, feats, by_early, net_summary = structure.run(games_path)
    report["network"] = net_summary
    report["early_adopters"] = by_early.round(4).to_dict()

    print(f"[5/8] {a.null_kind} null ({a.null_reps} replicates) ...")
    cmp = nulls.run(games_path,
                    config.PROCESSED / "trials.parquet",
                    n_reps=a.null_reps, kind=a.null_kind)
    report["null_comparison"] = (cmp.round(4).to_dict(orient="records")
                                 if len(cmp) else [])
    if len(cmp):
        print(cmp.round(3).to_string(index=False))

    print("[6/8] adoption-probability curve + verdict ...")
    tables, v, fig = curve.run(config.PROCESSED / "trials.parquet",
                               cmp if len(cmp) else None)
    report["curve_by_d"] = tables["by_d"].round(4).to_dict(orient="records")
    report["verdict"] = v
    print("      ", v)

    print("[7/8] matched controls + held-out AUC ...")
    report["matched_controls"] = matching.run(games_path)
    report["predictive"] = predict.run(config.PROCESSED / "trials.parquet",
                                       games_path)
    print("      ", report["matched_controls"])
    print("      ", {k: v for k, v in report["predictive"].items()
                     if k.startswith("auc")})

    if not a.no_animation:
        print("[8/8] diffusion animation ...")
        report["animation"] = {k: str(v) for k, v in
                               animate.run(games_path).items()}

    report["runtime_seconds"] = round(time.time() - t_start, 1)
    out = config.RESULTS / "report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\ndone in {report['runtime_seconds']}s -> {out}")


if __name__ == "__main__":
    main()
