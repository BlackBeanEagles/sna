"""Step 5 -- the adoption-probability curve. This is the whole project.

Simple contagion  -> the curve saturates after the first exposure.
Complex contagion -> adoption keeps rising with the number of distinct
                     exposers d (or with structural diversity sd) even when
                     the total exposure count k is held FIXED.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from . import config


def wilson(successes: int, n: int, z: float = 1.96):
    """Wilson score interval -- behaves at the small cell counts in the tail."""
    if n == 0:
        return (float("nan"),) * 3
    p = successes / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, centre - half), min(1.0, centre + half)


def rate_table(trials: pd.DataFrame, by: str) -> pd.DataFrame:
    """Group trials by exposure count/diversity and estimate adoption rates.

    The error bounds are Wilson intervals, which remain sensible for the
    smaller groups at the right-hand end of the chart.
    """
    g = trials.groupby(by)["adopted"].agg(["sum", "count"])
    out = []
    for val, row in g.iterrows():
        p, lo, hi = wilson(int(row["sum"]), int(row["count"]))
        out.append((val, int(row["count"]), int(row["sum"]), p, lo, hi))
    return pd.DataFrame(out, columns=[by, "n", "adopted", "rate", "lo", "hi"])


def held_k_table(trials: pd.DataFrame, k_values=(2, 3, 4), by: str = "d"
                 ) -> pd.DataFrame:
    """The decisive comparison: k fixed, d varying."""
    out = []
    for k in k_values:
        sub = trials[trials["k"] == k]
        if not len(sub):
            continue
        t = rate_table(sub, by)
        t.insert(0, "k", k)
        out.append(t)
    return (pd.concat(out, ignore_index=True) if out
            else pd.DataFrame(columns=["k", by, "n", "adopted", "rate", "lo", "hi"]))


def _clip(trials: pd.DataFrame) -> pd.DataFrame:
    t = trials.copy()
    t["k"] = t["k"].clip(upper=config.MAX_EXPOSURE_COUNT)
    t["d"] = t["d"].clip(upper=config.MAX_DIVERSITY)
    t["sd"] = t["sd"].clip(upper=config.MAX_DIVERSITY)
    return t


def analyse(trials: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build the raw curves and fixed-k checks used by charts and verdicts."""
    t = _clip(trials)
    return {
        "by_k": rate_table(t, "k"),
        "by_d": rate_table(t, "d"),
        "by_sd": rate_table(t, "sd"),
        "held_k_by_d": held_k_table(t, by="d"),
        "held_k_by_sd": held_k_table(t, by="sd"),
    }


def _yerr(tb: pd.DataFrame):
    """Wilson's centre is shifted from the point estimate, so rate-lo and
    hi-rate can go slightly negative at extreme p. Matplotlib rejects that."""
    return [(tb["rate"] - tb["lo"]).clip(lower=0).to_numpy(),
            (tb["hi"] - tb["rate"]).clip(lower=0).to_numpy()]


