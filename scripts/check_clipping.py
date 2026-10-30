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
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402


def main():
    """Widen plotted exposure buckets and rerun the real/null comparison.

    This checks whether the 6+ group hides a different pattern in its tail.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=str(config.INTERIM / "slice_2016-01_full.parquet"))
    ap.add_argument("--cap", type=int, default=12)
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()

    # Raise the caps BEFORE importing the analysis modules read them at call
    # time, so both the real curve and the null use the wider buckets.
    config.MAX_DIVERSITY = a.cap
    config.MAX_EXPOSURE_COUNT = a.cap

    from src import curve, events, nulls  # noqa: E402  (after the cap change)

    df = pd.read_parquet(a.games)
    print(f"{len(df):,} games, cap d at {a.cap}, {a.reps} null replicate(s)\n")

    trials = events.build_trials(df)
    tables = curve.analyse(trials)
    null_by_d = nulls.run_null(df, n_reps=a.reps, kind="shuffle",
                               window_days=config.ADOPTION_WINDOW_DAYS)
    cmp = nulls.compare(tables["by_d"], null_by_d)

    print(f"{'d':>3} {'n':>9} {'real':>8} {'null':>8} {'lift':>7} {'z':>8}")
    for r in cmp.itertuples(index=False):
        print(f"{int(r.d):>3} {int(r.n_real):>9,} {r.rate_real:>8.4f} "
              f"{r.rate_null:>8.4f} {r.lift_over_null:>7.3f} {r.z_vs_null:>8.1f}")

    v = curve.verdict(tables, cmp)
    print("\nverdict:", v["verdict"])
    for k in ("lift_over_null_at_min_d", "lift_over_null_at_max_d",
              "separated_at_fixed_k", "excess_over_null_grows_with_d"):
        if k in v:
            print(f"  {k}: {v[k]}")

    out = config.TABLES / f"null_comparison_cap{a.cap}.csv"
    cmp.to_csv(out, index=False)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
