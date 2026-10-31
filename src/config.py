"""Locked project decisions. Every module reads constants from here.

The Build Guide says to lock these early; changing them here changes the
whole pipeline consistently.
"""
import os  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.

# Data and results can live off the project root -- a full Lichess month of
# Parquet plus figures does not belong on a drive that is nearly full.
#   set SNA_DATA_ROOT=E:\sna_data
_DATA_ROOT = Path(os.environ.get("SNA_DATA_ROOT", ROOT))  # Saves a value named _DATA_ROOT so the next lines can use it.

DATA = _DATA_ROOT / "data"  # Saves a value named DATA so the next lines can use it.
RAW = DATA / "raw"  # Saves a value named RAW so the next lines can use it.
INTERIM = DATA / "interim"  # Saves a value named INTERIM so the next lines can use it.
PROCESSED = DATA / "processed"  # Saves a value named PROCESSED so the next lines can use it.
RESULTS = _DATA_ROOT / "results"  # Saves a value named RESULTS so the next lines can use it.
FIGURES = RESULTS / "figures"  # Saves a value named FIGURES so the next lines can use it.
TABLES = RESULTS / "tables"  # Saves a value named TABLES so the next lines can use it.

for _p in (RAW, INTERIM, PROCESSED, FIGURES, TABLES):  # Repeats the next indented steps once for each item.
    _p.mkdir(parents=True, exist_ok=True)  # Creates the folder needed for saved outputs.

# ---- sample selection -------------------------------------------------
RATING_MIN = 1800  # Saves a value named RATING_MIN so the next lines can use it.
RATING_MAX = 2200  # Saves a value named RATING_MAX so the next lines can use it.
# Lichess "Event" header contains the speed. Standard-ish time controls only.
ALLOWED_SPEEDS = ("Rapid", "Classical", "Blitz")  # Saves a value named ALLOWED_SPEEDS so the next lines can use it.
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
N_NULL_REPLICATES = 20       # timestamp-shuffle replicates
RATING_MATCH_TOLERANCE = 50  # matched controls: +/- rating points
ACTIVITY_MATCH_RATIO = 0.25  # matched controls: +/- 25% games played
TRAIN_FRACTION = 0.7         # grouped spell split for the held-out AUC

RANDOM_SEED = 20260916  # Saves a value named RANDOM_SEED so the next lines can use it.
