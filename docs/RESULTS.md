# Results — Lichess 2016-01

Run: full month streamed from `database.lichess.org`, 33 min end to end.
Raw outputs: `E:\sna_data\results\` (`report.json`, `tables/*.csv`, `figures/`).

## Sample

| | |
|---|---|
| Games scanned | 4,997,000 (full month) |
| Games kept | **249,505** |
| Players | **6,881** |
| Openings (ECO) | 40 |
| Span | 2015-12-31 23:00 – 2016-01-31 22:59 |
| Trials | 223,967 |
| Adoptions | 39,661 (17.71%) |

Attrition: 2,587,133 games lost to the 1800–2200 band (applied to *both*
players), 1,643,553 to time control, 224,268 to rare ECO codes, 64,896 to the
≥20-games activity filter. The surviving 6,881 players is an order of
magnitude below the 10⁵ the proposal projected — see Limitations.

## Headline: simple contagion, not complex

> Exposure matters, but the rise with distinct exposers is explained by the
> activity confound, not by social reinforcement.

### The raw curve rises — and that is a trap

| d (distinct exposers) | n | real rate | shuffled null | lift over null | z |
|---|---|---|---|---|---|
| 1 | 85,771 | 0.1595 | 0.1354 | **1.178** | 20.1 |
| 2 | 40,895 | 0.1583 | 0.1419 | 1.116 | 11.9 |
| 3 | 24,022 | 0.1689 | 0.1563 | 1.081 | 8.9 |
| 4 | 15,556 | 0.1817 | 0.1692 | 1.074 | 9.9 |
| 5 | 10,877 | 0.1851 | 0.1781 | 1.039 | 3.2 |
| 6+ | 46,846 | 0.2265 | 0.2267 | **0.999** | −0.1 |

The raw adoption rate climbs from 0.159 to 0.227 (lift 1.42). Read alone, that
looks like textbook complex contagion. But the timestamp-shuffled null climbs
just as fast, and the **excess over the null decays monotonically to exactly
zero**. Complex contagion predicts the opposite: reinforcement should make the
excess *grow* with d. High-d players are simply high-volume players who adopt
more of everything.

### The decisive comparison agrees

Holding total exposure count k fixed and varying d (k = 4):

| d | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| rate | 0.179 | 0.142 | 0.159 | 0.184 |

No trend. `separated_at_fixed_k: false`. Same at k = 2 and k = 3.

### But influence is real — it just needs only one exposure

Rating-and-activity matched controls, n = 61,376 pairs:

| | |
|---|---|
| Exposed adoption rate | 13.35% |
| Matched unexposed | 10.35% |
| **Difference** | **+3.00 pp**, 95% CI [2.64, 3.36] |
| Risk ratio | 1.29 |

Beating the null at d = 1 with z = 20.1 says the first exposure carries the
whole effect. That is simple contagion with a modest, tightly estimated
effect size.

## Network structure (Objective 4)

| | |
|---|---|
| Nodes / edges | 6,881 / 173,944 |
| Density | 0.0073 |
| Components | 1 |
| Communities (Louvain) | 5, modularity **0.493** |
| Mean degree | 50.6 |
| Pre-adoption exposures within community | **72.1%** |

Early adopters (first 10% to play a behaviour) are structurally distinctive:

| | early | rest |
|---|---|---|
| Degree | **84.3** | 60.8 |
| k-core | 30.9 | 28.3 |
| Betweenness | **0.00064** | 0.00033 |

Openings enter through hubs, not the periphery, and diffuse mostly within
communities (72%) — consistent with brokers carrying them across.

## What did not work

**The predictive check failed to demonstrate anything.** Held-out AUC
(train on first 70% of the month, score the later 30%):

| model | AUC |
|---|---|
| baseline (popularity + rating + activity) | 0.5255 |
| + network (k, d, sd, degree, k-core, betweenness) | 0.5289 |
| **gain** | **+0.0034** |

Both are barely above chance. Network features add essentially nothing. This
is consistent with the simple-contagion verdict — if d carries no signal, a
model given d should not improve — but it is equally consistent with the
feature set being too weak to predict individual adoption at all. It should
be reported as inconclusive, not as support.

## Robustness: the decay is not an artefact of the d-cap

`MAX_DIVERSITY = 6` makes d = 6 a *clipped* bucket holding every trial with six
or more distinct exposers — n = 46,846, larger than d = 4 and d = 5 combined.
Since the headline claim is that the excess over the null reaches 1.000 exactly
at that bucket, the obvious objection is that the convergence is produced by the
lumping rather than by the data.

Re-running with the cap raised to 12 (`scripts/check_clipping.py`, same 3
replicates, full month) spreads the tail out:

| d | n | observed | null | lift | z |
|---|---|---|---|---|---|
| 1 | 85,771 | 0.1595 | 0.1354 | **1.178** | 20.1 |
| 2 | 40,895 | 0.1583 | 0.1418 | 1.116 | 11.9 |
| 3 | 24,022 | 0.1689 | 0.1562 | 1.081 | 8.9 |
| 4 | 15,556 | 0.1817 | 0.1692 | 1.074 | 9.9 |
| 5 | 10,877 | 0.1851 | 0.1781 | 1.039 | 3.2 |
| 6 | 7,886 | 0.1962 | 0.1877 | 1.045 | 2.6 |
| 7 | 5,913 | 0.2028 | 0.1982 | 1.023 | 0.7 |
| 8 | 4,628 | 0.2141 | 0.2017 | 1.062 | 3.6 |
| 9 | 3,628 | 0.2056 | 0.2095 | 0.982 | −0.3 |
| 10 | 2,986 | 0.2130 | 0.2138 | 0.996 | −0.3 |
| 11 | 2,448 | 0.2214 | 0.2158 | 1.026 | 0.5 |
| 12+ | 19,357 | 0.2557 | 0.2636 | **0.970** | −4.3 |

The excess declines smoothly from 1.178 and sits on 1.0 from d ≈ 7 onward,
crossing slightly below it in the tail. **The convergence survives unclipping**,
and the verdict is unchanged. The effect really is concentrated at the first
exposure; it is not the d = 6 bucket doing the work.

Raw table: `results/tables/null_comparison_cap12.csv`.

## Limitations

1. **One month, one rating band, one platform.** The excess-over-null decay
   is the key claim and it has not been replicated. Running 2016-07 is the
   cheapest strengthening available.
2. **6,881 players, not 10⁵.** The filters compound harshly. Widening the
   band or relaxing the ≥20-game floor trades noise for scale.
3. **ECO-level granularity only.** The ply-level robustness check
   (`OPENING_GRANULARITY = "ply"`) has not been run.
4. **d = 6 is a clipped bucket** (all d ≥ 6) in the headline table, which is why
   its n is large. The robustness run above unclips it to d = 12 and the result
   holds.
5. **Adoption ≠ repertoire change.** A player may play an opening once
   experimentally; the design cannot distinguish that from real uptake.

## Note on a bug worth mentioning in the report

The first run printed *"complex contagion (marginal)"*. That verdict function
read only the raw d-curve and never consulted the null model the pipeline had
just computed. Since the null reproduces almost the entire raw rise, the
conclusion inverted once the null was included. `curve.verdict()` now requires
three things simultaneously — raw rise, survival at fixed k, and growth of the
excess over the null — and `run_pipeline` computes the null *before* the
verdict. This is a good slide: it is exactly the error the proposal's
identification strategy was designed to prevent, caught by its own null model.
