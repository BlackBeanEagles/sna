> **Historical, superseded.** This intermediate correction still used full-month rating and activity in matching and only three timestamp shuffles. See [current results](RESULTS.md).

# Corrected results — Lichess January 2016

This report uses the cached January 2016 game slice and the current analysis code. It was recomputed after requiring complete 14-day follow-up for **every** exposure trial and repairing the matched-control risk set. The source archive was not reparsed. The earlier report is preserved in [RESULTS_PRE_CORRECTION.md](RESULTS_PRE_CORRECTION.md); its numbers must not be cited as current.

## Sample and outcome

- 249,505 games, 6,881 players, 40 ECO codes, 1800–2200 Elo.
- 214,317 exposure trials with complete 14-day follow-up.
- 30,011 positive **trial rows**, a 14.00% trial adoption rate. A player-behaviour adoption may still appear in more than one trial row.

The previous analysis kept 9,650 late positive trials while dropping late negative trials. That raised the reported rate from 14.00% to 17.71%. [`src/events.py`](../src/events.py) now excludes both outcomes when the observation window extends past the archive.

## Exposure diversity and shuffled-time reference

| Distinct exposers, d | Complete trials | Observed adoption | Shuffled-time rate | Observed / reference |
|---:|---:|---:|---:|---:|
| 1 | 83,397 | 13.56% | 12.56% | 1.079 |
| 2 | 39,528 | 12.92% | 12.49% | 1.034 |
| 3 | 23,074 | 13.48% | 13.37% | 1.008 |
| 4 | 14,816 | 14.08% | 14.05% | 1.002 |
| 5 | 10,362 | 14.46% | 14.43% | 1.002 |
| 6+ | 43,140 | 16.01% | 16.48% | 0.971 |

The raw rate rises by 18.1% between the first and last buckets. The shuffled-time rate rises more. The excess above that reference declines from 1.079 to 0.971, and the fixed-exposure-count comparison does not show separation by distinct exposers. This is a **simple-contagion pattern**, meaning no clear evidence of reinforcement from additional distinct opponents in this sample. It is an observational comparison, not proof that the first encounter causes adoption.

The reference uses three timestamp permutations. Three replicates are too few for reliable tail probabilities; the ratio pattern is more defensible than treating the reported z-scores as formal significance tests. Trial rows are repeated within players and behaviours, so trial-level Wilson intervals are also optimistic. A one-row-per-spell sensitivity check yields 76,091 spells and 11,478 distinct adoptions; its observed/shuffled lift declines from **1.050** at one exposer to **0.928** at six or more. This preserves the direction of the main pattern while avoiding repeated trial rows. See [`null_comparison_perspell_last.csv`](../results/tables/null_comparison_perspell_last.csv).

## Matched controls

At each exposed spell's first encounter, eligible controls had **not yet** performed or encountered the target opening. Later exposure was recorded as a crossover instead of being used to select controls with knowledge of the future.

- 61,606 matched pairs.
- Exposed adoption: 13.41%; control adoption: 12.60%.
- Difference: **+0.82 percentage points**; descriptive paired interval **[+0.46, +1.17] points**.
- 17.84% of controls encounter the opening during follow-up.

The earlier +2.80-point estimate used an invalid control pool that included prior adopters and excluded people who would be exposed later. The corrected estimate remains associational. Matching still uses full-month rating and activity totals, and controls and exposed players can recur across pairs. The interval does not account for that clustering.

## Held-out prediction

A 14-day outcome window within a 31-day archive leaves too little time for a useful purged temporal train/test split. The revised check measures fixed background features before 4 January, then holds out entire player-opening-colour spells so one eventual adoption cannot appear in both sets.

| Model | Held-out AUC |
|---|---:|
| Popularity, rating, activity | 0.595 |
| + Repertoire proximity | 0.608 |
| + Exposure and network position | 0.633 |

There are 120,523 training and 50,929 test trials after the background period. Their positive rates are 12.66% and 12.96%. In separate additions to the repertoire model, total exposure count adds 0.024 AUC, distinct/structural diversity 0.007, and centrality 0.003. Training AUCs of 0.812–0.853 are much higher than test AUCs, so the model still overfits. These are predictive comparisons; they do not establish influence.

## Remaining work and provenance

- **Second-month replication:** not completed. The local connection presents an untrusted certificate for `database.lichess.org`; both Python and system curl reject it. Supply a verified downloaded archive or use a connection with a trusted certificate.
- **Archive reparse:** not completed for the same reason. The current results start from the cached game Parquet slice, which predates a parser fix.
- **Other robustness checks:** previous clipping, structural-diversity, ply and window CSVs are preserved under [`results/tables/legacy_pre_followup/`](../results/tables/legacy_pre_followup/) and are not current evidence. Rerun them with the corrected follow-up rule.
- **Causal identification:** opponent choice, repertoire, activity, and changing opening popularity can affect both exposure and adoption.

The current machine-readable report is [`results/report.json`](../results/report.json). The findings page is generated from it with `python site/build.py`.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.venv\Scripts\python.exe scripts\verify_published.py
.venv\Scripts\python.exe site\build.py
```

The tests cover exposure/adoption timing, complete follow-up, risk-set matching, grouped holdout, null propagation and verdict guards. The verification script rebuilds core January results from the cached slice; it does not reparse the archive or refit the predictive models.
