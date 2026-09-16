"""Locked project decisions. Every module reads constants from here.

The Build Guide says to lock these early; changing them here changes the
whole pipeline consistently.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Data and results can live off the project root -- a full Lichess month of
# Parquet plus figures does not belong on a drive that is nearly full.
#   set SNA_DATA_ROOT=E:\sna_data
_DATA_ROOT = Path(os.environ.get("SNA_DATA_ROOT", ROOT))

DATA = _DATA_ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
RESULTS = _DATA_ROOT / "results"
FIGURES = RESULTS / "figures"
TABLES = RESULTS / "tables"

for _p in (RAW, INTERIM, PROCESSED, FIGURES, TABLES):
    _p.mkdir(parents=True, exist_ok=True)

# ---- sample selection -------------------------------------------------
RATING_MIN = 1800
RATING_MAX = 2200
# Lichess "Event" header contains the speed. Standard-ish time controls only.
ALLOWED_SPEEDS = ("Rapid", "Classical", "Blitz")
TOP_N_OPENINGS = 40          # keep the most frequent ECO codes only

# ---- behaviour definition --------------------------------------------
# A behaviour is (opening, colour). Playing the Sicilian as Black and
# meeting it as White are different behaviours -- colour stays in the key.
OPENING_GRANULARITY = "eco"  # "eco" for the main analysis, "ply" for robustness
PLY_KEY_DEPTH = 8            # first k plies used when granularity == "ply"

# ---- contagion measurement -------------------------------------------
ADOPTION_WINDOW_DAYS = 14    # fixed window after an exposure
MIN_GAMES_PER_PLAYER = 20    # drop low-activity players: their timing is noise
MAX_EXPOSURE_COUNT = 8       # curve is reported for k = 1..8
MAX_DIVERSITY = 6            # d and structural diversity capped for plotting

# ---- identification ---------------------------------------------------
N_NULL_REPLICATES = 5        # timestamp-shuffle replicates
RATING_MATCH_TOLERANCE = 50  # matched controls: +/- rating points
ACTIVITY_MATCH_RATIO = 0.25  # matched controls: +/- 25% games played
TRAIN_FRACTION = 0.7         # temporal split for the held-out AUC

RANDOM_SEED = 20260916
