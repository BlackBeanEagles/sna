# Chess Openings As Contagion

Testing simple versus complex contagion in the diffusion of chess openings
across a player-interaction network. Implementation of the SNA research
proposal in `docs/SNA_Proposal.md`; build order follows `docs/Build_Guide.md`.

## The question in one line

When an opponent plays an opening against you, does one exposure suffice
(simple contagion), or does adoption require reinforcement from several
**structurally distinct** opponents (complex contagion)?

The game record timestamps encounters with an opening and the first later
game in which a player uses that opening. These are observational signals:
players and opponents choose moves, so an encounter is not randomized.

## Project report

The template-based Word report, with methodology diagrams and corrected result graphs, is in [`docs/Chess_Openings_As_Contagion_Project_Report.docx`](docs/Chess_Openings_As_Contagion_Project_Report.docx). The cover has placeholders for the student, guide and institution details to be filled before submission.

## Three ways to run it

| | what it is | how |
|---|---|---|
| **Live console** | Press a button and watch the whole pipeline execute on a real Lichess month — streaming, stage by stage, with a playable board. | `python server/app.py` → <http://localhost:8124> |
| **Findings page** | The static write-up of the result, with the charts. | `python -m http.server 8123 --directory site` → <http://localhost:8123> |
| **CLI** | Run the complete pipeline on a chosen archive. | `python -m src.run_pipeline --month 2016-01` |

### The live console

```bash
./.venv/Scripts/python.exe server/app.py --port 8124
```

Pick a month, a scan cap and the number of null replicates, then press **Run the
pipeline**. It streams the archive over HTTPS, decompresses in flight, and runs
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
  up. Use **20 null replicates** and the full month to reproduce the published
  reference; three is a quicker exploratory check.

The console's `d`-curve, null overlay and verdict come from the same
`src/` modules the CLI uses. Nothing in it is simulated. **Recent runs**
replays saved settings and progress after a page reload; **Retry** restarts an
interrupted run from its cached slice.

For a classroom presentation, leave **January 2016 · quick live demo** selected
and click **Run analysis**. The project recomputes every analysis stage from a
bundled 60,000-game sample of real January 2016 games. It needs no archive
download. Allow a few minutes for the verdict, then try a line on the playable
board and open **Findings**. The quick run uses one timing shuffle and is
exploratory; the published findings use all 249,505 filtered January games and
20 shuffles.

The deck, with 12 content slides plus a cover and speaker notes, is in
[`docs/Chess_Opening_Contagion_Presentation.pptx`](docs/Chess_Opening_Contagion_Presentation.pptx).

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
| `src/fetch.py` | 1 | how a month maps to an archive URL |
| `src/simulate.py` | 1 | synthetic PGN with a planted contagion rule — the pipeline's test |
| `src/parse.py` | 2 | PGN → one Parquet event table; nothing downstream re-reads PGN |
| `src/events.py` | 3–4 | exposure/adoption sweep, trial table, structural diversity |
| `src/structure.py` | 4 | graph, centrality, Louvain communities, early-adopter profile |
| `src/curve.py` | 5 | the adoption-probability curve and the simple/complex verdict |
| `src/nulls.py` | 6 | timestamp shuffling and degree-preserving rewiring (`--null-kind`) |
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
excluded regardless of whether adoption was observed. Every included trial
has the same complete follow-up.

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
2. **Matched controls.** Each exposed `(player, behaviour)` is matched to a
   player who has neither encountered nor played the target opening at the
   matching time, within ±50 rating points and ±25% games played. Later control
   exposure is recorded as crossover. This is an observational association.
3. **Held-out AUC.** Fixed background features are measured before evaluated
   trials, and entire player-opening-colour spells are held out together.
   Three nested models compare popularity/rating/activity, repertoire
   proximity, and exposure/network position without sharing an adoption event
   across train and test rows.

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
CC0, persistent player names, exact timestamps, ratings, full move lists.
`src/parse.py` opens the remote `.pgn.zst` directly and decompresses as it
reads, so the ~5 GB of PGN is never written to disk and a capped scan stops
without fetching the rest.

## Status

The corrected January 2016 analysis uses 249,505 games and 6,881 players.
Complete 14-day follow-up leaves **214,317 trial rows**, with a 14.00% trial
adoption rate. In 20 timestamp shuffles, observed/reference lift falls from
**1.084× at one distinct exposer to 0.959× at six or more**. This is a
simple-contagion *pattern* without clear reinforcement in this sample; it is
not a causal estimate.

Matching on rating and activity measured before each exposure yields
**+2.55 percentage points** (12.97% vs 10.42%, 56,459 pairs). A 400-replicate
player-cluster bootstrap gives a descriptive interval of [+1.82, +3.13]
points. The group-held-out prediction AUCs are 0.595 baseline, 0.608 with
repertoire proximity, and 0.633 with network features. See
[docs/RESULTS.md](docs/RESULTS.md) for limitations and provenance.

The findings page filters the observed curve by opening and colour, shows
sample sizes and descriptive intervals, and exports the selected CSV or SVG.
Filtered curves have no shuffled-time reference yet.

Tests: `python -m pytest tests -q -p no:cacheprovider` (26 passing tests).
`python scripts/verify_published.py` checks the core report from the cached
January slice. The source archive has not been reparsed, and a second month
remains blocked by the connection's untrusted archive certificate. The
one-row-per-spell check preserves the direction of the curve. Older robustness
tables under `results/tables/legacy_pre_followup/` are historical evidence.

To view both frontends locally, run `python server/app.py` and open
<http://localhost:8124>. The **Read the corrected findings** link opens the
report page from that same server. Alternatively, run `python site/build.py`
and serve `site/` as static files. Edit `site/page.html` and `site/style.css`, then rebuild to refresh the generated `site/index.html`.
