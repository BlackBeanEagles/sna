"""Draw the methodology workflow figure for the proposal.

The proposal template leaves a placeholder box for a workflow diagram. This
renders the real pipeline as a PNG that \\includegraphics can pick up, so the
preamble in Sample.tex does not have to change (graphicx is already loaded).

    python scripts/make_workflow_figure.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INK = "#1a1722"
MUTED = "#5c5670"
BOXES = {
    "data": "#eceaf4",
    "build": "#e4eef0",
    "test": "#f5e9e7",
    "out": "#efeadf",
}

# Laid out as a serpentine: each row runs in the opposite direction to the one
# above it, so every edge joins neighbouring boxes and none has to cut across
# the figure -- or through another box -- to reach its target.
ROW_A, ROW_B, ROW_C, ROW_D, ROW_E = 0.82, 0.615, 0.41, 0.205, 0.0
W, H = 0.215, 0.125
COL = [0.02, 0.27, 0.52, 0.77]

# (x, y, w, h, label, kind)
NODES = [
    # row A, left to right
    (COL[0], ROW_A, W, H, "Lichess monthly\narchive (.pgn.zst)", "data"),
    (COL[1], ROW_A, W, H, "Filter: rating band,\ntime control, top ECO", "data"),
    (COL[2], ROW_A, W, H, "Parse to temporal\nedge list", "data"),
    (COL[3], ROW_A, W, H, "Player interaction\nnetwork G = (V, E, T)", "build"),

    # row B, right to left
    (COL[3], ROW_B, W, H, "Exposure events\nA plays X against B", "build"),
    (COL[2], ROW_B, W, H, "Adoption events\nB first plays X", "build"),
    (COL[1], ROW_B, W, H, "Exposure neighbourhood\nper (player, opening)", "build"),
    (COL[0], ROW_B, W, H, "Structural diversity\n(components)", "build"),

    # row C
    (COL[0], ROW_C, W, H, "Adoption-probability\ncurve  P(adopt | k, d)", "build"),
    (COL[3], ROW_C, W, H, "Centrality, communities,\ndiffusion animation", "out"),

    # row D, the three validity checks
    (COL[0], ROW_D, W, H, "Shuffled-time\nnull model", "test"),
    (COL[1], ROW_D, W, H, "Rating & activity\nmatched controls", "test"),
    (COL[2], ROW_D, W, H, "Held-out\npredictive AUC", "test"),

    # row E, the verdict
    (COL[1], ROW_E, W, H, "Simple vs complex\ncontagion verdict", "out"),
]

EDGES = [
    (0, 1), (1, 2), (2, 3),          # row A
    (3, 4),                          # A -> B, straight down the right edge
    (4, 5), (5, 6), (6, 7),          # row B, leftwards
    (7, 8),                          # B -> C, straight down the left edge
    (8, 10), (8, 11), (8, 12),       # the curve feeds each validity check
    (10, 13), (11, 13), (12, 13),    # the checks converge on the verdict
]

# The network also drives the structural work, but that box sits two rows down
# in the same column, so a straight drop would run through the row between.
# This one edge is routed out around the right margin instead.
MARGIN_EDGES = [(3, 9)]


def main():
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    ax.set_xlim(0, 1.06)
    ax.set_ylim(-0.03, 0.98)
    ax.axis("off")

    centres = []
    for x, y, w, h, label, kind in NODES:
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
            linewidth=0.9, edgecolor="#b9b3c9", facecolor=BOXES[kind]))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                fontsize=8.4, color=INK, linespacing=1.45)
        centres.append((x + w / 2, y + h / 2, w, h))

    for a, b in EDGES:
        x0, y0, w0, h0 = centres[a]
        x1, y1, w1, h1 = centres[b]
        if abs(y0 - y1) < 1e-6:           # neighbours: leave from the facing sides
            sx = x0 + (w0 / 2 if x1 > x0 else -w0 / 2)
            ex = x1 - (w1 / 2 if x1 > x0 else -w1 / 2)
            start, end, rad = (sx, y0), (ex, y1), 0.0
        else:                             # drop to the row below
            start = (x0, y0 - h0 / 2)
            end = (x1, y1 + h1 / 2)
            rad = 0.0 if abs(x0 - x1) < 1e-6 else 0.06
        ax.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=9,
            linewidth=0.9, color=MUTED, shrinkA=1, shrinkB=3,
            connectionstyle=f"arc3,rad={rad}"))

    for a, b in MARGIN_EDGES:
        x0, y0, w0, h0 = centres[a]
        x1, y1, w1, h1 = centres[b]
        lane = max(x0 + w0 / 2, x1 + w1 / 2) + 0.035
        ax.plot([x0 + w0 / 2, lane, lane, x1 + w1 / 2],
                [y0, y0, y1, y1], color=MUTED, linewidth=0.9,
                solid_joinstyle="round", zorder=1)
        ax.add_patch(FancyArrowPatch(
            (lane, y1), (x1 + w1 / 2, y1), arrowstyle="-|>",
            mutation_scale=9, linewidth=0.9, color=MUTED, shrinkA=0, shrinkB=3))

    out = ROOT / "docs" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "methodology.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
