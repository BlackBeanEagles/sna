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
just as fast, and the **ratio of observed to null falls from 1.178 to 0.999** —
that is, the excess *above* the null vanishes. Complex contagion predicts the
opposite: reinforcement should make the excess *grow* with d. High-d players
are simply high-volume players who adopt more of everything: `corr(d, activity)
= 0.44`, and median activity runs from 68 games at d = 1 to 189 at d ≥ 6.

### The decisive comparison agrees

Holding total exposure count k fixed and varying d (k = 4):

| d | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| rate | 0.179 | 0.142 | 0.159 | 0.184 |

No trend. `separated_at_fixed_k: false`. Same at k = 2 and k = 3.

### But influence is real — it just needs only one exposure

Rating-and-activity matched controls, n = 61,519 pairs:

| | |
|---|---|
| Exposed adoption rate | 13.38% |
| Matched unexposed | 10.58% |
| **Difference** | **+2.80 pp**, 95% CI [2.44, 3.16] |
| Risk ratio | 1.265 |

This estimate uses one pair per exposed player-behaviour, so unlike the curve
above it is **not affected by the trial-independence problem** documented
below. It is the most robust number in the report — lead with it.

Beating the null at d = 1 says the first exposure carries the effect. Quote the
conservative per-spell figure for that (z = 8.9), not the per-exposure z = 20.1
in the table above, which is inflated by repeated counting.

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

## The predictive check, rebuilt

The original version of this check was the weakest part of the project: both
models sat at chance, and every feature was computed over the whole month
before being used to predict the last 30% of it, so both figures were
optimistic anyway. It has been rebuilt without the leakage and with the
competing explanation included.

**What was missing.** The old feature set only ever asked *who played this
opening at you*. De Marzo and Servedio [4] showed that a player's next opening
is largely predicted by how close it sits to what they already play -- an
"adjacent possible" effect with no social component. Leaving that out made the
social features look better than they are, because they were the only
candidate in the model. `repertoire_density` now measures it: the share of an
opening's total relatedness that points at openings the player already has,
with relatedness built from co-play exactly as in [4].

**Nested models, held out on the later part of the month:**

| Model | Test AUC | Gain |
|---|---|---|
| Baseline — popularity, rating, activity | 0.611 | — |
| **+ Repertoire proximity** | **0.646** | **+0.036** |
| + Network — exposure, diversity, centrality | 0.676 | +0.030 |

**Taking the network block apart.** It bundles two claims that mean opposite
things here, so they are separated:

| Added to the repertoire model | Test AUC | Gain |
|---|---|---|
| `k` — how many exposures | 0.649 | +0.003 |
| `d`, `sd` — how diverse those exposers were | 0.655 | +0.008 |
| centrality — degree, k-core, betweenness | 0.658 | +0.012 |

**Reading.** Repertoire proximity is worth +0.036 AUC. Knowing who played the
opening at the player is worth at most +0.008 on top of it, and most of what
the network block does contribute comes from centrality -- which is largely a
proxy for how much a player plays, the same activity confound the null model
exposes elsewhere in this report.

This is the same conclusion the adoption curve reaches, arrived at
independently: **what a player already knows explains adoption far better than
who has played it at them.**

### Three caveats, because this section is easy to over-read

1. **A linear model gets this badly wrong.** Fitted with logistic regression
   all three models sit near chance (0.55, 0.52, 0.54) and the richer ones
   score *worse* out of sample. The relationships are not linear. Both sets of
   figures are in `results/tables/predictive_auc.csv`; the gradient-boosted
   ones are reported here, and the choice is stated rather than hidden.
2. **The models overfit.** Training AUC is 0.79--0.85 against 0.61--0.68 on the
   held-out period. The ordering is stable but the absolute values are not
   impressive.
3. **The base rate shifts between the two periods** -- 15.1% of trials adopt in
   the training window against 23.8% in the test window -- so the test task is
   not identical to the training task. Compare the models against each other,
   not against an external benchmark.

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

