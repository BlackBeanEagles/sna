# Classroom sample provenance

`january_2016_classroom_sample.parquet` contains 60,000 real game rows selected
from the project's cached filtered January 2016 slice
(`data/interim/slice_2016-01_full.parquet`, 249,505 rows). Selection used
`pandas.DataFrame.sample(n=60000, random_state=20260916)` followed by sorting
on the game timestamp. The rows span the month and include 6,875 player IDs.

The sample exists so an examiner can start a fresh analysis without downloading
the archive during a presentation. It uses the project's regular trial,
network, curve, null, matching and prediction modules. Its one-shuffle output is
an exploratory demonstration, not the reported research estimate. See
`docs/RESULTS.md` for the full-slice analysis and limitations.
