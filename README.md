# Openings as Contagion

Testing simple versus complex contagion in the diffusion of chess openings
across a player-interaction network. Implementation of the SNA research
proposal in `docs/SNA_Proposal.md`; build order follows `docs/Build_Guide.md`.

## The question in one line

When an opponent plays an opening against you, does one exposure suffice
(simple contagion), or does adoption require reinforcement from several
**structurally distinct** opponents (complex contagion)?

Chess is the rare setting where both sides of that question are directly
observed: exposure is forced (you had to answer the opening at the board)
and adoption is timestamped to the second (the first game you play it
yourself).

## Three ways to run it

| | what it is | how |
|---|---|---|
| **Live console** | Press a button and watch the whole pipeline execute on a real Lichess month — streaming, stage by stage, with a playable board. | `python server/app.py` → <http://localhost:8124> |
| **Findings page** | The static write-up of the result, with the charts. | `python -m http.server 8123 --directory site` → <http://localhost:8123> |
| **CLI** | What produced every number in the report. | `python -m src.run_pipeline --month 2016-01` |

### The live console

```bash
./.venv/Scripts/python.exe server/app.py --port 8124
```

Pick a month, a scan cap and the number of null replicates, then press **Run the
pipeline**. It streams the archive over HTTP, decompresses in flight, and runs
every stage in front of you — parse, trials, network, curve, shuffled-time null,
matched controls, verdict — with a live throughput sparkline, a game ticker, a
force-directed network, and the charts drawing themselves as each stage lands.

Two things worth knowing:

- **Parsed slices are cached** under `data/interim/slice_<month>_<cap>.parquet`.
  The first run of a month downloads; every run after that loads in a second or
  two. Tick **Force re-download** to prove it is really streaming. Lichess
  throttles repeated downloads, so the cache is what makes a live demo reliable.
- **The board is playable.** Two people alternate moves; every move is validated
  server-side by `python-chess` and matched against the loaded slice, so the
  opening, its share of games, its exposure trials and its adoption count update
  move by move — and the players in the network who *adopted* that opening light
  up. Use **3 null replicates** and the full month to reproduce the published
  numbers.

The console's `d`-curve, null overlay and verdict come from the same
`src/` modules the CLI uses. Nothing in it is simulated.

## Quick start

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt

# validation run: synthetic games with a KNOWN contagion rule planted in them
./.venv/Scripts/python.exe -m src.run_pipeline --simulate

