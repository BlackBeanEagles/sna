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
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import json  # Loads JSON tools for saved results and browser messages.
import sys  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

from src import config, curve, events, matching, nulls, parse  # noqa: E402


def close(a, b, tol):  # Defines a reusable step; the following indented lines are its body.
    if a is None or b is None:  # Runs the next indented steps only when this condition is true.
        return False  # Gives this answer back to the code that called the function.
    return abs(float(a) - float(b)) <= tol  # Gives this answer back to the code that called the function.


def main():  # Recompute selected saved metrics before claiming reproducibility.
    """Recompute selected saved metrics before claiming reproducibility.

    This reads the cached filtered games, so archive parsing itself remains
    outside this check.
    """
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--report", default=str(config.RESULTS / "report.json"))  # Defines a command-line option for this script.
    ap.add_argument("--reps", type=int, default=None)  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.

    published = json.loads(Path(a.report).read_text())  # Decodes saved JSON text into Python data.
    a.reps = a.reps or published.get("null_replicates", 3)  # Saves a value named reps so the next lines can use it.
    df = parse.load_games(a.games)  # Stores the game table for the next step.
    print(f"cached slice: {len(df):,} games, "  # Prints this reading so a command-line run can be followed.
          f"{len(set(df.white) | set(df.black)):,} players\n")  # Runs this instruction as part of the current step.

    checks: list[tuple[str, object, object, float]] = []  # Saves a value named checks so the next lines can use it.

    # Prediction and network summaries are intentionally outside this check.
    # Refit prediction separately and reparse the archive to audit its source.

    # ---- sample -------------------------------------------------------
    checks.append(("games parsed", len(df), published["parse"]["games"], 0))  # Adds this item to the list being built.

    # ---- trials -------------------------------------------------------
    trials = events.build_trials(df)  # Stores the exposure-trial table for the next step.
    checks.append(("trials", len(trials), published["trials"]["n"], 0))  # Adds this item to the list being built.
    checks.append(("adoptions", int(trials.adopted.sum()),  # Part of the value, collection, or call spanning several lines.
                   published["trials"]["adoptions"], 0))  # Runs this instruction as part of the current step.

    # ---- curve --------------------------------------------------------
    tables = curve.analyse(trials)  # Calculates adoption rates for different exposure counts.
    by_d = tables["by_d"]  # Saves a value named by_d so the next lines can use it.
    pub_curve = {int(r["d"]): r for r in published["curve_by_d"]}  # Saves a value named pub_curve so the next lines can use it.
    for _, row in by_d.iterrows():  # Repeats the next indented steps once for each item.
        d = int(row["d"])  # Stores the distinct-opponent count for the next step.
        if d in pub_curve:  # Runs the next indented steps only when this condition is true.
            checks.append((f"adoption rate at d={d}", round(float(row["rate"]), 4),  # Part of the value, collection, or call spanning several lines.
                           pub_curve[d]["rate"], 0.0005))  # Runs this instruction as part of the current step.

    # ---- null ---------------------------------------------------------
    null = nulls.run_null(df, n_reps=a.reps, kind="shuffle",  # Stores the shuffled reference for the next step.
                          window_days=config.ADOPTION_WINDOW_DAYS)  # Saves a value named window_days so the next lines can use it.
    cmp = nulls.compare(by_d, null)  # Stores the observed-versus-reference comparison for the next step.
    pub_null = {int(r["d"]): r for r in published.get("null_comparison", [])}  # Saves a value named pub_null so the next lines can use it.
    for _, row in cmp.iterrows():  # Repeats the next indented steps once for each item.
        d = int(row["d"])  # Stores the distinct-opponent count for the next step.
        if d in pub_null and row["lift_over_null"] == row["lift_over_null"]:  # Compares the observed adoption rate with the shuffled-time reference rate.
            checks.append((f"lift over null at d={d}",  # Part of the value, collection, or call spanning several lines.
                           round(float(row["lift_over_null"]), 3),  # Compares the observed adoption rate with the shuffled-time reference rate.
                           pub_null[d]["lift_over_null"], 0.02))  # Compares the observed adoption rate with the shuffled-time reference rate.

    # ---- matched controls ---------------------------------------------
    msum = matching.summarise(matching.build_matched(df))  # Stores the summary of the matched comparison for the next step.
    pub_m = published["matched_controls"]  # Saves a value named pub_m so the next lines can use it.
    for key, tol in (("n_pairs", 400), ("difference", 0.002),  # Repeats the next indented steps once for each item.
                     ("risk_ratio", 0.02)):  # Part of the value, collection, or call spanning several lines.
        checks.append((f"matched {key}", msum.get(key), pub_m.get(key), tol))  # Adds this item to the list being built.

    # ---- verdict -------------------------------------------------------
    v = curve.verdict(tables, cmp)  # Applies the result rules to the real and shuffled curves.
    same_verdict = (  # Check whether the rebuilt result gives the same type of verdict.
        v["verdict"].split(":")[0] ==  # Take the short verdict from this run.
        published["verdict"]["verdict"].split(":")[0]  # Compare it with the saved report.
    )  # Keep this comparison together as one value.

    # ---- report --------------------------------------------------------
    width = max(len(n) for n, _, _, _ in checks)  # Saves a value named width so the next lines can use it.
    failed = 0  # Saves a value named failed so the next lines can use it.
    for name, got, want, tol in checks:  # Repeats the next indented steps once for each item.
        ok = close(got, want, tol) if tol else got == want  # Saves a value named ok so the next lines can use it.
        failed += not ok  # Adds this amount to the running total.
        print(f"  {'OK  ' if ok else 'FAIL'}  {name:<{width}}  "  # Prints this reading so a command-line run can be followed.
              f"now {got!s:>10}   published {want!s:>10}")  # Runs this instruction as part of the current step.
    print(f"\n  {'OK  ' if same_verdict else 'FAIL'}  verdict: {v['verdict'][:60]}")  # Prints this reading so a command-line run can be followed.

    print(f"\n{len(checks) + 1 - failed - (not same_verdict)}/{len(checks) + 1} "  # Prints this reading so a command-line run can be followed.
          f"checks pass")  # Runs this instruction as part of the current step.
    if failed or not same_verdict:  # Runs the next indented steps only when this condition is true.
        sys.exit("published core results are NOT reproducible by the current code")  # Runs this instruction as part of the current step.
    print("all checked core numbers are reproducible by the current code")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
