"""Aggregate complete trials for the findings page's opening/colour explorer."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from src import config

trials = pd.read_parquet(config.PROCESSED / "trials.parquet")
# The findings filters need pre-aggregated opening/colour cells; this script
# turns the full trial table into small, downloadable chart-ready groups.
trials["d"] = trials["d"].clip(upper=config.MAX_DIVERSITY)
grouped = (trials.groupby(["opening", "colour", "d"], observed=True)
           .agg(n=("adopted", "size"), adopted=("adopted", "sum"))
           .reset_index().sort_values(["opening", "colour", "d"]))
p = grouped["adopted"] / grouped["n"]
n = grouped["n"]
z = 1.96
# Wilson bounds give each selected group an uncertainty interval, especially
# useful where a less common opening has few complete trials.
den = 1 + z*z/n
center = (p + z*z/(2*n)) / den
half = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
grouped["rate"] = p
grouped["lo"] = center-half
grouped["hi"] = center+half
target = config.TABLES / "explorer_by_opening_colour.csv"
grouped.to_csv(target, index=False)
assert int(grouped["n"].sum()) == len(trials)
print(f"{len(grouped)} groups, {len(trials):,} trials -> {target}")
