"""Steps 3-4 -- exposure/adoption logs and the trial table.

A behaviour is (opening, colour). One game between white=u and black=v with
opening X produces two performances and two exposures:

    u performs (X, W)  ->  exposes v to (X, W)
    v performs (X, B)  ->  exposes u to (X, B)

Adoption of behaviour b by player p = the FIRST time p performs b.

The trial table is the unit of analysis. One row per (player, behaviour,
k-th exposure) where the player had not yet performed the behaviour:

    k   cumulative exposure events so far
    d   distinct exposing opponents so far
    sd  structural diversity: connected components of the subgraph induced
        on those d exposers, using only edges that exist by time t_k
        (Ugander et al. 2012)
    adopted  1 if the player first performs b within ADOPTION_WINDOW_DAYS

Holding k fixed and varying d (or sd) is the decisive comparison.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import pandas as pd

from . import config, parse


def behaviour_key(row, granularity: str) -> str:
    return row.eco if granularity == "eco" else f"{row.eco}|{row.ply_key}"


def sweep(df: pd.DataFrame, granularity: str = None):
    """Single time-ordered pass. Returns (exposures, first_performance, edge_first_t).

    exposures[(player, behaviour)] -> list of (timestamp, exposer)
    first_perf[(player, behaviour)] -> timestamp of first performance
    edge_first_t[frozenset{u,v}]    -> first time the pair ever met
    """
    granularity = granularity or config.OPENING_GRANULARITY
    df = df.sort_values("ts")
    key_col = df["eco"] if granularity == "eco" else df["eco"] + "|" + df["ply_key"]

    exposures: dict[tuple, list] = defaultdict(list)
    first_perf: dict[tuple, object] = {}
    edge_first_t: dict[frozenset, object] = {}

    for (ts, w, b), x in zip(
        zip(df["ts"].to_numpy(), df["white"].to_numpy(), df["black"].to_numpy()),
        key_col.to_numpy(),
    ):
        e = frozenset((w, b))
        if e not in edge_first_t:
            edge_first_t[e] = ts
        for actor, observer, colour in ((w, b, "W"), (b, w, "B")):
            beh = (x, colour)
            first_perf.setdefault((actor, beh), ts)      # performance
            exposures[(observer, beh)].append((ts, actor))  # exposure
    return exposures, first_perf, edge_first_t


def _components(nodes: list[str], edge_first_t: dict, t_now) -> int:
    """Connected components of the subgraph induced on `nodes`, counting only
    edges that already existed at t_now. O(d^2) -- d is small by construction."""
    n = len(nodes)
    if n <= 1:
        return n
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            t = edge_first_t.get(frozenset((nodes[i], nodes[j])))
            if t is not None and t <= t_now:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    return len({find(i) for i in range(n)})


def build_trials(df: pd.DataFrame, granularity: str = None,
                 window_days: int = None, with_diversity: bool = True
                 ) -> pd.DataFrame:
    window_days = window_days or config.ADOPTION_WINDOW_DAYS
    window = pd.Timedelta(days=window_days)
    exposures, first_perf, edge_first_t = sweep(df, granularity)

    t_end = df["ts"].max()
    games = pd.concat([df["white"], df["black"]]).value_counts()
    rating = pd.concat([
        df[["white", "white_rating"]].rename(
            columns={"white": "p", "white_rating": "r"}),
        df[["black", "black_rating"]].rename(
            columns={"black": "p", "black_rating": "r"}),
    ]).groupby("p")["r"].mean()
    popularity = (pd.concat([df["eco"], df["eco"]]).value_counts(normalize=True)
                  if granularity == "eco" else None)

    rows = []
    for (player, beh), evs in exposures.items():
        adopt_t = first_perf.get((player, beh))
        seen, distinct = set(), []
        for k, (t, exposer) in enumerate(evs, start=1):
            if adopt_t is not None and adopt_t <= t:
                break                       # already performing it; no longer at risk
            if exposer not in seen:
                seen.add(exposer)
                distinct.append(exposer)
            censored = (t + window) > t_end
            adopted = int(adopt_t is not None and t < adopt_t <= t + window)
            if censored and not adopted:
                continue                    # window does not fit in the observation period
            sd = _components(distinct, edge_first_t, t) if with_diversity else 0
            rows.append((player, beh[0], beh[1], t, k, len(distinct), sd, adopted))

    trials = pd.DataFrame(rows, columns=[
        "player", "opening", "colour", "t", "k", "d", "sd", "adopted"])
    if len(trials):
        trials["rating"] = trials["player"].map(rating)
        trials["activity"] = trials["player"].map(games)
        trials["popularity"] = (trials["opening"].map(popularity)
                                if popularity is not None else 0.0)
    return trials


def run(games_path: Path, out: Path, granularity=None) -> pd.DataFrame:
    df = parse.load_games(games_path)
    trials = build_trials(df, granularity)
    trials.to_parquet(out, index=False)
    return trials


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))
    ap.add_argument("--out", default=str(config.PROCESSED / "trials.parquet"))
    ap.add_argument("--granularity", default=config.OPENING_GRANULARITY)
    a = ap.parse_args()
    t = run(Path(a.games), Path(a.out), a.granularity)
    print(f"{len(t)} trials, {t.adopted.sum()} adoptions "
          f"({t.adopted.mean():.3%}) -> {a.out}")
    print(t.groupby("d")["adopted"].agg(["count", "mean"]).head(8))
