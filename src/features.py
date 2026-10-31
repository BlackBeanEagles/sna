"""Features for the held-out prediction check, built without leakage.

Two problems with the original check, both fixed here.

**Leakage.** The original model computed summary features over the whole
month. Here fixed background features are computed before the first evaluated
trial; exposure features are measured at each trial. Whole player-behaviour
spells are assigned to one side of the held-out split.

**A missing explanation.** The original feature set asked only "who played this
opening at you?". A player may choose a new opening simply because it is close
to openings they already know, without copying an opponent. Leaving that out
makes social features look better than they are. `repertoire_density` measures
this competing explanation. It is a project control, not a causal proof.

Three feature blocks are produced, so the three can be compared directly:

    BASELINE    popularity, rating, activity        "popular openings get played"
    REPERTOIRE  + density, repertoire size          "you learn what is near what you know"
    NETWORK     + k, d, sd, degree, kcore, between  "who played it at you"
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import numpy as np  # Loads the number library used for fast calculations.
import pandas as pd  # Loads the table library used to store games and trials.

from . import structure  # Loads the named parts of this project so this file can use their functions.

BASELINE = ["popularity", "rating", "activity"]  # Saves a value named BASELINE so the next lines can use it.
REPERTOIRE = BASELINE + ["repertoire_density", "repertoire_size"]  # Saves a value named REPERTOIRE so the next lines can use it.
NETWORK = REPERTOIRE + ["k", "d", "sd", "degree", "kcore", "betweenness"]  # Saves a value named NETWORK so the next lines can use it.


def _repertoires(df: pd.DataFrame) -> dict[str, set]:  # Which openings each player actually plays, by colour-agnostic ECO.
    """Which openings each player actually plays, by colour-agnostic ECO."""
    rep: dict[str, set] = {}  # Saves a value named rep so the next lines can use it.
    for col in ("white", "black"):  # Repeats the next indented steps once for each item.
        for player, eco in zip(df[col].to_numpy(), df["eco"].to_numpy()):  # Repeats the next indented steps once for each item.
            rep.setdefault(player, set()).add(eco)  # Adds this item to the collection being built.
    return rep  # Gives this answer back to the code that called the function.


def relatedness(rep: dict[str, set], openings: list[str]) -> pd.DataFrame:  # Opening-to-opening proximity from co-play, following De Marzo & Servedio.
    """Opening-to-opening proximity from co-play, following De Marzo & Servedio.

    Two openings are related when the same players tend to play both. Using
    min() in the denominator keeps a rare opening that is always played
    alongside a common one from being scored as unrelated to it.
    """
    idx = {o: i for i, o in enumerate(openings)}  # Saves a value named idx so the next lines can use it.
    n = len(openings)  # Saves a value named n so the next lines can use it.
    co = np.zeros((n, n), dtype=float)  # Saves a value named co so the next lines can use it.
    count = np.zeros(n, dtype=float)  # Saves a value named count so the next lines can use it.

    for played in rep.values():  # Repeats the next indented steps once for each item.
        ids = [idx[o] for o in played if o in idx]  # Saves a value named ids so the next lines can use it.
        for i in ids:  # Repeats the next indented steps once for each item.
            count[i] += 1  # Adds this amount to the running total.
        for a in range(len(ids)):  # Repeats the next indented steps once for each item.
            for b in range(a + 1, len(ids)):  # Repeats the next indented steps once for each item.
                co[ids[a], ids[b]] += 1  # Adds this amount to the running total.
                co[ids[b], ids[a]] += 1  # Adds this amount to the running total.

    denom = np.minimum.outer(count, count)  # Saves a value named denom so the next lines can use it.
    with np.errstate(divide="ignore", invalid="ignore"):  # Opens a resource and guarantees cleanup when the block ends.
        phi = np.where(denom > 0, co / denom, 0.0)  # Saves a value named phi so the next lines can use it.
    np.fill_diagonal(phi, 0.0)  # Runs this instruction as part of the current step.
    return pd.DataFrame(phi, index=openings, columns=openings)  # Creates a labelled table from the collected rows.


def density_matrix(rep: dict[str, set], phi: pd.DataFrame,  # Density for every (opening, player) pair at once.
                   players: list[str]) -> np.ndarray:  # Runs this instruction as part of the current step.
    """Density for every (opening, player) pair at once.

    How close an opening sits to what a player already plays: the share of that
    opening's total relatedness pointing at openings already in the repertoire.
    1.0 means everything related to it is already known, 0.0 means none of it.

    Done as a single matrix product. The obvious per-trial version costs a
    pandas label lookup and a fancy-index sum for each of ~224k trials, which
    took over ten minutes; this takes a fraction of a second and is the same
    arithmetic. phi has a zero diagonal, so an opening never counts itself.
    """
    openings = list(phi.index)  # Saves a value named openings so the next lines can use it.
    o_idx = {o: i for i, o in enumerate(openings)}  # Saves a value named o_idx so the next lines can use it.
    mask = np.zeros((len(players), len(openings)), dtype=float)  # Saves a value named mask so the next lines can use it.
    for pi, p in enumerate(players):  # Repeats the next indented steps once for each item.
        for o in rep.get(p, ()):  # Repeats the next indented steps once for each item.
            j = o_idx.get(o)  # Saves a value named j so the next lines can use it.
            if j is not None:  # Runs the next indented steps only when this condition is true.
                mask[pi, j] = 1.0  # Stores this value under its player, opening, or field key.

    phi_v = phi.to_numpy()  # Saves a value named phi_v so the next lines can use it.
    totals = phi_v.sum(axis=1)                 # per opening
    reach = phi_v @ mask.T                     # openings x players
    with np.errstate(divide="ignore", invalid="ignore"):  # Opens a resource and guarantees cleanup when the block ends.
        return np.where(totals[:, None] > 0, reach / totals[:, None], 0.0)  # Gives this answer back to the code that called the function.


def build(games: pd.DataFrame, trials: pd.DataFrame,  # Attach features computed ONLY from games before split_ts.
          split_ts) -> pd.DataFrame:  # Runs this instruction as part of the current step.
    """Attach features computed ONLY from games before `split_ts`.

    Explain the three blocks as activity/popularity, closeness to existing
    openings, and exposure/network position. Earlier games prevent future
    outcomes leaking into the model's predictors.
    """
    past = games[games["ts"] <= split_ts]  # Saves a value named past so the next lines can use it.
    if not len(past):  # Checks whether enough records exist for a trustworthy next step.
        raise ValueError("no games before the split; cannot build features")  # Stops with an explicit error when this requirement is violated.

    # --- who plays what, and how openings relate, as of the split ---------
    rep = _repertoires(past)  # Saves a value named rep so the next lines can use it.
    openings = sorted(past["eco"].unique())  # Saves a value named openings so the next lines can use it.
    phi = relatedness(rep, openings)  # Saves a value named phi so the next lines can use it.

    # --- player-level attributes from the training window -----------------
    activity = pd.concat([past["white"], past["black"]]).value_counts()  # Counts how often each player or opening occurs.
    rating = pd.concat([  # Saves a value named rating so the next lines can use it.
        past[["white", "white_rating"]].rename(  # Part of the value, collection, or call spanning several lines.
            columns={"white": "p", "white_rating": "r"}),  # Saves a value named columns so the next lines can use it.
        past[["black", "black_rating"]].rename(  # Part of the value, collection, or call spanning several lines.
            columns={"black": "p", "black_rating": "r"}),  # Saves a value named columns so the next lines can use it.
    ]).groupby("p")["r"].mean()  # Groups rows sharing these keys before counting or averaging them.
    popularity = past["eco"].value_counts(normalize=True)  # Counts how often each player or opening occurs.

    # --- network position as of the split ---------------------------------
    g = structure.build_graph(past)  # Connects players who faced each other in the selected games.
    feats = structure.node_features(g)[  # Stores the network features for the next step.
        ["player", "degree", "kcore", "betweenness"]]  # Part of the value, collection, or call spanning several lines.

    out = trials.copy()  # Stores the output value for the next step.
    out["rating"] = out["player"].map(rating).fillna(rating.mean())  # Stores this value under its player, opening, or field key.
    out["activity"] = out["player"].map(activity).fillna(0.0)  # Stores this value under its player, opening, or field key.
    out["popularity"] = out["opening"].map(popularity).fillna(0.0)  # Stores this value under its player, opening, or field key.
    out["repertoire_size"] = out["player"].map(  # Part of the value, collection, or call spanning several lines.
        {p: len(s) for p, s in rep.items()}).fillna(0.0)  # Part of the value, collection, or call spanning several lines.

    players = sorted(rep)  # Saves a value named players so the next lines can use it.
    dens = density_matrix(rep, phi, players)  # Saves a value named dens so the next lines can use it.
    p_idx = {p: i for i, p in enumerate(players)}  # Saves a value named p_idx so the next lines can use it.
    o_idx = {o: i for i, o in enumerate(phi.index)}  # Saves a value named o_idx so the next lines can use it.
    rows = out["opening"].map(o_idx).to_numpy()  # Stores the result rows collected for the output table for the next step.
    cols = out["player"].map(p_idx).to_numpy()  # Saves a value named cols so the next lines can use it.
    known = pd.notna(rows) & pd.notna(cols)  # Saves a value named known so the next lines can use it.
    vals = np.zeros(len(out), dtype=float)  # Saves a value named vals so the next lines can use it.
    vals[known] = dens[rows[known].astype(int), cols[known].astype(int)]  # Stores this value under its player, opening, or field key.
    out["repertoire_density"] = vals  # Stores this value under its player, opening, or field key.
    out = out.drop(columns=["degree", "kcore", "betweenness"], errors="ignore")  # Stores the output value for the next step.
    out = out.merge(feats, on="player", how="left")  # Joins two tables on shared identifiers so their columns can be compared.
    for c in ("degree", "kcore", "betweenness"):  # Repeats the next indented steps once for each item.
        out[c] = out[c].fillna(0.0)  # Stores this value under its player, opening, or field key.
    return out  # Gives this answer back to the code that called the function.
