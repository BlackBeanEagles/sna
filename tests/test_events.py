"""Tests for the exposure/adoption core.

`events.build_trials` is where the science lives: if it miscounts exposures,
mis-dates adoption or mis-measures structural diversity, every number
downstream is wrong and still looks plausible. These build tiny games tables
by hand where the right answer is known by inspection.

    python -m pytest tests -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import curve, events, nulls  # noqa: E402

T0 = datetime(2016, 1, 1)


def game(white, black, day, eco="B20", ply="e4 c5", wr=2000, br=2000):
    return {"game_id": f"g{day}", "ts": T0 + timedelta(days=day),
            "white": white, "black": black, "white_rating": wr,
            "black_rating": br, "eco": eco, "opening": "Test",
            "ply_key": ply, "speed": "Blitz", "result": "1-0"}


def frame(rows):
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


# ---------------------------------------------------------------- sweep
def test_one_game_makes_two_performances_and_two_exposures():
    """u plays (X,W) and exposes v to it; v plays (X,B) and exposes u."""
    df = frame([game("u", "v", 0)])
    exposures, first_perf, _ = events.sweep(df)

    assert ("u", ("B20", "W")) in first_perf      # white performed it as White
    assert ("v", ("B20", "B")) in first_perf      # black performed it as Black
    assert exposures[("v", ("B20", "W"))] == [(df.ts[0], "u")]
    assert exposures[("u", ("B20", "B"))] == [(df.ts[0], "v")]


def test_colour_is_part_of_the_behaviour():
    """Meeting the Sicilian as White is not the same behaviour as playing it
    as Black -- if colour dropped out of the key, adoption becomes meaningless."""
    df = frame([game("u", "v", 0)])
    _, first_perf, _ = events.sweep(df)
    assert ("u", ("B20", "B")) not in first_perf
    assert ("v", ("B20", "W")) not in first_perf


def test_first_performance_wins():
    df = frame([game("u", "v", 0), game("u", "w", 5)])
    _, first_perf, _ = events.sweep(df)
    assert first_perf[("u", ("B20", "W"))] == T0        # not day 5


# ---------------------------------------------------------------- trials
def test_adoption_inside_window_counts():
    # a exposes b on day 0; b plays it as White on day 3 -> adopted
    df = frame([game("a", "b", 0), game("b", "z", 3), game("q", "r", 40)])
    trials = events.build_trials(df, window_days=14)
    row = trials[(trials.player == "b") & (trials.colour == "W")]
    assert len(row) == 1
    assert row.iloc[0]["adopted"] == 1


def test_adoption_outside_window_does_not_count():
    # exposure day 0, first play day 20, window 14 -> not an adoption
    df = frame([game("a", "b", 0), game("b", "z", 20), game("q", "r", 60)])
    trials = events.build_trials(df, window_days=14)
    row = trials[(trials.player == "b") & (trials.colour == "W")]
    assert len(row) == 1
    assert row.iloc[0]["adopted"] == 0


def test_trials_censored_when_window_runs_past_the_data():
    """A window that does not fit inside the observation period is dropped,
    not silently scored as a non-adoption."""
    df = frame([game("a", "b", 0), game("c", "e", 1)])   # spans 1 day
    trials = events.build_trials(df, window_days=14)
    assert len(trials) == 0


def test_player_already_playing_it_is_not_at_risk():
    # b plays it on day 0 as White, is exposed to (X,W) later -> no trial
    df = frame([game("b", "z", 0), game("a", "b", 2), game("q", "r", 40)])
    trials = events.build_trials(df, window_days=14)
    assert trials[(trials.player == "b") & (trials.colour == "W")].empty


def test_distinct_exposers_counted_not_repeat_exposures():
    """Three games from the same opponent is d=1 with k=3."""
    df = frame([game("a", "b", 0), game("a", "b", 1), game("a", "b", 2),
                game("q", "r", 40)])
    trials = events.build_trials(df, window_days=14)
    row = trials[(trials.player == "b") & (trials.colour == "W")]
    assert row["d"].max() == 1
    assert row["k"].max() == 3


def test_three_different_exposers_give_d_three():
    df = frame([game("a", "b", 0), game("c", "b", 1), game("e", "b", 2),
                game("q", "r", 40)])
    trials = events.build_trials(df, window_days=14)
    row = trials[(trials.player == "b") & (trials.colour == "W")]
    assert row["d"].max() == 3


# ------------------------------------------------- structural diversity
def test_structural_diversity_separate_exposers_are_separate_components():
    """Two exposers who have never met are two components -> sd = 2."""
    df = frame([game("a", "b", 0), game("c", "b", 1), game("q", "r", 40)])
    trials = events.build_trials(df, window_days=14)
    row = trials[(trials.player == "b") & (trials.colour == "W")]
    assert row["sd"].max() == 2


def test_structural_diversity_connected_exposers_collapse_to_one():
    """If the two exposers have played each other, they are one social source."""
    df = frame([game("a", "c", 0),        # a and c know each other
                game("a", "b", 1), game("c", "b", 2), game("q", "r", 40)])
    trials = events.build_trials(df, window_days=14)
    row = trials[(trials.player == "b") & (trials.colour == "W")]
    assert row["d"].max() == 2          # still two distinct people
    assert row["sd"].max() == 1         # but only one component


def test_structural_diversity_ignores_edges_formed_later():
    """The exposure subgraph may only use edges that existed at the time."""
    df = frame([game("a", "b", 0), game("c", "b", 1),
                game("a", "c", 30),      # they meet only AFTER the exposures
                game("q", "r", 60)])
    trials = events.build_trials(df, window_days=14)
    row = trials[(trials.player == "b") & (trials.colour == "W")]
    assert row["sd"].max() == 2


# ---------------------------------------------------------------- nulls
def test_shuffling_timestamps_preserves_the_games_themselves():
    import numpy as np
    df = frame([game("a", "b", i) for i in range(10)])
    out = nulls.shuffle_timestamps(df, np.random.default_rng(0))
    assert sorted(out["ts"]) == sorted(df["ts"])
    assert len(out) == len(df)


def test_rewire_preserves_degree_and_makes_no_self_loops():
    """The proposal's second null: degree-preserving edge rewiring. It has to
    change who played whom while leaving every player's game count alone."""
    import numpy as np
    from collections import Counter

    df = pd.DataFrame({
        "white": [f"w{i % 7}" for i in range(60)],
        "black": [f"b{i % 5}" for i in range(60)],
        "ts": pd.date_range("2016-01-01", periods=60, freq="h"),
    })
    out = nulls.rewire_preserving_degree(df, np.random.default_rng(0))

    def degrees(d):
        c = Counter()
        for u, v in zip(d.white, d.black):
            c[u] += 1
            c[v] += 1
        return c

    assert degrees(df) == degrees(out)
    assert (out.white != out.black).all()          # no self-loops
    assert set(zip(df.white, df.black)) != set(zip(out.white, out.black))


