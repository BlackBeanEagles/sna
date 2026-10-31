"""Drives the real pipeline and emits structured progress events.

Same modules the CLI uses -- src.parse, src.events, src.structure, src.curve,
src.nulls, src.matching, src.predict -- against a live stream from
database.lichess.org. Nothing here is simulated.

Each run executes in a separate process and appends events to disk. The HTTP
server can restart while the worker continues, and browsers can replay events.
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import json  # Loads JSON tools for saved results and browser messages.
import os  # Loads code this file needs for the steps below.
import subprocess  # Loads code this file needs for the steps below.
import sys  # Loads code this file needs for the steps below.
import threading  # Loads code this file needs for the steps below.
import time  # Loads code this file needs for the steps below.
import traceback  # Loads code this file needs for the steps below.
import uuid  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

from src import config  # Loads the named parts of this project so this file can use their functions.
from src.fetch import BASE  # Loads code this file needs for the steps below.

RUNS_DIR = config.RESULTS / "runs"  # Saves a value named RUNS_DIR so the next lines can use it.
RUNS_DIR.mkdir(parents=True, exist_ok=True)  # Creates the folder needed for saved outputs.

# Months worth offering. Sizes are the compressed archive; a whole month is
# streamed and decompressed on the fly, never written to disk.
DEMO_MONTH = "demo-2016-01"  # Saves a value named DEMO_MONTH so the next lines can use it.
DEMO_FAST_MONTH = "demo-fast-2016-01"  # Saves a value named DEMO_FAST_MONTH so the next lines can use it.
BOARD_DEMO_ID = "board-demo"  # Saves a value named BOARD_DEMO_ID so the next lines can use it.
DEMO_SLICE = config.ROOT / "data" / "demo" / "january_2016_classroom_sample.parquet"  # Saves a value named DEMO_SLICE so the next lines can use it.
DEMO_SIZES = {DEMO_FAST_MONTH: 20_000, DEMO_MONTH: 60_000}  # Saves a value named DEMO_SIZES so the next lines can use it.
_BOARD_DEMO_CACHE: dict = {}  # Saves a value named _BOARD_DEMO_CACHE so the next lines can use it.

MONTHS = [  # Saves a value named MONTHS so the next lines can use it.
    {"id": DEMO_FAST_MONTH, "label": "January 2016 · fast presentation run", "mb": 2.4,  # Part of the value, collection, or call spanning several lines.
     "games": "20,000 sampled real"},
    {"id": DEMO_MONTH, "label": "January 2016 · quick live demo", "mb": 2.4,  # Part of the value, collection, or call spanning several lines.
     "games": "60,000 sampled real"},
    {"id": "2014-07", "label": "July 2014",    "mb": 200,  "games": "~1.0M"},  # Part of the value, collection, or call spanning several lines.
    {"id": "2015-01", "label": "January 2015", "mb": 285,  "games": "~1.5M"},  # Part of the value, collection, or call spanning several lines.
    {"id": "2015-07", "label": "July 2015",    "mb": 482,  "games": "~2.4M"},  # Part of the value, collection, or call spanning several lines.
    {"id": "2016-01", "label": "January 2016", "mb": 871,  "games": "~5.0M"},  # Part of the value, collection, or call spanning several lines.
]  # Closes the data structure or function call started above.

STAGES = [  # Saves a value named STAGES so the next lines can use it.
    ("stream",  "Stream & filter the archive"),  # Part of the value, collection, or call spanning several lines.
    ("trials",  "Build exposure / adoption trials"),  # Part of the value, collection, or call spanning several lines.
    ("network", "Network structure"),  # Part of the value, collection, or call spanning several lines.
    ("curve",   "Adoption-probability curve"),  # Part of the value, collection, or call spanning several lines.
    ("null",    "Timestamp-shuffled null"),  # Part of the value, collection, or call spanning several lines.
    ("matched", "Matched controls"),  # Part of the value, collection, or call spanning several lines.
    ("predict", "Group-held-out prediction (optional)"),  # Part of the value, collection, or call spanning several lines.
    ("verdict", "Verdict"),  # Part of the value, collection, or call spanning several lines.
]  # Closes the data structure or function call started above.

_RUNS: dict[str, "Run"] = {}  # Saves a value named _RUNS so the next lines can use it.

# The most recent successful run's data, kept so the interactive board can ask
# "what happened to THIS opening?" without re-streaming the archive.
LAST: dict = {"df": None, "trials": None, "month": None, "comm": None,  # Saves a value named LAST so the next lines can use it.
              "graph_players": None}


def board_state(sans: list[str], uci: str | None = None) -> dict:  # Replay a SAN list from the start position, optionally appending one move.
    """Replay a SAN list from the start position, optionally appending one move.

    Stateless by design: the client sends the whole (short) move list each time,
    so two people can share the board without the server tracking sessions.
    """
    import chess  # Loads chess rules so the board accepts only legal moves.

    board = chess.Board()  # Saves a value named board so the next lines can use it.
    played: list[str] = []  # Saves a value named played so the next lines can use it.
    for san in sans:  # Repeats the next indented steps once for each item.
        try:  # Starts an operation that may need error handling.
            board.push_san(san)  # Runs this instruction as part of the current step.
            played.append(san)  # Adds this item to the list being built.
        except Exception:  # Handles this specific failure without hiding other errors.
            break                                  # ignore a corrupt tail

    error = None  # Saves a value named error so the next lines can use it.
    if uci:  # Runs the next indented steps only when this condition is true.
        try:  # Starts an operation that may need error handling.
            mv = chess.Move.from_uci(uci)  # Saves a value named mv so the next lines can use it.
            if mv in board.legal_moves:  # Runs the next indented steps only when this condition is true.
                played.append(board.san(mv))  # Adds this item to the list being built.
                board.push(mv)  # Runs this instruction as part of the current step.
            else:  # Handles the alternative when the preceding condition was false.
                error = "illegal move"  # Saves a value named error so the next lines can use it.
        except Exception:  # Handles this specific failure without hiding other errors.
            error = "could not read that move"  # Saves a value named error so the next lines can use it.

    legal: dict[str, list[str]] = {}  # Saves a value named legal so the next lines can use it.
    for mv in board.legal_moves:  # Repeats the next indented steps once for each item.
        legal.setdefault(chess.square_name(mv.from_square), []).append(  # Part of the value, collection, or call spanning several lines.
            chess.square_name(mv.to_square))  # Runs this instruction as part of the current step.

    status = None  # Saves a value named status so the next lines can use it.
    if board.is_checkmate():  # Runs the next indented steps only when this condition is true.
        status = "checkmate"  # Saves a value named status so the next lines can use it.
    elif board.is_stalemate():  # Runs the next indented steps only when this condition is true.
        status = "stalemate"  # Saves a value named status so the next lines can use it.
    elif board.is_check():  # Runs the next indented steps only when this condition is true.
        status = "check"  # Saves a value named status so the next lines can use it.

    return {  # Gives this answer back to the code that called the function.
        "fen": board.fen(),
        "turn": "white" if board.turn else "black",
        "sans": played,
        "legal": legal,
        "status": status,
        "error": error,
        "opening": lookup_opening(played),
    }  # Closes the data structure or function call started above.


def lookup_opening(sans: list[str]) -> dict | None:  # Find what the loaded archive slice knows about the line being played.
    """Find what the loaded archive slice knows about the line being played.

    Matches on the SAN prefix, so the answer sharpens move by move: after 1.e4
    it reports every e4 game, after 1.e4 c5 only the Sicilians.
    """
    import pandas as pd  # Loads the table library used to store games and trials.

    df = LAST.get("df")  # Stores the game table for the next step.
    if df is None or not len(sans):  # Checks whether enough records exist for a trustworthy next step.
        return None  # Gives this answer back to the code that called the function.

    prefix = " ".join(sans)  # Saves a value named prefix so the next lines can use it.
    hit = df[df["ply_key"].str.startswith(prefix, na=False)]  # Saves a value named hit so the next lines can use it.
    if not len(hit):  # Checks whether enough records exist for a trustworthy next step.
        return {"matched": 0, "prefix": prefix, "ply": len(sans)}  # Gives this answer back to the code that called the function.

    top = hit.groupby(["eco", "opening"]).size().sort_values(ascending=False)  # Groups rows sharing these keys before counting or averaging them.
    (eco, name), n = top.index[0], int(top.iloc[0])  # Part of the value, collection, or call spanning several lines.
    # After a short prefix the leading ECO is only the commonest continuation,
    # not the name of the position: 1.e4 is not "the French Defense" just
    # because French games are the largest single group beneath it.
    top_share = n / len(hit)  # Saves a value named top_share so the next lines can use it.

    trials = LAST.get("trials")  # Stores the exposure-trial table for the next step.
    adoptions = exposures = 0  # Saves a value named adoptions so the next lines can use it.
    rate = None  # Saves a value named rate so the next lines can use it.
    if trials is not None and len(trials):  # Runs the next indented steps only when this condition is true.
        sub = trials[trials["opening"] == eco]  # Saves a value named sub so the next lines can use it.
        exposures = int(len(sub))  # Stores the encounter log keyed by player and behaviour for the next step.
        adoptions = int(sub["adopted"].sum())  # Saves a value named adoptions so the next lines can use it.
        rate = round(float(sub["adopted"].mean()), 4) if len(sub) else None  # Saves a value named rate so the next lines can use it.

    white = float((hit["result"] == "1-0").mean())  # Saves a value named white so the next lines can use it.
    black = float((hit["result"] == "0-1").mean())  # Saves a value named black so the next lines can use it.

    # Which drawn players relate to this line, as node indices the canvas can
    # light directly. Two different sets, and the distinction matters:
    #   played   - ever reached this position. High-degree players have played
    #              nearly everything, so 1.e4 lights up the whole graph.
    #   adopters - took the opening up for the first time AFTER being exposed
    #              to it. That is the contagion event, and it is the set worth
    #              looking at for clustering.
    graph_hits: list[int] = []  # Saves a value named graph_hits so the next lines can use it.
    graph_adopters: list[int] = []  # Saves a value named graph_adopters so the next lines can use it.
    drawn = LAST.get("graph_players")  # Saves a value named drawn so the next lines can use it.
    if drawn:  # Runs the next indented steps only when this condition is true.
        played_by = set(pd.unique(pd.concat([hit["white"], hit["black"]])))  # Saves a value named played_by so the next lines can use it.
        graph_hits = [i for i, p in enumerate(drawn) if p in played_by]  # Saves a value named graph_hits so the next lines can use it.
        if trials is not None and len(trials):  # Runs the next indented steps only when this condition is true.
            adopted_by = set(trials.loc[(trials["opening"] == eco)  # Saves a value named adopted_by so the next lines can use it.
                                        & (trials["adopted"] == 1), "player"])  # Runs this instruction as part of the current step.
            graph_adopters = [i for i, p in enumerate(drawn) if p in adopted_by]  # Saves a value named graph_adopters so the next lines can use it.
    return {  # Gives this answer back to the code that called the function.
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
                       for (e, nm), c in top.head(5).items()],  # Repeats the next indented steps once for each item.
        "graph_hits": graph_hits,
        "graph_adopters": graph_adopters,
        "graph_total": len(drawn) if drawn else 0,
    }  # Closes the data structure or function call started above.


class Run:  # One analysis attempt, with a manifest and append-only progress events.
    """One analysis attempt, with a manifest and append-only progress events.

    The manifest gives Recent runs its status. The JSONL event file lets a
    browser reopen a run and replay every stage after a refresh or disconnect.
    """
    def __init__(self, month: str, max_games: int | None, null_reps: int,  # Defines a reusable step; the following indented lines are its body.
                 window_days: int, refresh: bool = False,  # Saves a value named window_days so the next lines can use it.
                 predict: bool = True,  # Saves a value named predict so the next lines can use it.
                 run_id: str | None = None):  # Saves a value named run_id so the next lines can use it.
        self.id = run_id or uuid.uuid4().hex[:12]  # Saves a value named id so the next lines can use it.
        self.month = month  # Saves a value named month so the next lines can use it.
        self.max_games = max_games or None  # Saves a value named max_games so the next lines can use it.
        self.null_reps = max(1, min(20, null_reps))  # Saves a value named null_reps so the next lines can use it.
        self.window_days = window_days  # Saves a value named window_days so the next lines can use it.
        self.refresh = refresh  # Saves a value named refresh so the next lines can use it.
        self.predict = predict  # Saves a value named predict so the next lines can use it.
        self.dir = RUNS_DIR / self.id  # Saves a value named dir so the next lines can use it.
        self.dir.mkdir(parents=True, exist_ok=True)  # Creates the folder needed for saved outputs.
        self.events_path = self.dir / "events.jsonl"  # Saves a value named events_path so the next lines can use it.
        self.cancel_path = self.dir / "cancel"  # Saves a value named cancel_path so the next lines can use it.
        self.heartbeat_path = self.dir / "heartbeat"  # Saves a value named heartbeat_path so the next lines can use it.
        self.manifest_path = self.dir / "run.json"  # Saves a value named manifest_path so the next lines can use it.
        self.started = time.time()  # Saves a value named started so the next lines can use it.
        if run_id is None:  # Runs the next indented steps only when this condition is true.
            self._save_manifest({  # Part of the value, collection, or call spanning several lines.
                "id": self.id, "month": month, "max_games": self.max_games,
                "null_reps": self.null_reps, "window_days": window_days,
                "refresh": refresh, "predict": predict,
                "started": self.started,
                "status": "running",
            })  # Runs this instruction as part of the current step.
        else:  # Handles the alternative when the preceding condition was false.
            self.started = json.loads(self.manifest_path.read_text(  # Decodes saved JSON text into Python data.
                encoding="utf-8"))["started"]  # Saves a value named encoding so the next lines can use it.
        _RUNS[self.id] = self  # Stores this value under its player, opening, or field key.

    def _save_manifest(self, manifest: dict):  # Defines a reusable step; the following indented lines are its body.
        tmp = self.manifest_path.with_suffix(".tmp")  # Saves a value named tmp so the next lines can use it.
        tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")  # Encodes Python values as JSON for saving or sending to the browser.
        tmp.replace(self.manifest_path)  # Runs this instruction as part of the current step.

    @classmethod  # Configures the function or class immediately below it.
    def from_id(cls, run_id: str) -> "Run | None":  # Defines a reusable step; the following indented lines are its body.
        if len(run_id) != 12 or any(c not in "0123456789abcdef" for c in run_id):  # Runs the next indented steps only when this condition is true.
            return None  # Gives this answer back to the code that called the function.
        path = RUNS_DIR / run_id / "run.json"  # Saves a value named path so the next lines can use it.
        if not path.is_file():  # Runs the next indented steps only when this condition is true.
            return None  # Gives this answer back to the code that called the function.
        m = json.loads(path.read_text(encoding="utf-8"))  # Decodes saved JSON text into Python data.
        return cls(m["month"], m["max_games"], m["null_reps"],  # Gives this answer back to the code that called the function.
                   m["window_days"], m["refresh"],  # Part of the value, collection, or call spanning several lines.
                   predict=m.get("predict", True), run_id=run_id)  # Saves a value named predict so the next lines can use it.

    def emit(self, kind: str, **payload):  # Defines a reusable step; the following indented lines are its body.
        payload["kind"] = kind  # Stores this value under its player, opening, or field key.
        payload["t"] = round(time.time() - self.started, 1)  # Stores this value under its player, opening, or field key.
        with self.events_path.open("a", encoding="utf-8") as stream:  # Opens a resource and guarantees cleanup when the block ends.
            stream.write(json.dumps(payload, default=str) + "\n")  # Encodes Python values as JSON for saving or sending to the browser.
        if kind in ("stage", "done"):  # Runs the next indented steps only when this condition is true.
            m = json.loads(self.manifest_path.read_text(encoding="utf-8"))  # Decodes saved JSON text into Python data.
            if kind == "stage":  # Runs the next indented steps only when this condition is true.
                m["stage"] = payload["key"]  # Stores this value under its player, opening, or field key.
                m["stage_state"] = payload["state"]  # Stores this value under its player, opening, or field key.
            else:  # Handles the alternative when the preceding condition was false.
                m["status"] = ("completed" if payload.get("ok") else  # Stores this value under its player, opening, or field key.
                               "cancelled" if payload.get("cancelled") else "failed")
                m["finished"] = time.time()  # Stores this value under its player, opening, or field key.
            self._save_manifest(m)  # Runs this instruction as part of the current step.

    def log(self, msg: str, level: str = "info"):  # Defines a reusable step; the following indented lines are its body.
        self.emit("log", msg=msg, level=level)  # Runs this instruction as part of the current step.

    def stage(self, key: str, state: str, detail: str = ""):  # Defines a reusable step; the following indented lines are its body.
        self.emit("stage", key=key, state=state, detail=detail)  # Runs this instruction as part of the current step.

    def cancel(self):  # Defines a reusable step; the following indented lines are its body.
        self.cancel_path.touch()  # Runs this instruction as part of the current step.

    def stopped(self) -> bool:  # Defines a reusable step; the following indented lines are its body.
        return self.cancel_path.exists()  # Gives this answer back to the code that called the function.


def get(run_id: str) -> Run | None:  # Defines a reusable step; the following indented lines are its body.
    return _RUNS.get(run_id) or Run.from_id(run_id)  # Gives this answer back to the code that called the function.


def current_status(manifest: dict) -> str:  # Defines a reusable step; the following indented lines are its body.
    status = manifest.get("status", "unknown")  # Saves a value named status so the next lines can use it.
    if status != "running":  # Runs the next indented steps only when this condition is true.
        return status  # Gives this answer back to the code that called the function.
    heartbeat = RUNS_DIR / manifest["id"] / "heartbeat"  # Saves a value named heartbeat so the next lines can use it.
    if time.time() - manifest["started"] > 12:  # Runs the next indented steps only when this condition is true.
        if not heartbeat.is_file() or time.time() - heartbeat.stat().st_mtime > 12:  # Runs the next indented steps only when this condition is true.
            return "interrupted"  # Gives this answer back to the code that called the function.
    return status  # Gives this answer back to the code that called the function.

def list_runs(limit: int = 20) -> list[dict]:  # Defines a reusable step; the following indented lines are its body.
    manifests = sorted(RUNS_DIR.glob("*/run.json"),  # Saves a value named manifests so the next lines can use it.
                       key=lambda p: p.stat().st_mtime, reverse=True)  # Saves a value named key so the next lines can use it.
    out = []  # Stores the output value for the next step.
    for path in manifests[:limit]:  # Repeats the next indented steps once for each item.
        m = json.loads(path.read_text(encoding="utf-8"))  # Decodes saved JSON text into Python data.
        m["status"] = current_status(m)  # Stores this value under its player, opening, or field key.
        out.append(m)  # Adds this item to the list being built.
    return out  # Gives this answer back to the code that called the function.


def _launch(run: Run):  # Start the computation in a separate process from the web server.
    """Start the computation in a separate process from the web server."""
    flags = 0  # Saves a value named flags so the next lines can use it.
    if os.name == "nt":  # Runs the next indented steps only when this condition is true.
        flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # Saves a value named flags so the next lines can use it.
                 | subprocess.CREATE_NEW_PROCESS_GROUP)  # Runs this instruction as part of the current step.
    with (run.dir / "worker.log").open("ab") as log:  # Opens a resource and guarantees cleanup when the block ends.
        proc = subprocess.Popen(  # Saves a value named proc so the next lines can use it.
            [sys.executable, "-m", "server.runner", "--worker", run.id],  # Part of the value, collection, or call spanning several lines.
            cwd=str(config.ROOT), stdout=log, stderr=subprocess.STDOUT,  # Saves a value named cwd so the next lines can use it.
            creationflags=flags, close_fds=True)  # Saves a value named creationflags so the next lines can use it.
    m = json.loads(run.manifest_path.read_text(encoding="utf-8"))  # Decodes saved JSON text into Python data.
    m["pid"] = proc.pid  # Stores this value under its player, opening, or field key.
    run._save_manifest(m)  # Runs this instruction as part of the current step.


def start(month: str, max_games: int | None, null_reps: int,  # Defines a reusable step; the following indented lines are its body.
          window_days: int, refresh: bool = False,  # Saves a value named window_days so the next lines can use it.
          predict: bool = True) -> Run:  # Saves a value named predict so the next lines can use it.
    run = Run(month, max_games, null_reps, window_days, refresh, predict)  # Stores the current analysis run for the next step.
    _launch(run)  # Runs this instruction as part of the current step.
    return run  # Gives this answer back to the code that called the function.


def resume(run_id: str) -> Run | None:  # Defines a reusable step; the following indented lines are its body.
    run = get(run_id)  # Stores the current analysis run for the next step.
    if run is None:  # Runs the next indented steps only when this condition is true.
        return None  # Gives this answer back to the code that called the function.
    m = json.loads(run.manifest_path.read_text(encoding="utf-8"))  # Decodes saved JSON text into Python data.
    if current_status(m) not in ("interrupted", "failed"):  # Runs the next indented steps only when this condition is true.
        return None  # Gives this answer back to the code that called the function.
    if run.events_path.exists():  # Runs the next indented steps only when this condition is true.
        attempt = int(m.get("attempt", 1))  # Saves a value named attempt so the next lines can use it.
        run.events_path.rename(run.dir / f"events_attempt_{attempt}.jsonl")  # Runs this instruction as part of the current step.
        m["attempt"] = attempt + 1  # Stores this value under its player, opening, or field key.
    run.cancel_path.unlink(missing_ok=True)  # Runs this instruction as part of the current step.
    run.heartbeat_path.unlink(missing_ok=True)  # Runs this instruction as part of the current step.
    run.started = time.time()  # Saves a value named started so the next lines can use it.
    m.update(started=run.started, status="running")  # Adds this item to the collection being built.
    m.pop("finished", None)  # Runs this instruction as part of the current step.
    m.pop("stage", None)  # Runs this instruction as part of the current step.
    m.pop("stage_state", None)  # Runs this instruction as part of the current step.
    run._save_manifest(m)  # Runs this instruction as part of the current step.
    _launch(run)  # Runs this instruction as part of the current step.
    return run  # Gives this answer back to the code that called the function.

def load_board_data(run_id: str) -> bool:  # Defines a reusable step; the following indented lines are its body.
    import pandas as pd  # Loads the table library used to store games and trials.

    if run_id == BOARD_DEMO_ID:  # Runs the next indented steps only when this condition is true.
        board_demo_payload()  # Loads saved real games for the board without starting a new analysis.
        return True  # Gives this answer back to the code that called the function.
    run = get(run_id)  # Stores the current analysis run for the next step.
    if run is None:  # Runs the next indented steps only when this condition is true.
        return False  # Gives this answer back to the code that called the function.
    if LAST.get("run_id") == run_id and LAST.get("df") is not None:  # Runs the next indented steps only when this condition is true.
        return True  # Gives this answer back to the code that called the function.
    cache = (DEMO_SLICE if run.month in DEMO_SIZES else  # Saves a value named cache so the next lines can use it.
             config.INTERIM / f"slice_{run.month}_{run.max_games or 'full'}.parquet")  # Runs this instruction as part of the current step.
    trials_path = run.dir / "trials.parquet"  # Saves a value named trials_path so the next lines can use it.
    if not cache.is_file() or not trials_path.is_file():  # Runs the next indented steps only when this condition is true.
        return False  # Gives this answer back to the code that called the function.
    games = pd.read_parquet(cache)  # Loads a previously prepared game or trial table.
    if run.month == DEMO_FAST_MONTH:  # Runs the next indented steps only when this condition is true.
        games = games.sample(n=DEMO_SIZES[run.month], random_state=config.RANDOM_SEED).sort_values("ts").reset_index(drop=True)  # Orders the rows by this field before the next calculation.
    LAST.update(df=games, trials=pd.read_parquet(trials_path),  # Loads a previously prepared game or trial table.
                month=run.month, run_id=run_id, comm=None)  # Saves a value named month so the next lines can use it.
    graph_path = run.dir / "graph_players.json"  # Saves a value named graph_path so the next lines can use it.
    LAST["graph_players"] = (json.loads(graph_path.read_text(encoding="utf-8"))  # Decodes saved JSON text into Python data.
                             if graph_path.is_file() else None)  # Runs the next indented steps only when this condition is true.
    return True  # Gives this answer back to the code that called the function.


def board_demo_payload() -> dict:  # Loads saved real games for the board without starting a new analysis.
    """Load real January games for board interaction without a pipeline run.

    First-use trials are calculated once for the opening counts. Structural
    diversity is omitted here because the board does not display it; the
    full analysis still computes it in the ordinary pipeline.

    Say to the teacher: the board checks real saved games immediately. Moving
    a piece does not start the complete statistical study again.
    """
    import pandas as pd  # Loads the table library used to store games and trials.
    from src import events  # Loads the named parts of this project so this file can use their functions.

    if not _BOARD_DEMO_CACHE:  # Runs the next indented steps only when this condition is true.
        games = pd.read_parquet(DEMO_SLICE)  # Loads a previously prepared game or trial table.
        trials = events.build_trials(games, with_diversity=False)  # Stores the exposure-trial table for the next step.
        _BOARD_DEMO_CACHE.update(  # Part of the value, collection, or call spanning several lines.
            df=games, trials=trials,  # Stores the game table for the next step.
            openings=_openings_payload(games, trials),  # Saves a value named openings so the next lines can use it.
            players=len(set(games["white"]) | set(games["black"])),  # Saves a value named players so the next lines can use it.
        )  # Closes the data structure or function call started above.
    LAST.update(df=_BOARD_DEMO_CACHE["df"], trials=_BOARD_DEMO_CACHE["trials"],  # Part of the value, collection, or call spanning several lines.
                month="January 2016 board demo", run_id=BOARD_DEMO_ID,  # Saves a value named month so the next lines can use it.
                comm=None, graph_players=None)  # Saves a value named comm so the next lines can use it.
    return {"games": len(_BOARD_DEMO_CACHE["df"]),  # Gives this answer back to the code that called the function.
            "players": _BOARD_DEMO_CACHE["players"],
            "openings": _BOARD_DEMO_CACHE["openings"]["openings"]}



# ------------------------------------------------------------------ pipeline
def _execute(run: Run):  # Defines a reusable step; the following indented lines are its body.
    finished = threading.Event()  # Saves a value named finished so the next lines can use it.

    def heartbeat():  # Defines a reusable step; the following indented lines are its body.
        while not finished.is_set():  # Repeats the indented block until this condition stops holding.
            run.heartbeat_path.write_text(str(time.time()), encoding="ascii")  # Saves this result so it can be inspected or reused.
            finished.wait(2)  # Runs this instruction as part of the current step.

    beat = threading.Thread(target=heartbeat, daemon=True)  # Saves a value named beat so the next lines can use it.
    beat.start()  # Runs this instruction as part of the current step.
    try:  # Starts an operation that may need error handling.
        _pipeline(run)  # Runs this instruction as part of the current step.
    except Exception as exc:  # Handles this specific failure without hiding other errors.
        # Keep diagnostics in the run folder; only a useful, safe summary reaches the page.
        (run.dir / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")  # Part of the value, collection, or call spanning several lines.
        if "CERTIFICATE_VERIFY_FAILED" in str(exc) or "UNTRUSTED_ROOT" in str(exc):  # Runs the next indented steps only when this condition is true.
            run.log("The archive connection could not be verified. Try a trusted connection or a saved data slice.", "error")  # Adds a short explanation to the live progress log.
        else:  # Handles the alternative when the preceding condition was false.
            run.log("This analysis stopped unexpectedly. Open Recent runs and choose Retry.", "error")  # Adds a short explanation to the live progress log.
        run.emit("done", ok=False)  # Appends a structured progress event that the browser can replay.
    finally:  # Runs cleanup whether the operation succeeds or fails.
        finished.set()  # Runs this instruction as part of the current step.
        beat.join(timeout=3)  # Runs this instruction as part of the current step.

def _pipeline(run: Run):  # Load a real game slice, using the bundled sample for classroom demos.
    """Load a real game slice, using the bundled sample for classroom demos.

    The demo sample still runs the analysis; it only skips network downloading
    and avoids depending on a classroom internet connection.
    """
    import pandas as pd  # Loads the table library used to store games and trials.
    from src import parse  # Loads the named parts of this project so this file can use their functions.

    url = "bundled real January 2016 sample" if run.month in DEMO_SIZES else BASE.format(month=run.month)  # Saves a value named url so the next lines can use it.
    run.emit("init", stages=[{"key": k, "label": l} for k, l in STAGES],  # Appends a structured progress event that the browser can replay.
             month=run.month, url=url, max_games=run.max_games)  # Saves a value named month so the next lines can use it.

    # ---------------- 1. stream & filter ----------------
    run.stage("stream", "running")  # Sets the status shown in the live stage list.
    if run.month in DEMO_SIZES:  # Runs the next indented steps only when this condition is true.
        df = pd.read_parquet(DEMO_SLICE)  # Loads a previously prepared game or trial table.
        if run.month == DEMO_FAST_MONTH:  # Runs the next indented steps only when this condition is true.
            # A reproducible subset keeps the full month of dates while making
            # the in-class run shorter; the detailed option still uses 60,000.
            df = df.sample(n=DEMO_SIZES[run.month], random_state=config.RANDOM_SEED).sort_values("ts").reset_index(drop=True)  # Orders the rows by this field before the next calculation.
        df.attrs["skipped"] = {}  # Stores this value under its player, opening, or field key.
        run.log(f"Loaded {len(df):,} real January 2016 games from the bundled classroom sample.", "ok")  # Adds a short explanation to the live progress log.
        run.emit("scan", scanned=len(df), kept=len(df), rate=0, game=None)  # Appends a structured progress event that the browser can replay.
        return _analyse(run, df)  # Gives this answer back to the code that called the function.

    # A parsed slice is cached so a second demo of the same month is instant.
    # Lichess throttles repeated downloads, and a stalled stream in front of an
    # audience is the one failure worth engineering away.
    cache = config.INTERIM / f"slice_{run.month}_{run.max_games or 'full'}.parquet"  # Saves a value named cache so the next lines can use it.
    if cache.exists() and not run.refresh:  # Runs the next indented steps only when this condition is true.
        df = pd.read_parquet(cache)  # Loads a previously prepared game or trial table.
        df.attrs["skipped"] = {}       # filters already applied when it was cached
        run.log(f"Loaded saved games from {run.month} "  # Adds a short explanation to the live progress log.
                f"({len(df):,} games).", "ok")  # Runs this instruction as part of the current step.
        run.emit("scan", scanned=len(df), kept=len(df), rate=0, game=None)  # Appends a structured progress event that the browser can replay.
        return _analyse(run, df)  # Gives this answer back to the code that called the function.

    run.log("Opening the selected Lichess archive…")  # Adds a short explanation to the live progress log.
    run.log("Reading games from the archive…")  # Adds a short explanation to the live progress log.

    last = {"t": 0.0}  # Saves a value named last so the next lines can use it.

    def on_progress(scanned, kept, row=None):  # Defines a reusable step; the following indented lines are its body.
        now = time.time()  # Saves a value named now so the next lines can use it.
        if now - last["t"] < 0.4:                  # don't flood the socket
            return  # Stops this function here.
        last["t"] = now  # Stores this value under its player, opening, or field key.
        rate = scanned / max(1e-6, now - run.started)  # Saves a value named rate so the next lines can use it.
        game = None  # Saves a value named game so the next lines can use it.
        if row is not None:  # Runs the next indented steps only when this condition is true.
            # row order matches parse.parse's tuple
            game = {"white_elo": row[4], "black_elo": row[5], "eco": row[6],  # Saves a value named game so the next lines can use it.
                    "opening": row[7], "moves": " ".join(str(row[8]).split()[:6]),
                    "speed": row[9], "result": row[10]}
        run.emit("scan", scanned=scanned, kept=kept, rate=round(rate), game=game)  # Appends a structured progress event that the browser can replay.

    df = parse.parse(url, limit=run.max_games, progress=20000,  # Stores the game table for the next step.
                     on_progress=on_progress, should_stop=run.stopped)  # Saves a value named on_progress so the next lines can use it.

    if run.stopped():  # Stops the analysis when the user has cancelled the live run.
        run.log("Cancelled.", "warn")  # Adds a short explanation to the live progress log.
        run.emit("done", ok=False, cancelled=True)  # Appends a structured progress event that the browser can replay.
        return  # Stops this function here.
    if len(df) < 200:  # Checks whether enough records exist for a trustworthy next step.
        run.stage("stream", "failed")  # Sets the status shown in the live stage list.
        run.log(f"Only {len(df)} games survived the filters — "  # Adds a short explanation to the live progress log.
                "not enough to analyse. Try a larger cap or another month.", "error")
        run.emit("done", ok=False)  # Appends a structured progress event that the browser can replay.
        return  # Stops this function here.

    try:  # Starts an operation that may need error handling.
        df.to_parquet(cache, index=False)  # Saves a compact table for later analysis stages.
        run.log("Saved these games for a faster repeat analysis.")  # Adds a short explanation to the live progress log.
    except Exception:  # Handles this specific failure without hiding other errors.
        pass                                   # a cache failure must not kill the run

    return _analyse(run, df)  # Gives this answer back to the code that called the function.


def _analyse(run: "Run", df):  # Execute the same research stages as the CLI and emit UI events.
    """Execute the same research stages as the CLI and emit UI events.

    Follow this method during a demo: trials -> graph -> curve -> shuffled
    reference -> matched controls -> optional prediction -> verdict.
    In plain words: count encounters, draw player links, measure later use,
    compare it with shuffled dates and similar players, then give a verdict.
    """
    import pandas as pd  # Loads the table library used to store games and trials.
    # Keep the first visible readings responsive on a cold classroom laptop.
    # The predictive model imports scikit-learn only when that final stage starts.
    from src import curve, events as ev, matching, nulls, structure  # Loads the named parts of this project so this file can use their functions.

    span_days = (df["ts"].max() - df["ts"].min()).total_seconds() / 86400  # Saves a value named span_days so the next lines can use it.
    players = len(set(df["white"]) | set(df["black"]))  # Saves a value named players so the next lines can use it.
    skipped = df.attrs.get("skipped", {})  # Saves a value named skipped so the next lines can use it.
    run.emit("sample", games=len(df), players=players,  # Appends a structured progress event that the browser can replay.
             openings=int(df["eco"].nunique()), span_days=round(span_days, 2),  # Saves a value named openings so the next lines can use it.
             t0=str(df["ts"].min()), t1=str(df["ts"].max()), skipped=skipped)  # Stores the exposure time for the next step.
    run.stage("stream", "done", f"{len(df):,} games · {players:,} players")  # Sets the status shown in the live stage list.

    # The adoption window has to fit inside the observed span, or every trial
    # is censored. A capped slice covers only the first hours of the month.
    window = run.window_days  # Stores the time allowed for a later first use for the next step.
    if span_days < window * 2.2:  # Runs the next indented steps only when this condition is true.
        window = max(1, int(span_days / 2.2))  # Stores the time allowed for a later first use for the next step.
        run.log(f"Slice spans {span_days:.1f} days, so the adoption window is "  # Adds a short explanation to the live progress log.
                f"reduced from {run.window_days} to {window} day(s) — "  # Runs this instruction as part of the current step.
                "otherwise every trial would be censored.", "warn")
        run.emit("window", days=window, auto=True)  # Appends a structured progress event that the browser can replay.
    else:  # Handles the alternative when the preceding condition was false.
        run.emit("window", days=window, auto=False)  # Appends a structured progress event that the browser can replay.

    # ---------------- 2. trials ----------------
    run.stage("trials", "running")  # Sets the status shown in the live stage list.
    trials = ev.build_trials(df, window_days=window)  # Stores the exposure-trial table for the next step.
    trials.to_parquet(run.dir / "trials.parquet", index=False)  # Saves a compact table for later analysis stages.
    if not len(trials) or trials["adopted"].sum() < 30:  # Checks whether enough records exist for a trustworthy next step.
        run.stage("trials", "failed")  # Sets the status shown in the live stage list.
        run.log(f"Only {len(trials)} trials / "  # Adds a short explanation to the live progress log.
                f"{int(trials['adopted'].sum()) if len(trials) else 0} adoptions. "  # Runs this instruction as part of the current step.
                "Widen the sample.", "error")
        run.emit("done", ok=False)  # Appends a structured progress event that the browser can replay.
        return  # Stops this function here.
    run.emit("trials", n=int(len(trials)), adoptions=int(trials["adopted"].sum()),  # Appends a structured progress event that the browser can replay.
             rate=round(float(trials["adopted"].mean()), 4))  # Saves a value named rate so the next lines can use it.
    # make this slice queryable by the interactive board
    LAST["df"], LAST["trials"], LAST["month"] = df, trials, run.month  # Stores this value under its player, opening, or field key.
    run.emit("board_ready", month=run.month, games=int(len(df)))  # Appends a structured progress event that the browser can replay.
    run.emit("openings", **_openings_payload(df, trials))  # Appends a structured progress event that the browser can replay.
    run.stage("trials", "done", f"{len(trials):,} trials")  # Sets the status shown in the live stage list.
    if run.stopped(): return _cancel(run)  # Stops the analysis when the user has cancelled the live run.

    # ---------------- 3. network ----------------
    run.stage("network", "running")  # Sets the status shown in the live stage list.
    g = structure.build_graph(df)  # Connects players who faced each other in the selected games.
    feats = structure.node_features(g, betweenness_k=40 if run.month == DEMO_FAST_MONTH else 200)  # Stores the network features for the next step.
    early = structure.early_adopters(df).merge(feats, on="player", how="left")  # Joins two tables on shared identifiers so their columns can be compared.
    by_early = early.groupby("is_early")[["degree", "kcore", "betweenness"]].mean()  # Groups rows sharing these keys before counting or averaging them.
    run.emit("network",  # Appends a structured progress event that the browser can replay.
             nodes=g.number_of_nodes(), edges=g.number_of_edges(),  # Saves a value named nodes so the next lines can use it.
             communities=int(feats.attrs["n_communities"]),  # Saves a value named communities so the next lines can use it.
             modularity=round(float(feats.attrs["modularity"]), 4),  # Saves a value named modularity so the next lines can use it.
             early=_early_payload(by_early))  # Saves a value named early so the next lines can use it.
    run.emit("graph", **_graph_payload(g, feats, early))  # Appends a structured progress event that the browser can replay.
    (run.dir / "graph_players.json").write_text(  # Part of the value, collection, or call spanning several lines.
        json.dumps(LAST["graph_players"]), encoding="utf-8")  # Encodes Python values as JSON for saving or sending to the browser.
    run.stage("network", "done",  # Sets the status shown in the live stage list.
              f"{g.number_of_nodes():,} nodes · Q={feats.attrs['modularity']:.3f}")  # Runs this instruction as part of the current step.
    if run.stopped(): return _cancel(run)  # Stops the analysis when the user has cancelled the live run.

    # ---------------- 4. curve ----------------
    run.stage("curve", "running")  # Sets the status shown in the live stage list.
    tables = curve.analyse(trials)  # Calculates adoption rates for different exposure counts.
    run.emit("curve", by_d=_rows(tables["by_d"]), held_k=_rows(tables["held_k_by_d"]))  # Appends a structured progress event that the browser can replay.
    top = tables["by_d"]  # Saves a value named top so the next lines can use it.
    if len(top) >= 2:  # Runs the next indented steps only when this condition is true.
        lift = top.iloc[-1]["rate"] / top.iloc[0]["rate"] if top.iloc[0]["rate"] else 0  # Saves a value named lift so the next lines can use it.
        run.log(f"Raw curve rises {top.iloc[0]['rate']:.3f} → "  # Adds a short explanation to the live progress log.
                f"{top.iloc[-1]['rate']:.3f} (×{lift:.2f}). "  # Runs this instruction as part of the current step.
                "Compare the shuffled null before interpreting it.", "hl")
    run.stage("curve", "done")  # Sets the status shown in the live stage list.
    if run.stopped(): return _cancel(run)  # Stops the analysis when the user has cancelled the live run.

    # ---------------- 5. null ----------------
    run.stage("null", "running", f"{run.null_reps} replicate(s)")  # Sets the status shown in the live stage list.
    run.log("Shuffling timestamps: keeps degree, ratings and popularity, "  # Adds a short explanation to the live progress log.
            "destroys causal order.")
    null_by_d = nulls.run_null(df, n_reps=run.null_reps, kind="shuffle",  # Stores the reference rates grouped by different opponents for the next step.
                               window_days=window, should_stop=run.stopped,  # Saves a value named window_days so the next lines can use it.
                               on_progress=lambda done, total: run.emit("null_progress", done=done, total=total))  # Appends a structured progress event that the browser can replay.
    cmp = nulls.compare(tables["by_d"], null_by_d) if len(null_by_d) else pd.DataFrame()  # Creates a labelled table from the collected rows.
    run.emit("null", rows=_rows(cmp))  # Appends a structured progress event that the browser can replay.
    run.stage("null", "done")  # Sets the status shown in the live stage list.
    if run.stopped(): return _cancel(run)  # Stops the analysis when the user has cancelled the live run.

    # ---------------- 6. matched controls ----------------
    run.stage("matched", "running")  # Sets the status shown in the live stage list.
    pairs = matching.build_matched(df, max_trials=15000 if run.month == DEMO_FAST_MONTH else 60000, window_days=window)  # Stores the matched exposed and unexposed player pairs for the next step.
    msum = matching.summarise(pairs)  # Stores the summary of the matched comparison for the next step.
    run.emit("matched", **msum)  # Appends a structured progress event that the browser can replay.
    run.stage("matched", "done",  # Sets the status shown in the live stage list.
              (f"+{msum['difference']*100:.2f} pp" if msum.get("n_pairs") else "no pairs"))  # Part of the value, collection, or call spanning several lines.
    if run.stopped(): return _cancel(run)  # Stops the analysis when the user has cancelled the live run.

    # ---------------- 7. prediction ----------------
    if run.predict:  # Runs the slower prediction check only when the presenter chooses it.
        run.stage("predict", "running")  # Sets the status shown in the live stage list.
        from src import predict  # Loads the named parts of this project so this file can use their functions.
        # same code path as the CLI: features rebuilt from the training window
        pred = predict.evaluate(df, trials, full=False)  # Stores the held-out prediction results for the next step.
        run.emit("predict", **pred)  # Appends a structured progress event that the browser can replay.
        if "error" in pred:  # Runs the next indented steps only when this condition is true.
            run.stage("predict", "skipped", "insufficient variation")  # Sets the status shown in the live stage list.
        else:  # Handles the alternative when the preceding condition was false.
            run.log(pred["reading"], "hl")  # Adds a short explanation to the live progress log.
            run.stage("predict", "done",  # Sets the status shown in the live stage list.
                      f"repertoire {pred['gain_repertoire_over_baseline']:+.3f} "  # Runs this instruction as part of the current step.
                      f"vs network {pred['gain_network_over_repertoire']:+.3f}")  # Runs this instruction as part of the current step.
    else:  # Handles the alternative when the preceding condition was false.
        run.stage("predict", "skipped", "optional model not selected")  # Sets the status shown in the live stage list.

    # ---------------- 8. verdict ----------------
    run.stage("verdict", "running")  # Sets the status shown in the live stage list.
    v = curve.verdict(tables, cmp if len(cmp) else None)  # Applies the result rules to the real and shuffled curves.
    run.emit("verdict", **v)  # Appends a structured progress event that the browser can replay.
    run.stage("verdict", "done")  # Sets the status shown in the live stage list.
    run.log("Run complete.", "ok")  # Adds a short explanation to the live progress log.
    run.emit("done", ok=True, seconds=round(time.time() - run.started, 1))  # Appends a structured progress event that the browser can replay.


def _cancel(run: Run):  # Defines a reusable step; the following indented lines are its body.
    run.log("Cancelled.", "warn")  # Adds a short explanation to the live progress log.
    run.emit("done", ok=False, cancelled=True)  # Appends a structured progress event that the browser can replay.


def _openings_payload(df: pd.DataFrame, trials: pd.DataFrame | None = None,  # The openings actually present in this slice, each with the real board positions of its opening line.
                      top: int = 10) -> dict:  # Saves a value named top so the next lines can use it.
    """The openings actually present in this slice, each with the real board
    positions of its opening line.

    The SAN is replayed through python-chess here rather than in the browser:
    the page then only has to draw a FEN, and the positions are guaranteed
    legal rather than reconstructed by hand.
    """
    import chess  # Loads chess rules so the board accepts only legal moves.

    counts = df.groupby(["eco", "opening"]).size().sort_values(ascending=False)  # Groups rows sharing these keys before counting or averaging them.
    adopt = {}  # Saves a value named adopt so the next lines can use it.
    if trials is not None and len(trials):  # Runs the next indented steps only when this condition is true.
        a = trials[trials["adopted"] == 1].groupby("opening").size()  # Groups rows sharing these keys before counting or averaging them.
        adopt = a.to_dict()  # Converts table values into JSON-friendly records for a report or UI event.

    out = []  # Stores the output value for the next step.
    for (eco, name), n in counts.head(top).items():  # Repeats the next indented steps once for each item.
        line = df.loc[(df["eco"] == eco) & (df["opening"] == name), "ply_key"]  # Saves a value named line so the next lines can use it.
        sans = str(line.mode().iloc[0]).split() if len(line) else []  # Stores the moves written in chess notation for the next step.
        board, fens, played = chess.Board(), [chess.Board().fen()], []  # Runs this instruction as part of the current step.
        for san in sans[:8]:  # Repeats the next indented steps once for each item.
            try:  # Starts an operation that may need error handling.
                board.push_san(san)  # Runs this instruction as part of the current step.
            except Exception:  # Handles this specific failure without hiding other errors.
                break                       # truncated or ambiguous SAN: stop here
            played.append(san)  # Adds this item to the list being built.
            fens.append(board.fen())  # Adds this item to the list being built.
        out.append({"eco": eco, "name": name or eco, "games": int(n),  # Part of the value, collection, or call spanning several lines.
                    "adoptions": int(adopt.get(eco, 0)),
                    "sans": played, "fens": fens})
    return {"openings": out}  # Gives this answer back to the code that called the function.


def _graph_payload(g, feats, early, max_nodes: int = 240,  # A drawable subsample of the interaction network: the highest-degree nodes plus the heaviest edges among them.
                   max_edges: int = 1400) -> dict:  # Saves a value named max_edges so the next lines can use it.
    """A drawable subsample of the interaction network: the highest-degree
    nodes plus the heaviest edges among them. The full graph has tens of
    thousands of edges -- far past what a browser force layout can move."""
    deg = dict(g.degree())  # Saves a value named deg so the next lines can use it.
    keep = [n for n, _ in sorted(deg.items(), key=lambda kv: -kv[1])[:max_nodes]]  # Saves a value named keep so the next lines can use it.
    idx = {n: i for i, n in enumerate(keep)}  # Saves a value named idx so the next lines can use it.
    # remember the draw order so the board can map players -> node indices
    LAST["graph_players"] = keep  # Stores this value under its player, opening, or field key.

    comm = dict(zip(feats["player"], feats["community"]))  # Saves a value named comm so the next lines can use it.
    early_set = set(early.loc[early["is_early"] == 1, "player"]) if len(early) else set()  # Saves a value named early_set so the next lines can use it.

    edges = []  # Saves a value named edges so the next lines can use it.
    for u, v, data in g.subgraph(keep).edges(data=True):  # Repeats the next indented steps once for each item.
        edges.append((idx[u], idx[v], int(data.get("games", 1))))  # Adds this item to the list being built.
    edges.sort(key=lambda e: -e[2])  # Runs this instruction as part of the current step.
    edges = edges[:max_edges]  # Saves a value named edges so the next lines can use it.

    return {  # Gives this answer back to the code that called the function.
        "nodes": [{"d": int(deg[n]), "c": int(comm.get(n, 0)),
                   "e": 1 if n in early_set else 0} for n in keep],
        "edges": [[e[0], e[1]] for e in edges],
        "total_nodes": g.number_of_nodes(),
        "total_edges": g.number_of_edges(),
    }  # Closes the data structure or function call started above.


def _early_payload(by_early) -> dict:  # Defines a reusable step; the following indented lines are its body.
    out = {}  # Stores the output value for the next step.
    for flag in (0, 1):  # Repeats the next indented steps once for each item.
        if flag in by_early.index:  # Runs the next indented steps only when this condition is true.
            r = by_early.loc[flag]  # Saves a value named r so the next lines can use it.
            out["early" if flag else "rest"] = {  # Part of the value, collection, or call spanning several lines.
                "degree": round(float(r["degree"]), 2),
                "kcore": round(float(r["kcore"]), 2),
                "betweenness": round(float(r["betweenness"]), 6),
            }  # Closes the data structure or function call started above.
    return out  # Gives this answer back to the code that called the function.


def _rows(df: pd.DataFrame) -> list[dict]:  # Defines a reusable step; the following indented lines are its body.
    if df is None or not len(df):  # Checks whether enough records exist for a trustworthy next step.
        return []  # Gives this answer back to the code that called the function.
    clean = df.replace({float("nan"): None})  # Saves a value named clean so the next lines can use it.
    return clean.to_dict(orient="records")  # Converts table values into JSON-friendly records for a report or UI event.



if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":  # Runs the next indented steps only when this condition is true.
        worker_run = Run.from_id(sys.argv[2])  # Saves a value named worker_run so the next lines can use it.
        if worker_run is None:  # Runs the next indented steps only when this condition is true.
            raise SystemExit("unknown run")  # Stops with an explicit error when this requirement is violated.
        _execute(worker_run)  # Runs this instruction as part of the current step.
