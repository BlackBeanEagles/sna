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
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
from collections import defaultdict  # Loads containers for counting or collecting game records.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

from . import config, parse  # Loads the named parts of this project so this file can use their functions.


def behaviour_key(row, granularity: str) -> str:  # Defines a reusable step; the following indented lines are its body.
    return row.eco if granularity == "eco" else f"{row.eco}|{row.ply_key}"  # Gives this answer back to the code that called the function.


def sweep(df: pd.DataFrame, granularity: str = None):  # Single time-ordered pass.
    """Single time-ordered pass. Returns (exposures, first_performance, edge_first_t).

    Say to the teacher: we read games in date order. For each game, we record
    what opening each player used and what opening their opponent saw.

    exposures[(player, behaviour)] -> list of (timestamp, exposer)
    first_perf[(player, behaviour)] -> timestamp of first performance
    edge_first_t[frozenset{u,v}]    -> first time the pair ever met
    """
    granularity = granularity or config.OPENING_GRANULARITY  # Saves a value named granularity so the next lines can use it.
    df = df.sort_values("ts")  # Puts games in time order so earlier encounters cannot use future information.
    key_col = df["eco"] if granularity == "eco" else df["eco"] + "|" + df["ply_key"]  # Chooses whether the behaviour is an ECO opening or a more specific opening line.

    exposures: dict[tuple, list] = defaultdict(list)  # Stores the encounter log keyed by player and behaviour for the next step.
    first_perf: dict[tuple, object] = {}  # Stores the first-use time for each player and behaviour for the next step.
    edge_first_t: dict[frozenset, object] = {}  # Stores the first meeting time for each opponent pair for the next step.

    for (ts, w, b), x in zip(  # Repeats the next indented steps once for each item.
        zip(df["ts"].to_numpy(), df["white"].to_numpy(), df["black"].to_numpy()),  # Part of the value, collection, or call spanning several lines.
        key_col.to_numpy(),  # Part of the value, collection, or call spanning several lines.
    ):  # Runs this instruction as part of the current step.
        e = frozenset((w, b))  # Makes an unordered opponent pair, so White–Black order cannot create two links.
        if e not in edge_first_t:  # Adds only the first meeting time for this opponent pair.
            edge_first_t[e] = ts  # Remembers when these two players first met, so later structure uses only past links.
        for actor, observer, colour in ((w, b, "W"), (b, w, "B")):  # Processes both sides of each game as a performance and an exposure.
            beh = (x, colour)  # Stores the opening-and-colour behaviour for the next step.
            first_perf.setdefault((actor, beh), ts)      # performance
            exposures[(observer, beh)].append((ts, actor))  # exposure
    return exposures, first_perf, edge_first_t  # Gives this answer back to the code that called the function.


def _components(nodes: list[str], edge_first_t: dict, t_now) -> int:  # Connected components of the subgraph induced on nodes, counting only edges that already existed at t_now.
    """Connected components of the subgraph induced on `nodes`, counting only
    edges that already existed at t_now. O(d^2) -- d is small by construction."""
    n = len(nodes)  # Saves a value named n so the next lines can use it.
    if n <= 1:  # Runs the next indented steps only when this condition is true.
        return n  # Gives this answer back to the code that called the function.
    parent = list(range(n))  # Stores the union-find parent list for grouping connected exposers for the next step.

    def find(i):  # Defines a reusable step; the following indented lines are its body.
        while parent[i] != i:  # Repeats the indented block until this condition stops holding.
            parent[i] = parent[parent[i]]  # Shortens the search path while finding a connected exposer group.
            i = parent[i]  # Saves a value named i so the next lines can use it.
        return i  # Gives this answer back to the code that called the function.

    for i in range(n):  # Repeats the next indented steps once for each item.
        for j in range(i + 1, n):  # Repeats the next indented steps once for each item.
            t = edge_first_t.get(frozenset((nodes[i], nodes[j])))  # Saves a temporary value used by the next calculation.
            if t is not None and t <= t_now:  # Runs the next indented steps only when this condition is true.
                ri, rj = find(i), find(j)  # Runs this instruction as part of the current step.
                if ri != rj:  # Runs the next indented steps only when this condition is true.
                    parent[ri] = rj  # Joins two exposer groups after finding a link between them.
    return len({find(i) for i in range(n)})  # Counts how many separate social sources the exposing opponents form.


