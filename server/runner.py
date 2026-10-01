"""Drives the real pipeline and emits structured progress events.

Same modules the CLI uses -- src.parse, src.events, src.structure, src.curve,
src.nulls, src.matching, src.predict -- against a live stream from
database.lichess.org. Nothing here is simulated.

Events are plain dicts pushed onto a queue; server.app relays them to the
browser as Server-Sent Events.
"""
from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid

import pandas as pd

from src import config, curve, events as ev, matching, nulls, parse, predict, structure
from src.fetch import BASE

# Months worth offering. Sizes are the compressed archive; a whole month is
# streamed and decompressed on the fly, never written to disk.
MONTHS = [
    {"id": "2014-07", "label": "July 2014",    "mb": 200,  "games": "~1.0M"},
    {"id": "2015-01", "label": "January 2015", "mb": 285,  "games": "~1.5M"},
    {"id": "2015-07", "label": "July 2015",    "mb": 482,  "games": "~2.4M"},
    {"id": "2016-01", "label": "January 2016", "mb": 871,  "games": "~5.0M"},
]

STAGES = [
    ("stream",  "Stream & filter the archive"),
    ("trials",  "Build exposure / adoption trials"),
    ("network", "Network structure"),
    ("curve",   "Adoption-probability curve"),
    ("null",    "Timestamp-shuffled null"),
    ("matched", "Matched controls"),
    ("predict", "Held-out prediction"),
    ("verdict", "Verdict"),
]

_RUNS: dict[str, "Run"] = {}

# The most recent successful run's data, kept so the interactive board can ask
# "what happened to THIS opening?" without re-streaming the archive.
LAST: dict = {"df": None, "trials": None, "month": None, "comm": None,
              "graph_players": None}


def board_state(sans: list[str], uci: str | None = None) -> dict:
    """Replay a SAN list from the start position, optionally appending one move.

    Stateless by design: the client sends the whole (short) move list each time,
    so two people can share the board without the server tracking sessions.
    """
    import chess

    board = chess.Board()
    played: list[str] = []
    for san in sans:
        try:
            board.push_san(san)
            played.append(san)
        except Exception:
            break                                  # ignore a corrupt tail

    error = None
    if uci:
        try:
            mv = chess.Move.from_uci(uci)
            if mv in board.legal_moves:
                played.append(board.san(mv))
                board.push(mv)
            else:
                error = "illegal move"
        except Exception:
            error = "could not read that move"

    legal: dict[str, list[str]] = {}
    for mv in board.legal_moves:
        legal.setdefault(chess.square_name(mv.from_square), []).append(
            chess.square_name(mv.to_square))

    status = None
    if board.is_checkmate():
        status = "checkmate"
    elif board.is_stalemate():
        status = "stalemate"
    elif board.is_check():
        status = "check"

    return {
        "fen": board.fen(),
        "turn": "white" if board.turn else "black",
        "sans": played,
        "legal": legal,
        "status": status,
        "error": error,
        "opening": lookup_opening(played),
    }


def lookup_opening(sans: list[str]) -> dict | None:
    """Find what the loaded archive slice knows about the line being played.

    Matches on the SAN prefix, so the answer sharpens move by move: after 1.e4
    it reports every e4 game, after 1.e4 c5 only the Sicilians.
    """
    df = LAST.get("df")
    if df is None or not len(sans):
        return None

    prefix = " ".join(sans)
    hit = df[df["ply_key"].str.startswith(prefix, na=False)]
    if not len(hit):
        return {"matched": 0, "prefix": prefix, "ply": len(sans)}

    top = hit.groupby(["eco", "opening"]).size().sort_values(ascending=False)
    (eco, name), n = top.index[0], int(top.iloc[0])
    # After a short prefix the leading ECO is only the commonest continuation,
    # not the name of the position: 1.e4 is not "the French Defense" just
    # because French games are the largest single group beneath it.
    top_share = n / len(hit)

    trials = LAST.get("trials")
    adoptions = exposures = 0
    rate = None
    if trials is not None and len(trials):
        sub = trials[trials["opening"] == eco]
        exposures = int(len(sub))
        adoptions = int(sub["adopted"].sum())
        rate = round(float(sub["adopted"].mean()), 4) if len(sub) else None

    white = float((hit["result"] == "1-0").mean())
    black = float((hit["result"] == "0-1").mean())

    # Which drawn players relate to this line, as node indices the canvas can
    # light directly. Two different sets, and the distinction matters:
    #   played   - ever reached this position. High-degree players have played
    #              nearly everything, so 1.e4 lights up the whole graph.
    #   adopters - took the opening up for the first time AFTER being exposed
    #              to it. That is the contagion event, and it is the set worth
    #              looking at for clustering.
    graph_hits: list[int] = []
    graph_adopters: list[int] = []
    drawn = LAST.get("graph_players")
    if drawn:
        played_by = set(pd.unique(pd.concat([hit["white"], hit["black"]])))
        graph_hits = [i for i, p in enumerate(drawn) if p in played_by]
        if trials is not None and len(trials):
            adopted_by = set(trials.loc[(trials["opening"] == eco)
                                        & (trials["adopted"] == 1), "player"])
            graph_adopters = [i for i, p in enumerate(drawn) if p in adopted_by]
    return {
        "matched": int(len(hit)),
        "prefix": prefix,
        "ply": len(sans),
        "eco": eco,
        "name": name or eco,
        "games": n,
        "top_share": round(top_share, 4),
        "settled": bool(top_share >= 0.5),
        "share": round(len(hit) / len(df), 5),
        "white_win": round(white, 3),
        "black_win": round(black, 3),
        "mean_elo": int(((hit["white_rating"] + hit["black_rating"]) / 2).mean()),
        "trials": exposures,
        "adoptions": adoptions,
        "adoption_rate": rate,
        "variations": [{"eco": e, "name": nm or e, "games": int(c)}
                       for (e, nm), c in top.head(5).items()],
        "graph_hits": graph_hits,
        "graph_adopters": graph_adopters,
        "graph_total": len(drawn) if drawn else 0,
    }


