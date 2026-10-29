# Current results — Lichess January 2016

This analysis uses the cached 249,505-game January 2016 slice. The source archive has not been reparsed. A fresh parse and second-month replication still require a verified archive connection. [Earlier results](RESULTS_PRE_CORRECTION.md) and the [intermediate correction](RESULTS_PRE_PREEXPOSURE.md) are preserved for provenance.

## Sample

- 249,505 games, 6,881 players, 40 ECO codes in the 1800–2200 Elo band.
- 214,317 exposure trials with complete 14-day follow-up.
- 30,011 positive trial rows: a 14.00% rate. One eventual adoption can appear in several exposure trials.

Late positive and negative trials are both excluded. Earlier outcome-dependent censoring inflated the reported rate.

## Exposure curve and shuffled-time reference

| Distinct exposers | Complete trials | Observed rate | 20-shuffle reference | Observed / reference |
|---:|---:|---:|---:|---:|
| 1 | 83,397 | 13.56% | 12.50% | 1.084 |
| 2 | 39,528 | 12.92% | 12.44% | 1.038 |
| 3 | 23,074 | 13.48% | 13.22% | 1.019 |
| 4 | 14,816 | 14.08% | 13.84% | 1.017 |
| 5 | 10,362 | 14.46% | 14.41% | 1.003 |
| 6+ | 43,140 | 16.01% | 16.68% | 0.959 |

The raw rate rises with distinct opponents, but the excess above the shuffled-time reference declines from 1.084 to 0.959. The fixed-exposure-count comparison also shows no clear separation by distinct opponents. This is a **simple-contagion pattern**, a descriptive association without clear reinforcement. It does not establish that an encounter caused adoption.

Twenty permutations stabilize the reference mean compared with the earlier three, but they are still too few for precise tail probabilities. Repeated trial rows make trial-level Wilson intervals optimistic. A one-row-per-player-opening-spell sensitivity check yields 76,091 spells and 11,478 distinct adoptions; its observed/reference lift falls from 1.050 to 0.928. That check used three shuffles and supports direction, not formal significance. See [the per-spell table](../results/tables/null_comparison_perspell_last.csv).

## Matched comparison

For each exposed spell, the control had neither played nor encountered the opening at the match time. Both players' rating and activity are calculated **strictly from earlier games**. Controls exposed later remain in the analysis, with crossover recorded.

- 56,459 pairs; exposed adoption 12.97%, control adoption 10.42%.
- Difference **+2.55 percentage points**.
- Descriptive 95% player-cluster bootstrap interval **[+1.82, +3.13] points**, using 400 Poisson bootstrap replicates and weighting both players in each pair.
- 16.16% of controls were exposed during follow-up.
- Mean pre-match rating: exposed 1936.8, control 1935.4. Mean pre-match games: 18.4 and 17.6.

The matched difference changed from +0.82 points after removing full-month covariates. This is still an observational contrast: opponent choice, existing repertoire and opening popularity can influence both exposure and adoption. The initial 20-game player inclusion filter was defined using the full cached month, and multiple pairs share players. The bootstrap addresses repeated player IDs in the interval but does not remove confounding or account for every source of dependence.

## Held-out prediction

Fixed background features are measured before evaluated trials. Entire player-opening-colour spells are held out together.

| Model | Held-out AUC |
|---|---:|
| Popularity, rating, activity | 0.595 |
| + Repertoire proximity | 0.608 |
| + Exposure and network position | 0.633 |

There are 120,523 training and 50,929 test trials. Training AUCs of 0.812–0.853 versus lower test AUCs show overfitting. The model comparisons describe predictive value, not influence.

## Frontend and run records

The findings page supports opening and colour filters, trial counts, descriptive Wilson error bars, CSV export and SVG chart export. Filtered subsets show observed rates only; the shuffled reference has not been computed per subset.

The live console stores each run's settings and event history under `results/runs/`. A separate worker writes progress there, so a page reload can replay it. If a server restart interrupts the worker in this environment, **Retry** restarts that run from the cached slice. It does not resume a partially completed statistical stage.

## Remaining work

- A second archive month and fresh parse remain blocked because the local connection presents an untrusted certificate for `database.lichess.org`. Use a connection with a trusted certificate or a verified local archive.
- Earlier clipping, structural-diversity, ply and window checks under [legacy tables](../results/tables/legacy_pre_followup/) predate the complete-follow-up correction and are not current evidence.
- The shuffled null preserves several game-level margins but does not resolve opponent selection or changing popularity. The reported verdict remains associational.

Machine-readable outputs are in [report.json](../results/report.json), [matched_controls.csv](../results/tables/matched_controls.csv), [null_comparison.csv](../results/tables/null_comparison.csv) and [explorer_by_opening_colour.csv](../results/tables/explorer_by_opening_colour.csv).
