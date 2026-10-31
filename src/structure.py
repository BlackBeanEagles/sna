"""Objective 4 -- who are the early adopters, structurally?

Builds the aggregate player-interaction graph, computes centrality and
Louvain communities, and asks whether the first players to take up an
opening sit at the core (hubs) or the periphery, and whether diffusion is
mostly within-community with brokers carrying it across.
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
from pathlib import Path  # Loads Path to find and save project files.

import networkx as nx  # Loads the library used to build and measure player links.
import pandas as pd  # Loads the table library used to store games and trials.

from . import config, events, parse  # Loads the named parts of this project so this file can use their functions.


def build_graph(df: pd.DataFrame) -> nx.Graph:  # Make one player node per account and one edge per opponent pair.
    """Make one player node per account and one edge per opponent pair.

    Repeated games increase the edge's `games` weight; they do not make extra
    nodes or edges. This is the network displayed during the live demo.
    """
    g = nx.Graph()  # Stores the player graph for the next step.
    w = df.groupby(["white", "black"]).size().reset_index(name="games")  # Groups rows sharing these keys before counting or averaging them.
    for u, v, n in w.itertuples(index=False):  # Repeats the next indented steps once for each item.
        if g.has_edge(u, v):  # Runs the next indented steps only when this condition is true.
            g[u][v]["games"] += int(n)  # Adds this amount to the running total.
        else:  # Handles the alternative when the preceding condition was false.
            g.add_edge(u, v, games=int(n))  # Runs this instruction as part of the current step.
    return g  # Gives this answer back to the code that called the function.


def node_features(g: nx.Graph, betweenness_k: int = 200) -> pd.DataFrame:  # Describe each player's position and detect groups in the network.
    """Describe each player's position and detect groups in the network.

    Degree counts opponents, k-core measures membership in a dense centre,
    and betweenness approximates how often a player bridges shortest paths.
    Louvain groups players who are more connected to one another.
    """
    deg = dict(g.degree())  # Saves a value named deg so the next lines can use it.
    core = nx.core_number(g)  # Measures how deeply each player lies in a mutually connected core.
    k = min(betweenness_k, g.number_of_nodes())  # Stores the total exposure count for the next step.
    btw = nx.betweenness_centrality(g, k=k, seed=config.RANDOM_SEED) if k > 2 else {}  # Estimates how often players bridge shortest routes through the graph.
    clus = nx.clustering(g)  # Saves a value named clus so the next lines can use it.
    comms = nx.community.louvain_communities(g, seed=config.RANDOM_SEED)  # Finds groups of players with relatively dense internal connections.
    comm_of = {n: i for i, c in enumerate(comms) for n in c}  # Saves a value named comm_of so the next lines can use it.
    feats = pd.DataFrame({  # Creates a labelled table from the collected rows.
        "player": list(g.nodes()),
        "degree": [deg.get(n, 0) for n in g.nodes()],
        "kcore": [core.get(n, 0) for n in g.nodes()],
        "betweenness": [btw.get(n, 0.0) for n in g.nodes()],
        "clustering": [clus.get(n, 0.0) for n in g.nodes()],
        "community": [comm_of.get(n, -1) for n in g.nodes()],
    })  # Runs this instruction as part of the current step.
    feats.attrs["n_communities"] = len(comms)  # Stores this value under its player, opening, or field key.
    feats.attrs["modularity"] = nx.community.modularity(g, comms)  # Stores this value under its player, opening, or field key.
    return feats  # Gives this answer back to the code that called the function.


def early_adopters(df: pd.DataFrame, quantile: float = 0.1) -> pd.DataFrame:  # First quantile of adopters of each behaviour, by adoption time.
    """First `quantile` of adopters of each behaviour, by adoption time."""
    _, first_perf, _ = events.sweep(df)  # Runs this instruction as part of the current step.
    rows = [(p, beh[0], beh[1], t) for (p, beh), t in first_perf.items()]  # Stores the result rows collected for the output table for the next step.
    fp = pd.DataFrame(rows, columns=["player", "opening", "colour", "t"])  # Creates a labelled table from the collected rows.
    fp["rank"] = fp.groupby(["opening", "colour"])["t"].rank(method="first", pct=True)  # Groups rows sharing these keys before counting or averaging them.
    fp["is_early"] = (fp["rank"] <= quantile).astype(int)  # Stores this value under its player, opening, or field key.
    return fp  # Gives this answer back to the code that called the function.


def cross_community_flow(df: pd.DataFrame, feats: pd.DataFrame) -> dict:  # Count pre-adoption encounters within and across detected communities.
    """Count pre-adoption encounters within and across detected communities.

    This is descriptive: sharing a community does not prove one opponent
    caused another player to choose an opening.
    """
    comm = dict(zip(feats["player"], feats["community"]))  # Saves a value named comm so the next lines can use it.
    exposures, first_perf, _ = events.sweep(df)  # Runs this instruction as part of the current step.
    within = across = 0  # Saves a value named within so the next lines can use it.
    for (p, beh), evs in exposures.items():  # Repeats the next indented steps once for each item.
        adopt_t = first_perf.get((p, beh))  # Saves a value named adopt_t so the next lines can use it.
        if adopt_t is None:  # Checks whether this player had already adopted before the current exposure.
            continue  # Skips this item and moves to the next loop iteration.
        for t, exposer in evs:  # Repeats the next indented steps once for each item.
            if t >= adopt_t:  # Checks whether this player had already adopted before the current exposure.
                break  # Ends the current loop.
            if comm.get(p, -1) == comm.get(exposer, -2):  # Runs the next indented steps only when this condition is true.
                within += 1  # Adds this amount to the running total.
            else:  # Handles the alternative when the preceding condition was false.
                across += 1  # Adds this amount to the running total.
    total = within + across  # Saves a value named total so the next lines can use it.
    return {"pre_adoption_exposures": total,  # Gives this answer back to the code that called the function.
            "within_community": within,
            "across_community": across,
            "share_within": round(within / total, 4) if total else None}


def run(games_path: Path):  # Defines a reusable step; the following indented lines are its body.
    df = parse.load_games(games_path)  # Stores the game table for the next step.
    g = build_graph(df)  # Stores the player graph for the next step.
    feats = node_features(g)  # Stores the network features for the next step.
    fp = early_adopters(df)  # Saves a value named fp so the next lines can use it.

    merged = fp.merge(feats, on="player", how="left")  # Joins two tables on shared identifiers so their columns can be compared.
    by_early = merged.groupby("is_early")[  # Groups rows sharing these keys before counting or averaging them.
        ["degree", "kcore", "betweenness", "clustering"]].mean()  # Part of the value, collection, or call spanning several lines.
    by_early.to_csv(config.TABLES / "early_adopter_structure.csv")  # Writes a result table that can be inspected or downloaded.
    feats.to_parquet(config.PROCESSED / "node_features.parquet", index=False)  # Saves a compact table for later analysis stages.

    summary = {  # Saves a value named summary so the next lines can use it.
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "density": round(nx.density(g), 6),
        "components": nx.number_connected_components(g),
        "communities": feats.attrs["n_communities"],
        "modularity": round(feats.attrs["modularity"], 4),
        "mean_degree": round(sum(dict(g.degree()).values()) / g.number_of_nodes(), 2),
        **cross_community_flow(df, feats),  # Part of the value, collection, or call spanning several lines.
    }  # Closes the data structure or function call started above.
    pd.DataFrame([summary]).to_csv(config.TABLES / "network_summary.csv", index=False)  # Creates a labelled table from the collected rows.
    return g, feats, by_early, summary  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    _, _, by_early, summary = run(Path(a.games))  # Runs this instruction as part of the current step.
    print("network:", summary)  # Prints this reading so a command-line run can be followed.
    print("\nearly adopters (is_early=1) vs the rest:")  # Prints this reading so a command-line run can be followed.
    print(by_early.to_string())  # Prints this reading so a command-line run can be followed.
