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
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, curve, events, nulls  # noqa: E402


def report(name: str, cmp: pd.DataFrame, key: str):
    print(f"\n--- {name} ---")
    print(f"{key:>3} {'n':>9} {'real':>8} {'null':>8} {'lift':>7} {'z':>7}")
    for r in cmp.itertuples(index=False):
        print(f"{int(getattr(r, key)):>3} {int(r.n_real):>9,} {r.rate_real:>8.4f} "
              f"{r.rate_null:>8.4f} {r.lift_over_null:>7.3f} {r.z_vs_null:>7.1f}")
    first, last = cmp.iloc[0], cmp.iloc[-1]
    print(f"excess {first.lift_over_null:.3f}x at {key}=1 -> "
          f"{last.lift_over_null:.3f}x at {key}={int(getattr(last, key))}  "
          f"({'RISES' if last.lift_over_null > first.lift_over_null else 'decays'})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games",
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()

    df = pd.read_parquet(a.games)
    print(f"{len(df):,} games, {a.reps} null replicate(s), "
          f"window {config.ADOPTION_WINDOW_DAYS}d")

    trials = events.build_trials(df)
    tables = curve.analyse(trials)
    w = config.ADOPTION_WINDOW_DAYS

    out = {}
    for key in ("d", "sd"):
        null = nulls.run_null(df, n_reps=a.reps, kind="shuffle",
                              window_days=w, by=key)
        cmp = nulls.compare(tables["by_" + key], null, by=key)
        cmp.to_csv(config.TABLES / f"null_comparison_{key}.csv", index=False)
        out[key] = cmp
        report("d  (distinct exposers)" if key == "d"
               else "sd (structural diversity, Ugander et al.)", cmp, key)

    # Does holding k fixed and varying sd separate anything?
    hk = tables["held_k_by_sd"]
    hk = hk[hk["n"] >= 20]
    sep = False
    for k, sub in hk.groupby("k"):
        if len(sub) >= 2 and sub.iloc[-1]["lo"] > sub.iloc[0]["hi"]:
            sep = True
    print(f"\nfixed-k separation on sd: {sep}")

    d_last = out["d"].iloc[-1]["lift_over_null"]
    s_last = out["sd"].iloc[-1]["lift_over_null"]
    print(f"\nconclusion: sd tracks d "
          f"(excess at max: d {d_last:.3f}x, sd {s_last:.3f}x). "
          f"{'sd tells a different story - investigate' if abs(d_last - s_last) > 0.08 else 'Same verdict on both measures.'}")


if __name__ == "__main__":
    main()
