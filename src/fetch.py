"""Where the Lichess archives live.

This module used to download a slice to disk before parsing it. That step is
gone: `parse._open` opens the remote `.pgn.zst` directly and decompresses as it
reads, so a month is never written out as PGN (it would be ~5 GB) and the scan
can stop early without having fetched the rest.

What remains is the one thing worth having in a single place — how a month
maps to a URL.

Source: https://database.lichess.org  (CC0).
"""
from __future__ import annotations

BASE = "https://database.lichess.org/standard/lichess_db_standard_rated_{month}.pgn.zst"


def url(month: str) -> str:
    """`month` is 'YYYY-MM', e.g. '2016-01'."""
    return BASE.format(month=month)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", default="2016-01", help="YYYY-MM")
    a = ap.parse_args()
    print(url(a.month))
    print("\nTo analyse it:  python -m src.run_pipeline --month " + a.month)
