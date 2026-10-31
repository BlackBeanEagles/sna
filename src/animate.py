"""Step 8 -- animated diffusion of one opening across the player network.

The demo, not the result. Picks the opening with the most adoptions, lays
the interaction graph out once, then walks forward in time colouring nodes
as they adopt. Writes a GIF plus a static small-multiple panel for the
report (GIFs do not paste into a PDF).
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
from pathlib import Path  # Loads Path to find and save project files.

import matplotlib  # Loads code this file needs for the steps below.
matplotlib.use("Agg")  # Runs this instruction as part of the current step.
import matplotlib.pyplot as plt  # Loads code this file needs for the steps below.
import networkx as nx  # Loads the library used to build and measure player links.
import pandas as pd  # Loads the table library used to store games and trials.
from matplotlib.animation import FuncAnimation, PillowWriter  # Loads code this file needs for the steps below.

from . import config, events, parse, structure  # Loads the named parts of this project so this file can use their functions.

UNADOPTED = "#d9d9d9"  # Saves a value named UNADOPTED so the next lines can use it.
ADOPTED = "#c2185b"  # Saves a value named ADOPTED so the next lines can use it.
NEW = "#f9a825"  # Saves a value named NEW so the next lines can use it.


def pick_behaviour(df: pd.DataFrame):  # Defines a reusable step; the following indented lines are its body.
    _, first_perf, _ = events.sweep(df)  # Runs this instruction as part of the current step.
    rows = [(p, beh[0], beh[1], t) for (p, beh), t in first_perf.items()]  # Stores the result rows collected for the output table for the next step.
    fp = pd.DataFrame(rows, columns=["player", "opening", "colour", "t"])  # Creates a labelled table from the collected rows.
    best = fp.groupby(["opening", "colour"]).size().idxmax()  # Groups rows sharing these keys before counting or averaging them.
    sel = fp[(fp["opening"] == best[0]) & (fp["colour"] == best[1])]  # Saves a value named sel so the next lines can use it.
    return best, sel.sort_values("t")  # Orders the rows by this field before the next calculation.


def animate(df: pd.DataFrame, out_gif: Path = None, out_png: Path = None,  # Draw first use of one opening over time on a network subset.
            frames: int = 40, max_nodes: int = 400):  # Saves a value named frames so the next lines can use it.
    """Draw first use of one opening over time on a network subset.

    The animation explains the idea of diffusion visually. The trial curves
    and reference checks, rather than this picture, carry the study finding.
    """
    out_gif = out_gif or (config.FIGURES / "diffusion.gif")  # Saves a value named out_gif so the next lines can use it.
    out_png = out_png or (config.FIGURES / "diffusion_panels.png")  # Saves a value named out_png so the next lines can use it.

    g = structure.build_graph(df)  # Connects players who faced each other in the selected games.
    if g.number_of_nodes() > max_nodes:  # Runs the next indented steps only when this condition is true.
        keep = [n for n, _ in sorted(g.degree(), key=lambda x: -x[1])[:max_nodes]]  # Saves a value named keep so the next lines can use it.
        g = g.subgraph(keep).copy()  # Stores the player graph for the next step.
    (opening, colour), adopters = pick_behaviour(df)  # Part of the value, collection, or call spanning several lines.
    adopters = adopters[adopters["player"].isin(g.nodes())]  # Saves a value named adopters so the next lines can use it.

    pos = nx.spring_layout(g, seed=config.RANDOM_SEED, k=1.6 / (g.number_of_nodes() ** .5))  # Saves a value named pos so the next lines can use it.
    t0, t1 = df["ts"].min(), df["ts"].max()  # Runs this instruction as part of the current step.
    cuts = pd.date_range(t0, t1, periods=frames)  # Saves a value named cuts so the next lines can use it.
    nodes = list(g.nodes())  # Saves a value named nodes so the next lines can use it.
    adopt_t = dict(zip(adopters["player"], adopters["t"]))  # Saves a value named adopt_t so the next lines can use it.

    def colours_at(i):  # Defines a reusable step; the following indented lines are its body.
        cut, prev = cuts[i], cuts[max(i - 1, 0)]  # Runs this instruction as part of the current step.
        out = []  # Stores the output value for the next step.
        for n in nodes:  # Repeats the next indented steps once for each item.
            t = adopt_t.get(n)  # Saves a temporary value used by the next calculation.
            if t is None or t > cut:  # Runs the next indented steps only when this condition is true.
                out.append(UNADOPTED)  # Adds this item to the list being built.
            elif t > prev:  # Runs the next indented steps only when this condition is true.
                out.append(NEW)  # Adds this item to the list being built.
            else:  # Handles the alternative when the preceding condition was false.
                out.append(ADOPTED)  # Adds this item to the list being built.
        return out  # Gives this answer back to the code that called the function.

    def sizes_at(i):  # Defines a reusable step; the following indented lines are its body.
        return [70 if c == NEW else 26 for c in colours_at(i)]  # Gives this answer back to the code that called the function.

    fig, ax = plt.subplots(figsize=(7.5, 7.5))  # Runs this instruction as part of the current step.
    nx.draw_networkx_edges(g, pos, ax=ax, alpha=.05, width=.5)  # Runs this instruction as part of the current step.
    scat = ax.scatter([pos[n][0] for n in nodes], [pos[n][1] for n in nodes],  # Saves a value named scat so the next lines can use it.
                      s=26, c=colours_at(0), zorder=3, linewidths=0)  # Saves a value named s so the next lines can use it.
    ax.set_axis_off()  # Runs this instruction as part of the current step.
    title = ax.set_title("")  # Saves a value named title so the next lines can use it.

    def update(i):  # Defines a reusable step; the following indented lines are its body.
        scat.set_color(colours_at(i))  # Runs this instruction as part of the current step.
        scat.set_sizes(sizes_at(i))  # Runs this instruction as part of the current step.
        n_ad = sum(1 for n in nodes if adopt_t.get(n) is not None  # Saves a value named n_ad so the next lines can use it.
                   and adopt_t[n] <= cuts[i])  # Runs this instruction as part of the current step.
        title.set_text(f"{opening} as {colour}  |  {cuts[i]:%d %b %H:%M}  |  "  # Runs this instruction as part of the current step.
                       f"{n_ad}/{len(nodes)} playing it")  # Runs this instruction as part of the current step.
        return scat, title  # Gives this answer back to the code that called the function.

    anim = FuncAnimation(fig, update, frames=len(cuts), blit=False)  # Saves a value named anim so the next lines can use it.
    anim.save(out_gif, writer=PillowWriter(fps=6))  # Runs this instruction as part of the current step.
    plt.close(fig)  # Runs this instruction as part of the current step.

    # static small multiples for the written report
    picks = [0, len(cuts) // 3, 2 * len(cuts) // 3, len(cuts) - 1]  # Saves a value named picks so the next lines can use it.
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.8))  # Runs this instruction as part of the current step.
    for ax, i in zip(axes, picks):  # Repeats the next indented steps once for each item.
        nx.draw_networkx_edges(g, pos, ax=ax, alpha=.05, width=.4)  # Runs this instruction as part of the current step.
        ax.scatter([pos[n][0] for n in nodes], [pos[n][1] for n in nodes],  # Part of the value, collection, or call spanning several lines.
                   s=18, c=colours_at(i), zorder=3, linewidths=0)  # Saves a value named s so the next lines can use it.
        n_ad = sum(1 for n in nodes if adopt_t.get(n) is not None  # Saves a value named n_ad so the next lines can use it.
                   and adopt_t[n] <= cuts[i])  # Runs this instruction as part of the current step.
        ax.set_title(f"{cuts[i]:%d %b}  ({n_ad} adopters)", fontsize=10)  # Runs this instruction as part of the current step.
        ax.set_axis_off()  # Runs this instruction as part of the current step.
    fig.suptitle(f"Diffusion of {opening} played as {colour}", y=1.02)  # Runs this instruction as part of the current step.
    fig.tight_layout()  # Runs this instruction as part of the current step.
    fig.savefig(out_png, dpi=150, bbox_inches="tight")  # Runs this instruction as part of the current step.
    plt.close(fig)  # Runs this instruction as part of the current step.
    return {"behaviour": f"{opening}/{colour}", "gif": out_gif, "panels": out_png,  # Gives this answer back to the code that called the function.
            "nodes_drawn": len(nodes), "adopters": len(adopt_t)}


def run(games_path: Path):  # Defines a reusable step; the following indented lines are its body.
    return animate(parse.load_games(games_path))  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    print(run(Path(a.games)))  # Prints this reading so a command-line run can be followed.
