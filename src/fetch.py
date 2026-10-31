"""Where the Lichess archives live.

This module used to download a slice to disk before parsing it. That step is
gone: `parse._open` opens the remote `.pgn.zst` directly and decompresses as it
reads, so a month is never written out as PGN (it would be ~5 GB) and the scan
can stop early without having fetched the rest.

What remains is the one thing worth having in a single place — how a month
maps to a URL.

Source: https://database.lichess.org  (CC0).
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

BASE = "https://database.lichess.org/standard/lichess_db_standard_rated_{month}.pgn.zst"  # Saves a value named BASE so the next lines can use it.


def url(month: str) -> str:  # month is 'YYYY-MM', e.g.
    """`month` is 'YYYY-MM', e.g. '2016-01'."""
    return BASE.format(month=month)  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    import argparse  # Loads the tool that reads command-line choices.

    ap = argparse.ArgumentParser(description=__doc__)  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--month", default="2016-01", help="YYYY-MM")  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    print(url(a.month))  # Prints this reading so a command-line run can be followed.
    print("\nTo analyse it:  python -m src.run_pipeline --month " + a.month)  # Prints this reading so a command-line run can be followed.
