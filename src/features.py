"""Features for the held-out prediction check, built without leakage.

Two problems with the original check, both fixed here.

**Leakage.** The original model computed summary features over the whole
month. Here fixed background features are computed before the first evaluated
trial; exposure features are measured at each trial. Whole player-behaviour
spells are assigned to one side of the held-out split.

**A missing explanation.** The original feature set asked only "who played this
opening at you?". De Marzo and Servedio [4] showed that a player's next opening
is largely predicted by how close it sits to what they already play -- an
"adjacent possible" effect in opening space, with no social component at all.
Leaving that out makes the social features look better than they are, because
they are the only candidate on offer. `repertoire_density` puts the competing
explanation in the model.

Three feature blocks are produced, so the three can be compared directly:

    BASELINE    popularity, rating, activity        "popular openings get played"
    REPERTOIRE  + density, repertoire size          "you learn what is near what you know"
    NETWORK     + k, d, sd, degree, kcore, between  "who played it at you"
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import structure

BASELINE = ["popularity", "rating", "activity"]
REPERTOIRE = BASELINE + ["repertoire_density", "repertoire_size"]
NETWORK = REPERTOIRE + ["k", "d", "sd", "degree", "kcore", "betweenness"]


def _repertoires(df: pd.DataFrame) -> dict[str, set]:
    """Which openings each player actually plays, by colour-agnostic ECO."""
    rep: dict[str, set] = {}
    for col in ("white", "black"):
        for player, eco in zip(df[col].to_numpy(), df["eco"].to_numpy()):
            rep.setdefault(player, set()).add(eco)
    return rep


def relatedness(rep: dict[str, set], openings: list[str]) -> pd.DataFrame:
    """Opening-to-opening proximity from co-play, following De Marzo & Servedio.

    Two openings are related when the same players tend to play both. Using
    min() in the denominator keeps a rare opening that is always played
    alongside a common one from being scored as unrelated to it.
    """
    idx = {o: i for i, o in enumerate(openings)}
    n = len(openings)
    co = np.zeros((n, n), dtype=float)
    count = np.zeros(n, dtype=float)

    for played in rep.values():
        ids = [idx[o] for o in played if o in idx]
        for i in ids:
            count[i] += 1
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                co[ids[a], ids[b]] += 1
                co[ids[b], ids[a]] += 1

    denom = np.minimum.outer(count, count)
    with np.errstate(divide="ignore", invalid="ignore"):
        phi = np.where(denom > 0, co / denom, 0.0)
    np.fill_diagonal(phi, 0.0)
    return pd.DataFrame(phi, index=openings, columns=openings)


def density_matrix(rep: dict[str, set], phi: pd.DataFrame,
                   players: list[str]) -> np.ndarray:
    """Density for every (opening, player) pair at once.

    How close an opening sits to what a player already plays: the share of that
    opening's total relatedness pointing at openings already in the repertoire.
    1.0 means everything related to it is already known, 0.0 means none of it.

    Done as a single matrix product. The obvious per-trial version costs a
    pandas label lookup and a fancy-index sum for each of ~224k trials, which
    took over ten minutes; this takes a fraction of a second and is the same
    arithmetic. phi has a zero diagonal, so an opening never counts itself.
    """
    openings = list(phi.index)
    o_idx = {o: i for i, o in enumerate(openings)}
    mask = np.zeros((len(players), len(openings)), dtype=float)
    for pi, p in enumerate(players):
        for o in rep.get(p, ()):
            j = o_idx.get(o)
            if j is not None:
                mask[pi, j] = 1.0

    phi_v = phi.to_numpy()
    totals = phi_v.sum(axis=1)                 # per opening
    reach = phi_v @ mask.T                     # openings x players
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(totals[:, None] > 0, reach / totals[:, None], 0.0)


def build(games: pd.DataFrame, trials: pd.DataFrame,
          split_ts) -> pd.DataFrame:
    """Attach features computed ONLY from games before `split_ts`."""
    past = games[games["ts"] <= split_ts]
    if not len(past):
        raise ValueError("no games before the split; cannot build features")

    # --- who plays what, and how openings relate, as of the split ---------
    rep = _repertoires(past)
    openings = sorted(past["eco"].unique())
    phi = relatedness(rep, openings)

    # --- player-level attributes from the training window -----------------
    activity = pd.concat([past["white"], past["black"]]).value_counts()
    rating = pd.concat([
        past[["white", "white_rating"]].rename(
            columns={"white": "p", "white_rating": "r"}),
        past[["black", "black_rating"]].rename(
            columns={"black": "p", "black_rating": "r"}),
    ]).groupby("p")["r"].mean()
    popularity = past["eco"].value_counts(normalize=True)

    # --- network position as of the split ---------------------------------
    g = structure.build_graph(past)
    feats = structure.node_features(g)[
        ["player", "degree", "kcore", "betweenness"]]

    out = trials.copy()
    out["rating"] = out["player"].map(rating).fillna(rating.mean())
    out["activity"] = out["player"].map(activity).fillna(0.0)
    out["popularity"] = out["opening"].map(popularity).fillna(0.0)
    out["repertoire_size"] = out["player"].map(
        {p: len(s) for p, s in rep.items()}).fillna(0.0)

    players = sorted(rep)
    dens = density_matrix(rep, phi, players)
    p_idx = {p: i for i, p in enumerate(players)}
    o_idx = {o: i for i, o in enumerate(phi.index)}
    rows = out["opening"].map(o_idx).to_numpy()
    cols = out["player"].map(p_idx).to_numpy()
    known = pd.notna(rows) & pd.notna(cols)
    vals = np.zeros(len(out), dtype=float)
    vals[known] = dens[rows[known].astype(int), cols[known].astype(int)]
    out["repertoire_density"] = vals
    out = out.drop(columns=["degree", "kcore", "betweenness"], errors="ignore")
    out = out.merge(feats, on="player", how="left")
    for c in ("degree", "kcore", "betweenness"):
        out[c] = out[c].fillna(0.0)
    return out
