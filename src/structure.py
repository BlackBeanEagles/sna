"""Objective 4 -- who are the early adopters, structurally?

Builds the aggregate player-interaction graph, computes centrality and
Louvain communities, and asks whether the first players to take up an
opening sit at the core (hubs) or the periphery, and whether diffusion is
mostly within-community with brokers carrying it across.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx
import pandas as pd

from . import config, events, parse


def build_graph(df: pd.DataFrame) -> nx.Graph:
    """Make one player node per account and one edge per opponent pair.

    Repeated games increase the edge's `games` weight; they do not make extra
    nodes or edges. This is the network displayed during the live demo.
    """
    g = nx.Graph()
    w = df.groupby(["white", "black"]).size().reset_index(name="games")
    for u, v, n in w.itertuples(index=False):
        if g.has_edge(u, v):
            g[u][v]["games"] += int(n)
        else:
            g.add_edge(u, v, games=int(n))
    return g


def node_features(g: nx.Graph, betweenness_k: int = 200) -> pd.DataFrame:
    """Describe each player's position and detect groups in the network.

    Degree counts opponents, k-core measures membership in a dense centre,
    and betweenness approximates how often a player bridges shortest paths.
    Louvain groups players who are more connected to one another.
    """
    deg = dict(g.degree())
    core = nx.core_number(g)
    k = min(betweenness_k, g.number_of_nodes())
    btw = nx.betweenness_centrality(g, k=k, seed=config.RANDOM_SEED) if k > 2 else {}
    clus = nx.clustering(g)
    comms = nx.community.louvain_communities(g, seed=config.RANDOM_SEED)
    comm_of = {n: i for i, c in enumerate(comms) for n in c}
    feats = pd.DataFrame({
        "player": list(g.nodes()),
        "degree": [deg.get(n, 0) for n in g.nodes()],
        "kcore": [core.get(n, 0) for n in g.nodes()],
        "betweenness": [btw.get(n, 0.0) for n in g.nodes()],
        "clustering": [clus.get(n, 0.0) for n in g.nodes()],
        "community": [comm_of.get(n, -1) for n in g.nodes()],
    })
    feats.attrs["n_communities"] = len(comms)
    feats.attrs["modularity"] = nx.community.modularity(g, comms)
    return feats


def early_adopters(df: pd.DataFrame, quantile: float = 0.1) -> pd.DataFrame:
    """First `quantile` of adopters of each behaviour, by adoption time."""
    _, first_perf, _ = events.sweep(df)
    rows = [(p, beh[0], beh[1], t) for (p, beh), t in first_perf.items()]
    fp = pd.DataFrame(rows, columns=["player", "opening", "colour", "t"])
    fp["rank"] = fp.groupby(["opening", "colour"])["t"].rank(method="first", pct=True)
    fp["is_early"] = (fp["rank"] <= quantile).astype(int)
    return fp


def cross_community_flow(df: pd.DataFrame, feats: pd.DataFrame) -> dict:
    """Count pre-adoption encounters within and across detected communities.

    This is descriptive: sharing a community does not prove one opponent
    caused another player to choose an opening.
    """
    comm = dict(zip(feats["player"], feats["community"]))
    exposures, first_perf, _ = events.sweep(df)
    within = across = 0
    for (p, beh), evs in exposures.items():
        adopt_t = first_perf.get((p, beh))
        if adopt_t is None:
            continue
        for t, exposer in evs:
            if t >= adopt_t:
                break
            if comm.get(p, -1) == comm.get(exposer, -2):
                within += 1
            else:
                across += 1
    total = within + across
    return {"pre_adoption_exposures": total,
            "within_community": within,
            "across_community": across,
            "share_within": round(within / total, 4) if total else None}


def run(games_path: Path):
    df = parse.load_games(games_path)
    g = build_graph(df)
    feats = node_features(g)
    fp = early_adopters(df)

    merged = fp.merge(feats, on="player", how="left")
    by_early = merged.groupby("is_early")[
        ["degree", "kcore", "betweenness", "clustering"]].mean()
    by_early.to_csv(config.TABLES / "early_adopter_structure.csv")
    feats.to_parquet(config.PROCESSED / "node_features.parquet", index=False)

    summary = {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "density": round(nx.density(g), 6),
        "components": nx.number_connected_components(g),
        "communities": feats.attrs["n_communities"],
        "modularity": round(feats.attrs["modularity"], 4),
        "mean_degree": round(sum(dict(g.degree()).values()) / g.number_of_nodes(), 2),
        **cross_community_flow(df, feats),
    }
    pd.DataFrame([summary]).to_csv(config.TABLES / "network_summary.csv", index=False)
    return g, feats, by_early, summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))
    a = ap.parse_args()
    _, _, by_early, summary = run(Path(a.games))
    print("network:", summary)
    print("\nearly adopters (is_early=1) vs the rest:")
    print(by_early.to_string())
