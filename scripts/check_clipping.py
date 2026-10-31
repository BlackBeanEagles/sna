"""Is the excess-over-null decay real, or an artefact of the d-bucket cap?

The headline result says the excess over the shuffled-time null decays to
1.000 by d = 6. But MAX_DIVERSITY = 6 makes d = 6 a *clipped* bucket holding
every trial with six or more distinct exposers -- in the full-month run that
was n = 46,846, larger than d = 4 and d = 5 combined. If the tail is doing the
work, the convergence could be an artefact of lumping it together.

This re-runs the curve and the null with the cap raised, so the tail is spread
out and the decay can be read move by move.

    python scripts/check_clipping.py --cap 12 --reps 3
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import sys  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

from src import config  # noqa: E402


def main():  # Widen plotted exposure buckets and rerun the real/null comparison.
    """Widen plotted exposure buckets and rerun the real/null comparison.

    This checks whether the 6+ group hides a different pattern in its tail.
    """
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games", default=str(config.INTERIM / "slice_2016-01_full.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--cap", type=int, default=12)  # Defines a command-line option for this script.
    ap.add_argument("--reps", type=int, default=3)  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.

    # Raise the caps BEFORE importing the analysis modules read them at call
    # time, so both the real curve and the null use the wider buckets.
    config.MAX_DIVERSITY = a.cap  # Saves a value named MAX_DIVERSITY so the next lines can use it.
    config.MAX_EXPOSURE_COUNT = a.cap  # Saves a value named MAX_EXPOSURE_COUNT so the next lines can use it.

    from src import curve, events, nulls  # noqa: E402  (after the cap change)

    df = pd.read_parquet(a.games)  # Loads a previously prepared game or trial table.
    print(f"{len(df):,} games, cap d at {a.cap}, {a.reps} null replicate(s)\n")  # Prints this reading so a command-line run can be followed.

    trials = events.build_trials(df)  # Stores the exposure-trial table for the next step.
    tables = curve.analyse(trials)  # Calculates adoption rates for different exposure counts.
    null_by_d = nulls.run_null(df, n_reps=a.reps, kind="shuffle",  # Stores the reference rates grouped by different opponents for the next step.
                               window_days=config.ADOPTION_WINDOW_DAYS)  # Saves a value named window_days so the next lines can use it.
    cmp = nulls.compare(tables["by_d"], null_by_d)  # Stores the observed-versus-reference comparison for the next step.

    print(f"{'d':>3} {'n':>9} {'real':>8} {'null':>8} {'lift':>7} {'z':>8}")  # Prints this reading so a command-line run can be followed.
    for r in cmp.itertuples(index=False):  # Repeats the next indented steps once for each item.
        print(f"{int(r.d):>3} {int(r.n_real):>9,} {r.rate_real:>8.4f} "  # Prints this reading so a command-line run can be followed.
              f"{r.rate_null:>8.4f} {r.lift_over_null:>7.3f} {r.z_vs_null:>8.1f}")  # Compares the observed adoption rate with the shuffled-time reference rate.

    v = curve.verdict(tables, cmp)  # Applies the result rules to the real and shuffled curves.
    print("\nverdict:", v["verdict"])  # Prints this reading so a command-line run can be followed.
    for k in ("lift_over_null_at_min_d", "lift_over_null_at_max_d",  # Compares the observed adoption rate with the shuffled-time reference rate.
              "separated_at_fixed_k", "excess_over_null_grows_with_d"):
        if k in v:  # Runs the next indented steps only when this condition is true.
            print(f"  {k}: {v[k]}")  # Prints this reading so a command-line run can be followed.

    out = config.TABLES / f"null_comparison_cap{a.cap}.csv"  # Stores the output value for the next step.
    cmp.to_csv(out, index=False)  # Writes a result table that can be inspected or downloaded.
    print(f"\nwrote {out}")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
