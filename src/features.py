"""Features for the held-out prediction check, built without leakage.

Two problems with the original check, both fixed here.

**Leakage.** Every feature used to be computed over the whole month and then
used to predict the last 30% of it, so the model saw summary statistics that
partly encoded the held-out period. Here every feature is computed from games
strictly before the split, so nothing about the test period reaches the model.

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


def density(rep: dict[str, set], phi: pd.DataFrame, player: str,
            opening: str) -> float:
    """How close `opening` sits to what `player` already plays.

    The share of that opening's total relatedness that points at openings the
    player already has. 1.0 means everything related to it is already in the
    repertoire; 0.0 means none of it is.
    """
    if opening not in phi.index:
        return 0.0
    row = phi.loc[opening]
    total = row.sum()
    if total <= 0:
        return 0.0
    have = [o for o in rep.get(player, ()) if o in phi.index and o != opening]
    return float(row[have].sum() / total) if have else 0.0


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
    out["repertoire_density"] = [
        density(rep, phi, p, o)
        for p, o in zip(out["player"].to_numpy(), out["opening"].to_numpy())
    ]
    out = out.drop(columns=["degree", "kcore", "betweenness"], errors="ignore")
    out = out.merge(feats, on="player", how="left")
    for c in ("degree", "kcore", "betweenness"):
        out[c] = out[c].fillna(0.0)
    return out
