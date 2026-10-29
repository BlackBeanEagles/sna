"""Step 7a -- rating-and-activity matched controls.

Each exposed (player, behaviour) spell is matched to a comparable player
who had not yet performed or been exposed to that behaviour at the matching
time. Rating and activity use only earlier games. Later exposure is recorded
as a crossover. The resulting difference is observational.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, events, parse


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
    """Risk-set match with rating and activity observed strictly before t0."""
    rng = np.random.default_rng(seed)
    window = pd.Timedelta(days=window_days or config.ADOPTION_WINDOW_DAYS)
    t_end = df["ts"].max()
    exposures, first_perf, _ = events.sweep(df)
    keys = list(exposures)
    if max_trials and len(keys) > max_trials:
        keys = [keys[i] for i in rng.choice(len(keys), max_trials, replace=False)]
    keys.sort(key=lambda key: exposures[key][0][0])

    players = pd.Index(pd.unique(pd.concat([df["white"], df["black"]])))
    player_idx = {p: i for i, p in enumerate(players)}
    n_players = len(players)
    never = np.iinfo(np.int64).max
    first_exp_ns = defaultdict(lambda: np.full(n_players, never, dtype=np.int64))
    first_perf_ns = defaultdict(lambda: np.full(n_players, never, dtype=np.int64))
    for key, evs in exposures.items():
        first_exp_ns[key[1]][player_idx[key[0]]] = pd.Timestamp(evs[0][0]).value
    for (p, beh), t in first_perf.items():
        first_perf_ns[beh][player_idx[p]] = pd.Timestamp(t).value

    # Advance a game-time sweep to strictly before each exposed player's t0.
    # The bucket index changes as players accumulate games. No full-month
    # covariate contributes to a control decision.
    past_games = df.sort_values("ts")[["ts", "white", "black",
                                       "white_rating", "black_rating"]]
    game_rows = past_games.itertuples(index=False, name=None)
    upcoming = next(game_rows, None)
    activity = np.zeros(n_players, dtype=np.int64)
    rating_sum = np.zeros(n_players, dtype=float)
    rating_n = np.zeros(n_players, dtype=np.int64)
    bucket_of = [None] * n_players
    buckets: dict[tuple[int, int], set[int]] = defaultdict(set)
    r_w = config.RATING_MATCH_TOLERANCE
    a_ratio = 1.0 + config.ACTIVITY_MATCH_RATIO
    log_ratio = np.log(a_ratio)

    def update_player(p: str, r: float):
        i = player_idx[p]
        old = bucket_of[i]
        if old is not None:
            buckets[old].discard(i)
        activity[i] += 1
        if np.isfinite(r):
            rating_sum[i] += float(r)
            rating_n[i] += 1
        if rating_n[i]:
            mean = rating_sum[i] / rating_n[i]
            new = (int(mean // r_w), int(np.log(activity[i]) / log_ratio))
            buckets[new].add(i)
            bucket_of[i] = new

    rows = []
    window_ns = window.value
    eligible_until = {}
    for player, beh in keys:
        t0 = exposures[(player, beh)][0][0]
        while upcoming is not None and upcoming[0] < t0:
            _, white, black, wr, br = upcoming
            update_player(white, wr)
            update_player(black, br)
            upcoming = next(game_rows, None)
        if t0 + window > t_end:
            continue
        pi = player_idx[player]
        if not rating_n[pi]:
            continue
        t0_ns = pd.Timestamp(t0).value
        adopt_t = first_perf_ns[beh][pi]
        if adopt_t <= t0_ns:
            continue
        r0 = rating_sum[pi] / rating_n[pi]
        a0 = activity[pi]
        rb, ab = bucket_of[pi]
        pool = set()
        for dr in (-1, 0, 1):
            for da in (-2, -1, 0, 1, 2):
                pool.update(buckets.get((rb + dr, ab + da), ()))
        pool.discard(pi)
        if not pool:
            continue
        peers = np.fromiter(pool, dtype=np.int64)
        peers = peers[
            (np.abs(rating_sum[peers] / rating_n[peers] - r0) <= r_w)
            & (np.abs(activity[peers] - a0)
               <= config.ACTIVITY_MATCH_RATIO * a0)
        ]
        if not len(peers):
            continue
        if beh not in eligible_until:
            eligible_until[beh] = np.minimum(first_exp_ns[beh],
                                             first_perf_ns[beh])
        valid = peers[eligible_until[beh][peers] > t0_ns]
        if not len(valid):
            continue
        take = min(n_per_trial, len(valid))
        treat = int(t0_ns < adopt_t <= t0_ns + window_ns)
        for ci in rng.choice(valid, size=take, replace=False):
            ci = int(ci)
            c_adopt = first_perf_ns[beh][ci]
            c_exposed = first_exp_ns[beh][ci]
            rows.append((player, str(players[ci]), beh[0], beh[1], t0,
                         treat, int(t0_ns < c_adopt <= t0_ns + window_ns),
                         int(t0_ns < c_exposed <= t0_ns + window_ns),
                         float(r0), float(rating_sum[ci] / rating_n[ci]),
                         int(a0), int(activity[ci])))

    return pd.DataFrame(rows, columns=[
        "exposed", "control", "opening", "colour", "t0",
        "exposed_adopted", "control_adopted", "control_crossover",
        "exposed_pre_rating", "control_pre_rating",
        "exposed_pre_games", "control_pre_games"])


def summarise(pairs: pd.DataFrame, bootstrap_reps: int = 400,
              seed: int = config.RANDOM_SEED) -> dict:
    """Summarise pairs, resampling both exposed and control player clusters."""
    if not len(pairs):
        return {"n_pairs": 0}
    a = pairs["exposed_adopted"].to_numpy(dtype=float)
    b = pairs["control_adopted"].to_numpy(dtype=float)
    difference = a - b
    diff = float(difference.mean())
    names = pd.Index(pd.unique(pd.concat([pairs["exposed"], pairs["control"]])))
    indices = {p: i for i, p in enumerate(names)}
    treated_idx = pairs["exposed"].map(indices).to_numpy(dtype=np.int64)
    control_idx = pairs["control"].map(indices).to_numpy(dtype=np.int64)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(bootstrap_reps):
        player_weight = rng.poisson(1, len(names))
        pair_weight = player_weight[treated_idx] * player_weight[control_idx]
        total = pair_weight.sum()
        if total:
            estimates.append(float(np.dot(pair_weight, difference) / total))
    ci = np.quantile(estimates, [0.025, 0.975]) if len(estimates) >= 20 else [np.nan, np.nan]
    return {
        "n_pairs": int(len(pairs)),
        "exposed_adoption_rate": round(float(a.mean()), 4),
        "control_adoption_rate": round(float(b.mean()), 4),
        "difference": round(diff, 4),
        "ci95": [round(float(v), 4) for v in ci],
        "ci95_method": "player-cluster Poisson bootstrap; both pair members",
        "bootstrap_reps": len(estimates),
        "risk_ratio": round(float(a.mean() / b.mean()), 3) if b.mean() else None,
        "control_crossover_rate": round(float(pairs["control_crossover"].mean()), 4),
        "pre_match_balance": {
            "exposed_rating_mean": round(float(pairs["exposed_pre_rating"].mean()), 1),
            "control_rating_mean": round(float(pairs["control_pre_rating"].mean()), 1),
            "exposed_games_mean": round(float(pairs["exposed_pre_games"].mean()), 1),
            "control_games_mean": round(float(pairs["control_pre_games"].mean()), 1),
        },
    }


def run(games_path: Path):
    df = parse.load_games(games_path)
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
