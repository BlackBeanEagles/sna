"""Step 5 -- the adoption-probability curve. This is the whole project.

Simple contagion  -> the curve saturates after the first exposure.
Complex contagion -> adoption keeps rising with the number of distinct
                     exposers d (or with structural diversity sd) even when
                     the total exposure count k is held FIXED.
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import math  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

from . import config  # Loads the named parts of this project so this file can use their functions.


def wilson(successes: int, n: int, z: float = 1.96):  # Wilson score interval -- behaves at the small cell counts in the tail.
    """Wilson score interval -- behaves at the small cell counts in the tail."""
    if n == 0:  # Runs the next indented steps only when this condition is true.
        return (float("nan"),) * 3  # Gives this answer back to the code that called the function.
    p = successes / n  # Saves a value named p so the next lines can use it.
    den = 1 + z * z / n  # Saves a value named den so the next lines can use it.
    centre = (p + z * z / (2 * n)) / den  # Saves a value named centre so the next lines can use it.
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den  # Saves a value named half so the next lines can use it.
    return p, max(0.0, centre - half), min(1.0, centre + half)  # Gives this answer back to the code that called the function.


def rate_table(trials: pd.DataFrame, by: str) -> pd.DataFrame:  # Group trials by exposure count/diversity and estimate adoption rates.
    """Group trials by exposure count/diversity and estimate adoption rates.

    The error bounds are Wilson intervals, which remain sensible for the
    smaller groups at the right-hand end of the chart.
    """
    g = trials.groupby(by)["adopted"].agg(["sum", "count"])  # Groups rows sharing these keys before counting or averaging them.
    out = []  # Stores the output value for the next step.
    for val, row in g.iterrows():  # Repeats the next indented steps once for each item.
        p, lo, hi = wilson(int(row["sum"]), int(row["count"]))  # Runs this instruction as part of the current step.
        out.append((val, int(row["count"]), int(row["sum"]), p, lo, hi))  # Adds this item to the list being built.
    return pd.DataFrame(out, columns=[by, "n", "adopted", "rate", "lo", "hi"])  # Creates a labelled table from the collected rows.


def held_k_table(trials: pd.DataFrame, k_values=(2, 3, 4), by: str = "d"  # The decisive comparison: k fixed, d varying.
                 ) -> pd.DataFrame:  # Runs this instruction as part of the current step.
    """The decisive comparison: k fixed, d varying."""
    out = []  # Stores the output value for the next step.
    for k in k_values:  # Repeats the next indented steps once for each item.
        sub = trials[trials["k"] == k]  # Saves a value named sub so the next lines can use it.
        if not len(sub):  # Checks whether enough records exist for a trustworthy next step.
            continue  # Skips this item and moves to the next loop iteration.
        t = rate_table(sub, by)  # Saves a temporary value used by the next calculation.
        t.insert(0, "k", k)  # Runs this instruction as part of the current step.
        out.append(t)  # Adds this item to the list being built.
    return (pd.concat(out, ignore_index=True) if out  # Gives this answer back to the code that called the function.
            else pd.DataFrame(columns=["k", by, "n", "adopted", "rate", "lo", "hi"]))  # Creates a labelled table from the collected rows.


def _clip(trials: pd.DataFrame) -> pd.DataFrame:  # Defines a reusable step; the following indented lines are its body.
    t = trials.copy()  # Saves a temporary value used by the next calculation.
    t["k"] = t["k"].clip(upper=config.MAX_EXPOSURE_COUNT)  # Caps large counts into the final chart bucket, such as six or more opponents.
    t["d"] = t["d"].clip(upper=config.MAX_DIVERSITY)  # Caps large counts into the final chart bucket, such as six or more opponents.
    t["sd"] = t["sd"].clip(upper=config.MAX_DIVERSITY)  # Caps large counts into the final chart bucket, such as six or more opponents.
    return t  # Gives this answer back to the code that called the function.


def analyse(trials: pd.DataFrame) -> dict[str, pd.DataFrame]:  # Build the raw curves and fixed-k checks used by charts and verdicts.
    """Build the raw curves and fixed-k checks used by charts and verdicts."""
    t = _clip(trials)  # Saves a temporary value used by the next calculation.
    return {  # Gives this answer back to the code that called the function.
        "by_k": rate_table(t, "k"),
        "by_d": rate_table(t, "d"),
        "by_sd": rate_table(t, "sd"),
        "held_k_by_d": held_k_table(t, by="d"),
        "held_k_by_sd": held_k_table(t, by="sd"),
    }  # Closes the data structure or function call started above.


def _yerr(tb: pd.DataFrame):  # Wilson's centre is shifted from the point estimate, so rate-lo and hi-rate can go slightly negative at extreme p.
    """Wilson's centre is shifted from the point estimate, so rate-lo and
    hi-rate can go slightly negative at extreme p. Matplotlib rejects that."""
    return [(tb["rate"] - tb["lo"]).clip(lower=0).to_numpy(),  # Caps large counts into the final chart bucket, such as six or more opponents.
            (tb["hi"] - tb["rate"]).clip(lower=0).to_numpy()]  # Caps large counts into the final chart bucket, such as six or more opponents.


def plot(tables: dict[str, pd.DataFrame], out: Path,  # Defines a reusable step; the following indented lines are its body.
         null_cmp: pd.DataFrame = None):  # Saves a value named null_cmp so the next lines can use it.
    # The live console only needs numeric tables, not a PNG. Import plotting
    # when a CLI/report run actually asks for a figure.
    import matplotlib  # Loads code this file needs for the steps below.
    matplotlib.use("Agg")  # Runs this instruction as part of the current step.
    import matplotlib.pyplot as plt  # Loads code this file needs for the steps below.
    n_panels = 3 if (null_cmp is not None and len(null_cmp)) else 2  # Saves a value named n_panels so the next lines can use it.
    fig, axes = plt.subplots(1, n_panels, figsize=(6 * n_panels, 4.6))  # Runs this instruction as part of the current step.

    ax = axes[0]  # Saves a value named ax so the next lines can use it.
    for name, lbl, mk in (("by_k", "k  (total exposures)", "o"),  # Repeats the next indented steps once for each item.
                          ("by_d", "d  (distinct exposers)", "s"),  # Part of the value, collection, or call spanning several lines.
                          ("by_sd", "sd (structural diversity)", "^")):  # Part of the value, collection, or call spanning several lines.
        tb = tables[name]  # Saves a value named tb so the next lines can use it.
        tb = tb[tb["n"] >= 5]  # Saves a value named tb so the next lines can use it.
        if not len(tb):  # Checks whether enough records exist for a trustworthy next step.
            continue  # Skips this item and moves to the next loop iteration.
        x = tb.iloc[:, 0]  # Saves a value named x so the next lines can use it.
        ax.errorbar(x, tb["rate"], yerr=_yerr(tb),  # Part of the value, collection, or call spanning several lines.
                    marker=mk, capsize=3, label=lbl)  # Saves a value named marker so the next lines can use it.
    # The null belongs ON this panel. Without it the rising curve reads as
    # complex contagion, which is exactly the misreading it refutes.
    if null_cmp is not None and len(null_cmp):  # Runs the next indented steps only when this condition is true.
        ax.plot(null_cmp["d"], null_cmp["rate_null"], "k--", marker="x",  # Part of the value, collection, or call spanning several lines.
                linewidth=1.3, label="shuffled-time null (by d)")  # Saves a value named linewidth so the next lines can use it.
    ax.set_xlabel("exposure measure")  # Runs this instruction as part of the current step.
    ax.set_ylabel(f"P(adopt within {config.ADOPTION_WINDOW_DAYS}d)")  # Runs this instruction as part of the current step.
    ax.set_title("Adoption probability curve")  # Runs this instruction as part of the current step.
    ax.legend(fontsize=8)  # Runs this instruction as part of the current step.
    ax.grid(alpha=.3)  # Runs this instruction as part of the current step.

    ax = axes[1]  # Saves a value named ax so the next lines can use it.
    hk = tables["held_k_by_d"]  # Saves a value named hk so the next lines can use it.
    for k, sub in hk.groupby("k"):  # Groups rows sharing these keys before counting or averaging them.
        sub = sub[sub["n"] >= 5]  # Saves a value named sub so the next lines can use it.
        if len(sub) < 2:  # Checks whether enough records exist for a trustworthy next step.
            continue  # Skips this item and moves to the next loop iteration.
        ax.errorbar(sub["d"], sub["rate"], yerr=_yerr(sub),  # Part of the value, collection, or call spanning several lines.
                    marker="o", capsize=3, label=f"k = {k}")  # Saves a value named marker so the next lines can use it.
    ax.set_xlabel("d  (distinct exposers), total exposures k held fixed")  # Runs this instruction as part of the current step.
    ax.set_ylabel("P(adopt)")  # Runs this instruction as part of the current step.
    ax.set_title("Decisive comparison: k fixed, d varying")  # Runs this instruction as part of the current step.
    ax.legend(fontsize=8)  # Runs this instruction as part of the current step.
    ax.grid(alpha=.3)  # Runs this instruction as part of the current step.

    if n_panels == 3:  # Runs the next indented steps only when this condition is true.
        ax = axes[2]  # Saves a value named ax so the next lines can use it.
        ax.axhline(1.0, color="k", linewidth=1, linestyle=":")  # Runs this instruction as part of the current step.
        ax.plot(null_cmp["d"], null_cmp["lift_over_null"], marker="D",  # Compares the observed adoption rate with the shuffled-time reference rate.
                color="#c2185b")  # Saves a value named color so the next lines can use it.
        ax.set_xlabel("d  (distinct exposers)")  # Runs this instruction as part of the current step.
        ax.set_ylabel("real rate / null rate")  # Runs this instruction as part of the current step.
        ax.set_title("Excess over the null"  # Runs this instruction as part of the current step.
                     + chr(10) + "(complex contagion needs this to RISE)")  # Runs this instruction as part of the current step.
        ax.grid(alpha=.3)  # Runs this instruction as part of the current step.

    fig.tight_layout()  # Runs this instruction as part of the current step.
    fig.savefig(out, dpi=150)  # Runs this instruction as part of the current step.
    plt.close(fig)  # Runs this instruction as part of the current step.
    return out  # Gives this answer back to the code that called the function.


def verdict(tables: dict[str, pd.DataFrame], null_cmp: pd.DataFrame = None,  # Simple vs complex, read off the curve AND the null.
            min_n: int = 20) -> dict:  # Saves a value named min_n so the next lines can use it.
    """Simple vs complex, read off the curve AND the null.

    A rising raw d-curve is NOT sufficient. High-d players are high-activity
    players, and activity alone produces a rising curve -- the timestamp-
    shuffled null reproduces it. Complex contagion requires the EXCESS over
    the null to grow with d, and requires the rise to survive with the total
    exposure count k held fixed.
    """
    d = tables["by_d"]  # Stores the distinct-opponent count for the next step.
    d = d[d["n"] >= min_n]  # Stores the distinct-opponent count for the next step.
    if len(d) < 2:  # Checks whether enough records exist for a trustworthy next step.
        return {"verdict": "insufficient data"}  # Gives this answer back to the code that called the function.
    first, last = d.iloc[0], d.iloc[-1]  # Runs this instruction as part of the current step.
    out = {  # Stores the output value for the next step.
        "raw_lift_d_last_over_first": round(float(last["rate"] / first["rate"]), 3)
        if first["rate"] else None,  # Runs the next indented steps only when this condition is true.
        "rate_d_min": round(float(first["rate"]), 4),
        "rate_d_max": round(float(last["rate"]), 4),
        "raw_curve_rises": bool(last["lo"] > first["hi"]),
    }  # Closes the data structure or function call started above.

    # (a) does the rise survive with k held fixed?
    hk = tables["held_k_by_d"]  # Saves a value named hk so the next lines can use it.
    hk = hk[hk["n"] >= min_n]  # Saves a value named hk so the next lines can use it.
    held = False  # Saves a value named held so the next lines can use it.
    for _, sub in hk.groupby("k"):  # Groups rows sharing these keys before counting or averaging them.
        if len(sub) >= 2 and sub.iloc[-1]["lo"] > sub.iloc[0]["hi"]:  # Runs the next indented steps only when this condition is true.
            held = True  # Saves a value named held so the next lines can use it.
            break  # Ends the current loop.
    out["separated_at_fixed_k"] = held  # Stores this value under its player, opening, or field key.

    # (b) does the EXCESS over the shuffled null grow with d?
    excess_grows = None  # Saves a value named excess_grows so the next lines can use it.
    if null_cmp is not None and len(null_cmp) >= 2:  # Runs the next indented steps only when this condition is true.
        nc = null_cmp.dropna(subset=["lift_over_null"])  # Compares the observed adoption rate with the shuffled-time reference rate.
        if len(nc) >= 2:  # Runs the next indented steps only when this condition is true.
            lo_d, hi_d = nc.iloc[0], nc.iloc[-1]  # Runs this instruction as part of the current step.
            out["lift_over_null_at_min_d"] = round(float(lo_d["lift_over_null"]), 3)  # Compares the observed adoption rate with the shuffled-time reference rate.
            out["lift_over_null_at_max_d"] = round(float(hi_d["lift_over_null"]), 3)  # Compares the observed adoption rate with the shuffled-time reference rate.
            excess_grows = bool(hi_d["lift_over_null"] > lo_d["lift_over_null"])  # Compares the observed adoption rate with the shuffled-time reference rate.
            out["excess_over_null_grows_with_d"] = excess_grows  # Stores this value under its player, opening, or field key.
            # any influence at all? the null must be beaten somewhere
            out["beats_null_anywhere"] = bool((nc["z_vs_null"] > 3).any())  # Stores this value under its player, opening, or field key.

    if excess_grows is None:  # Runs the next indented steps only when this condition is true.
        out["verdict"] = ("raw curve rises, but no null model supplied -- "  # Stores this value under its player, opening, or field key.
                          "verdict withheld")
    elif out["raw_curve_rises"] and held and excess_grows:  # Runs the next indented steps only when this condition is true.
        out["verdict"] = "complex contagion"  # Stores this value under its player, opening, or field key.
    elif out.get("beats_null_anywhere"):  # Runs the next indented steps only when this condition is true.
        out["verdict"] = ("simple contagion pattern: first-exposure association "  # Stores this value under its player, opening, or field key.
                          "exceeds the shuffled null; no clear evidence that "
                          "distinct exposers reinforce adoption")
    else:  # Handles the alternative when the preceding condition was false.
        out["verdict"] = "no detectable contagion above the null"  # Stores this value under its player, opening, or field key.
    return out  # Gives this answer back to the code that called the function.


def run(trials_path: Path, null_cmp: pd.DataFrame = None):  # Defines a reusable step; the following indented lines are its body.
    trials = pd.read_parquet(trials_path)  # Loads a previously prepared game or trial table.
    tables = analyse(trials)  # Stores the adoption-rate tables for the charts for the next step.
    for name, tb in tables.items():  # Repeats the next indented steps once for each item.
        tb.to_csv(config.TABLES / f"curve_{name}.csv", index=False)  # Writes a result table that can be inspected or downloaded.
    fig = plot(tables, config.FIGURES / "adoption_curve.png",  # Saves a value named fig so the next lines can use it.
               null_cmp=null_cmp)  # Saves a value named null_cmp so the next lines can use it.
    return tables, verdict(tables, null_cmp), fig  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--trials", default=str(config.PROCESSED / "trials.parquet"))  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    tables, v, fig = run(Path(a.trials))  # Runs this instruction as part of the current step.
    print(tables["by_d"].to_string(index=False))  # Prints this reading so a command-line run can be followed.
    print("\nVERDICT:", v)  # Prints this reading so a command-line run can be followed.
    print("figure ->", fig)  # Prints this reading so a command-line run can be followed.
