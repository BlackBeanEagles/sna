"""Are the trials independent? They are not — how much does it matter?

The trial table has one row per (player, behaviour, k-th exposure). That means
a single player-behaviour spell contributes several rows, and — because
`adopted` is scored for every exposure whose window contains the adoption —
one real adoption event can be counted many times over.

On the full 2016-01 month:

    223,967 trial rows   from    78,274 spells   and   6,730 players
     39,661 'adoptions'  from    14,320 distinct adoption events

so each adoption is counted 2.77x on average (max 144x), and 47% of events are
counted more than once. Wilson intervals and z-scores both assume independent
Bernoulli trials, so both are too narrow — which matters, because the verdict
turns on interval separation and on z > 3.

This script recomputes the headline comparison with ONE row per spell, so each
player-behaviour contributes exactly one observation and each adoption is
counted exactly once. If the excess-over-null decay survives that, the finding
is not an artefact of pseudo-replication.

    python scripts/check_independence.py --reps 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, curve, events, nulls  # noqa: E402

SPELL = ["player", "opening", "colour"]


def collapse(trials: pd.DataFrame, how: str = "last") -> pd.DataFrame:
    """One row per spell. 'last' keeps the final exposure state before the
    window closes (largest k and d); 'first' keeps the first exposure."""
    if not len(trials):
        return trials
    t = trials.sort_values(["player", "opening", "colour", "k"])
    idx = t.groupby(SPELL)["k"].idxmax() if how == "last" else t.groupby(SPELL)["k"].idxmin()
    out = t.loc[idx].copy()
    # adopted at spell level: did this spell ever record an adoption?
    ever = trials.groupby(SPELL)["adopted"].max().rename("ever")
    out = out.merge(ever, on=SPELL, how="left")
    out["adopted"] = out["ever"].astype(int)
    return out.drop(columns="ever")


def curve_from(trials: pd.DataFrame) -> pd.DataFrame:
    t = trials.copy()
    t["d"] = t["d"].clip(upper=config.MAX_DIVERSITY)
    return curve.rate_table(t, "d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games",
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--how", default="last", choices=["last", "first"])
    a = ap.parse_args()

    df = pd.read_parquet(a.games)
    w = config.ADOPTION_WINDOW_DAYS
    real = events.build_trials(df, window_days=w)
    real_sp = collapse(real, a.how)

    print(f"{len(df):,} games")
    print(f"per-exposure rows {len(real):,}  ->  per-spell rows {len(real_sp):,}"
          f"  ({len(real_sp)/len(real):.1%})")
    print(f"adoptions {int(real.adopted.sum()):,} -> "
          f"{int(real_sp.adopted.sum()):,} distinct events\n")

    # null, collapsed exactly the same way
    rng = np.random.default_rng(config.RANDOM_SEED)
    frames = []
    for rep in range(a.reps):
        nd = nulls.shuffle_timestamps(df, rng)
        nt = events.build_trials(nd, window_days=w)
        if not len(nt):
            continue
        tb = curve_from(collapse(nt, a.how))
        tb["rep"] = rep
        frames.append(tb)
    null = (pd.concat(frames, ignore_index=True)
            .groupby("d").agg(n=("n", "sum"), rate=("rate", "mean"),
                              rate_sd=("rate", "std")).reset_index())

    cmp = nulls.compare(curve_from(real_sp), null)
    print(f"{'d':>3} {'n':>8} {'real':>8} {'null':>8} {'lift':>7} {'z':>7}")
    for r in cmp.itertuples(index=False):
        print(f"{int(r.d):>3} {int(r.n_real):>8,} {r.rate_real:>8.4f} "
              f"{r.rate_null:>8.4f} {r.lift_over_null:>7.3f} {r.z_vs_null:>7.1f}")

    f, l = cmp.iloc[0], cmp.iloc[-1]
    print(f"\nexcess {f.lift_over_null:.3f}x at d=1 -> {l.lift_over_null:.3f}x "
          f"at d={int(l.d)}  "
          f"({'RISES - would support complex contagion' if l.lift_over_null > f.lift_over_null else 'decays - same as the headline'})")

    out = config.TABLES / f"null_comparison_perspell_{a.how}.csv"
    cmp.to_csv(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
