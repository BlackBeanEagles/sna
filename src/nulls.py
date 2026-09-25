"""Step 6 -- the timestamp-shuffled null model.

Permuting the timestamps across games destroys causal ordering while keeping
the degree sequence, the rating distribution and the opening popularity
distribution exactly as they are. Anything the curve still shows under that
permutation is an artefact of activity and popularity, not of influence.
The real effect has to clear it.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, curve, events, parse


def shuffle_timestamps(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    out = df.copy()
    out["ts"] = rng.permutation(out["ts"].to_numpy())
    return out.sort_values("ts").reset_index(drop=True)


def rewire_preserving_degree(df: pd.DataFrame, rng: np.random.Generator,
                             n_swaps_per_edge: int = 5) -> pd.DataFrame:
    """Degree-preserving double-edge swap on the game list, timestamps kept."""
    w = df["white"].to_numpy().copy()
    b = df["black"].to_numpy().copy()
    m = len(w)
    for _ in range(n_swaps_per_edge * m):
        i, j = rng.integers(0, m, 2)
        if i == j:
            continue
        if b[i] == w[j] or b[j] == w[i]:
            continue
        b[i], b[j] = b[j], b[i]
    out = df.copy()
    out["white"], out["black"] = w, b
    return out


def run_null(df: pd.DataFrame, n_reps: int = None, kind: str = "shuffle",
             seed: int = config.RANDOM_SEED,
             window_days: int = None, by: str = "d",
             granularity: str = None) -> pd.DataFrame:
    """Build the null trials with EXACTLY the same parameters as the real ones.

    Both window_days and granularity must match, or the comparison is not a
    comparison. Two ways this has already gone wrong:

    * a window wider than the observed span censors every non-adopter, so the
      null adoption rate goes to 1.0 and the lift collapses;
    * leaving granularity at the default while the real trials are keyed by
      ply compares a 0.6%-adoption ply world against a 17.7%-adoption ECO
      world, which manufactures a spurious "complex contagion" verdict.
    """
    n_reps = n_reps or config.N_NULL_REPLICATES
    rng = np.random.default_rng(seed)
    frames = []
    for rep in range(n_reps):
        null_df = (shuffle_timestamps(df, rng) if kind == "shuffle"
                   else rewire_preserving_degree(df, rng))
        trials = events.build_trials(null_df, window_days=window_days,
                                     granularity=granularity)
        if not len(trials):
            continue
        tb = curve.analyse(trials)["by_" + by]
        tb["rep"] = rep
        frames.append(tb)
    if not frames:
        return pd.DataFrame()
    allreps = pd.concat(frames, ignore_index=True)
    return (allreps.groupby(by)
            .agg(n=("n", "sum"), rate=("rate", "mean"), rate_sd=("rate", "std"))
            .reset_index())


def compare(real_by_d: pd.DataFrame, null_by_d: pd.DataFrame,
            by: str = "d") -> pd.DataFrame:
    m = real_by_d.merge(null_by_d, on=by, suffixes=("_real", "_null"))
    m["lift_over_null"] = m["rate_real"] / m["rate_null"].replace(0, np.nan)

    # Spread of the null rate across replicates. With a single replicate there
    # is no spread to measure (std of one value is NaN), which would silently
    # make every z NaN and collapse the verdict to "nothing detected". Fall
    # back to the binomial standard error of the null rate, which is a valid
    # estimate of the same quantity and lets one replicate still be informative.
    se = m["rate_sd"].replace(0, np.nan)
    binom = np.sqrt(m["rate_null"] * (1 - m["rate_null"]) / m["n_null"].clip(lower=1))
    m["null_se"] = se.fillna(binom)
    m["z_vs_null"] = (m["rate_real"] - m["rate_null"]) / m["null_se"].replace(0, np.nan)
    return m[[by, "n_real", "rate_real", "rate_null", "rate_sd",
              "lift_over_null", "z_vs_null"]]


def run(games_path: Path, trials_path: Path, n_reps: int = None,
        kind: str = "shuffle"):
    df = parse.load_games(games_path)
    real = curve.analyse(pd.read_parquet(trials_path))["by_d"]
    null = run_null(df, n_reps=n_reps, kind=kind)
    cmp = compare(real, null) if len(null) else pd.DataFrame()
    if len(cmp):
        suffix = "" if kind == "shuffle" else f"_{kind}"
        cmp.to_csv(config.TABLES / f"null_comparison{suffix}.csv", index=False)
    return cmp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))
    ap.add_argument("--trials", default=str(config.PROCESSED / "trials.parquet"))
    ap.add_argument("--reps", type=int, default=config.N_NULL_REPLICATES)
    ap.add_argument("--kind", default="shuffle", choices=["shuffle", "rewire"],
                    help="shuffle timestamps, or degree-preserving edge rewiring")
    a = ap.parse_args()
    c = run(Path(a.games), Path(a.trials), a.reps, a.kind)
    print(c.to_string(index=False) if len(c) else "null produced no trials")
