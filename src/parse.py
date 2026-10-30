"""Step 2 -- PGN -> one Parquet event table. Nothing downstream re-reads PGN.

A hand-rolled header scanner, not python-chess's full game parser: on a real
Lichess month we need millions of games/minute, and we only ever want the
headers plus the first few plies. Handles plain .pgn and zstd-compressed
.pgn.zst transparently.

Row schema:
    game_id, ts, white, black, white_rating, black_rating,
    eco, opening, ply_key, speed, result
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config

TAG_RE = re.compile(r'^\[([A-Za-z0-9_]+)\s+"(.*)"\]\s*$')
# strip move numbers, clock comments, NAGs, evals and result tokens
CLEAN_RE = re.compile(r"\{[^}]*\}|\$\d+|\d+\.(\.\.)?|[?!]+|1-0|0-1|1/2-1/2|\*")

WANTED = ("Event", "Site", "White", "Black", "Result", "UTCDate", "UTCTime",
          "WhiteElo", "BlackElo", "ECO", "Opening", "TimeControl", "Termination")


def _open(path):
    """Text stream over a local .pgn, a local .pgn.zst, or a remote .pgn.zst
    URL. The remote case decompresses on the fly -- a full Lichess month is
    ~5 GB of PGN that we never need to write to disk."""
    src = str(path)
    if src.startswith(("http://", "https://")):
        import urllib.request
        import zstandard as zstd
        req = urllib.request.Request(
            src, headers={"User-Agent": "sna-chess-contagion/0.1"})
        raw = urllib.request.urlopen(req)
        dctx = zstd.ZstdDecompressor(max_window_size=2 ** 31)
        return io.TextIOWrapper(dctx.stream_reader(raw, read_size=1 << 20),
                                encoding="utf-8", errors="replace")
    if src.endswith(".zst"):
        import zstandard as zstd
        fh = open(path, "rb")
        dctx = zstd.ZstdDecompressor(max_window_size=2 ** 31)
        return io.TextIOWrapper(dctx.stream_reader(fh), encoding="utf-8",
                                errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def _ply_key(movetext: str, depth: int) -> str:
    toks = [t for t in CLEAN_RE.sub(" ", movetext).split() if t]
    return " ".join(toks[:depth])


def _speed(event: str) -> str | None:
    for s in ("Bullet", "Blitz", "Rapid", "Classical", "Correspondence"):
        if s in event:
            return s
    return None


def iter_games(path, limit: int | None = None):
    """Yield header dicts + movetext, one per game, streaming."""
    tags: dict[str, str] = {}
    moves: list[str] = []
    in_moves = False
    n = 0
    with _open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("["):
                # [Event ...] starts a game. Reset on it rather than only after
                # a game with moves, or an aborted game (headers, no movetext --
                # Lichess does contain them) leaks its tags into the next game,
                # silently giving it the wrong opening and ratings.
                if line.startswith("[Event ") and tags:
                    if in_moves:
                        yield tags, " ".join(moves)
                        n += 1
                        if limit and n >= limit:
                            return
                    tags, moves, in_moves = {}, [], False
                m = TAG_RE.match(line)
                if m and m.group(1) in WANTED:
                    tags[m.group(1)] = m.group(2)
            elif line.strip():
                in_moves = True
                moves.append(line.strip())
    if tags and in_moves:
        yield tags, " ".join(moves)


def parse(path, limit: int | None = None, ply_depth: int | None = None,
          apply_filters: bool = True, progress: int = 0,
          on_progress=None, should_stop=None) -> pd.DataFrame:
    """Scan PGN into the filtered game table used throughout the project.

    The input is streamed, so a compressed month need not fit in memory as
    text. `on_progress` updates the live UI; `should_stop` lets it cancel.
    Filtering here fixes the study population before network analysis.
    """
    ply_depth = ply_depth or config.PLY_KEY_DEPTH
    rows, skipped = [], Counter()
    seen = 0

    for tags, movetext in iter_games(path, limit=limit):
        seen += 1
        if progress and seen % progress == 0:
            if on_progress is not None:
                # hand back the most recent kept row so a UI can show what is
                # actually streaming past, not just a counter
                on_progress(seen, len(rows), rows[-1] if rows else None)
            else:
                print(f"  scanned {seen:,} games, kept {len(rows):,}",
                      file=sys.stderr, flush=True)
            if should_stop is not None and should_stop():
                skipped["cancelled"] = 1
                break
        try:
            speed = _speed(tags.get("Event", ""))
            if apply_filters and speed not in config.ALLOWED_SPEEDS:
                skipped["speed"] += 1
                continue
            we, be = tags.get("WhiteElo", "?"), tags.get("BlackElo", "?")
            if not (we.isdigit() and be.isdigit()):
                skipped["no_rating"] += 1
                continue
            we, be = int(we), int(be)
            if apply_filters and not all(
                config.RATING_MIN <= r <= config.RATING_MAX for r in (we, be)
            ):
                skipped["rating_band"] += 1
                continue
            eco = tags.get("ECO", "?")
            if eco in ("?", ""):
                skipped["no_eco"] += 1
                continue
            date, time = tags.get("UTCDate"), tags.get("UTCTime")
            if not date or not time:
                skipped["no_time"] += 1
                continue
            ts = datetime.strptime(f"{date} {time}", "%Y.%m.%d %H:%M:%S")
            rows.append((
                tags.get("Site", "").rsplit("/", 1)[-1], ts,
                tags.get("White", "?"), tags.get("Black", "?"), we, be,
                eco, tags.get("Opening", ""), _ply_key(movetext, ply_depth),
                speed, tags.get("Result", "*"),
            ))
        except Exception:
            skipped["error"] += 1

    df = pd.DataFrame(rows, columns=[
        "game_id", "ts", "white", "black", "white_rating", "black_rating",
        "eco", "opening", "ply_key", "speed", "result"])

    if apply_filters and len(df):
        top = df["eco"].value_counts().head(config.TOP_N_OPENINGS).index
        skipped["rare_eco"] = int((~df["eco"].isin(top)).sum())
        df = df[df["eco"].isin(top)]
        # drop low-activity players: their adoption timing is noise
        games = pd.concat([df["white"], df["black"]]).value_counts()
        keep = set(games[games >= config.MIN_GAMES_PER_PLAYER].index)
        before = len(df)
        df = df[df["white"].isin(keep) & df["black"].isin(keep)]
        skipped["low_activity"] = before - len(df)

    df = df.sort_values("ts").reset_index(drop=True)
    df.attrs["skipped"] = dict(skipped)
    return df


def load_games(path) -> pd.DataFrame:
    """Read a parsed games table, refusing simulated data.

    src/simulate.py writes players named `sim_00001`. A synthetic table left
    sitting at the default path is silently analysed as though it were real --
    which is exactly what happened once, and the numbers looked plausible.
    Simulated runs write to a filename containing "simulated"; anything else
    holding sim_ players is a mistake, so say so loudly instead of returning it.
    """
    df = pd.read_parquet(path)
    if "simulated" in Path(path).name:
        return df
    if len(df) and df["white"].astype(str).str.fullmatch(r"sim_\d+").any():
        raise SystemExit(
            f"{path} contains SIMULATED games (players named sim_*), not real "
            f"ones.\nRe-run the pipeline on a real month, or point --games at a "
            f"real slice such as slice_<month>_full.parquet.")
    return df


def run(src, out: Path, limit=None, apply_filters=True,
        progress: int = 0) -> pd.DataFrame:
    df = parse(src, limit=limit, apply_filters=apply_filters, progress=progress)
    df.to_parquet(out, index=False)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(config.RAW / "simulated.pgn"))
    ap.add_argument("--out", default=str(config.INTERIM / "games.parquet"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-filters", action="store_true")
    ap.add_argument("--progress", type=int, default=0,
                    help="print a line every N games scanned")
    a = ap.parse_args()
    src = a.src if a.src.startswith("http") else Path(a.src)
    d = run(src, Path(a.out), a.limit, not a.no_filters, a.progress)
    print(f"{len(d)} games kept -> {a.out}")
    print("skipped:", d.attrs["skipped"])
    print(f"players: {len(set(d.white) | set(d.black))}, "
          f"span: {d.ts.min()} .. {d.ts.max()}")
