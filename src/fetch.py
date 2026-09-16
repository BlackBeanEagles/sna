"""Step 1 (real data) -- pull a SLICE of the Lichess open database.

The monthly dumps are 30+ GB compressed. We never need the whole thing: we
stream the .pgn.zst over HTTP, decompress on the fly, and stop as soon as we
have enough games. A 200k-game slice is a few hundred MB of transfer.

    python -m src.fetch --month 2024-01 --games 200000

Source: https://database.lichess.org  (permissive licence, CC0).
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
from pathlib import Path

from . import config

BASE = "https://database.lichess.org/standard/lichess_db_standard_rated_{month}.pgn.zst"


def stream_slice(month: str, n_games: int, out: Path | None = None,
                 chunk: int = 1 << 20) -> Path:
    import zstandard as zstd

    url = BASE.format(month=month)
    out = out or (config.RAW / f"lichess_{month}_{n_games}.pgn")
    req = urllib.request.Request(url, headers={"User-Agent": "sna-chess-contagion/0.1"})

    written = games = 0
    print(f"streaming {url}", file=sys.stderr)
    with urllib.request.urlopen(req) as resp:
        dctx = zstd.ZstdDecompressor(max_window_size=2 ** 31)
        reader = io.TextIOWrapper(dctx.stream_reader(resp, read_size=chunk),
                                  encoding="utf-8", errors="replace")
        with open(out, "w", encoding="utf-8") as fh:
            for line in reader:
                fh.write(line)
                written += len(line)
                if line.startswith("[Event "):
                    games += 1
                    if games % 25000 == 0:
                        print(f"  {games:,} games / {written/1e6:.0f} MB",
                              file=sys.stderr)
                    if games > n_games:
                        break
    print(f"wrote {games:,} games -> {out}", file=sys.stderr)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2024-01", help="YYYY-MM")
    ap.add_argument("--games", type=int, default=200000)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    stream_slice(a.month, a.games, Path(a.out) if a.out else None)
