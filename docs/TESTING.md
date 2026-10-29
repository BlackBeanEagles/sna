# Verification

The published January analysis starts from the cached 249,505-game slice. Its source PGN has not been reparsed.

## Regression and report checks

```powershell
.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.venv\Scripts\python.exe scripts\verify_published.py
```

Expected: **26 tests pass** and all checked report metrics match. The verifier rebuilds complete trials, the curve, **20** timestamp shuffles, matching and the verdict. It does not reparse the archive or refit prediction.

| Measure | Current value |
|---|---:|
| Complete exposure trials | 214,317 |
| Positive trial rows | 30,011 |
| Trial adoption rate | 14.00% |
| Observed / shuffled rate at d = 1 | 1.084 |
| Observed / shuffled rate at d ≥ 6 | 0.959 |
| Matched pairs | 56,459 |
| Matched adoption difference | +2.55 percentage points |
| Player-cluster bootstrap interval | [+1.82, +3.13] points |
| Control crossover during follow-up | 16.16% |
| Group-held-out AUC, baseline / repertoire / network | 0.595 / 0.608 / 0.633 |

## One-row-per-spell sensitivity

```powershell
.venv\Scripts\python.exe scripts\check_independence.py --reps 3 --how last
```

Expected: 76,091 spells and 11,478 distinct adoption events. The observed/shuffled lift falls from 1.050 at d=1 to 0.928 at d≥6. This sensitivity run uses only three shuffles; avoid formal tail-probability claims.

## Frontend checks

Run `python server/app.py` and open <http://localhost:8124>. The console should show an eight-stage rail and **Recent runs**. Start a cached January full-month run; progress should appear in that panel. Reload the browser: selecting the saved run should replay the event log. If the server interrupts the worker, **Retry** should restart that run from its cached slice.

Open **Read the corrected findings**. The page should show 214,317 complete trials, 14.0% trial adoption, 1.084× at the first distinct exposer, 0.959× at six or more, and +2.55 points for matching. Select B20 / Black: the chart should use only 3,642 complete trials, disable the shuffled reference and show descriptive error bars. CSV and SVG buttons should export the selected view. Check narrow and wide viewports.

## Archive limitation

A fresh parse and second-month replication require a verified archive download. This connection presents an untrusted certificate for `database.lichess.org`; Python and system curl reject it. Use a trusted connection or a verified local archive rather than disabling certificate validation.