def plot(tables: dict[str, pd.DataFrame], out: Path,
         null_cmp: pd.DataFrame = None):
    # The live console only needs numeric tables, not a PNG. Import plotting
    # when a CLI/report run actually asks for a figure.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n_panels = 3 if (null_cmp is not None and len(null_cmp)) else 2
    fig, axes = plt.subplots(1, n_panels, figsize=(6 * n_panels, 4.6))

    ax = axes[0]
    for name, lbl, mk in (("by_k", "k  (total exposures)", "o"),
                          ("by_d", "d  (distinct exposers)", "s"),
                          ("by_sd", "sd (structural diversity)", "^")):
        tb = tables[name]
        tb = tb[tb["n"] >= 5]
        if not len(tb):
            continue
        x = tb.iloc[:, 0]
        ax.errorbar(x, tb["rate"], yerr=_yerr(tb),
                    marker=mk, capsize=3, label=lbl)
    # The null belongs ON this panel. Without it the rising curve reads as
    # complex contagion, which is exactly the misreading it refutes.
    if null_cmp is not None and len(null_cmp):
        ax.plot(null_cmp["d"], null_cmp["rate_null"], "k--", marker="x",
                linewidth=1.3, label="shuffled-time null (by d)")
    ax.set_xlabel("exposure measure")
    ax.set_ylabel(f"P(adopt within {config.ADOPTION_WINDOW_DAYS}d)")
    ax.set_title("Adoption probability curve")
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)

    ax = axes[1]
    hk = tables["held_k_by_d"]
    for k, sub in hk.groupby("k"):
        sub = sub[sub["n"] >= 5]
        if len(sub) < 2:
            continue
        ax.errorbar(sub["d"], sub["rate"], yerr=_yerr(sub),
                    marker="o", capsize=3, label=f"k = {k}")
    ax.set_xlabel("d  (distinct exposers), total exposures k held fixed")
    ax.set_ylabel("P(adopt)")
    ax.set_title("Decisive comparison: k fixed, d varying")
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)

    if n_panels == 3:
        ax = axes[2]
        ax.axhline(1.0, color="k", linewidth=1, linestyle=":")
        ax.plot(null_cmp["d"], null_cmp["lift_over_null"], marker="D",
                color="#c2185b")
        ax.set_xlabel("d  (distinct exposers)")
        ax.set_ylabel("real rate / null rate")
        ax.set_title("Excess over the null"
                     + chr(10) + "(complex contagion needs this to RISE)")
        ax.grid(alpha=.3)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def verdict(tables: dict[str, pd.DataFrame], null_cmp: pd.DataFrame = None,
            min_n: int = 20) -> dict:
    """Simple vs complex, read off the curve AND the null.

    A rising raw d-curve is NOT sufficient. High-d players are high-activity
    players, and activity alone produces a rising curve -- the timestamp-
    shuffled null reproduces it. Complex contagion requires the EXCESS over
    the null to grow with d, and requires the rise to survive with the total
    exposure count k held fixed.
    """
    d = tables["by_d"]
    d = d[d["n"] >= min_n]
    if len(d) < 2:
        return {"verdict": "insufficient data"}
    first, last = d.iloc[0], d.iloc[-1]
    out = {
        "raw_lift_d_last_over_first": round(float(last["rate"] / first["rate"]), 3)
        if first["rate"] else None,
        "rate_d_min": round(float(first["rate"]), 4),
        "rate_d_max": round(float(last["rate"]), 4),
        "raw_curve_rises": bool(last["lo"] > first["hi"]),
    }

    # (a) does the rise survive with k held fixed?
    hk = tables["held_k_by_d"]
    hk = hk[hk["n"] >= min_n]
    held = False
    for _, sub in hk.groupby("k"):
        if len(sub) >= 2 and sub.iloc[-1]["lo"] > sub.iloc[0]["hi"]:
            held = True
            break
    out["separated_at_fixed_k"] = held

    # (b) does the EXCESS over the shuffled null grow with d?
    excess_grows = None
    if null_cmp is not None and len(null_cmp) >= 2:
        nc = null_cmp.dropna(subset=["lift_over_null"])
        if len(nc) >= 2:
            lo_d, hi_d = nc.iloc[0], nc.iloc[-1]
            out["lift_over_null_at_min_d"] = round(float(lo_d["lift_over_null"]), 3)
            out["lift_over_null_at_max_d"] = round(float(hi_d["lift_over_null"]), 3)
            excess_grows = bool(hi_d["lift_over_null"] > lo_d["lift_over_null"])
            out["excess_over_null_grows_with_d"] = excess_grows
            # any influence at all? the null must be beaten somewhere
            out["beats_null_anywhere"] = bool((nc["z_vs_null"] > 3).any())

    if excess_grows is None:
        out["verdict"] = ("raw curve rises, but no null model supplied -- "
                          "verdict withheld")
    elif out["raw_curve_rises"] and held and excess_grows:
        out["verdict"] = "complex contagion"
    elif out.get("beats_null_anywhere"):
        out["verdict"] = ("simple contagion pattern: first-exposure association "
                          "exceeds the shuffled null; no clear evidence that "
                          "distinct exposers reinforce adoption")
    else:
        out["verdict"] = "no detectable contagion above the null"
    return out


def run(trials_path: Path, null_cmp: pd.DataFrame = None):
    trials = pd.read_parquet(trials_path)
    tables = analyse(trials)
    for name, tb in tables.items():
        tb.to_csv(config.TABLES / f"curve_{name}.csv", index=False)
    fig = plot(tables, config.FIGURES / "adoption_curve.png",
               null_cmp=null_cmp)
    return tables, verdict(tables, null_cmp), fig


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", default=str(config.PROCESSED / "trials.parquet"))
    a = ap.parse_args()
    tables, v, fig = run(Path(a.trials))
    print(tables["by_d"].to_string(index=False))
    print("\nVERDICT:", v)
    print("figure ->", fig)