class Run:
    def __init__(self, month: str, max_games: int | None, null_reps: int,
                 window_days: int, refresh: bool = False):
        self.id = uuid.uuid4().hex[:12]
        self.month = month
        self.max_games = max_games or None
        self.null_reps = max(1, min(5, null_reps))
        self.window_days = window_days
        self.refresh = refresh
        self.q: queue.Queue = queue.Queue()
        self.cancelled = threading.Event()
        self.started = time.time()
        _RUNS[self.id] = self

    # ---- event helpers -------------------------------------------------
    def emit(self, kind: str, **payload):
        payload["kind"] = kind
        payload["t"] = round(time.time() - self.started, 1)
        self.q.put(payload)

    def log(self, msg: str, level: str = "info"):
        self.emit("log", msg=msg, level=level)

    def stage(self, key: str, state: str, detail: str = ""):
        self.emit("stage", key=key, state=state, detail=detail)

    def cancel(self):
        self.cancelled.set()

    def stopped(self) -> bool:
        return self.cancelled.is_set()


def get(run_id: str) -> Run | None:
    return _RUNS.get(run_id)


def start(month: str, max_games: int | None, null_reps: int,
          window_days: int, refresh: bool = False) -> Run:
    run = Run(month, max_games, null_reps, window_days, refresh)
    threading.Thread(target=_execute, args=(run,), daemon=True).start()
    return run


# ------------------------------------------------------------------ pipeline
def _execute(run: Run):
    try:
        _pipeline(run)
    except Exception as exc:                       # surface, never swallow
        run.log("FAILED: " + str(exc), "error")
        run.emit("log", msg=traceback.format_exc()[-1200:], level="trace")
        run.emit("done", ok=False)
    finally:
        run.q.put(None)


def _pipeline(run: Run):
    url = BASE.format(month=run.month)
    run.emit("init", stages=[{"key": k, "label": l} for k, l in STAGES],
             month=run.month, url=url, max_games=run.max_games)

    # ---------------- 1. stream & filter ----------------
    run.stage("stream", "running")

    # A parsed slice is cached so a second demo of the same month is instant.
    # Lichess throttles repeated downloads, and a stalled stream in front of an
    # audience is the one failure worth engineering away.
    cache = config.INTERIM / f"slice_{run.month}_{run.max_games or 'full'}.parquet"
    if cache.exists() and not run.refresh:
        df = pd.read_parquet(cache)
        df.attrs["skipped"] = {}       # filters already applied when it was cached
        run.log(f"Loaded a cached slice of {run.month} "
                f"({len(df):,} games) — no download needed.", "ok")
        run.emit("scan", scanned=len(df), kept=len(df), rate=0, game=None)
        return _analyse(run, df)

    run.log(f"GET {url}")
    run.log("Decompressing zstd on the fly — the PGN is never written to disk.")

    last = {"t": 0.0}

    def on_progress(scanned, kept, row=None):
        now = time.time()
        if now - last["t"] < 0.4:                  # don't flood the socket
            return
        last["t"] = now
        rate = scanned / max(1e-6, now - run.started)
        game = None
        if row is not None:
            # row order matches parse.parse's tuple
            game = {"white_elo": row[4], "black_elo": row[5], "eco": row[6],
                    "opening": row[7], "moves": " ".join(str(row[8]).split()[:6]),
                    "speed": row[9], "result": row[10]}
        run.emit("scan", scanned=scanned, kept=kept, rate=round(rate), game=game)

    df = parse.parse(url, limit=run.max_games, progress=20000,
                     on_progress=on_progress, should_stop=run.stopped)

    if run.stopped():
        run.log("Cancelled.", "warn")
        run.emit("done", ok=False, cancelled=True)
        return
    if len(df) < 200:
        run.stage("stream", "failed")
        run.log(f"Only {len(df)} games survived the filters — "
                "not enough to analyse. Try a larger cap or another month.", "error")
        run.emit("done", ok=False)
        return

    try:
        df.to_parquet(cache, index=False)
        run.log(f"Cached this slice — re-running {run.month} will be instant.")
    except Exception:
        pass                                   # a cache failure must not kill the run

    return _analyse(run, df)


