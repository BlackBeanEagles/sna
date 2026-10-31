"""End-to-end runner. Every stage is a function so the null model can replay
stages 3-5 on permuted data (Build Guide, Step 6).

Presentation route: start here for the command-line workflow. The live web
demo follows the same analysis in server/runner.py and reports its progress to
server/static/index.html. The final tables and figure are written to results/.

    python -m src.run_pipeline --simulate            # synthetic validation run
    python -m src.run_pipeline --pgn data/raw/x.pgn  # real archive slice
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import json  # Loads JSON tools for saved results and browser messages.
import time  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

from . import (animate, config, curve, events, matching, nulls, parse,  # Loads the named parts of this project so this file can use their functions.
               predict, simulate, structure)  # Runs this instruction as part of the current step.


def main():  # Defines a reusable step; the following indented lines are its body.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--pgn", default=None,  # Defines a command-line option for this script.
                    help="PGN / .pgn.zst path, or a database.lichess.org URL")  # Saves a value named help so the next lines can use it.
    ap.add_argument("--month", default=None,  # Defines a command-line option for this script.
                    help="YYYY-MM: stream that Lichess month directly, no download")  # Saves a value named help so the next lines can use it.
    ap.add_argument("--simulate", action="store_true",  # Defines a command-line option for this script.
                    help="generate synthetic data with a known contagion rule")  # Saves a value named help so the next lines can use it.
    ap.add_argument("--sim-players", type=int, default=2000)  # Defines a command-line option for this script.
    ap.add_argument("--sim-games", type=int, default=80000)  # Defines a command-line option for this script.
    ap.add_argument("--limit", type=int, default=None)  # Defines a command-line option for this script.
    ap.add_argument("--null-reps", type=int, default=config.N_NULL_REPLICATES)  # Defines a command-line option for this script.
    ap.add_argument("--null-kind", default="shuffle",  # Defines a command-line option for this script.
                    choices=["shuffle", "rewire"],  # Saves a value named choices so the next lines can use it.
                    help="timestamp shuffling, or degree-preserving rewiring")  # Saves a value named help so the next lines can use it.
    ap.add_argument("--no-animation", action="store_true")  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.

    t_start = time.time()  # Saves a value named t_start so the next lines can use it.
    report: dict = {}  # Stores the saved study results for the next step.

    if a.month:  # Runs the next indented steps only when this condition is true.
        from .fetch import BASE  # Loads code this file needs for the steps below.
        a.pgn = BASE.format(month=a.month)  # Saves a value named pgn so the next lines can use it.

    if a.simulate or not a.pgn:  # Runs the next indented steps only when this condition is true.
        # Synthetic games are a check that the method can recover a known rule.
        # The reported January findings come from real Lichess games instead.
        print("[1/8] simulating games with a planted complex-contagion rule ...")  # Prints this reading so a command-line run can be followed.
        info = simulate.simulate(n_players=a.sim_players, n_games=a.sim_games)  # Saves a value named info so the next lines can use it.
        pgn = Path(info["path"])  # Saves a value named pgn so the next lines can use it.
        report["simulation"] = {k: str(v) for k, v in info.items()}  # Stores this value under its player, opening, or field key.
    else:  # Handles the alternative when the preceding condition was false.
        pgn = a.pgn if str(a.pgn).startswith("http") else Path(a.pgn)  # Saves a value named pgn so the next lines can use it.

    # Simulated runs write to their own filename so that games.parquet always
    # means real data -- a stale synthetic table there gets analysed silently.
    games_path = config.INTERIM / (  # Saves a value named games_path so the next lines can use it.
        "simulated_games.parquet" if (a.simulate or not a.pgn) else "games.parquet")

    label = str(pgn).rsplit("/", 1)[-1]  # Saves a value named label so the next lines can use it.
    print(f"[2/8] parsing {label} ...")  # Prints this reading so a command-line run can be followed.
    games = parse.run(pgn, games_path, limit=a.limit,  # Saves a value named games so the next lines can use it.
                      progress=250000)  # Saves a value named progress so the next lines can use it.
    report["parse"] = {  # Part of the value, collection, or call spanning several lines.
        "games": len(games), "skipped": games.attrs["skipped"],
        "players": len(set(games.white) | set(games.black)),
        "span": [str(games.ts.min()), str(games.ts.max())],
        "openings": int(games.eco.nunique()),
    }  # Closes the data structure or function call started above.
    print("      ", report["parse"])  # Prints this reading so a command-line run can be followed.
    if len(games) < 100:  # Checks whether enough records exist for a trustworthy next step.
        print("!! too few games survived the filters -- widen the sample")  # Prints this reading so a command-line run can be followed.
        return  # Stops this function here.

    print("[3/8] building exposure/adoption trials ...")  # Prints this reading so a command-line run can be followed.
    # A trial asks: after seeing an opening, did this player use it within the
    # observation window? events.py creates one row per eligible exposure.
    trials = events.run(games_path,  # Stores the exposure-trial table for the next step.
                        config.PROCESSED / "trials.parquet")  # Runs this instruction as part of the current step.
    report["trials"] = {"n": len(trials), "adoptions": int(trials.adopted.sum()),  # Part of the value, collection, or call spanning several lines.
                        "rate": round(float(trials.adopted.mean()), 4)}
    print("      ", report["trials"])  # Prints this reading so a command-line run can be followed.

    print("[4/8] network structure and early adopters ...")  # Prints this reading so a command-line run can be followed.
    _, feats, by_early, net_summary = structure.run(games_path)  # Runs this instruction as part of the current step.
    report["network"] = net_summary  # Stores this value under its player, opening, or field key.
    report["early_adopters"] = by_early.round(4).to_dict()  # Converts table values into JSON-friendly records for a report or UI event.

    print(f"[5/8] {a.null_kind} null ({a.null_reps} replicates) ...")  # Prints this reading so a command-line run can be followed.
    # Re-running the trial construction after shuffling game times gives the
    # baseline expected from popularity/activity without the original order.
    cmp = nulls.run(games_path,  # Stores the observed-versus-reference comparison for the next step.
                    config.PROCESSED / "trials.parquet",  # Part of the value, collection, or call spanning several lines.
                    n_reps=a.null_reps, kind=a.null_kind)  # Saves a value named n_reps so the next lines can use it.
    report["null_comparison"] = (cmp.round(4).to_dict(orient="records")  # Converts table values into JSON-friendly records for a report or UI event.
                                 if len(cmp) else [])  # Runs the next indented steps only when this condition is true.
    if len(cmp):  # Runs the next indented steps only when this condition is true.
        print(cmp.round(3).to_string(index=False))  # Prints this reading so a command-line run can be followed.

    print("[6/8] adoption-probability curve + verdict ...")  # Prints this reading so a command-line run can be followed.
    tables, v, fig = curve.run(config.PROCESSED / "trials.parquet",  # Part of the value, collection, or call spanning several lines.
                               cmp if len(cmp) else None)  # Runs this instruction as part of the current step.
    report["curve_by_d"] = tables["by_d"].round(4).to_dict(orient="records")  # Converts table values into JSON-friendly records for a report or UI event.
    report["verdict"] = v  # Stores this value under its player, opening, or field key.
    print("      ", v)  # Prints this reading so a command-line run can be followed.

    print("[7/8] matched controls + held-out AUC ...")  # Prints this reading so a command-line run can be followed.
    # These are independent checks: similar unexposed players for comparison,
    # and prediction on player-opening spells the model did not train on.
    report["matched_controls"] = matching.run(games_path)  # Stores this value under its player, opening, or field key.
    report["predictive"] = predict.run(config.PROCESSED / "trials.parquet",  # Part of the value, collection, or call spanning several lines.
                                       games_path)  # Runs this instruction as part of the current step.
    print("      ", report["matched_controls"])  # Prints this reading so a command-line run can be followed.
    print("      ", {k: v for k, v in report["predictive"].items()  # Prints this reading so a command-line run can be followed.
                     if k.startswith("auc")})  # Runs the next indented steps only when this condition is true.

    if not a.no_animation:  # Runs the next indented steps only when this condition is true.
        print("[8/8] diffusion animation ...")  # Prints this reading so a command-line run can be followed.
        report["animation"] = {k: str(v) for k, v in  # Stores this value under its player, opening, or field key.
                               animate.run(games_path).items()}  # Runs this instruction as part of the current step.

    report["runtime_seconds"] = round(time.time() - t_start, 1)  # Stores this value under its player, opening, or field key.
    out = config.RESULTS / "report.json"  # Stores the output value for the next step.
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")  # Encodes Python values as JSON for saving or sending to the browser.
    print(f"\ndone in {report['runtime_seconds']}s -> {out}")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
