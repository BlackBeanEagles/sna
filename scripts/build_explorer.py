"""Aggregate complete trials for the findings page's opening/colour explorer."""
from pathlib import Path  # Loads Path to find and save project files.
import sys  # Loads code this file needs for the steps below.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Runs this instruction as part of the current step.
import numpy as np  # Loads the number library used for fast calculations.
import pandas as pd  # Loads the table library used to store games and trials.
from src import config  # Loads the named parts of this project so this file can use their functions.

trials = pd.read_parquet(config.PROCESSED / "trials.parquet")  # Loads a previously prepared game or trial table.
# The findings filters need pre-aggregated opening/colour cells; this script
# turns the full trial table into small, downloadable chart-ready groups.
trials["d"] = trials["d"].clip(upper=config.MAX_DIVERSITY)  # Caps large counts into the final chart bucket, such as six or more opponents.
grouped = (trials.groupby(["opening", "colour", "d"], observed=True)  # Groups rows sharing these keys before counting or averaging them.
           .agg(n=("adopted", "size"), adopted=("adopted", "sum"))  # Runs this instruction as part of the current step.
           .reset_index().sort_values(["opening", "colour", "d"]))  # Orders the rows by this field before the next calculation.
p = grouped["adopted"] / grouped["n"]  # Saves a value named p so the next lines can use it.
n = grouped["n"]  # Saves a value named n so the next lines can use it.
z = 1.96  # Saves a value named z so the next lines can use it.
# Wilson bounds give each selected group an uncertainty interval, especially
# useful where a less common opening has few complete trials.
den = 1 + z*z/n  # Saves a value named den so the next lines can use it.
center = (p + z*z/(2*n)) / den  # Saves a value named center so the next lines can use it.
half = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den  # Saves a value named half so the next lines can use it.
grouped["rate"] = p  # Stores this value under its player, opening, or field key.
grouped["lo"] = center-half  # Stores this value under its player, opening, or field key.
grouped["hi"] = center+half  # Stores this value under its player, opening, or field key.
target = config.TABLES / "explorer_by_opening_colour.csv"  # Saves a value named target so the next lines can use it.
grouped.to_csv(target, index=False)  # Writes a result table that can be inspected or downloaded.
assert int(grouped["n"].sum()) == len(trials)  # Checks an invariant; the script fails if it is false.
print(f"{len(grouped)} groups, {len(trials):,} trials -> {target}")  # Prints this reading so a command-line run can be followed.
