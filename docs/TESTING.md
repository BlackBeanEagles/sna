# What to test

Four levels, cheapest first. If you only have ten minutes, do level 1 and 2.

Every expected value below comes from the committed run on the full January
2016 Lichess month. If something disagrees, that is a real finding, not a
rounding difference — write down what you saw.

---

## Level 1 — does the code work at all  (about 1 minute)

```bash
cd C:\Users\hridy\Desktop\sna
.venv\Scripts\python.exe -m pytest tests -q
```

**Expect:** `20 passed`

These cover the part where the science lives — who was exposed to what, when
someone counts as having adopted, and whether the verdict logic can be fooled.
Four of them exist because a bug once produced a confident wrong answer.

---

## Level 2 — do the published numbers still come out  (about 5 minutes)

```bash
.venv\Scripts\python.exe scripts\verify_published.py
```

**Expect:** `19/19 checks pass` and the closing line
*"every published number is reproducible by the current code"*.

It rebuilds the trials, the adoption curve, three null replicates, the matched
controls and the verdict from scratch and compares each against
`results/report.json`. This is the single most valuable check in the project:
it is the difference between "the results match the code" being true and being
assumed.

**Known limit:** it verifies the analysis, not the parser. Re-parsing needs the
archive downloaded again.

---

## Level 3 — the live demonstration  (about 5 minutes)

```bash
.venv\Scripts\python.exe server\app.py
```

Open <http://localhost:8124>. Set **January 2016**, scan to **maximum**,
replicates **3**, press **Run the pipeline**.

### 3a. It starts

- First log line within a second or two: *"Loaded a cached slice of 2016-01
  (249,505 games) — no download needed."*
- If instead it says `GET https://database.lichess.org/...` and then stalls,
  the cache is missing and you are on a network that blocks the download.

### 3b. The numbers, as each stage lands

| Stage | Expect |
|---|---|
| Stream & filter | 249,505 games · 6,881 players · 40 ECO codes · spans 31 days |
| Trials | 223,967 trials, 39,661 adoptions (17.7%) |
| Network | 6,881 nodes, 173,944 edges, 5 communities, modularity 0.493 |
| Curve | raw curve rises 0.159 → 0.227 (×1.42) |
| Null | excess **1.178× at d=1 → 0.999× at d=6** |
| Matched controls | about **+2.97 pp**, CI roughly [2.51, 3.44] |
| Prediction | repertoire gain about +0.036, network about +0.030 |
| Verdict | **simple contagion** |

The matched-control figure differs from the report's **+2.80 pp** on purpose:
the console subsamples to stay responsive, the CLI does not. Quote +2.80 in
writing, and say so if anyone notices the difference on screen.

### 3c. The reveal — this is the demo

Once the curve is drawn, toggle **the null** off and on. Off, the curve reads
as textbook complex contagion. On, it collapses. That is the whole argument in
one control.

### 3d. The board

Click a white pawn — legal destinations should appear as dots. Play `1.e4 c5`.

- The panel beside the board should name the Sicilian and show its games,
  share, exposure trials and adoptions.
- Players in the network who **adopted** that opening should light up; the rest
  dim. Expect roughly 31 of 240 drawn players.

---

## Level 4 — the design, which has had the least eyes on it

These were built and served but barely looked at. They are the most likely
place to find something visibly wrong.

- **Stage rail** should read like a scoresheet: numbered 1–8, hairline rules,
  alternating banding from the board's two square tones.
- **Board** should carry **a–h** along the bottom and **1–8** up the side.
- **Move list** should be figurine notation — `1.e4 c5 2.♘f3`, piece symbols
  rather than letters. If you see `Nf3`, the glyph substitution is not firing.
- **Both themes.** The page follows your OS light/dark setting. Check both;
  dark mode has had less attention.
- **Narrow window.** Drag the browser narrow and confirm nothing overflows
  sideways.

---

## What cannot be tested here

Two things are blocked by the campus network inspecting HTTPS, and both need a
different connection:

```bash
.venv\Scripts\python.exe -m src.run_pipeline --month 2016-01   # re-parse with the fixed parser
.venv\Scripts\python.exe -m src.run_pipeline --month 2016-07   # replicate on a second month
```

The first matters because the cached slice was parsed *before* a bug was fixed
in which an aborted game leaked its opening and ratings into the next game. The
effect is probably nil — the Lichess database holds rated completed games, and
aborted games are unrated — but that is reasoning, not measurement.

The second is the largest remaining scientific gap: the central finding rests
on one month.

---

## If you want to try breaking it

Worth doing once, so you know the guards are real rather than decorative.

| Try | Should happen |
|---|---|
| Point `--games` at a simulated table | Refuses, names the file, says what to use instead |
| Run the console with **1** null replicate | Still works — a binomial fallback covers the missing spread |
| Close the browser tab mid-run | The run cancels server-side rather than orphaning |
| Resize the window after the network draws | The graph repaints instead of vanishing |