def test_null_honours_granularity():
    """The null must build trials the same way the real analysis does.

    Leaving granularity at the default while the real trials are keyed by ply
    compares a sparse ply world against a dense ECO world and manufactures a
    spurious 'complex contagion' verdict. Same class of bug as the adoption
    window mismatch, so it gets the same guard.
    """
    rows = [game(f"p{d}", f"q{d}", d,
                 ply="e4 c5 Nf3 d6" if d % 2 == 0 else "e4 c5 Nc3 Nc6")
            for d in range(6)]
    df = frame(rows)

    # ply granularity must actually split the single ECO into two behaviours
    eco_keys = {events.behaviour_key(r, "eco") for r in df.itertuples()}
    ply_keys = {events.behaviour_key(r, "ply") for r in df.itertuples()}
    assert len(eco_keys) == 1 and len(ply_keys) == 2

    # and run_null must forward that choice to build_trials, not silently
    # fall back to the configured default
    seen = []
    real_build = events.build_trials

    def spy(frame_, *args, **kwargs):
        seen.append(kwargs.get("granularity"))
        return real_build(frame_, *args, **kwargs)

    events.build_trials = spy
    try:
        nulls.run_null(df, n_reps=1, window_days=2, granularity="ply")
    finally:
        events.build_trials = real_build

    assert seen and all(g == "ply" for g in seen), (
        f"run_null passed granularity={seen} to build_trials, expected 'ply'")


def test_compare_falls_back_to_binomial_se_with_one_replicate():
    """A single replicate has no across-replicate spread. Without a fallback
    every z is NaN and the verdict silently collapses to 'nothing detected'."""
    import numpy as np
    real = pd.DataFrame({"d": [1, 2], "n": [100, 50], "rate": [0.20, 0.25],
                         "lo": [0, 0], "hi": [1, 1]})
    one = pd.DataFrame({"d": [1, 2], "n": [100, 50], "rate": [0.15, 0.24],
                        "rate_sd": [np.nan, np.nan]})
    z = nulls.compare(real, one)["z_vs_null"]
    assert z.notna().all()


# --------------------------------------------------------------- verdict
def test_verdict_needs_the_null_before_it_will_call_complex_contagion():
    """The bug this guards: a rising raw curve alone was enough to print
    'complex contagion', even though the null reproduced the whole rise."""
    rising = pd.DataFrame({"d": [1, 2, 3], "n": [1000] * 3,
                           "adopted": [100, 200, 300],
                           "rate": [0.10, 0.20, 0.30],
                           "lo": [0.09, 0.19, 0.29], "hi": [0.11, 0.21, 0.31]})
    tables = {"by_d": rising, "held_k_by_d": pd.DataFrame(
        columns=["k", "d", "n", "rate", "lo", "hi"])}
    v = curve.verdict(tables, None)
    assert "complex contagion" != v["verdict"]
    assert "withheld" in v["verdict"] or "no null" in v["verdict"]


def test_verdict_reports_simple_when_null_matches_the_rise():
    rising = pd.DataFrame({"d": [1, 2, 3], "n": [1000] * 3,
                           "adopted": [100, 200, 300],
                           "rate": [0.10, 0.20, 0.30],
                           "lo": [0.09, 0.19, 0.29], "hi": [0.11, 0.21, 0.31]})
    tables = {"by_d": rising, "held_k_by_d": pd.DataFrame(
        columns=["k", "d", "n", "rate", "lo", "hi"])}
    cmp = pd.DataFrame({"d": [1, 2, 3],
                        "rate_real": [0.10, 0.20, 0.30],
                        "rate_null": [0.08, 0.18, 0.30],
                        "lift_over_null": [1.25, 1.11, 1.00],
                        "z_vs_null": [9.0, 5.0, 0.1]})
    v = curve.verdict(tables, cmp)
    assert v["excess_over_null_grows_with_d"] is False
    assert v["verdict"].startswith("simple contagion")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
