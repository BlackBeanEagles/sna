"""Step 2 -- PGN -> one Parquet event table. Nothing downstream re-reads PGN.

A hand-rolled header scanner, not python-chess's full game parser: on a real
Lichess month we need millions of games/minute, and we only ever want the
headers plus the first few plies. Handles plain .pgn and zstd-compressed
.pgn.zst transparently.

Row schema:
    game_id, ts, white, black, white_rating, black_rating,
    eco, opening, ply_key, speed, result
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import io  # Loads code this file needs for the steps below.
import re  # Loads pattern matching for text in game records.
import sys  # Loads code this file needs for the steps below.
from collections import Counter  # Loads containers for counting or collecting game records.
from datetime import datetime  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.

from . import config  # Loads the named parts of this project so this file can use their functions.

TAG_RE = re.compile(r'^\[([A-Za-z0-9_]+)\s+"(.*)"\]\s*$')  # Saves a value named TAG_RE so the next lines can use it.
# strip move numbers, clock comments, NAGs, evals and result tokens
CLEAN_RE = re.compile(r"\{[^}]*\}|\$\d+|\d+\.(\.\.)?|[?!]+|1-0|0-1|1/2-1/2|\*")  # Saves a value named CLEAN_RE so the next lines can use it.

WANTED = ("Event", "Site", "White", "Black", "Result", "UTCDate", "UTCTime",  # Saves a value named WANTED so the next lines can use it.
          "WhiteElo", "BlackElo", "ECO", "Opening", "TimeControl", "Termination")


def _open(path):  # Text stream over a local .pgn, a local .pgn.zst, or a remote .pgn.zst URL.
    """Text stream over a local .pgn, a local .pgn.zst, or a remote .pgn.zst
    URL. The remote case decompresses on the fly -- a full Lichess month is
    ~5 GB of PGN that we never need to write to disk."""
    src = str(path)  # Saves a value named src so the next lines can use it.
    if src.startswith(("http://", "https://")):  # Runs the next indented steps only when this condition is true.
        import urllib.request  # Loads code this file needs for the steps below.
        import zstandard as zstd  # Loads code this file needs for the steps below.
        req = urllib.request.Request(  # Saves a value named req so the next lines can use it.
            src, headers={"User-Agent": "sna-chess-contagion/0.1"})  # Runs this instruction as part of the current step.
        raw = urllib.request.urlopen(req)  # Saves a value named raw so the next lines can use it.
        dctx = zstd.ZstdDecompressor(max_window_size=2 ** 31)  # Saves a value named dctx so the next lines can use it.
        return io.TextIOWrapper(dctx.stream_reader(raw, read_size=1 << 20),  # Gives this answer back to the code that called the function.
                                encoding="utf-8", errors="replace")  # Saves a value named encoding so the next lines can use it.
    if src.endswith(".zst"):  # Runs the next indented steps only when this condition is true.
        import zstandard as zstd  # Loads code this file needs for the steps below.
        fh = open(path, "rb")  # Saves a value named fh so the next lines can use it.
        dctx = zstd.ZstdDecompressor(max_window_size=2 ** 31)  # Saves a value named dctx so the next lines can use it.
        return io.TextIOWrapper(dctx.stream_reader(fh), encoding="utf-8",  # Gives this answer back to the code that called the function.
                                errors="replace")  # Saves a value named errors so the next lines can use it.
    return open(path, "r", encoding="utf-8", errors="replace")  # Gives this answer back to the code that called the function.


def _ply_key(movetext: str, depth: int) -> str:  # Defines a reusable step; the following indented lines are its body.
    toks = [t for t in CLEAN_RE.sub(" ", movetext).split() if t]  # Saves a value named toks so the next lines can use it.
    return " ".join(toks[:depth])  # Gives this answer back to the code that called the function.


def _speed(event: str) -> str | None:  # Defines a reusable step; the following indented lines are its body.
    for s in ("Bullet", "Blitz", "Rapid", "Classical", "Correspondence"):  # Repeats the next indented steps once for each item.
        if s in event:  # Runs the next indented steps only when this condition is true.
            return s  # Gives this answer back to the code that called the function.
    return None  # Gives this answer back to the code that called the function.


def iter_games(path, limit: int | None = None):  # Yield header dicts + movetext, one per game, streaming.
    """Yield header dicts + movetext, one per game, streaming."""
    tags: dict[str, str] = {}  # Saves a value named tags so the next lines can use it.
    moves: list[str] = []  # Saves a value named moves so the next lines can use it.
    in_moves = False  # Saves a value named in_moves so the next lines can use it.
    n = 0  # Saves a value named n so the next lines can use it.
    with _open(path) as fh:  # Opens a resource and guarantees cleanup when the block ends.
        for line in fh:  # Repeats the next indented steps once for each item.
            line = line.rstrip("\n")  # Saves a value named line so the next lines can use it.
            if line.startswith("["):  # Runs the next indented steps only when this condition is true.
                # [Event ...] starts a game. Reset on it rather than only after
                # a game with moves, or an aborted game (headers, no movetext --
                # Lichess does contain them) leaks its tags into the next game,
                # silently giving it the wrong opening and ratings.
                if line.startswith("[Event ") and tags:  # Runs the next indented steps only when this condition is true.
                    if in_moves:  # Runs the next indented steps only when this condition is true.
                        yield tags, " ".join(moves)  # Runs this instruction as part of the current step.
                        n += 1  # Adds this amount to the running total.
                        if limit and n >= limit:  # Runs the next indented steps only when this condition is true.
                            return  # Stops this function here.
                    tags, moves, in_moves = {}, [], False  # Runs this instruction as part of the current step.
                m = TAG_RE.match(line)  # Saves a value named m so the next lines can use it.
                if m and m.group(1) in WANTED:  # Runs the next indented steps only when this condition is true.
                    tags[m.group(1)] = m.group(2)  # Stores this value under its player, opening, or field key.
            elif line.strip():  # Runs the next indented steps only when this condition is true.
                in_moves = True  # Saves a value named in_moves so the next lines can use it.
                moves.append(line.strip())  # Adds this item to the list being built.
    if tags and in_moves:  # Runs the next indented steps only when this condition is true.
        yield tags, " ".join(moves)  # Runs this instruction as part of the current step.


def parse(path, limit: int | None = None, ply_depth: int | None = None,  # Scan PGN into the filtered game table used throughout the project.
          apply_filters: bool = True, progress: int = 0,  # Saves a value named apply_filters so the next lines can use it.
          on_progress=None, should_stop=None) -> pd.DataFrame:  # Saves a value named on_progress so the next lines can use it.
    """Scan PGN into the filtered game table used throughout the project.

    The input is streamed, so a compressed month need not fit in memory as
    text. `on_progress` updates the live UI; `should_stop` lets it cancel.
    Filtering here fixes the study population before network analysis.
    """
    ply_depth = ply_depth or config.PLY_KEY_DEPTH  # Saves a value named ply_depth so the next lines can use it.
    rows, skipped = [], Counter()  # Runs this instruction as part of the current step.
    seen = 0  # Stores the set of opponents already counted for the next step.

    for tags, movetext in iter_games(path, limit=limit):  # Repeats the next indented steps once for each item.
        seen += 1  # Adds this amount to the running total.
        if progress and seen % progress == 0:  # Runs the next indented steps only when this condition is true.
            if on_progress is not None:  # Runs the next indented steps only when this condition is true.
                # hand back the most recent kept row so a UI can show what is
                # actually streaming past, not just a counter
                on_progress(seen, len(rows), rows[-1] if rows else None)  # Runs this instruction as part of the current step.
            else:  # Handles the alternative when the preceding condition was false.
                print(f"  scanned {seen:,} games, kept {len(rows):,}",  # Prints this reading so a command-line run can be followed.
                      file=sys.stderr, flush=True)  # Saves a value named file so the next lines can use it.
            if should_stop is not None and should_stop():  # Runs the next indented steps only when this condition is true.
                skipped["cancelled"] = 1  # Stores this value under its player, opening, or field key.
                break  # Ends the current loop.
        try:  # Starts an operation that may need error handling.
            speed = _speed(tags.get("Event", ""))  # Saves a value named speed so the next lines can use it.
            if apply_filters and speed not in config.ALLOWED_SPEEDS:  # Runs the next indented steps only when this condition is true.
                skipped["speed"] += 1  # Adds this amount to the running total.
                continue  # Skips this item and moves to the next loop iteration.
            we, be = tags.get("WhiteElo", "?"), tags.get("BlackElo", "?")  # Runs this instruction as part of the current step.
            if not (we.isdigit() and be.isdigit()):  # Runs the next indented steps only when this condition is true.
                skipped["no_rating"] += 1  # Adds this amount to the running total.
                continue  # Skips this item and moves to the next loop iteration.
            we, be = int(we), int(be)  # Runs this instruction as part of the current step.
            if apply_filters and not all(  # Runs the next indented steps only when this condition is true.
                config.RATING_MIN <= r <= config.RATING_MAX for r in (we, be)  # Runs this instruction as part of the current step.
            ):  # Runs this instruction as part of the current step.
                skipped["rating_band"] += 1  # Adds this amount to the running total.
                continue  # Skips this item and moves to the next loop iteration.
            eco = tags.get("ECO", "?")  # Saves a value named eco so the next lines can use it.
            if eco in ("?", ""):  # Runs the next indented steps only when this condition is true.
                skipped["no_eco"] += 1  # Adds this amount to the running total.
                continue  # Skips this item and moves to the next loop iteration.
            date, time = tags.get("UTCDate"), tags.get("UTCTime")  # Runs this instruction as part of the current step.
            if not date or not time:  # Runs the next indented steps only when this condition is true.
                skipped["no_time"] += 1  # Adds this amount to the running total.
                continue  # Skips this item and moves to the next loop iteration.
            ts = datetime.strptime(f"{date} {time}", "%Y.%m.%d %H:%M:%S")  # Saves a value named ts so the next lines can use it.
            rows.append((  # Part of the value, collection, or call spanning several lines.
                tags.get("Site", "").rsplit("/", 1)[-1], ts,  # Part of the value, collection, or call spanning several lines.
                tags.get("White", "?"), tags.get("Black", "?"), we, be,  # Part of the value, collection, or call spanning several lines.
                eco, tags.get("Opening", ""), _ply_key(movetext, ply_depth),  # Part of the value, collection, or call spanning several lines.
                speed, tags.get("Result", "*"),  # Part of the value, collection, or call spanning several lines.
            ))  # Runs this instruction as part of the current step.
        except Exception:  # Handles this specific failure without hiding other errors.
            skipped["error"] += 1  # Adds this amount to the running total.

    df = pd.DataFrame(rows, columns=[  # Creates a labelled table from the collected rows.
        "game_id", "ts", "white", "black", "white_rating", "black_rating",
        "eco", "opening", "ply_key", "speed", "result"])

    if apply_filters and len(df):  # Runs the next indented steps only when this condition is true.
        top = df["eco"].value_counts().head(config.TOP_N_OPENINGS).index  # Counts how often each player or opening occurs.
        skipped["rare_eco"] = int((~df["eco"].isin(top)).sum())  # Stores this value under its player, opening, or field key.
        df = df[df["eco"].isin(top)]  # Stores the game table for the next step.
        # drop low-activity players: their adoption timing is noise
        games = pd.concat([df["white"], df["black"]]).value_counts()  # Counts how often each player or opening occurs.
        keep = set(games[games >= config.MIN_GAMES_PER_PLAYER].index)  # Saves a value named keep so the next lines can use it.
        before = len(df)  # Saves a value named before so the next lines can use it.
        df = df[df["white"].isin(keep) & df["black"].isin(keep)]  # Stores the game table for the next step.
        skipped["low_activity"] = before - len(df)  # Stores this value under its player, opening, or field key.

    df = df.sort_values("ts").reset_index(drop=True)  # Puts games in time order so earlier encounters cannot use future information.
    df.attrs["skipped"] = dict(skipped)  # Stores this value under its player, opening, or field key.
    return df  # Gives this answer back to the code that called the function.


def load_games(path) -> pd.DataFrame:  # Read a parsed games table, refusing simulated data.
    """Read a parsed games table, refusing simulated data.

    src/simulate.py writes players named `sim_00001`. A synthetic table left
    sitting at the default path is silently analysed as though it were real --
    which is exactly what happened once, and the numbers looked plausible.
    Simulated runs write to a filename containing "simulated"; anything else
    holding sim_ players is a mistake, so say so loudly instead of returning it.
    """
    df = pd.read_parquet(path)  # Loads a previously prepared game or trial table.
    if "simulated" in Path(path).name:  # Runs the next indented steps only when this condition is true.
        return df  # Gives this answer back to the code that called the function.
    if len(df) and df["white"].astype(str).str.fullmatch(r"sim_\d+").any():  # Runs the next indented steps only when this condition is true.
        raise SystemExit(  # Stops with an explicit error when this requirement is violated.
            f"{path} contains SIMULATED games (players named sim_*), not real "  # Runs this instruction as part of the current step.
            f"ones.\nRe-run the pipeline on a real month, or point --games at a "  # Runs this instruction as part of the current step.
            f"real slice such as slice_<month>_full.parquet.")  # Runs this instruction as part of the current step.
    return df  # Gives this answer back to the code that called the function.


def run(src, out: Path, limit=None, apply_filters=True,  # Defines a reusable step; the following indented lines are its body.
        progress: int = 0) -> pd.DataFrame:  # Saves a value named progress so the next lines can use it.
    df = parse(src, limit=limit, apply_filters=apply_filters, progress=progress)  # Stores the game table for the next step.
    df.to_parquet(out, index=False)  # Saves a compact table for later analysis stages.
    return df  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--src", default=str(config.RAW / "simulated.pgn"))  # Defines a command-line option for this script.
    ap.add_argument("--out", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--limit", type=int, default=None)  # Defines a command-line option for this script.
    ap.add_argument("--no-filters", action="store_true")  # Defines a command-line option for this script.
    ap.add_argument("--progress", type=int, default=0,  # Defines a command-line option for this script.
                    help="print a line every N games scanned")  # Saves a value named help so the next lines can use it.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    src = a.src if a.src.startswith("http") else Path(a.src)  # Saves a value named src so the next lines can use it.
    d = run(src, Path(a.out), a.limit, not a.no_filters, a.progress)  # Stores the distinct-opponent count for the next step.
    print(f"{len(d)} games kept -> {a.out}")  # Prints this reading so a command-line run can be followed.
    print("skipped:", d.attrs["skipped"])  # Prints this reading so a command-line run can be followed.
    print(f"players: {len(set(d.white) | set(d.black))}, "  # Prints this reading so a command-line run can be followed.
          f"span: {d.ts.min()} .. {d.ts.max()}")  # Runs this instruction as part of the current step.
