"""Does the verdict depend on the 14-day adoption window?

The window is a researcher's choice, not a property of the data. The Build
Guide says to pick one and state it, which the project does — but an unstated
sensitivity is a free parameter an examiner can push on. This reruns the whole
comparison at several windows.

    python scripts/check_window.py --windows 7 14 28 --reps 2
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import sys  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

from src import config, curve, events, nulls  # noqa: E402


def main():  # Defines a reusable step; the following indented lines are its body.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games",  # Defines a command-line option for this script.
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))  # Saves a value named default so the next lines can use it.
    ap.add_argument("--windows", type=int, nargs="+", default=[7, 14, 28])  # Defines a command-line option for this script.
    ap.add_argument("--reps", type=int, default=2)  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.

    df = pd.read_parquet(a.games)  # Loads a previously prepared game or trial table.
    print(f"{len(df):,} games · windows {a.windows} · {a.reps} replicate(s)\n")  # Prints this reading so a command-line run can be followed.

    rows = []  # Stores the result rows collected for the output table for the next step.
    for w in a.windows:  # Repeats the next indented steps once for each item.
        # Rebuild both sides with the SAME window. Otherwise a change in the
        # verdict could be a mismatched comparison instead of sensitivity.
        trials = events.build_trials(df, window_days=w)  # Stores the exposure-trial table for the next step.
        if not len(trials):  # Checks whether enough records exist for a trustworthy next step.
            print(f"window {w}d: no trials"); continue  # Prints this reading so a command-line run can be followed.
        tables = curve.analyse(trials)  # Calculates adoption rates for different exposure counts.
        null = nulls.run_null(df, n_reps=a.reps, kind="shuffle", window_days=w)  # Stores the shuffled reference for the next step.
        cmp = nulls.compare(tables["by_d"], null)  # Stores the observed-versus-reference comparison for the next step.
        v = curve.verdict(tables, cmp)  # Applies the result rules to the real and shuffled curves.
        f, l = cmp.iloc[0], cmp.iloc[-1]  # Runs this instruction as part of the current step.
        rows.append({  # Part of the value, collection, or call spanning several lines.
            "window_days": w,
            "trials": len(trials),
            "adoptions": int(trials.adopted.sum()),
            "rate": round(float(trials.adopted.mean()), 4),
            "excess_at_d1": round(float(f.lift_over_null), 3),
            "excess_at_dmax": round(float(l.lift_over_null), 3),
            "decays": bool(l.lift_over_null < f.lift_over_null),
            "verdict": v["verdict"].split(":")[0],
        })  # Runs this instruction as part of the current step.
        print(f"window {w:>3}d  trials {len(trials):>8,}  "  # Prints this reading so a command-line run can be followed.
              f"adoptions {int(trials.adopted.sum()):>7,} "  # Runs this instruction as part of the current step.
              f"({trials.adopted.mean()*100:5.2f}%)  "  # Runs this instruction as part of the current step.
              f"excess {f.lift_over_null:.3f} -> {l.lift_over_null:.3f}  "  # Compares the observed adoption rate with the shuffled-time reference rate.
              f"{rows[-1]['verdict']}")  # Runs this instruction as part of the current step.

    out = pd.DataFrame(rows)  # Creates a labelled table from the collected rows.
    p = config.TABLES / "window_sensitivity.csv"  # Saves a value named p so the next lines can use it.
    out.to_csv(p, index=False)  # Writes a result table that can be inspected or downloaded.
    print(f"\nall windows decay: {out['decays'].all()}")  # Prints this reading so a command-line run can be followed.
    print(f"verdicts: {sorted(set(out['verdict']))}")  # Prints this reading so a command-line run can be followed.
    print(f"wrote {p}")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