# real data: stream a whole Lichess month straight into the analysis
# (nothing is written to disk -- the ~5 GB of PGN is decompressed on the fly)
./.venv/Scripts/python.exe -m src.run_pipeline --month 2016-01
```

Everything lands in `results/` — `report.json`, `tables/*.csv`,
`figures/adoption_curve.png`, `figures/diffusion.gif`.

## Modules

| file | build-guide step | what it does |
|---|---|---|
| `src/config.py` | — | every locked decision in one place |
| `src/fetch.py` | 1 | streams a slice of a 30 GB Lichess dump, stops early |
| `src/simulate.py` | 1 | synthetic PGN with a planted contagion rule — the pipeline's test |
| `src/parse.py` | 2 | PGN → one Parquet event table; nothing downstream re-reads PGN |
| `src/events.py` | 3–4 | exposure/adoption sweep, trial table, structural diversity |
| `src/structure.py` | 4 | graph, centrality, Louvain communities, early-adopter profile |
| `src/curve.py` | 5 | the adoption-probability curve and the simple/complex verdict |
| `src/nulls.py` | 6 | timestamp shuffling + degree-preserving rewiring |
| `src/matching.py` | 7a | rating-and-activity matched controls |
| `src/predict.py` | 7b | held-out AUC, network features vs baseline |
| `src/animate.py` | 8 | diffusion GIF + static panels for the report |
| `src/run_pipeline.py` | — | runs all of it, writes `results/report.json` |

## Definitions the code actually uses

**Behaviour** = `(opening, colour)`. Playing the Sicilian as Black and meeting
it as White are different behaviours; colour stays in the key throughout.

**One game** between white `u` and black `v` with opening `X` at time `t`
produces two performances and two exposures:

```
u performs (X, W)   ->   exposes v to (X, W)
v performs (X, B)   ->   exposes u to (X, B)
```

**Adoption** of behaviour `b` by player `p` = the first time `p` performs `b`.

**Trial** — the unit of analysis. One row per `(player, behaviour, k-th
exposure)` for which the player had not yet performed the behaviour:

- `k` — cumulative exposure events so far
- `d` — distinct exposing opponents so far
- `sd` — structural diversity: connected components of the subgraph induced
  on those `d` exposers, counting only edges that already existed at `t_k`
  (Ugander et al. 2012)
- `adopted` — 1 if the player first performs `b` within 14 days

Trials whose 14-day window runs past the end of the observation period are
censored out unless adoption already happened inside it.

**The decisive comparison** is `k` held fixed while `d` varies. A rising
`d`-curve on its own is not evidence of complex contagion — see below.

## Identification: why the raw curve is not enough

A player who plays 500 games a month is exposed to more of everything and
adopts more of everything. So the raw `d`-curve rises even with no influence
at all. Three checks separate influence from that:

1. **Timestamp-shuffled null.** Permuting timestamps keeps degree, ratings and
   opening popularity exactly as they are but destroys causal ordering.
   On the synthetic runs this null *also* produces a rising `d`-curve — which
   is the point: the real effect has to clear the null, not merely rise.
2. **Matched controls.** Each exposed `(player, behaviour)` is matched to an
   unexposed player within ±50 rating points and ±25% games played, over the
   same window. This also absorbs external shocks — a tournament broadcast
   lifts exposed and unexposed alike.
3. **Held-out AUC.** Train on the first 70% of the period, score on the later
   30%. Network features (`k`, `d`, `sd`, centrality) against a baseline of
   opening popularity + rating + activity.

## Locked decisions

Set in `src/config.py`, all changeable in one place:

- rating band 1800–2200; Blitz/Rapid/Classical; top 40 ECO codes
- `OPENING_GRANULARITY = "eco"` for the main analysis, `"ply"` (first 8 plies)
  as a robustness check
- 14-day adoption window
- players with fewer than 20 games dropped — their adoption timing is noise
- `k` reported to 8, `d`/`sd` to 6

## Data

Lichess open database, <https://database.lichess.org> — monthly PGN archives,
permissive licence, persistent player names, exact timestamps, ratings, full
move lists. `src/fetch.py` streams and decompresses on the fly and stops once
it has enough games, so a 200k-game slice costs a few hundred MB of transfer
rather than the full 30 GB.

## Status

Complete. Run on the full Lichess 2016-01 month: 249,505 games, 6,881 players,
223,967 trials. **Verdict: simple contagion, not complex** — see
[docs/RESULTS.md](docs/RESULTS.md) for the numbers.

The raw d-curve rises (0.159 -> 0.227) but the timestamp-shuffled null rises
just as fast, and the excess over the null decays to zero as d grows. Matched
controls show a real but modest exposure effect: +3.0 pp, 95% CI [2.64, 3.36].
The held-out AUC check was inconclusive (gain +0.003, both models near chance).

Data and results live outside the repo:

```bash
export SNA_DATA_ROOT='E:\sna_data'      # or set SNA_DATA_ROOT=E:\sna_data on cmd
./.venv/Scripts/python.exe -m src.run_pipeline --month 2016-01
```

Robustness checks that have been run (see [docs/RESULTS.md](docs/RESULTS.md)):

- **d-cap** — unclipping the top bucket to d = 12 leaves the decay intact, so
  the convergence is not an artefact of lumping the tail (`scripts/check_clipping.py`).
- **Structural diversity** — Ugander's components-of-the-exposure-subgraph
  measure gives the same verdict as raw exposer count (`scripts/check_diversity.py`).
- **Ply granularity** — behaviours keyed by the first 8 plies instead of ECO
  code give the same verdict (`scripts/check_ply.py`).
- **Trial independence** — one row per player-behaviour spell instead of one
  per exposure. The verdict survives; the z-scores fall two- to four-fold, so
  the published intervals are optimistic (`scripts/check_independence.py`).
- **Adoption window** — 7, 14 and 28 days all give the same verdict
  (`scripts/check_window.py`).

Tests: `python -m pytest tests -q` (16 tests over the exposure/adoption core,
the null model and the verdict logic).

Still open: replication on a second month.
