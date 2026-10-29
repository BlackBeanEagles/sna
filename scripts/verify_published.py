"""Re-derive the published core metrics and check results/report.json.

The committed results were produced at one point in time; the code has changed
since. This re-runs the analysis stages on the cached slice with whatever the
code says *today* and compares, so "the published numbers are reproducible" is
a thing that gets checked rather than assumed.

It deliberately does not re-parse the archive -- that needs the network -- so
it verifies the analysis, not the parser. Anything the parser changed is out of
its reach and has to be re-run from the raw month.

    python scripts/verify_published.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config, curve, events, matching, nulls, parse  # noqa: E402


def close(a, b, tol):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))
    ap.add_argument("--report", default=str(config.RESULTS / "report.json"))
    ap.add_argument("--reps", type=int, default=None)
    a = ap.parse_args()

    published = json.loads(Path(a.report).read_text())
    a.reps = a.reps or published.get("null_replicates", 3)
    df = parse.load_games(a.games)
    print(f"cached slice: {len(df):,} games, "
          f"{len(set(df.white) | set(df.black)):,} players\n")

    checks: list[tuple[str, object, object, float]] = []

    # Prediction and network summaries are intentionally outside this check.
    # Refit prediction separately and reparse the archive to audit its source.

    # ---- sample -------------------------------------------------------
    checks.append(("games parsed", len(df), published["parse"]["games"], 0))

    # ---- trials -------------------------------------------------------
    trials = events.build_trials(df)
    checks.append(("trials", len(trials), published["trials"]["n"], 0))
    checks.append(("adoptions", int(trials.adopted.sum()),
                   published["trials"]["adoptions"], 0))

    # ---- curve --------------------------------------------------------
    tables = curve.analyse(trials)
    by_d = tables["by_d"]
    pub_curve = {int(r["d"]): r for r in published["curve_by_d"]}
    for _, row in by_d.iterrows():
        d = int(row["d"])
        if d in pub_curve:
            checks.append((f"adoption rate at d={d}", round(float(row["rate"]), 4),
                           pub_curve[d]["rate"], 0.0005))

    # ---- null ---------------------------------------------------------
    null = nulls.run_null(df, n_reps=a.reps, kind="shuffle",
                          window_days=config.ADOPTION_WINDOW_DAYS)
    cmp = nulls.compare(by_d, null)
    pub_null = {int(r["d"]): r for r in published.get("null_comparison", [])}
    for _, row in cmp.iterrows():
        d = int(row["d"])
        if d in pub_null and row["lift_over_null"] == row["lift_over_null"]:
            checks.append((f"lift over null at d={d}",
                           round(float(row["lift_over_null"]), 3),
                           pub_null[d]["lift_over_null"], 0.02))

    # ---- matched controls ---------------------------------------------
    msum = matching.summarise(matching.build_matched(df))
    pub_m = published["matched_controls"]
    for key, tol in (("n_pairs", 400), ("difference", 0.002),
                     ("risk_ratio", 0.02)):
        checks.append((f"matched {key}", msum.get(key), pub_m.get(key), tol))

    # ---- verdict -------------------------------------------------------
    v = curve.verdict(tables, cmp)
    same_verdict = v["verdict"].split(":")[0] == \
        published["verdict"]["verdict"].split(":")[0]

    # ---- report --------------------------------------------------------
    width = max(len(n) for n, _, _, _ in checks)
    failed = 0
    for name, got, want, tol in checks:
        ok = close(got, want, tol) if tol else got == want
        failed += not ok
        print(f"  {'OK  ' if ok else 'FAIL'}  {name:<{width}}  "
              f"now {got!s:>10}   published {want!s:>10}")
    print(f"\n  {'OK  ' if same_verdict else 'FAIL'}  verdict: {v['verdict'][:60]}")

    print(f"\n{len(checks) + 1 - failed - (not same_verdict)}/{len(checks) + 1} "
          f"checks pass")
    if failed or not same_verdict:
        sys.exit("published core results are NOT reproducible by the current code")
    print("all checked core numbers are reproducible by the current code")


if __name__ == "__main__":
    main()
