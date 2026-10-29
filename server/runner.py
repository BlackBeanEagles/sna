"""Drives the real pipeline and emits structured progress events.

Same modules the CLI uses -- src.parse, src.events, src.structure, src.curve,
src.nulls, src.matching, src.predict -- against a live stream from
database.lichess.org. Nothing here is simulated.

Each run executes in a separate process and appends events to disk. The HTTP
server can restart while the worker continues, and browsers can replay events.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

import pandas as pd

from src import config, curve, events as ev, matching, nulls, parse, predict, structure
from src.fetch import BASE

RUNS_DIR = config.RESULTS / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

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
    ("predict", "Group-held-out prediction"),
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
                 window_days: int, refresh: bool = False,
                 run_id: str | None = None):
        self.id = run_id or uuid.uuid4().hex[:12]
        self.month = month
        self.max_games = max_games or None
        self.null_reps = max(1, min(20, null_reps))
        self.window_days = window_days
        self.refresh = refresh
        self.dir = RUNS_DIR / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.cancel_path = self.dir / "cancel"
        self.heartbeat_path = self.dir / "heartbeat"
        self.manifest_path = self.dir / "run.json"
        self.started = time.time()
        if run_id is None:
            self._save_manifest({
                "id": self.id, "month": month, "max_games": self.max_games,
                "null_reps": self.null_reps, "window_days": window_days,
                "refresh": refresh, "started": self.started,
                "status": "running",
            })
        else:
            self.started = json.loads(self.manifest_path.read_text(
                encoding="utf-8"))["started"]
        _RUNS[self.id] = self

    def _save_manifest(self, manifest: dict):
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)

    @classmethod
    def from_id(cls, run_id: str) -> "Run | None":
        if len(run_id) != 12 or any(c not in "0123456789abcdef" for c in run_id):
            return None
        path = RUNS_DIR / run_id / "run.json"
        if not path.is_file():
            return None
        m = json.loads(path.read_text(encoding="utf-8"))
        return cls(m["month"], m["max_games"], m["null_reps"],
                   m["window_days"], m["refresh"], run_id=run_id)

    def emit(self, kind: str, **payload):
        payload["kind"] = kind
        payload["t"] = round(time.time() - self.started, 1)
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, default=str) + "\n")
        if kind in ("stage", "done"):
            m = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if kind == "stage":
                m["stage"] = payload["key"]
                m["stage_state"] = payload["state"]
            else:
                m["status"] = ("completed" if payload.get("ok") else
                               "cancelled" if payload.get("cancelled") else "failed")
                m["finished"] = time.time()
            self._save_manifest(m)

    def log(self, msg: str, level: str = "info"):
        self.emit("log", msg=msg, level=level)

    def stage(self, key: str, state: str, detail: str = ""):
        self.emit("stage", key=key, state=state, detail=detail)

    def cancel(self):
        self.cancel_path.touch()

    def stopped(self) -> bool:
        return self.cancel_path.exists()


def get(run_id: str) -> Run | None:
    return _RUNS.get(run_id) or Run.from_id(run_id)


def current_status(manifest: dict) -> str:
    status = manifest.get("status", "unknown")
    if status != "running":
        return status
    heartbeat = RUNS_DIR / manifest["id"] / "heartbeat"
    if time.time() - manifest["started"] > 12:
        if not heartbeat.is_file() or time.time() - heartbeat.stat().st_mtime > 12:
            return "interrupted"
    return status

def list_runs(limit: int = 20) -> list[dict]:
    manifests = sorted(RUNS_DIR.glob("*/run.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for path in manifests[:limit]:
        m = json.loads(path.read_text(encoding="utf-8"))
        m["status"] = current_status(m)
        out.append(m)
    return out


def _launch(run: Run):
    flags = 0
    if os.name == "nt":
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                 | subprocess.CREATE_NEW_PROCESS_GROUP)
    with (run.dir / "worker.log").open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "server.runner", "--worker", run.id],
            cwd=str(config.ROOT), stdout=log, stderr=subprocess.STDOUT,
            creationflags=flags, close_fds=True)
    m = json.loads(run.manifest_path.read_text(encoding="utf-8"))
    m["pid"] = proc.pid
    run._save_manifest(m)


def start(month: str, max_games: int | None, null_reps: int,
          window_days: int, refresh: bool = False) -> Run:
    run = Run(month, max_games, null_reps, window_days, refresh)
    _launch(run)
    return run


def resume(run_id: str) -> Run | None:
    run = get(run_id)
    if run is None:
        return None
    m = json.loads(run.manifest_path.read_text(encoding="utf-8"))
    if current_status(m) not in ("interrupted", "failed"):
        return None
    if run.events_path.exists():
        attempt = int(m.get("attempt", 1))
        run.events_path.rename(run.dir / f"events_attempt_{attempt}.jsonl")
        m["attempt"] = attempt + 1
    run.cancel_path.unlink(missing_ok=True)
    run.heartbeat_path.unlink(missing_ok=True)
    run.started = time.time()
    m.update(started=run.started, status="running")
    m.pop("finished", None)
    m.pop("stage", None)
    m.pop("stage_state", None)
    run._save_manifest(m)
    _launch(run)
    return run

def load_board_data(run_id: str) -> bool:
    run = get(run_id)
    if run is None:
        return False
    if LAST.get("run_id") == run_id and LAST.get("df") is not None:
        return True
    cache = config.INTERIM / f"slice_{run.month}_{run.max_games or 'full'}.parquet"
    trials_path = run.dir / "trials.parquet"
    if not cache.is_file() or not trials_path.is_file():
        return False
    LAST.update(df=pd.read_parquet(cache), trials=pd.read_parquet(trials_path),
                month=run.month, run_id=run_id, comm=None)
    graph_path = run.dir / "graph_players.json"
    LAST["graph_players"] = (json.loads(graph_path.read_text(encoding="utf-8"))
                             if graph_path.is_file() else None)
    return True



# ------------------------------------------------------------------ pipeline
def _execute(run: Run):
    finished = threading.Event()

    def heartbeat():
        while not finished.is_set():
            run.heartbeat_path.write_text(str(time.time()), encoding="ascii")
            finished.wait(2)

    beat = threading.Thread(target=heartbeat, daemon=True)
    beat.start()
    try:
        _pipeline(run)
    except Exception as exc:
        # Keep diagnostics in the run folder; only a useful, safe summary reaches the page.
        (run.dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if "CERTIFICATE_VERIFY_FAILED" in str(exc) or "UNTRUSTED_ROOT" in str(exc):
            run.log("The archive connection could not be verified. Try a trusted connection or a saved data slice.", "error")
        else:
            run.log("This analysis stopped unexpectedly. Open Recent runs and choose Retry.", "error")
        run.emit("done", ok=False)
    finally:
        finished.set()
        beat.join(timeout=3)

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
        run.log(f"Loaded saved games from {run.month} "
                f"({len(df):,} games).", "ok")
        run.emit("scan", scanned=len(df), kept=len(df), rate=0, game=None)
        return _analyse(run, df)

    run.log("Opening the selected Lichess archive…")
    run.log("Reading games from the archive…")

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
        run.log("Saved these games for a faster repeat analysis.")
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
    trials.to_parquet(run.dir / "trials.parquet", index=False)
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
    (run.dir / "graph_players.json").write_text(
        json.dumps(LAST["graph_players"]), encoding="utf-8")
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
                "Compare the shuffled null before interpreting it.", "hl")
    run.stage("curve", "done")
    if run.stopped(): return _cancel(run)

    # ---------------- 5. null ----------------
    run.stage("null", "running", f"{run.null_reps} replicate(s)")
    run.log("Shuffling timestamps: keeps degree, ratings and popularity, "
            "destroys causal order.")
    null_by_d = nulls.run_null(df, n_reps=run.null_reps, kind="shuffle",
                               window_days=window, should_stop=run.stopped,
                               on_progress=lambda done, total: run.emit("null_progress", done=done, total=total))
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



if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker_run = Run.from_id(sys.argv[2])
        if worker_run is None:
            raise SystemExit("unknown run")
        _execute(worker_run)