def build_trials(df: pd.DataFrame, granularity: str = None,  # Turn encounters into the rows used by every later statistical check.
                 window_days: int = None, with_diversity: bool = True  # Saves a value named window_days so the next lines can use it.
                 ) -> pd.DataFrame:  # Runs this instruction as part of the current step.
    """Turn encounters into the rows used by every later statistical check.

    Explain this in a demo as: k counts all encounters, d counts different
    opponents, sd counts separate groups among those opponents, and adopted
    means the player first used that opening/colour within the next 14 days.
    """
    window_days = window_days or config.ADOPTION_WINDOW_DAYS  # Saves a value named window_days so the next lines can use it.
    window = pd.Timedelta(days=window_days)  # Stores the time allowed for a later first use for the next step.
    exposures, first_perf, edge_first_t = sweep(df, granularity)  # Runs this instruction as part of the current step.

    t_end = df["ts"].max()  # Finds the last game date; a trial needs enough time after it to observe the outcome.
    games = pd.concat([df["white"], df["black"]]).value_counts()  # Counts how often each player or opening occurs.
    rating = pd.concat([  # Saves a value named rating so the next lines can use it.
        df[["white", "white_rating"]].rename(  # Part of the value, collection, or call spanning several lines.
            columns={"white": "p", "white_rating": "r"}),  # Saves a value named columns so the next lines can use it.
        df[["black", "black_rating"]].rename(  # Part of the value, collection, or call spanning several lines.
            columns={"black": "p", "black_rating": "r"}),  # Saves a value named columns so the next lines can use it.
    ]).groupby("p")["r"].mean()  # Groups rows sharing these keys before counting or averaging them.
    popularity = (pd.concat([df["eco"], df["eco"]]).value_counts(normalize=True)  # Counts how often each player or opening occurs.
                  if granularity == "eco" else None)  # Runs the next indented steps only when this condition is true.

    rows = []  # Stores the result rows collected for the output table for the next step.
    for (player, beh), evs in exposures.items():  # Repeats the next indented steps once for each item.
        # A player/opening pair is one story: first seeing it, then possibly
        # playing it. We stop counting exposures once that player has used it.
        adopt_t = first_perf.get((player, beh))  # Saves a value named adopt_t so the next lines can use it.
        seen, distinct = set(), []  # Runs this instruction as part of the current step.
        for k, (t, exposer) in enumerate(evs, start=1):  # Repeats the next indented steps once for each item.
            if adopt_t is not None and adopt_t <= t:  # Stops creating trials after the player has already performed this behaviour.
                break                       # already performing it; no longer at risk
            if exposer not in seen:  # Counts a repeat opponent once for d, even if they played many games.
                seen.add(exposer)  # Marks this opponent as already included in the distinct count.
                distinct.append(exposer)  # Keeps this new opponent for the structural-diversity calculation.
            # Every included trial needs the same observable follow-up. Keeping
            # late positive trials while dropping late negative trials makes
            # adoption rates (and the temporal test set) outcome-dependent.
            if t + window > t_end:  # Skips late encounters because we cannot observe a full follow-up period for them.
                continue  # Skips this item and moves to the next loop iteration.
            # The outcome is 1 only for first use after this encounter and
            # before the chosen follow-up period ends; otherwise it is 0.
            adopted = int(adopt_t is not None and t < adopt_t <= t + window)  # Marks adoption only when first use occurs after exposure and within the follow-up window.
            sd = _components(distinct, edge_first_t, t) if with_diversity else 0  # Counts independent groups among the distinct exposing opponents.
            rows.append((player, beh[0], beh[1], t, k, len(distinct), sd, adopted))  # Adds this item to the list being built.

    trials = pd.DataFrame(rows, columns=[  # Turns the collected encounters into the table used by later tests.
        "player", "opening", "colour", "t", "k", "d", "sd", "adopted"])
    if len(trials):  # Runs the next indented steps only when this condition is true.
        trials["rating"] = trials["player"].map(rating)  # Stores this value under its player, opening, or field key.
        trials["activity"] = trials["player"].map(games)  # Stores this value under its player, opening, or field key.
        trials["popularity"] = (trials["opening"].map(popularity)  # Stores this value under its player, opening, or field key.
                                if popularity is not None else 0.0)  # Runs the next indented steps only when this condition is true.
    return trials  # Gives this answer back to the code that called the function.


def run(games_path: Path, out: Path, granularity=None) -> pd.DataFrame:  # Defines a reusable step; the following indented lines are its body.
    df = parse.load_games(games_path)  # Stores the game table for the next step.
    trials = build_trials(df, granularity)  # Stores the exposure-trial table for the next step.
    trials.to_parquet(out, index=False)  # Saves a compact table for later analysis stages.
    return trials  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--out", default=str(config.PROCESSED / "trials.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--granularity", default=config.OPENING_GRANULARITY)  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    t = run(Path(a.games), Path(a.out), a.granularity)  # Saves a temporary value used by the next calculation.
    print(f"{len(t)} trials, {t.adopted.sum()} adoptions "  # Prints this reading so a command-line run can be followed.
          f"({t.adopted.mean():.3%}) -> {a.out}")  # Runs this instruction as part of the current step.
    print(t.groupby("d")["adopted"].agg(["count", "mean"]).head(8))  # Groups rows sharing these keys before counting or averaging them.
