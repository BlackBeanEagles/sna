"""Robustness check at ply granularity (proposal, Section 4 / Build Guide).

The main analysis defines a behaviour by ECO code, which is coarse: many
distinct ideas share one code. Defining it by the first k plies is sharper but
fragments the data, so it is a robustness check rather than the main result.

If the verdict flips between the two granularities, the ECO-level finding is an
artefact of the coding scheme and must be reported as such.

    python scripts/check_ply.py --reps 3
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import sys  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

from src import config, curve, events, nulls  # noqa: E402


def analyse(df: pd.DataFrame, granularity: str, reps: int) -> dict:  # Repeat the core comparison with one opening definition at a time.
    """Repeat the core comparison with one opening definition at a time."""
    trials = events.build_trials(df, granularity=granularity)  # Stores the exposure-trial table for the next step.
    if not len(trials):  # Checks whether enough records exist for a trustworthy next step.
        return {"granularity": granularity, "error": "no trials"}  # Gives this answer back to the code that called the function.
    tables = curve.analyse(trials)  # Calculates adoption rates for different exposure counts.
    # the null MUST use the same granularity as the real trials
    null = nulls.run_null(df, n_reps=reps, kind="shuffle",  # Stores the shuffled reference for the next step.
                          window_days=config.ADOPTION_WINDOW_DAYS,  # Saves a value named window_days so the next lines can use it.
                          granularity=granularity)  # Saves a value named granularity so the next lines can use it.
    cmp = nulls.compare(tables["by_d"], null)  # Stores the observed-versus-reference comparison for the next step.
    v = curve.verdict(tables, cmp)  # Applies the result rules to the real and shuffled curves.
    return {  # Gives this answer back to the code that called the function.
        "granularity": granularity,
        "behaviours": int(trials["opening"].nunique()),
        "trials": int(len(trials)),
        "adoptions": int(trials["adopted"].sum()),
        "rate": round(float(trials["adopted"].mean()), 4),
        "cmp": cmp,
        "verdict": v,
    }  # Closes the data structure or function call started above.


def show(r: dict):  # Defines a reusable step; the following indented lines are its body.
    print(f"\n=== {r['granularity']} ===")  # Prints this reading so a command-line run can be followed.
    if "error" in r:  # Runs the next indented steps only when this condition is true.
        print(" ", r["error"]); return  # Prints this reading so a command-line run can be followed.
    print(f"  behaviours {r['behaviours']:,} · trials {r['trials']:,} · "  # Prints this reading so a command-line run can be followed.
          f"adoptions {r['adoptions']:,} ({r['rate']*100:.2f}%)")  # Runs this instruction as part of the current step.
    c = r["cmp"]  # Saves a value named c so the next lines can use it.
    print(f"  {'d':>3} {'n':>9} {'real':>8} {'null':>8} {'lift':>7}")  # Prints this reading so a command-line run can be followed.
    for row in c.itertuples(index=False):  # Repeats the next indented steps once for each item.
        print(f"  {int(row.d):>3} {int(row.n_real):>9,} {row.rate_real:>8.4f} "  # Prints this reading so a command-line run can be followed.
              f"{row.rate_null:>8.4f} {row.lift_over_null:>7.3f}")  # Compares the observed adoption rate with the shuffled-time reference rate.
    v = r["verdict"]  # Saves a value named v so the next lines can use it.
    print(f"  excess {v.get('lift_over_null_at_min_d')}x -> "  # Compares the observed adoption rate with the shuffled-time reference rate.
          f"{v.get('lift_over_null_at_max_d')}x")  # Compares the observed adoption rate with the shuffled-time reference rate.
    print(f"  VERDICT: {v['verdict']}")  # Prints this reading so a command-line run can be followed.


def main():  # Defines a reusable step; the following indented lines are its body.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games",  # Defines a command-line option for this script.
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))  # Saves a value named default so the next lines can use it.
    ap.add_argument("--reps", type=int, default=3)  # Defines a command-line option for this script.
    ap.add_argument("--depth", type=int, default=config.PLY_KEY_DEPTH)  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.

    config.PLY_KEY_DEPTH = a.depth  # Saves a value named PLY_KEY_DEPTH so the next lines can use it.
    df = pd.read_parquet(a.games)  # Loads a previously prepared game or trial table.
    print(f"{len(df):,} games · ply depth {a.depth} · {a.reps} null replicate(s)")  # Prints this reading so a command-line run can be followed.

    results = [analyse(df, g, a.reps) for g in ("eco", "ply")]  # Saves a value named results so the next lines can use it.
    for r in results:  # Repeats the next indented steps once for each item.
        show(r)  # Runs this instruction as part of the current step.

    ok = [r for r in results if "error" not in r]  # Saves a value named ok so the next lines can use it.
    if len(ok) == 2:  # Runs the next indented steps only when this condition is true.
        same = ok[0]["verdict"]["verdict"] == ok[1]["verdict"]["verdict"]  # Saves a value named same so the next lines can use it.
        print(f"\nverdicts agree across granularity: {same}")  # Prints this reading so a command-line run can be followed.
        if not same:  # Runs the next indented steps only when this condition is true.
            print("  !! the ECO-level result does NOT survive at ply level — "  # Prints this reading so a command-line run can be followed.
                  "report this prominently")
        for r in ok:  # Repeats the next indented steps once for each item.
            r["cmp"].to_csv(  # Writes a result table that can be inspected or downloaded.
                config.TABLES / f"null_comparison_{r['granularity']}.csv",  # Part of the value, collection, or call spanning several lines.
                index=False)  # Saves a value named index so the next lines can use it.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
