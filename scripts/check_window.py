"""Does the verdict depend on the 14-day adoption window?

The window is a researcher's choice, not a property of the data. The Build
Guide says to pick one and state it, which the project does — but an unstated
sensitivity is a free parameter an examiner can push on. This reruns the whole
comparison at several windows.

    python scripts/check_window.py --windows 7 14 28 --reps 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, curve, events, nulls  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games",
                    default=str(config.INTERIM / "slice_2016-01_full.parquet"))
    ap.add_argument("--windows", type=int, nargs="+", default=[7, 14, 28])
    ap.add_argument("--reps", type=int, default=2)
    a = ap.parse_args()

    df = pd.read_parquet(a.games)
    print(f"{len(df):,} games · windows {a.windows} · {a.reps} replicate(s)\n")

    rows = []
    for w in a.windows:
        trials = events.build_trials(df, window_days=w)
        if not len(trials):
            print(f"window {w}d: no trials"); continue
        tables = curve.analyse(trials)
        null = nulls.run_null(df, n_reps=a.reps, kind="shuffle", window_days=w)
        cmp = nulls.compare(tables["by_d"], null)
        v = curve.verdict(tables, cmp)
        f, l = cmp.iloc[0], cmp.iloc[-1]
        rows.append({
            "window_days": w,
            "trials": len(trials),
            "adoptions": int(trials.adopted.sum()),
            "rate": round(float(trials.adopted.mean()), 4),
            "excess_at_d1": round(float(f.lift_over_null), 3),
            "excess_at_dmax": round(float(l.lift_over_null), 3),
            "decays": bool(l.lift_over_null < f.lift_over_null),
            "verdict": v["verdict"].split(":")[0],
        })
        print(f"window {w:>3}d  trials {len(trials):>8,}  "
              f"adoptions {int(trials.adopted.sum()):>7,} "
              f"({trials.adopted.mean()*100:5.2f}%)  "
              f"excess {f.lift_over_null:.3f} -> {l.lift_over_null:.3f}  "
              f"{rows[-1]['verdict']}")

    out = pd.DataFrame(rows)
    p = config.TABLES / "window_sensitivity.csv"
    out.to_csv(p, index=False)
    print(f"\nall windows decay: {out['decays'].all()}")
    print(f"verdicts: {sorted(set(out['verdict']))}")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
