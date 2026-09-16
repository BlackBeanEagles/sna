# Build Guide — Chess Opening Contagion (SNA Project)

Working notes for implementation. Not part of the proposal submission.

## Build order

**Step 1 — get a small slice of data first.** Do not download a full month before you know your parser works. Take a few thousand games, get the whole pipeline running end to end on that, then scale up. The full dumps are very large and a broken pipeline on 30 GB wastes days.

**Step 2 — parse into an event table.** Use `python-chess` to read PGN. For each game emit one row: `white_id, black_id, timestamp, eco, first_k_plies, white_rating, black_rating, result`. Write it to Parquet. Everything downstream reads this table, never the PGN again.

**Step 3 — build exposure and adoption logs.** Sort by timestamp and sweep once through the table. Maintain, per `(player, opening, colour)`, the set of opponents who have played it against them and the first time the player played it themselves. One pass, dictionary of sets — no graph library needed yet.

**Step 4 — build the graph.** NetworkX is fine at this scale; switch to `igraph` or `graph-tool` if it drags. You only need the graph for the structural-diversity measure (components of the exposure subgraph) and for centrality.

**Step 5 — the core curve.** Group by `(k exposures, d distinct exposers)` and compute adoption rate within a fixed window. Hold `k` fixed and vary `d` — that comparison is the whole project. Plot it with confidence intervals.

**Step 6 — the null model.** Shuffle timestamps, re-run steps 3–5. This is a loop over the same functions, so write steps 3–5 as functions from the start.

**Step 7 — matched controls and the predictive check.** Both are straightforward once the event table exists.

**Step 8 — the animation.** Last, not first. It is the demo, not the result.

## Decisions to lock early

- **Opening granularity.** ECO code alone is coarse (many distinct ideas share a code). First 6–10 plies is sharper but fragments the data. Suggestion: run the main analysis at ECO level, report a robustness check at ply level.
- **Colour matters.** Playing the Sicilian as Black and meeting it as White are different behaviours. Keep colour in the key throughout, or the adoption definition becomes meaningless.
- **Adoption window.** Pick a fixed window (e.g. 14 days after exposure) and state it; otherwise heavy players appear to adopt more simply because they play more.
- **Activity confound.** A player who plays 500 games a month is exposed to more of everything and adopts more of everything. Normalise by games played, and include activity in the matching.
- **Minimum activity filter.** Drop players with very few games — their adoption timing is noise.

## Things an examiner will ask

- *How do you know they didn't just watch a tournament broadcast?* — External shocks hit everyone at once, so they inflate the baseline equally for exposed and unexposed players. The matched design absorbs this. Mention it before they ask.
- *Isn't rating a confound?* — Yes, which is why it is in the matching and in the null.
- *Why is this a network problem and not a statistics problem?* — Because the key predictor (structural diversity of the exposure neighbourhood) is only definable on the graph.

## Resources

- Lichess open database: https://database.lichess.org
- `python-chess` for PGN parsing
- NetworkX / igraph for the graph work
- Reference implementations worth reading: the structural-diversity measure in [2]
