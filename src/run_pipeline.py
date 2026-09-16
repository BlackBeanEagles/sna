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

import pandas as pd

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

    label = str(pgn).rsplit("/", 1)[-1]
    print(f"[2/8] parsing {label} ...")
    games = parse.run(pgn, config.INTERIM / "games.parquet", limit=a.limit,
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
    trials = events.run(config.INTERIM / "games.parquet",
                        config.PROCESSED / "trials.parquet")
    report["trials"] = {"n": len(trials), "adoptions": int(trials.adopted.sum()),
                        "rate": round(float(trials.adopted.mean()), 4)}
    print("      ", report["trials"])

    print("[4/8] network structure and early adopters ...")
    _, feats, by_early, net_summary = structure.run(config.INTERIM / "games.parquet")
    report["network"] = net_summary
    report["early_adopters"] = by_early.round(4).to_dict()

    print(f"[5/8] timestamp-shuffled null ({a.null_reps} replicates) ...")
    cmp = nulls.run(config.INTERIM / "games.parquet",
                    config.PROCESSED / "trials.parquet", n_reps=a.null_reps)
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
    report["matched_controls"] = matching.run(config.INTERIM / "games.parquet")
    report["predictive"] = predict.run(config.PROCESSED / "trials.parquet",
                                       config.PROCESSED / "node_features.parquet")
    print("      ", report["matched_controls"])
    print("      ", {k: v for k, v in report["predictive"].items()
                     if k.startswith("auc")})

    if not a.no_animation:
        print("[8/8] diffusion animation ...")
        report["animation"] = {k: str(v) for k, v in
                               animate.run(config.INTERIM / "games.parquet").items()}

    report["runtime_seconds"] = round(time.time() - t_start, 1)
    out = config.RESULTS / "report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\ndone in {report['runtime_seconds']}s -> {out}")


if __name__ == "__main__":
    main()
