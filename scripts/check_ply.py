"""Robustness check at ply granularity (proposal, Section 4 / Build Guide).

The main analysis defines a behaviour by ECO code, which is coarse: many
distinct ideas share one code. Defining it by the first k plies is sharper but
fragments the data, so it is a robustness check rather than the main result.

If the verdict flips between the two granularities, the ECO-level finding is an
artefact of the coding scheme and must be reported as such.

    python scripts/check_ply.py --reps 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, curve, events, nulls  # noqa: E402


def analyse(df: pd.DataFrame, granularity: str, reps: int) -> dict:
    """Repeat the core comparison with one opening definition at a time."""
    trials = events.build_trials(df, granularity=granularity)
    if not len(trials):
        return {"granularity": granularity, "error": "no trials"}
    tables = curve.analyse(trials)
    # the null MUST use the same granularity as the real trials
    null = nulls.run_null(df, n_reps=reps, kind="shuffle",
                          window_days=config.ADOPTION_WINDOW_DAYS,
                          granularity=granularity)
    cmp = nulls.compare(tables["by_d"], null)
    v = curve.verdict(tables, cmp)
    return {
        "granularity": granularity,
        "behaviours": int(trials["opening"].nunique()),
        "trials": int(len(trials)),
        "adoptions": int(trials["adopted"].sum()),
        "rate": round(float(trials["adopted"].mean()), 4),
        "cmp": cmp,
        "verdict": v,
    }


def show(r: dict):
    print(f"\n=== {r['granularity']} ===")
    if "error" in r:
        print(" ", r["error"]); return
    print(f"  behaviours {r['behaviours']:,} · trials {r['trials']:,} · "
          f"adoptions {r['adoptions']:,} ({r['rate']*100:.2f}%)")
    c = r["cmp"]
    print(f"  {'d':>3} {'n':>9} {'real':>8} {'null':>8} {'lift':>7}")
    for row in c.itertuples(index=False):
        print(f"  {int(row.d):>3} {int(row.n_real):>9,} {row.rate_real:>8.4f} "
              f"{row.rate_null:>8.4f} {row.lift_over_null:>7.3f}")
    v = r["verdict"]
    print(f"  excess {v.get('lift_over_null_at_min_d')}x -> "
          f"{v.get('lift_over_null_at_max_d')}x")
    print(f"  VERDICT: {v['verdict']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games",
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--depth", type=int, default=config.PLY_KEY_DEPTH)
    a = ap.parse_args()

    config.PLY_KEY_DEPTH = a.depth
    df = pd.read_parquet(a.games)
    print(f"{len(df):,} games · ply depth {a.depth} · {a.reps} null replicate(s)")

    results = [analyse(df, g, a.reps) for g in ("eco", "ply")]
    for r in results:
        show(r)

    ok = [r for r in results if "error" not in r]
    if len(ok) == 2:
        same = ok[0]["verdict"]["verdict"] == ok[1]["verdict"]["verdict"]
        print(f"\nverdicts agree across granularity: {same}")
        if not same:
            print("  !! the ECO-level result does NOT survive at ply level — "
                  "report this prominently")
        for r in ok:
            r["cmp"].to_csv(
                config.TABLES / f"null_comparison_{r['granularity']}.csv",
                index=False)


if __name__ == "__main__":
    main()