## Structural diversity gives the same answer as raw exposer count

The proposal's stated technique is Ugander et al.'s measure — not how many
distinct neighbours exposed you (`d`), but how many **connected components**
the exposing neighbourhood breaks into (`sd`). Two exposures from two players
who have met is one social source; from two strangers, two. Testing `d` alone
would leave the proposal's actual promise untested, so `sd` was put through the
identical shuffled-time null (`scripts/check_diversity.py`).

| sd | n | observed | null | lift | z |
|---|---|---|---|---|---|
| 1 | 87,558 | 0.1601 | 0.1355 | **1.181** | 23.4 |
| 2 | 42,703 | 0.1608 | 0.1435 | 1.120 | 24.3 |
| 3 | 25,318 | 0.1738 | 0.1612 | 1.078 | 6.9 |
| 4 | 16,685 | 0.1896 | 0.1766 | 1.074 | 7.0 |
| 5 | 11,660 | 0.1961 | 0.1905 | 1.029 | 3.2 |
| 6+ | 40,043 | 0.2230 | 0.2245 | **0.993** | −0.6 |

The excess decays from 1.181 to 0.993, the fixed-`k` comparison still fails to
separate, and the verdict is unchanged. **Structural diversity tracks raw
exposer count almost exactly** (excess at the top bucket: d 0.999, sd 0.993),
so the conclusion does not depend on which of the two measures is used — the
sharper, network-defined measure finds no reinforcement either.

Raw tables: `results/tables/null_comparison_d.csv`, `null_comparison_sd.csv`.

## Robustness: ply-level granularity

ECO codes are coarse — many distinct ideas share one code. The proposal
promised a robustness check at ply level, where a behaviour is keyed by the
first 8 plies instead. That fragments the data hard: 40 ECO behaviours become
**56,912 ply behaviours**, and the adoption rate falls from 17.71% to 0.65%
(1,712 adoptions), because almost nobody repeats an exact 8-ply line.

| d | ECO lift | ply lift | ply n |
|---|---|---|---|
| 1 | 1.178 | **1.162** | 229,966 |
| 2 | 1.116 | 1.080 | 19,335 |
| 3 | 1.081 | 0.991 | 6,310 |
| 4 | 1.074 | 1.191 | 2,936 |
| 5 | 1.039 | 1.238 | 1,625 |
| 6+ | 0.999 | **0.865** | 3,302 |

**The verdict is the same at both granularities**: simple contagion, with the
excess over the null starting near 1.16 at d = 1 and ending at or below 1.0.

Report the ply curve with the caveat it deserves: from d = 3 onward the buckets
hold only 1,600–6,300 trials with an adoption rate under 4%, so the middle of
that column is noisy and non-monotonic (0.991, then 1.191, then 1.238, then
0.865). What is stable is the pair of endpoints and the verdict — not the shape
in between. The ECO-level analysis remains the headline for that reason.

Reproduce: `python scripts/check_ply.py --reps 3`.

## The trials are not independent — and the intervals say otherwise

This is the most serious caveat in the project, and it is not visible from the
headline table.

The trial table has one row per (player, behaviour, k-th exposure), and
`adopted` is scored for *every* exposure whose 14-day window contains the
adoption. So one real adoption event is counted many times:

| | |
|---|---|
| trial rows | 223,967 |
| distinct (player, behaviour) spells | 78,274 |
| distinct players | 6,730 |
| "adoptions" reported | 39,661 |
| **distinct adoption events** | **14,320** |
| each adoption counted | **2.77× on average, up to 144×** |
| adoption events counted more than once | 46.9% |

Wilson intervals and z-scores both assume independent Bernoulli trials. They
are therefore **too narrow**, and the verdict rests on exactly those quantities
(interval separation, and z > 3 against the null).