def _analyse(run: "Run", df):
    span_days = (df["ts"].max() - df["ts"].min()).total_seconds() / 86400
    players = len(set(df["white"]) | set(df["black"]))
    skipped = df.attrs.get("skipped", {})
    run.emit("sample", games=len(df), players=players,
             openings=int(df["eco"].nunique()), span_days=round(span_days, 2),
             t0=str(df["ts"].min()), t1=str(df["ts"].max()), skipped=skipped)
    run.stage("stream", "done", f"{len(df):,} games · {players:,} players")

    # The adoption window has to fit inside the observed span, or every trial
    # is censored. A capped slice covers only the first hours of the month.
    window = run.window_days
    if span_days < window * 2.2:
        window = max(1, int(span_days / 2.2))
        run.log(f"Slice spans {span_days:.1f} days, so the adoption window is "
                f"reduced from {run.window_days} to {window} day(s) — "
                "otherwise every trial would be censored.", "warn")
        run.emit("window", days=window, auto=True)
    else:
        run.emit("window", days=window, auto=False)

    # ---------------- 2. trials ----------------
    run.stage("trials", "running")
    trials = ev.build_trials(df, window_days=window)
    if not len(trials) or trials["adopted"].sum() < 30:
        run.stage("trials", "failed")
        run.log(f"Only {len(trials)} trials / "
                f"{int(trials['adopted'].sum()) if len(trials) else 0} adoptions. "
                "Widen the sample.", "error")
        run.emit("done", ok=False)
        return
    run.emit("trials", n=int(len(trials)), adoptions=int(trials["adopted"].sum()),
             rate=round(float(trials["adopted"].mean()), 4))
    # make this slice queryable by the interactive board
    LAST["df"], LAST["trials"], LAST["month"] = df, trials, run.month
    run.emit("board_ready", month=run.month, games=int(len(df)))
    run.emit("openings", **_openings_payload(df, trials))
    run.stage("trials", "done", f"{len(trials):,} trials")
    if run.stopped(): return _cancel(run)

    # ---------------- 3. network ----------------
    run.stage("network", "running")
    g = structure.build_graph(df)
    feats = structure.node_features(g)
    early = structure.early_adopters(df).merge(feats, on="player", how="left")
    by_early = early.groupby("is_early")[["degree", "kcore", "betweenness"]].mean()
    run.emit("network",
             nodes=g.number_of_nodes(), edges=g.number_of_edges(),
             communities=int(feats.attrs["n_communities"]),
             modularity=round(float(feats.attrs["modularity"]), 4),
             early=_early_payload(by_early))
    run.emit("graph", **_graph_payload(g, feats, early))
    run.stage("network", "done",
              f"{g.number_of_nodes():,} nodes · Q={feats.attrs['modularity']:.3f}")
    if run.stopped(): return _cancel(run)

    # ---------------- 4. curve ----------------
    run.stage("curve", "running")
    tables = curve.analyse(trials)
    run.emit("curve", by_d=_rows(tables["by_d"]), held_k=_rows(tables["held_k_by_d"]))
    top = tables["by_d"]
    if len(top) >= 2:
        lift = top.iloc[-1]["rate"] / top.iloc[0]["rate"] if top.iloc[0]["rate"] else 0
        run.log(f"Raw curve rises {top.iloc[0]['rate']:.3f} → "
                f"{top.iloc[-1]['rate']:.3f} (×{lift:.2f}). "
                "On its own this looks like complex contagion.", "hl")
    run.stage("curve", "done")
    if run.stopped(): return _cancel(run)

    # ---------------- 5. null ----------------
    run.stage("null", "running", f"{run.null_reps} replicate(s)")
    run.log("Shuffling timestamps: keeps degree, ratings and popularity, "
            "destroys causal order.")
    null_by_d = nulls.run_null(df, n_reps=run.null_reps, kind="shuffle",
                               window_days=window)
    cmp = nulls.compare(tables["by_d"], null_by_d) if len(null_by_d) else pd.DataFrame()
    run.emit("null", rows=_rows(cmp))
    run.stage("null", "done")
    if run.stopped(): return _cancel(run)

    # ---------------- 6. matched controls ----------------
    run.stage("matched", "running")
    pairs = matching.build_matched(df, max_trials=60000, window_days=window)
    msum = matching.summarise(pairs)
    run.emit("matched", **msum)
    run.stage("matched", "done",
              (f"+{msum['difference']*100:.2f} pp" if msum.get("n_pairs") else "no pairs"))
    if run.stopped(): return _cancel(run)

    # ---------------- 7. prediction ----------------
    run.stage("predict", "running")
    # same code path as the CLI: features rebuilt from the training window
    # only, three nested models, and the network block taken apart
    pred = predict.evaluate(df, trials, full=False)
    run.emit("predict", **pred)
    if "error" in pred:
        run.stage("predict", "skipped", "insufficient variation")
    else:
        run.log(pred["reading"], "hl")
        run.stage("predict", "done",
                  f"repertoire {pred['gain_repertoire_over_baseline']:+.3f} "
                  f"vs network {pred['gain_network_over_repertoire']:+.3f}")

    # ---------------- 8. verdict ----------------
    run.stage("verdict", "running")
    v = curve.verdict(tables, cmp if len(cmp) else None)
    run.emit("verdict", **v)
    run.stage("verdict", "done")
    run.log("Run complete.", "ok")
    run.emit("done", ok=True, seconds=round(time.time() - run.started, 1))


