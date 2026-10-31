"""Does STRUCTURAL diversity behave any differently from raw exposer count?

The proposal's headline technique is Ugander et al.'s measure: not how many
distinct neighbours exposed you (`d`), but how many *connected components* the
exposing neighbourhood breaks into (`sd`). Two exposures from two friends who
know each other are one social source; from two strangers, two sources.

The main analysis put `d` through the shuffled-time null and found the excess
decaying to 1.0. This runs the identical treatment on `sd`, so the proposal's
actual promise is tested rather than a proxy for it.

    python scripts/check_diversity.py --reps 3
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import sys  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

from src import config, curve, events, nulls  # noqa: E402


def report(name: str, cmp: pd.DataFrame, key: str):  # Defines a reusable step; the following indented lines are its body.
    print(f"\n--- {name} ---")  # Prints this reading so a command-line run can be followed.
    print(f"{key:>3} {'n':>9} {'real':>8} {'null':>8} {'lift':>7} {'z':>7}")  # Prints this reading so a command-line run can be followed.
    for r in cmp.itertuples(index=False):  # Repeats the next indented steps once for each item.
        print(f"{int(getattr(r, key)):>3} {int(r.n_real):>9,} {r.rate_real:>8.4f} "  # Prints this reading so a command-line run can be followed.
              f"{r.rate_null:>8.4f} {r.lift_over_null:>7.3f} {r.z_vs_null:>7.1f}")  # Compares the observed adoption rate with the shuffled-time reference rate.
    first, last = cmp.iloc[0], cmp.iloc[-1]  # Runs this instruction as part of the current step.
    print(f"excess {first.lift_over_null:.3f}x at {key}=1 -> "  # Compares the observed adoption rate with the shuffled-time reference rate.
          f"{last.lift_over_null:.3f}x at {key}={int(getattr(last, key))}  "  # Compares the observed adoption rate with the shuffled-time reference rate.
          f"({'RISES' if last.lift_over_null > first.lift_over_null else 'decays'})")  # Compares the observed adoption rate with the shuffled-time reference rate.


def main():  # Compare the distinct-opponent and structural-diversity readings.
    """Compare the distinct-opponent and structural-diversity readings."""
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games",  # Defines a command-line option for this script.
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))  # Saves a value named default so the next lines can use it.
    ap.add_argument("--reps", type=int, default=3)  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.

    df = pd.read_parquet(a.games)  # Loads a previously prepared game or trial table.
    print(f"{len(df):,} games, {a.reps} null replicate(s), "  # Prints this reading so a command-line run can be followed.
          f"window {config.ADOPTION_WINDOW_DAYS}d")  # Runs this instruction as part of the current step.

    trials = events.build_trials(df)  # Stores the exposure-trial table for the next step.
    tables = curve.analyse(trials)  # Calculates adoption rates for different exposure counts.
    w = config.ADOPTION_WINDOW_DAYS  # Saves a value named w so the next lines can use it.

    out = {}  # Stores the output value for the next step.
    for key in ("d", "sd"):  # Repeats the next indented steps once for each item.
        null = nulls.run_null(df, n_reps=a.reps, kind="shuffle",  # Stores the shuffled reference for the next step.
                              window_days=w, by=key)  # Saves a value named window_days so the next lines can use it.
        cmp = nulls.compare(tables["by_" + key], null, by=key)  # Stores the observed-versus-reference comparison for the next step.
        cmp.to_csv(config.TABLES / f"null_comparison_{key}.csv", index=False)  # Writes a result table that can be inspected or downloaded.
        out[key] = cmp  # Stores this value under its player, opening, or field key.
        report("d  (distinct exposers)" if key == "d"  # Runs this instruction as part of the current step.
               else "sd (structural diversity, Ugander et al.)", cmp, key)  # Runs this instruction as part of the current step.

    # Does holding k fixed and varying sd separate anything?
    hk = tables["held_k_by_sd"]  # Saves a value named hk so the next lines can use it.
    hk = hk[hk["n"] >= 20]  # Saves a value named hk so the next lines can use it.
    sep = False  # Saves a value named sep so the next lines can use it.
    for k, sub in hk.groupby("k"):  # Groups rows sharing these keys before counting or averaging them.
        if len(sub) >= 2 and sub.iloc[-1]["lo"] > sub.iloc[0]["hi"]:  # Runs the next indented steps only when this condition is true.
            sep = True  # Saves a value named sep so the next lines can use it.
    print(f"\nfixed-k separation on sd: {sep}")  # Prints this reading so a command-line run can be followed.

    d_last = out["d"].iloc[-1]["lift_over_null"]  # Compares the observed adoption rate with the shuffled-time reference rate.
    s_last = out["sd"].iloc[-1]["lift_over_null"]  # Compares the observed adoption rate with the shuffled-time reference rate.
    print(f"\nconclusion: sd tracks d "  # Prints this reading so a command-line run can be followed.
          f"(excess at max: d {d_last:.3f}x, sd {s_last:.3f}x). "  # Runs this instruction as part of the current step.
          f"{'sd tells a different story - investigate' if abs(d_last - s_last) > 0.08 else 'Same verdict on both measures.'}")  # Runs this instruction as part of the current step.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