Recomputing with **one row per spell** — each player-behaviour contributing a
single observation and each adoption counted once — gives
(`scripts/check_independence.py`):

| d | n | observed | null | lift | z (per-spell) | z (per-exposure) |
|---|---|---|---|---|---|---|
| 1 | 41,617 | 0.1802 | 0.1584 | **1.138** | 8.9 | 20.1 |
| 2 | 15,481 | 0.1724 | 0.1599 | 1.078 | 3.1 | 11.9 |
| 3 | 7,616 | 0.1754 | 0.1729 | 1.015 | 2.1 | 8.9 |
| 4 | 4,209 | 0.1894 | 0.1818 | 1.042 | 1.2 | 9.9 |
| 5 | 2,582 | 0.1921 | 0.1924 | 0.998 | −0.1 | 3.2 |
| 6+ | 6,769 | 0.2248 | 0.2258 | **0.996** | −1.4 | −0.1 |

**What survives:** the decay from ~1.14 to ~1.00, the verdict, and a clearly
significant effect at the first exposure (z = 8.9).

**What does not:** the apparent strength of the middle of the curve. At d = 3
and d = 4 the per-exposure z-scores of 8.9 and 9.9 collapse to 2.1 and 1.2 —
below any reasonable threshold. The per-exposure z-scores are inflated roughly
two- to four-fold throughout.

So the honest statement of the result is: *the first exposure carries a real
effect; beyond it, nothing distinguishable from the null* — which is the same
verdict, argued from weaker and more defensible numbers. Quote the per-spell
figures when precision is being challenged.

Raw table: `results/tables/null_comparison_perspell_last.csv`.

## Robustness: the 14-day adoption window

The window is the analyst's choice, not a property of the data, so it is a free
parameter worth testing (`scripts/check_window.py`).

| window | trials | adoptions | rate | excess at d=1 | excess at d=6+ | verdict |
|---|---|---|---|---|---|---|
| 7 days | 302,631 | 29,091 | 9.61% | 1.323 | 1.114 | simple contagion |
| **14 days** | 223,967 | 39,661 | 17.71% | 1.180 | 0.996 | simple contagion |
| 28 days | 76,571 | 47,066 | 61.47% | 1.109 | 0.952 | simple contagion |

**The verdict is stable at every window**, and the excess decays in all three.

Two things not to overclaim. First, *how far* it decays is window-dependent: at
7 days the excess is still 1.114 at the top bucket rather than reaching 1.0, so
"the excess falls to exactly 1" is a 14-day statement, whereas "the excess
decays with d" holds throughout. Second, the 28-day row should be read with
care — a 28-day window inside a 31-day month censors most non-adopters, which
is why the trial count collapses from 223,967 to 76,571 and the adoption rate
jumps to 61%. It agrees, but it is the weakest of the three.

Raw table: `results/tables/window_sensitivity.csv`.

## Limitations

1. **One month, one rating band, one platform.** The excess-over-null decay
   is the key claim and it has not been replicated on a second month. This is
   now the largest remaining gap: every other robustness check above has been
   run and passed.
2. **6,881 players, not 10⁵.** The filters compound harshly. Widening the
   band or relaxing the ≥20-game floor trades noise for scale.
3. **Ply-level granularity is noisy.** The check agrees with the ECO result
   (section above), but its buckets beyond d = 2 hold 1,600–6,300 trials at
   under 4% adoption, so only the endpoints are trustworthy.
4. **The predictive models overfit and the base rate shifts** between the
   training and test halves of the month; read the model comparison as an
   ordering, not as absolute performance.
5. **d = 6 is a clipped bucket** (all d ≥ 6) in the headline table, which is why
   its n is large. The robustness run above unclips it to d = 12 and the result
   holds.
6. **Confidence intervals throughout this report are optimistic** for the
   reason above; the per-spell table is the conservative version.
7. **Adoption ≠ repertoire change.** A player may play an opening once
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
