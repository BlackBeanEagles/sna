"""Are the trials independent? They are not — how much does it matter?

The trial table has one row per (player, behaviour, k-th exposure). That means
a single player-behaviour spell contributes several rows, and — because
`adopted` is scored for every exposure whose window contains the adoption —
one real adoption event can be counted many times over.

Earlier reports counted many exposure rows per eventual adoption. Trial-level
Wilson intervals and z-scores assume independent observations and can be too
narrow when players and behaviours recur. The current numbers are printed by
this script from the selected game table.
This script recomputes the headline comparison with ONE row per spell, so each
player-behaviour contributes exactly one observation and each adoption is
counted exactly once. If the excess-over-null decay survives that, the finding
is not an artefact of pseudo-replication.

    python scripts/check_independence.py --reps 3
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import sys  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import numpy as np  # Loads the number library used for fast calculations.
import pandas as pd  # Loads the table library used to store games and trials.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

from src import config, curve, events, nulls  # noqa: E402

SPELL = ["player", "opening", "colour"]  # Saves a value named SPELL so the next lines can use it.


def collapse(trials: pd.DataFrame, how: str = "last") -> pd.DataFrame:  # One row per spell.
    """One row per spell. 'last' keeps the final exposure state before the
    window closes (largest k and d); 'first' keeps the first exposure.
    This checks whether repeated rows for one eventual adoption drive a
    result that looks stronger than it should.
    """
    if not len(trials):  # Checks whether enough records exist for a trustworthy next step.
        return trials  # Gives this answer back to the code that called the function.
    t = trials.sort_values(["player", "opening", "colour", "k"])  # Orders the rows by this field before the next calculation.
    idx = t.groupby(SPELL)["k"].idxmax() if how == "last" else t.groupby(SPELL)["k"].idxmin()  # Groups rows sharing these keys before counting or averaging them.
    out = t.loc[idx].copy()  # Stores the output value for the next step.
    # adopted at spell level: did this spell ever record an adoption?
    ever = trials.groupby(SPELL)["adopted"].max().rename("ever")  # Groups rows sharing these keys before counting or averaging them.
    out = out.merge(ever, on=SPELL, how="left")  # Joins two tables on shared identifiers so their columns can be compared.
    out["adopted"] = out["ever"].astype(int)  # Stores this value under its player, opening, or field key.
    return out.drop(columns="ever")  # Gives this answer back to the code that called the function.


def curve_from(trials: pd.DataFrame) -> pd.DataFrame:  # Defines a reusable step; the following indented lines are its body.
    t = trials.copy()  # Stores the current game or exposure time for the next step.
    t["d"] = t["d"].clip(upper=config.MAX_DIVERSITY)  # Caps large counts into the final chart bucket, such as six or more opponents.
    return curve.rate_table(t, "d")  # Gives this answer back to the code that called the function.


def main():  # Defines a reusable step; the following indented lines are its body.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games",  # Defines a command-line option for this script.
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))  # Saves a value named default so the next lines can use it.
    ap.add_argument("--reps", type=int, default=3)  # Defines a command-line option for this script.
    ap.add_argument("--how", default="last", choices=["last", "first"])  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.

    df = pd.read_parquet(a.games)  # Loads a previously prepared game or trial table.
    w = config.ADOPTION_WINDOW_DAYS  # Saves a value named w so the next lines can use it.
    real = events.build_trials(df, window_days=w)  # Saves a value named real so the next lines can use it.
    real_sp = collapse(real, a.how)  # Saves a value named real_sp so the next lines can use it.

    print(f"{len(df):,} games")  # Prints this reading so a command-line run can be followed.
    print(f"per-exposure rows {len(real):,}  ->  per-spell rows {len(real_sp):,}"  # Prints this reading so a command-line run can be followed.
          f"  ({len(real_sp)/len(real):.1%})")  # Runs this instruction as part of the current step.
    print(f"adoptions {int(real.adopted.sum()):,} -> "  # Prints this reading so a command-line run can be followed.
          f"{int(real_sp.adopted.sum()):,} distinct events\n")  # Runs this instruction as part of the current step.

    # null, collapsed exactly the same way
    rng = np.random.default_rng(config.RANDOM_SEED)  # Saves a value named rng so the next lines can use it.
    frames = []  # Saves a value named frames so the next lines can use it.
    for rep in range(a.reps):  # Repeats the next indented steps once for each item.
        nd = nulls.shuffle_timestamps(df, rng)  # Saves a value named nd so the next lines can use it.
        nt = events.build_trials(nd, window_days=w)  # Saves a value named nt so the next lines can use it.
        if not len(nt):  # Checks whether enough records exist for a trustworthy next step.
            continue  # Skips this item and moves to the next loop iteration.
        tb = curve_from(collapse(nt, a.how))  # Saves a value named tb so the next lines can use it.
        tb["rep"] = rep  # Stores this value under its player, opening, or field key.
        frames.append(tb)  # Adds this item to the list being built.
    null = (pd.concat(frames, ignore_index=True)  # Stores the shuffled reference for the next step.
            .groupby("d").agg(n=("n", "sum"), rate=("rate", "mean"),  # Groups rows sharing these keys before counting or averaging them.
                              rate_sd=("rate", "std")).reset_index())  # Saves a value named rate_sd so the next lines can use it.

    cmp = nulls.compare(curve_from(real_sp), null)  # Stores the observed-versus-reference comparison for the next step.
    print(f"{'d':>3} {'n':>8} {'real':>8} {'null':>8} {'lift':>7} {'z':>7}")  # Prints this reading so a command-line run can be followed.
    for r in cmp.itertuples(index=False):  # Repeats the next indented steps once for each item.
        print(f"{int(r.d):>3} {int(r.n_real):>8,} {r.rate_real:>8.4f} "  # Prints this reading so a command-line run can be followed.
              f"{r.rate_null:>8.4f} {r.lift_over_null:>7.3f} {r.z_vs_null:>7.1f}")  # Compares the observed adoption rate with the shuffled-time reference rate.

    f, l = cmp.iloc[0], cmp.iloc[-1]  # Runs this instruction as part of the current step.
    print(f"\nexcess {f.lift_over_null:.3f}x at d=1 -> {l.lift_over_null:.3f}x "  # Compares the observed adoption rate with the shuffled-time reference rate.
          f"at d={int(l.d)}  "  # Runs this instruction as part of the current step.
          f"({'RISES - would support complex contagion' if l.lift_over_null > f.lift_over_null else 'decays - same as the headline'})")  # Compares the observed adoption rate with the shuffled-time reference rate.

    out = config.TABLES / f"null_comparison_perspell_{a.how}.csv"  # Stores the output value for the next step.
    cmp.to_csv(out, index=False)  # Writes a result table that can be inspected or downloaded.
    print(f"wrote {out}")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
