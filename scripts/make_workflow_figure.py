"""Draw the methodology workflow figure for the proposal.

The proposal template leaves a placeholder box for a workflow diagram. This
renders the real pipeline as a PNG that \\includegraphics can pick up, so the
preamble in Sample.tex does not have to change (graphicx is already loaded).

    python scripts/make_workflow_figure.py
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import sys  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import matplotlib  # Loads code this file needs for the steps below.
matplotlib.use("Agg")  # Runs this instruction as part of the current step.
import matplotlib.pyplot as plt  # Loads code this file needs for the steps below.
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # Loads code this file needs for the steps below.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
sys.path.insert(0, str(ROOT))  # Runs this instruction as part of the current step.

INK = "#1a1722"  # Saves a value named INK so the next lines can use it.
MUTED = "#5c5670"  # Saves a value named MUTED so the next lines can use it.
BOXES = {  # Saves a value named BOXES so the next lines can use it.
    "data": "#eceaf4",
    "build": "#e4eef0",
    "test": "#f5e9e7",
    "out": "#efeadf",
}  # Closes the data structure or function call started above.

# Laid out as a serpentine: each row runs in the opposite direction to the one
# above it, so every edge joins neighbouring boxes and none has to cut across
# the figure -- or through another box -- to reach its target.
ROW_A, ROW_B, ROW_C, ROW_D, ROW_E = 0.82, 0.615, 0.41, 0.205, 0.0  # Runs this instruction as part of the current step.
W, H = 0.215, 0.125  # Runs this instruction as part of the current step.
COL = [0.02, 0.27, 0.52, 0.77]  # Saves a value named COL so the next lines can use it.

# (x, y, w, h, label, kind)
NODES = [  # Saves a value named NODES so the next lines can use it.
    # row A, left to right
    (COL[0], ROW_A, W, H, "Lichess monthly\narchive (.pgn.zst)", "data"),  # Part of the value, collection, or call spanning several lines.
    (COL[1], ROW_A, W, H, "Filter: rating band,\ntime control, top ECO", "data"),  # Part of the value, collection, or call spanning several lines.
    (COL[2], ROW_A, W, H, "Parse to temporal\nedge list", "data"),  # Part of the value, collection, or call spanning several lines.
    (COL[3], ROW_A, W, H, "Player interaction\nnetwork G = (V, E, T)", "build"),  # Part of the value, collection, or call spanning several lines.

    # row B, right to left
    (COL[3], ROW_B, W, H, "Exposure events\nA plays X against B", "build"),  # Part of the value, collection, or call spanning several lines.
    (COL[2], ROW_B, W, H, "Adoption events\nB first plays X", "build"),  # Part of the value, collection, or call spanning several lines.
    (COL[1], ROW_B, W, H, "Exposure neighbourhood\nper (player, opening)", "build"),  # Part of the value, collection, or call spanning several lines.
    (COL[0], ROW_B, W, H, "Structural diversity\n(components)", "build"),  # Part of the value, collection, or call spanning several lines.

    # row C
    (COL[0], ROW_C, W, H, "Adoption-probability\ncurve  P(adopt | k, d)", "build"),  # Part of the value, collection, or call spanning several lines.
    (COL[3], ROW_C, W, H, "Centrality, communities,\ndiffusion animation", "out"),  # Part of the value, collection, or call spanning several lines.

    # row D, the three validity checks
    (COL[0], ROW_D, W, H, "Shuffled-time\nnull model", "test"),  # Part of the value, collection, or call spanning several lines.
    (COL[1], ROW_D, W, H, "Rating & activity\nmatched controls", "test"),  # Part of the value, collection, or call spanning several lines.
    (COL[2], ROW_D, W, H, "Held-out\npredictive AUC", "test"),  # Part of the value, collection, or call spanning several lines.

    # row E, the verdict
    (COL[1], ROW_E, W, H, "Simple vs complex\ncontagion verdict", "out"),  # Part of the value, collection, or call spanning several lines.
]  # Closes the data structure or function call started above.

EDGES = [  # Saves a value named EDGES so the next lines can use it.
    (0, 1), (1, 2), (2, 3),          # row A
    (3, 4),                          # A -> B, straight down the right edge
    (4, 5), (5, 6), (6, 7),          # row B, leftwards
    (7, 8),                          # B -> C, straight down the left edge
    (8, 10), (8, 11), (8, 12),       # the curve feeds each validity check
    (10, 13), (11, 13), (12, 13),    # the checks converge on the verdict
]  # Closes the data structure or function call started above.

# The network also drives the structural work, but that box sits two rows down
# in the same column, so a straight drop would run through the row between.
# This one edge is routed out around the right margin instead.
MARGIN_EDGES = [(3, 9)]  # Saves a value named MARGIN_EDGES so the next lines can use it.


def main():  # Draw the methodology flow used in the written project material.
    """Draw the methodology flow used in the written project material."""
    fig, ax = plt.subplots(figsize=(10.5, 6.2))  # Runs this instruction as part of the current step.
    ax.set_xlim(0, 1.06)  # Runs this instruction as part of the current step.
    ax.set_ylim(-0.03, 0.98)  # Runs this instruction as part of the current step.
    ax.axis("off")  # Runs this instruction as part of the current step.

    centres = []  # Saves a value named centres so the next lines can use it.
    for x, y, w, h, label, kind in NODES:  # Repeats the next indented steps once for each item.
        ax.add_patch(FancyBboxPatch(  # Part of the value, collection, or call spanning several lines.
            (x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",  # Part of the value, collection, or call spanning several lines.
            linewidth=0.9, edgecolor="#b9b3c9", facecolor=BOXES[kind]))  # Saves a value named linewidth so the next lines can use it.
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",  # Part of the value, collection, or call spanning several lines.
                fontsize=8.4, color=INK, linespacing=1.45)  # Saves a value named fontsize so the next lines can use it.
        centres.append((x + w / 2, y + h / 2, w, h))  # Adds this item to the list being built.

    for a, b in EDGES:  # Repeats the next indented steps once for each item.
        x0, y0, w0, h0 = centres[a]  # Runs this instruction as part of the current step.
        x1, y1, w1, h1 = centres[b]  # Runs this instruction as part of the current step.
        if abs(y0 - y1) < 1e-6:           # neighbours: leave from the facing sides
            sx = x0 + (w0 / 2 if x1 > x0 else -w0 / 2)  # Saves a value named sx so the next lines can use it.
            ex = x1 - (w1 / 2 if x1 > x0 else -w1 / 2)  # Saves a value named ex so the next lines can use it.
            start, end, rad = (sx, y0), (ex, y1), 0.0  # Runs this instruction as part of the current step.
        else:                             # drop to the row below
            start = (x0, y0 - h0 / 2)  # Saves a value named start so the next lines can use it.
            end = (x1, y1 + h1 / 2)  # Saves a value named end so the next lines can use it.
            rad = 0.0 if abs(x0 - x1) < 1e-6 else 0.06  # Saves a value named rad so the next lines can use it.
        ax.add_patch(FancyArrowPatch(  # Part of the value, collection, or call spanning several lines.
            start, end, arrowstyle="-|>", mutation_scale=9,  # Part of the value, collection, or call spanning several lines.
            linewidth=0.9, color=MUTED, shrinkA=1, shrinkB=3,  # Saves a value named linewidth so the next lines can use it.
            connectionstyle=f"arc3,rad={rad}"))  # Saves a value named connectionstyle so the next lines can use it.

    for a, b in MARGIN_EDGES:  # Repeats the next indented steps once for each item.
        x0, y0, w0, h0 = centres[a]  # Runs this instruction as part of the current step.
        x1, y1, w1, h1 = centres[b]  # Runs this instruction as part of the current step.
        lane = max(x0 + w0 / 2, x1 + w1 / 2) + 0.035  # Saves a value named lane so the next lines can use it.
        ax.plot([x0 + w0 / 2, lane, lane, x1 + w1 / 2],  # Part of the value, collection, or call spanning several lines.
                [y0, y0, y1, y1], color=MUTED, linewidth=0.9,  # Part of the value, collection, or call spanning several lines.
                solid_joinstyle="round", zorder=1)  # Saves a value named solid_joinstyle so the next lines can use it.
        ax.add_patch(FancyArrowPatch(  # Part of the value, collection, or call spanning several lines.
            (lane, y1), (x1 + w1 / 2, y1), arrowstyle="-|>",  # Part of the value, collection, or call spanning several lines.
            mutation_scale=9, linewidth=0.9, color=MUTED, shrinkA=0, shrinkB=3))  # Saves a value named mutation_scale so the next lines can use it.

    out = ROOT / "docs" / "figures"  # Stores the output value for the next step.
    out.mkdir(parents=True, exist_ok=True)  # Creates the folder needed for saved outputs.
    path = out / "methodology.png"  # Saves a value named path so the next lines can use it.
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")  # Runs this instruction as part of the current step.
    plt.close(fig)  # Runs this instruction as part of the current step.
    print(f"wrote {path}")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
