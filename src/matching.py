"""Step 7a -- rating-and-activity matched controls.

Answers "would they have adopted anyway?". Each exposed (player, behaviour)
spell is matched to an unexposed player of comparable rating and activity,
observed over the same window, who had NOT been exposed to that behaviour.
The difference in adoption rates is the influence effect net of baseline
drift -- which also absorbs external shocks (a tournament broadcast lifts
exposed and unexposed alike).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, events


def _match_index(rating: pd.Series, games: pd.Series):
    """Bucket players by (rating band, log-activity band) so finding a control
    is a dict lookup instead of a scan over every player. Bucket widths are the
    matching tolerances; exact tolerance is still verified on each candidate,
    so the index only narrows the search -- it never loosens it."""
    r_w = config.RATING_MATCH_TOLERANCE
    a_ratio = 1.0 + config.ACTIVITY_MATCH_RATIO
    idx: dict[tuple[int, int], list[str]] = defaultdict(list)
    meta: dict[str, tuple[float, float]] = {}
    for p, r in rating.items():
        a = games.get(p, 0)
        if not np.isfinite(r) or a <= 0:
            continue
        idx[(int(r // r_w), int(np.log(a) / np.log(a_ratio)))].append(p)
        meta[p] = (float(r), float(a))
    return idx, meta


def build_matched(df: pd.DataFrame, n_per_trial: int = 1,
                  max_trials: int | None = 100_000,
                  seed: int = config.RANDOM_SEED,
                  window_days: int = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    window = pd.Timedelta(days=window_days or config.ADOPTION_WINDOW_DAYS)
    t_end = df["ts"].max()

    exposures, first_perf, _ = events.sweep(df)
    exposed_players = defaultdict(set)          # behaviour -> players ever exposed
    for (p, beh) in exposures:
        exposed_players[beh].add(p)

    games = pd.concat([df["white"], df["black"]]).value_counts()
    rating = pd.concat([
        df[["white", "white_rating"]].rename(columns={"white": "p", "white_rating": "r"}),
        df[["black", "black_rating"]].rename(columns={"black": "p", "black_rating": "r"}),
    ]).groupby("p")["r"].mean()
    idx, meta = _match_index(rating, games)

    keys = list(exposures.keys())
    if max_trials and len(keys) > max_trials:
        # random subsample of exposure spells: unbiased, and keeps a full
        # month tractable
        keys = [keys[i] for i in rng.choice(len(keys), max_trials, replace=False)]

    r_w = config.RATING_MATCH_TOLERANCE
    a_ratio = 1.0 + config.ACTIVITY_MATCH_RATIO
    rows = []
    for key in keys:
        player, beh = key
        t0, _ = exposures[key][0]               # first exposure only
        if t0 + window > t_end:
            continue
        adopt_t = first_perf.get((player, beh))
        if adopt_t is not None and adopt_t <= t0:
            continue                            # already performing it
        if player not in meta:
            continue
        treat = int(adopt_t is not None and t0 < adopt_t <= t0 + window)
        r0, a0 = meta[player]

        rb, ab = int(r0 // r_w), int(np.log(a0) / np.log(a_ratio))
        pool = []
        for dr in (-1, 0, 1):
            for da in (-1, 0, 1):
                pool.extend(idx.get((rb + dr, ab + da), ()))
        if not pool:
            continue
        banned = exposed_players[beh]
        cand = []
        for i in rng.choice(len(pool), min(len(pool), 60), replace=False):
            c = pool[i]
            if c == player or c in banned:
                continue
            rc, ac = meta[c]
            if (abs(rc - r0) <= config.RATING_MATCH_TOLERANCE
                    and abs(ac - a0) <= config.ACTIVITY_MATCH_RATIO * a0):
                cand.append(c)
                if len(cand) >= n_per_trial:
                    break
        for c in cand:
            c_adopt = first_perf.get((c, beh))
            ctrl = int(c_adopt is not None and t0 < c_adopt <= t0 + window)
            rows.append((player, c, beh[0], beh[1], t0, treat, ctrl))

    return pd.DataFrame(rows, columns=[
        "exposed", "control", "opening", "colour", "t0",
        "exposed_adopted", "control_adopted"])


def summarise(pairs: pd.DataFrame) -> dict:
    if not len(pairs):
        return {"n_pairs": 0}
    a, b = pairs["exposed_adopted"], pairs["control_adopted"]
    diff = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return {
        "n_pairs": int(len(pairs)),
        "exposed_adoption_rate": round(float(a.mean()), 4),
        "control_adoption_rate": round(float(b.mean()), 4),
        "difference": round(float(diff), 4),
        "ci95": [round(float(diff - 1.96 * se), 4), round(float(diff + 1.96 * se), 4)],
        "risk_ratio": round(float(a.mean() / b.mean()), 3) if b.mean() else None,
    }


def run(games_path: Path):
    df = pd.read_parquet(games_path)
    pairs = build_matched(df)
    pairs.to_parquet(config.PROCESSED / "matched_pairs.parquet", index=False)
    s = summarise(pairs)
    pd.DataFrame([s]).to_csv(config.TABLES / "matched_controls.csv", index=False)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))
    a = ap.parse_args()
    print(run(Path(a.games)))
