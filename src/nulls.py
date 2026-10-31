"""Step 6 -- the timestamp-shuffled null model.

Permuting the timestamps across games destroys causal ordering while keeping
the degree sequence, the rating distribution and the opening popularity
distribution exactly as they are. Anything the curve still shows under that
permutation is an artefact of activity and popularity, not of influence.
The real effect has to clear it.
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
from pathlib import Path  # Loads Path to find and save project files.

import numpy as np  # Loads the number library used for fast calculations.
import pandas as pd  # Loads the table library used to store games and trials.

from . import config, curve, events, parse  # Loads the named parts of this project so this file can use their functions.


def shuffle_timestamps(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:  # Keep each game's players/opening, but remove the original time order.
    """Keep each game's players/opening, but remove the original time order.

    Say: if the observed rise also appears after this shuffle, activity and
    opening popularity may explain it without opponent-to-opponent spread.
    """
    out = df.copy()  # Stores the output value for the next step.
    out["ts"] = rng.permutation(out["ts"].to_numpy())  # Mixes up game dates but keeps the players and opening in each game.
    return out.sort_values("ts").reset_index(drop=True)  # Orders the rows by this field before the next calculation.


def rewire_preserving_degree(df: pd.DataFrame, rng: np.random.Generator,  # Degree-preserving double-edge swap on the game list, timestamps kept.
                             n_swaps_per_edge: int = 5) -> pd.DataFrame:  # Saves a value named n_swaps_per_edge so the next lines can use it.
    """Degree-preserving double-edge swap on the game list, timestamps kept."""
    w = df["white"].to_numpy().copy()  # Saves a value named w so the next lines can use it.
    b = df["black"].to_numpy().copy()  # Saves a value named b so the next lines can use it.
    m = len(w)  # Saves a value named m so the next lines can use it.
    for _ in range(n_swaps_per_edge * m):  # Repeats the next indented steps once for each item.
        i, j = rng.integers(0, m, 2)  # Runs this instruction as part of the current step.
        if i == j:  # Runs the next indented steps only when this condition is true.
            continue  # Skips this item and moves to the next loop iteration.
        if b[i] == w[j] or b[j] == w[i]:  # Runs the next indented steps only when this condition is true.
            continue  # Skips this item and moves to the next loop iteration.
        b[i], b[j] = b[j], b[i]  # Stores this value under its player, opening, or field key.
    out = df.copy()  # Stores the output value for the next step.
    out["white"], out["black"] = w, b  # Stores this value under its player, opening, or field key.
    return out  # Gives this answer back to the code that called the function.


def run_null(df: pd.DataFrame, n_reps: int = None, kind: str = "shuffle",  # Build the null trials with EXACTLY the same parameters as the real ones.
             seed: int = config.RANDOM_SEED,  # Saves a value named seed so the next lines can use it.
             window_days: int = None, by: str = "d",  # Saves a value named window_days so the next lines can use it.
             granularity: str = None, should_stop=None,  # Saves a value named granularity so the next lines can use it.
             on_progress=None) -> pd.DataFrame:  # Saves a value named on_progress so the next lines can use it.
    """Build the null trials with EXACTLY the same parameters as the real ones.

    Both window_days and granularity must match, or the comparison is not a
    comparison. Two ways this has already gone wrong:

    * a window wider than the observed span censors every non-adopter, so the
      null adoption rate goes to 1.0 and the lift collapses;
    * leaving granularity at the default while the real trials are keyed by
      ply compares a 0.6%-adoption ply world against a ECO-adoption
      world, which manufactures a spurious "complex contagion" verdict.
    """
    # Simple explanation: repeat the analysis after mixing up game dates.
    # If the same rise appears, the rise alone is weak evidence of spreading.
    n_reps = n_reps or config.N_NULL_REPLICATES  # Saves a value named n_reps so the next lines can use it.
    rng = np.random.default_rng(seed)  # Saves a value named rng so the next lines can use it.
    frames = []  # Saves a value named frames so the next lines can use it.
    for rep in range(n_reps):  # Repeats the next indented steps once for each item.
        if should_stop is not None and should_stop():  # Runs the next indented steps only when this condition is true.
            break  # Ends the current loop.
        null_df = (shuffle_timestamps(df, rng) if kind == "shuffle"  # Creates one shuffled-date version of the same games.
                   else rewire_preserving_degree(df, rng))  # Runs this instruction as part of the current step.
        trials = events.build_trials(null_df, window_days=window_days,  # Stores the exposure-trial table for the next step.
                                     granularity=granularity)  # Saves a value named granularity so the next lines can use it.
        if not len(trials):  # Checks whether enough records exist for a trustworthy next step.
            continue  # Skips this item and moves to the next loop iteration.
        tb = curve.analyse(trials)["by_" + by]  # Recalculates the adoption curve from these shuffled-date trials.
        tb["rep"] = rep  # Stores this value under its player, opening, or field key.
        frames.append(tb)  # Adds this item to the list being built.
        if on_progress is not None:  # Runs the next indented steps only when this condition is true.
            on_progress(rep + 1, n_reps)  # Runs this instruction as part of the current step.
    if not frames:  # Runs the next indented steps only when this condition is true.
        return pd.DataFrame()  # Creates a labelled table from the collected rows.
    allreps = pd.concat(frames, ignore_index=True)  # Saves a value named allreps so the next lines can use it.
    return (allreps.groupby(by)  # Groups rows sharing these keys before counting or averaging them.
            .agg(n=("n", "sum"), rate=("rate", "mean"), rate_sd=("rate", "std"))  # Runs this instruction as part of the current step.
            .reset_index())  # Runs this instruction as part of the current step.


def compare(real_by_d: pd.DataFrame, null_by_d: pd.DataFrame,  # Put observed and shuffled rates side by side for each d value.
            by: str = "d") -> pd.DataFrame:  # Saves a value named by so the next lines can use it.
    """Put observed and shuffled rates side by side for each d value.

    `lift_over_null` is observed rate / shuffled rate. Above 1 means excess
    over that reference, not a causal effect estimate.
    """
    # Each row now shows two rates for the same number of different opponents:
    # what really happened and what happened after dates were shuffled.
    m = real_by_d.merge(null_by_d, on=by, suffixes=("_real", "_null"))  # Joins two tables on shared identifiers so their columns can be compared.
    m["lift_over_null"] = m["rate_real"] / m["rate_null"].replace(0, np.nan)  # Compares the observed adoption rate with the shuffled-time reference rate.

    # Spread of the null rate across replicates. With a single replicate there
    # is no spread to measure (std of one value is NaN), which would silently
    # make every z NaN and collapse the verdict to "nothing detected". Fall
    # back to the binomial standard error of the null rate, which is a valid
    # estimate of the same quantity and lets one replicate still be informative.
    se = m["rate_sd"].replace(0, np.nan)  # Saves a value named se so the next lines can use it.
    binom = np.sqrt(m["rate_null"] * (1 - m["rate_null"]) / m["n_null"].clip(lower=1))  # Caps large counts into the final chart bucket, such as six or more opponents.
    m["null_se"] = se.fillna(binom)  # Stores this value under its player, opening, or field key.
    m["z_vs_null"] = (m["rate_real"] - m["rate_null"]) / m["null_se"].replace(0, np.nan)  # Stores this value under its player, opening, or field key.
    return m[[by, "n_real", "rate_real", "rate_null", "rate_sd",  # Gives this answer back to the code that called the function.
              "lift_over_null", "z_vs_null"]]


def run(games_path: Path, trials_path: Path, n_reps: int = None,  # Defines a reusable step; the following indented lines are its body.
        kind: str = "shuffle"):  # Saves a value named kind so the next lines can use it.
    df = parse.load_games(games_path)  # Stores the game table for the next step.
    real = curve.analyse(pd.read_parquet(trials_path))["by_d"]  # Loads a previously prepared game or trial table.
    null = run_null(df, n_reps=n_reps, kind=kind)  # Stores the shuffled reference for the next step.
    cmp = compare(real, null) if len(null) else pd.DataFrame()  # Creates a labelled table from the collected rows.
    if len(cmp):  # Runs the next indented steps only when this condition is true.
        suffix = "" if kind == "shuffle" else f"_{kind}"  # Saves a value named suffix so the next lines can use it.
        cmp.to_csv(config.TABLES / f"null_comparison{suffix}.csv", index=False)  # Writes a result table that can be inspected or downloaded.
    return cmp  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--trials", default=str(config.PROCESSED / "trials.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--reps", type=int, default=config.N_NULL_REPLICATES)  # Defines a command-line option for this script.
    ap.add_argument("--kind", default="shuffle", choices=["shuffle", "rewire"],  # Defines a command-line option for this script.
                    help="shuffle timestamps, or degree-preserving edge rewiring")  # Saves a value named help so the next lines can use it.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    c = run(Path(a.games), Path(a.trials), a.reps, a.kind)  # Saves a value named c so the next lines can use it.
    print(c.to_string(index=False) if len(c) else "null produced no trials")  # Prints this reading so a command-line run can be followed.