def _cancel(run: Run):
    run.log("Cancelled.", "warn")
    run.emit("done", ok=False, cancelled=True)


def _openings_payload(df: pd.DataFrame, trials: pd.DataFrame | None = None,
                      top: int = 10) -> dict:
    """The openings actually present in this slice, each with the real board
    positions of its opening line.

    The SAN is replayed through python-chess here rather than in the browser:
    the page then only has to draw a FEN, and the positions are guaranteed
    legal rather than reconstructed by hand.
    """
    import chess

    counts = df.groupby(["eco", "opening"]).size().sort_values(ascending=False)
    adopt = {}
    if trials is not None and len(trials):
        a = trials[trials["adopted"] == 1].groupby("opening").size()
        adopt = a.to_dict()

    out = []
    for (eco, name), n in counts.head(top).items():
        line = df.loc[(df["eco"] == eco) & (df["opening"] == name), "ply_key"]
        sans = str(line.mode().iloc[0]).split() if len(line) else []
        board, fens, played = chess.Board(), [chess.Board().fen()], []
        for san in sans[:8]:
            try:
                board.push_san(san)
            except Exception:
                break                       # truncated or ambiguous SAN: stop here
            played.append(san)
            fens.append(board.fen())
        out.append({"eco": eco, "name": name or eco, "games": int(n),
                    "adoptions": int(adopt.get(eco, 0)),
                    "sans": played, "fens": fens})
    return {"openings": out}


def _graph_payload(g, feats, early, max_nodes: int = 240,
                   max_edges: int = 1400) -> dict:
    """A drawable subsample of the interaction network: the highest-degree
    nodes plus the heaviest edges among them. The full graph has tens of
    thousands of edges -- far past what a browser force layout can move."""
    deg = dict(g.degree())
    keep = [n for n, _ in sorted(deg.items(), key=lambda kv: -kv[1])[:max_nodes]]
    idx = {n: i for i, n in enumerate(keep)}
    # remember the draw order so the board can map players -> node indices
    LAST["graph_players"] = keep

    comm = dict(zip(feats["player"], feats["community"]))
    early_set = set(early.loc[early["is_early"] == 1, "player"]) if len(early) else set()

    edges = []
    for u, v, data in g.subgraph(keep).edges(data=True):
        edges.append((idx[u], idx[v], int(data.get("games", 1))))
    edges.sort(key=lambda e: -e[2])
    edges = edges[:max_edges]

    return {
        "nodes": [{"d": int(deg[n]), "c": int(comm.get(n, 0)),
                   "e": 1 if n in early_set else 0} for n in keep],
        "edges": [[e[0], e[1]] for e in edges],
        "total_nodes": g.number_of_nodes(),
        "total_edges": g.number_of_edges(),
    }


def _early_payload(by_early) -> dict:
    out = {}
    for flag in (0, 1):
        if flag in by_early.index:
            r = by_early.loc[flag]
            out["early" if flag else "rest"] = {
                "degree": round(float(r["degree"]), 2),
                "kcore": round(float(r["kcore"]), 2),
                "betweenness": round(float(r["betweenness"]), 6),
            }
    return out


def _rows(df: pd.DataFrame) -> list[dict]:
    if df is None or not len(df):
        return []
    clean = df.replace({float("nan"): None})
    return clean.to_dict(orient="records")
