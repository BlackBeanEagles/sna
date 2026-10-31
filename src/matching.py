"""Step 7a -- rating-and-activity matched controls.

Each exposed (player, behaviour) spell is matched to a comparable player
who had not yet performed or been exposed to that behaviour at the matching
time. Rating and activity use only earlier games. Later exposure is recorded
as a crossover. The resulting difference is observational.
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
from collections import defaultdict  # Loads containers for counting or collecting game records.
from pathlib import Path  # Loads Path to find and save project files.

import numpy as np  # Loads the number library used for fast calculations.
import pandas as pd  # Loads the table library used to store games and trials.

from . import config, events, parse  # Loads the named parts of this project so this file can use their functions.


def _match_index(rating: pd.Series, games: pd.Series):  # Bucket players by (rating band, log-activity band) so finding a control is a dict lookup instead of a scan over every player.
    """Bucket players by (rating band, log-activity band) so finding a control
    is a dict lookup instead of a scan over every player. Bucket widths are the
    matching tolerances; exact tolerance is still verified on each candidate,
    so the index only narrows the search -- it never loosens it."""
    r_w = config.RATING_MATCH_TOLERANCE  # Saves a value named r_w so the next lines can use it.
    a_ratio = 1.0 + config.ACTIVITY_MATCH_RATIO  # Saves a value named a_ratio so the next lines can use it.
    idx: dict[tuple[int, int], list[str]] = defaultdict(list)  # Saves a value named idx so the next lines can use it.
    meta: dict[str, tuple[float, float]] = {}  # Saves a value named meta so the next lines can use it.
    for p, r in rating.items():  # Repeats the next indented steps once for each item.
        a = games.get(p, 0)  # Saves a value named a so the next lines can use it.
        if not np.isfinite(r) or a <= 0:  # Runs the next indented steps only when this condition is true.
            continue  # Skips this item and moves to the next loop iteration.
        idx[(int(r // r_w), int(np.log(a) / np.log(a_ratio)))].append(p)  # Adds this item to the list being built.
        meta[p] = (float(r), float(a))  # Stores this value under its player, opening, or field key.
    return idx, meta  # Gives this answer back to the code that called the function.


def build_matched(df: pd.DataFrame, n_per_trial: int = 1,  # Compare an exposed player to a similar player still at risk at t0.
                  max_trials: int | None = 100_000,  # Saves a value named max_trials so the next lines can use it.
                  seed: int = config.RANDOM_SEED,  # Saves a value named seed so the next lines can use it.
                  window_days: int = None) -> pd.DataFrame:  # Saves a value named window_days so the next lines can use it.
    """Compare an exposed player to a similar player still at risk at t0.

    Rating and game activity are taken only from games before t0. A control
    cannot already have seen or played this opening/colour. This reduces some
    differences between players, but it is still observational matching.
    """
    # Presentation answer: compare an exposed player with a similarly rated,
    # similarly active player who had not yet met or played this opening.
    # We only use information available before the comparison time.
    rng = np.random.default_rng(seed)  # Saves a value named rng so the next lines can use it.
    window = pd.Timedelta(days=window_days or config.ADOPTION_WINDOW_DAYS)  # Stores the time allowed for a later first use for the next step.
    t_end = df["ts"].max()  # Finds the last game date; a trial needs enough time after it to observe the outcome.
    exposures, first_perf, _ = events.sweep(df)  # Runs this instruction as part of the current step.
    keys = list(exposures)  # Saves a value named keys so the next lines can use it.
    if max_trials and len(keys) > max_trials:  # Runs the next indented steps only when this condition is true.
        keys = [keys[i] for i in rng.choice(len(keys), max_trials, replace=False)]  # Saves a value named keys so the next lines can use it.
    keys.sort(key=lambda key: exposures[key][0][0])  # Runs this instruction as part of the current step.

    players = pd.Index(pd.unique(pd.concat([df["white"], df["black"]])))  # Saves a value named players so the next lines can use it.
    player_idx = {p: i for i, p in enumerate(players)}  # Saves a value named player_idx so the next lines can use it.
    n_players = len(players)  # Saves a value named n_players so the next lines can use it.
    never = np.iinfo(np.int64).max  # Saves a value named never so the next lines can use it.
    first_exp_ns = defaultdict(lambda: np.full(n_players, never, dtype=np.int64))  # Tracks when a control player was first exposed, so matching uses only people still at risk.
    first_perf_ns = defaultdict(lambda: np.full(n_players, never, dtype=np.int64))  # Tracks first performance time to exclude people who already adopted before matching.
    for key, evs in exposures.items():  # Repeats the next indented steps once for each item.
        first_exp_ns[key[1]][player_idx[key[0]]] = pd.Timestamp(evs[0][0]).value  # Tracks when a control player was first exposed, so matching uses only people still at risk.
    for (p, beh), t in first_perf.items():  # Repeats the next indented steps once for each item.
        first_perf_ns[beh][player_idx[p]] = pd.Timestamp(t).value  # Tracks first performance time to exclude people who already adopted before matching.

    # Advance a game-time sweep to strictly before each exposed player's t0.
    # The bucket index changes as players accumulate games. No full-month
    # covariate contributes to a control decision.
    past_games = df.sort_values("ts")[["ts", "white", "black",  # Orders the rows by this field before the next calculation.
                                       "white_rating", "black_rating"]]
    game_rows = past_games.itertuples(index=False, name=None)  # Saves a value named game_rows so the next lines can use it.
    upcoming = next(game_rows, None)  # Saves a value named upcoming so the next lines can use it.
    activity = np.zeros(n_players, dtype=np.int64)  # Saves a value named activity so the next lines can use it.
    rating_sum = np.zeros(n_players, dtype=float)  # Saves a value named rating_sum so the next lines can use it.
    rating_n = np.zeros(n_players, dtype=np.int64)  # Saves a value named rating_n so the next lines can use it.
    bucket_of = [None] * n_players  # Saves a value named bucket_of so the next lines can use it.
    buckets: dict[tuple[int, int], set[int]] = defaultdict(set)  # Saves a value named buckets so the next lines can use it.
    r_w = config.RATING_MATCH_TOLERANCE  # Saves a value named r_w so the next lines can use it.
    a_ratio = 1.0 + config.ACTIVITY_MATCH_RATIO  # Saves a value named a_ratio so the next lines can use it.
    log_ratio = np.log(a_ratio)  # Saves a value named log_ratio so the next lines can use it.

    def update_player(p: str, r: float):  # Defines a reusable step; the following indented lines are its body.
        i = player_idx[p]  # Saves a value named i so the next lines can use it.
        old = bucket_of[i]  # Saves a value named old so the next lines can use it.
        if old is not None:  # Runs the next indented steps only when this condition is true.
            buckets[old].discard(i)  # Runs this instruction as part of the current step.
        activity[i] += 1  # Adds this amount to the running total.
        if np.isfinite(r):  # Runs the next indented steps only when this condition is true.
            rating_sum[i] += float(r)  # Adds this amount to the running total.
            rating_n[i] += 1  # Adds this amount to the running total.
        if rating_n[i]:  # Runs the next indented steps only when this condition is true.
            mean = rating_sum[i] / rating_n[i]  # Saves a value named mean so the next lines can use it.
            new = (int(mean // r_w), int(np.log(activity[i]) / log_ratio))  # Saves a value named new so the next lines can use it.
            buckets[new].add(i)  # Adds this item to the collection being built.
            bucket_of[i] = new  # Stores this value under its player, opening, or field key.

    rows = []  # Stores the result rows collected for the output table for the next step.
    window_ns = window.value  # Saves a value named window_ns so the next lines can use it.
    eligible_until = {}  # Saves a value named eligible_until so the next lines can use it.
    for player, beh in keys:  # Repeats the next indented steps once for each item.
        t0 = exposures[(player, beh)][0][0]  # Stores the exposure time for the next step.
        while upcoming is not None and upcoming[0] < t0:  # Repeats the indented block until this condition stops holding.
            _, white, black, wr, br = upcoming  # Runs this instruction as part of the current step.
            update_player(white, wr)  # Runs this instruction as part of the current step.
            update_player(black, br)  # Runs this instruction as part of the current step.
            upcoming = next(game_rows, None)  # Saves a value named upcoming so the next lines can use it.
        if t0 + window > t_end:  # Runs the next indented steps only when this condition is true.
            continue  # Skips this item and moves to the next loop iteration.
        pi = player_idx[player]  # Saves a value named pi so the next lines can use it.
        if not rating_n[pi]:  # Runs the next indented steps only when this condition is true.
            continue  # Skips this item and moves to the next loop iteration.
        t0_ns = pd.Timestamp(t0).value  # Stores the comparison time in a fast numeric form for the next step.
        adopt_t = first_perf_ns[beh][pi]  # Tracks first performance time to exclude people who already adopted before matching.
        if adopt_t <= t0_ns:  # Checks whether this player had already adopted before the current exposure.
            continue  # Skips this item and moves to the next loop iteration.
        r0 = rating_sum[pi] / rating_n[pi]  # Saves a value named r0 so the next lines can use it.
        a0 = activity[pi]  # Saves a value named a0 so the next lines can use it.
        rb, ab = bucket_of[pi]  # Runs this instruction as part of the current step.
        pool = set()  # Saves a value named pool so the next lines can use it.
        for dr in (-1, 0, 1):  # Repeats the next indented steps once for each item.
            for da in (-2, -1, 0, 1, 2):  # Repeats the next indented steps once for each item.
                pool.update(buckets.get((rb + dr, ab + da), ()))  # Adds this item to the collection being built.
        pool.discard(pi)  # Runs this instruction as part of the current step.
        if not pool:  # Runs the next indented steps only when this condition is true.
            continue  # Skips this item and moves to the next loop iteration.
        peers = np.fromiter(pool, dtype=np.int64)  # Saves a value named peers so the next lines can use it.
        peers = peers[  # Saves a value named peers so the next lines can use it.
            (np.abs(rating_sum[peers] / rating_n[peers] - r0) <= r_w)  # Part of the value, collection, or call spanning several lines.
            & (np.abs(activity[peers] - a0)  # Runs this instruction as part of the current step.
               <= config.ACTIVITY_MATCH_RATIO * a0)  # Runs this instruction as part of the current step.
        ]  # Closes the data structure or function call started above.
        if not len(peers):  # Checks whether enough records exist for a trustworthy next step.
            continue  # Skips this item and moves to the next loop iteration.
        if beh not in eligible_until:  # Runs the next indented steps only when this condition is true.
            eligible_until[beh] = np.minimum(first_exp_ns[beh],  # Tracks when a control player was first exposed, so matching uses only people still at risk.
                                             first_perf_ns[beh])  # Tracks first performance time to exclude people who already adopted before matching.
        valid = peers[eligible_until[beh][peers] > t0_ns]  # Keeps only comparison players who had not yet seen or played this opening.
        if not len(valid):  # Checks whether enough records exist for a trustworthy next step.
            continue  # Skips this item and moves to the next loop iteration.
        take = min(n_per_trial, len(valid))  # Saves a value named take so the next lines can use it.
        treat = int(t0_ns < adopt_t <= t0_ns + window_ns)  # Records whether the exposed player first used the opening during follow-up.
        for ci in rng.choice(valid, size=take, replace=False):  # Repeats the next indented steps once for each item.
            ci = int(ci)  # Saves a value named ci so the next lines can use it.
            c_adopt = first_perf_ns[beh][ci]  # Finds when the comparison player first used the opening.
            c_exposed = first_exp_ns[beh][ci]  # Finds when the comparison player later encountered the opening.
            rows.append((player, str(players[ci]), beh[0], beh[1], t0,  # Part of the value, collection, or call spanning several lines.
                         treat, int(t0_ns < c_adopt <= t0_ns + window_ns),  # Part of the value, collection, or call spanning several lines.
                         int(t0_ns < c_exposed <= t0_ns + window_ns),  # Part of the value, collection, or call spanning several lines.
                         float(r0), float(rating_sum[ci] / rating_n[ci]),  # Part of the value, collection, or call spanning several lines.
                         int(a0), int(activity[ci])))  # Runs this instruction as part of the current step.

    return pd.DataFrame(rows, columns=[  # Creates a labelled table from the collected rows.
        "exposed", "control", "opening", "colour", "t0",
        "exposed_adopted", "control_adopted", "control_crossover",
        "exposed_pre_rating", "control_pre_rating",
        "exposed_pre_games", "control_pre_games"])


def summarise(pairs: pd.DataFrame, bootstrap_reps: int = 400,  # Summarise pairs, resampling both exposed and control player clusters.
              seed: int = config.RANDOM_SEED) -> dict:  # Saves a value named seed so the next lines can use it.
    """Summarise pairs, resampling both exposed and control player clusters."""
    if not len(pairs):  # Checks whether enough records exist for a trustworthy next step.
        return {"n_pairs": 0}  # Gives this answer back to the code that called the function.
    a = pairs["exposed_adopted"].to_numpy(dtype=float)  # Saves a value named a so the next lines can use it.
    b = pairs["control_adopted"].to_numpy(dtype=float)  # Saves a value named b so the next lines can use it.
    difference = a - b  # Saves a value named difference so the next lines can use it.
    diff = float(difference.mean())  # Saves a value named diff so the next lines can use it.
    names = pd.Index(pd.unique(pd.concat([pairs["exposed"], pairs["control"]])))  # Saves a value named names so the next lines can use it.
    indices = {p: i for i, p in enumerate(names)}  # Saves a value named indices so the next lines can use it.
    treated_idx = pairs["exposed"].map(indices).to_numpy(dtype=np.int64)  # Saves a value named treated_idx so the next lines can use it.
    control_idx = pairs["control"].map(indices).to_numpy(dtype=np.int64)  # Saves a value named control_idx so the next lines can use it.
    rng = np.random.default_rng(seed)  # Saves a value named rng so the next lines can use it.
    estimates = []  # Saves a value named estimates so the next lines can use it.
    for _ in range(bootstrap_reps):  # Repeats the next indented steps once for each item.
        player_weight = rng.poisson(1, len(names))  # Saves a value named player_weight so the next lines can use it.
        pair_weight = player_weight[treated_idx] * player_weight[control_idx]  # Saves a value named pair_weight so the next lines can use it.
        total = pair_weight.sum()  # Saves a value named total so the next lines can use it.
        if total:  # Runs the next indented steps only when this condition is true.
            estimates.append(float(np.dot(pair_weight, difference) / total))  # Adds this item to the list being built.
    ci = np.quantile(estimates, [0.025, 0.975]) if len(estimates) >= 20 else [np.nan, np.nan]  # Saves a value named ci so the next lines can use it.
    return {  # Gives this answer back to the code that called the function.
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
        },  # Closes the data structure or function call started above.
    }  # Closes the data structure or function call started above.


def run(games_path: Path):  # Defines a reusable step; the following indented lines are its body.
    df = parse.load_games(games_path)  # Stores the game table for the next step.
    pairs = build_matched(df)  # Stores the matched exposed and unexposed player pairs for the next step.
    pairs.to_parquet(config.PROCESSED / "matched_pairs.parquet", index=False)  # Saves a compact table for later analysis stages.
    s = summarise(pairs)  # Saves a value named s so the next lines can use it.
    pd.DataFrame([s]).to_csv(config.TABLES / "matched_controls.csv", index=False)  # Creates a labelled table from the collected rows.
    return s  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    print(run(Path(a.games)))  # Prints this reading so a command-line run can be followed.
