"""Step 8 -- animated diffusion of one opening across the player network.

The demo, not the result. Picks the opening with the most adoptions, lays
the interaction graph out once, then walks forward in time colouring nodes
as they adopt. Writes a GIF plus a static small-multiple panel for the
report (GIFs do not paste into a PDF).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter

from . import config, events, parse, structure

UNADOPTED = "#d9d9d9"
ADOPTED = "#c2185b"
NEW = "#f9a825"


def pick_behaviour(df: pd.DataFrame):
    _, first_perf, _ = events.sweep(df)
    rows = [(p, beh[0], beh[1], t) for (p, beh), t in first_perf.items()]
    fp = pd.DataFrame(rows, columns=["player", "opening", "colour", "t"])
    best = fp.groupby(["opening", "colour"]).size().idxmax()
    sel = fp[(fp["opening"] == best[0]) & (fp["colour"] == best[1])]
    return best, sel.sort_values("t")


def animate(df: pd.DataFrame, out_gif: Path = None, out_png: Path = None,
            frames: int = 40, max_nodes: int = 400):
    out_gif = out_gif or (config.FIGURES / "diffusion.gif")
    out_png = out_png or (config.FIGURES / "diffusion_panels.png")

    g = structure.build_graph(df)
    if g.number_of_nodes() > max_nodes:
        keep = [n for n, _ in sorted(g.degree(), key=lambda x: -x[1])[:max_nodes]]
        g = g.subgraph(keep).copy()
    (opening, colour), adopters = pick_behaviour(df)
    adopters = adopters[adopters["player"].isin(g.nodes())]

    pos = nx.spring_layout(g, seed=config.RANDOM_SEED, k=1.6 / (g.number_of_nodes() ** .5))
    t0, t1 = df["ts"].min(), df["ts"].max()
    cuts = pd.date_range(t0, t1, periods=frames)
    nodes = list(g.nodes())
    adopt_t = dict(zip(adopters["player"], adopters["t"]))

    def colours_at(i):
        cut, prev = cuts[i], cuts[max(i - 1, 0)]
        out = []
        for n in nodes:
            t = adopt_t.get(n)
            if t is None or t > cut:
                out.append(UNADOPTED)
            elif t > prev:
                out.append(NEW)
            else:
                out.append(ADOPTED)
        return out

    def sizes_at(i):
        return [70 if c == NEW else 26 for c in colours_at(i)]

    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    nx.draw_networkx_edges(g, pos, ax=ax, alpha=.05, width=.5)
    scat = ax.scatter([pos[n][0] for n in nodes], [pos[n][1] for n in nodes],
                      s=26, c=colours_at(0), zorder=3, linewidths=0)
    ax.set_axis_off()
    title = ax.set_title("")

    def update(i):
        scat.set_color(colours_at(i))
        scat.set_sizes(sizes_at(i))
        n_ad = sum(1 for n in nodes if adopt_t.get(n) is not None
                   and adopt_t[n] <= cuts[i])
        title.set_text(f"{opening} as {colour}  |  {cuts[i]:%d %b %H:%M}  |  "
                       f"{n_ad}/{len(nodes)} playing it")
        return scat, title

    anim = FuncAnimation(fig, update, frames=len(cuts), blit=False)
    anim.save(out_gif, writer=PillowWriter(fps=6))
    plt.close(fig)

    # static small multiples for the written report
    picks = [0, len(cuts) // 3, 2 * len(cuts) // 3, len(cuts) - 1]
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.8))
    for ax, i in zip(axes, picks):
        nx.draw_networkx_edges(g, pos, ax=ax, alpha=.05, width=.4)
        ax.scatter([pos[n][0] for n in nodes], [pos[n][1] for n in nodes],
                   s=18, c=colours_at(i), zorder=3, linewidths=0)
        n_ad = sum(1 for n in nodes if adopt_t.get(n) is not None
                   and adopt_t[n] <= cuts[i])
        ax.set_title(f"{cuts[i]:%d %b}  ({n_ad} adopters)", fontsize=10)
        ax.set_axis_off()
    fig.suptitle(f"Diffusion of {opening} played as {colour}", y=1.02)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"behaviour": f"{opening}/{colour}", "gif": out_gif, "panels": out_png,
            "nodes_drawn": len(nodes), "adopters": len(adopt_t)}


def run(games_path: Path):
    return animate(parse.load_games(games_path))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))
    a = ap.parse_args()
    print(run(Path(a.games)))
