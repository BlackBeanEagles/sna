"""Tests for the exposure/adoption core.

`events.build_trials` is where the science lives: if it miscounts exposures,
mis-dates adoption or mis-measures structural diversity, every number
downstream is wrong and still looks plausible. These build tiny games tables
by hand where the right answer is known by inspection.

    python -m pytest tests -q
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import sys  # Loads code this file needs for the steps below.
from datetime import datetime, timedelta  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.
import pytest  # Loads code this file needs for the steps below.

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Runs this instruction as part of the current step.

from src import curve, events, nulls  # noqa: E402

T0 = datetime(2016, 1, 1)  # Saves a value named T0 so the next lines can use it.


def game(white, black, day, eco="B20", ply="e4 c5", wr=2000, br=2000):  # Make a tiny known game; tests vary just the detail under inspection.
    """Make a tiny known game; tests vary just the detail under inspection."""
    return {"game_id": f"g{day}", "ts": T0 + timedelta(days=day),  # Gives this answer back to the code that called the function.
            "white": white, "black": black, "white_rating": wr,
            "black_rating": br, "eco": eco, "opening": "Test",
            "ply_key": ply, "speed": "Blitz", "result": "1-0"}


def frame(rows):  # Defines a reusable step; the following indented lines are its body.
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)  # Orders the rows by this field before the next calculation.


# ---------------------------------------------------------------- sweep
def test_one_game_makes_two_performances_and_two_exposures():  # u plays (X,W) and exposes v to it; v plays (X,B) and exposes u.
    """u plays (X,W) and exposes v to it; v plays (X,B) and exposes u."""
    df = frame([game("u", "v", 0)])  # Stores the game table for the next step.
    exposures, first_perf, _ = events.sweep(df)  # Runs this instruction as part of the current step.

    assert ("u", ("B20", "W")) in first_perf      # white performed it as White
    assert ("v", ("B20", "B")) in first_perf      # black performed it as Black
    assert exposures[("v", ("B20", "W"))] == [(df.ts[0], "u")]  # Checks an invariant; the script fails if it is false.
    assert exposures[("u", ("B20", "B"))] == [(df.ts[0], "v")]  # Checks an invariant; the script fails if it is false.


def test_colour_is_part_of_the_behaviour():  # Meeting the Sicilian as White is not the same behaviour as playing it as Black -- if colour dropped out of the key, adoption becomes meaningless.
    """Meeting the Sicilian as White is not the same behaviour as playing it
    as Black -- if colour dropped out of the key, adoption becomes meaningless."""
    df = frame([game("u", "v", 0)])  # Stores the game table for the next step.
    _, first_perf, _ = events.sweep(df)  # Runs this instruction as part of the current step.
    assert ("u", ("B20", "B")) not in first_perf  # Checks an invariant; the script fails if it is false.
    assert ("v", ("B20", "W")) not in first_perf  # Checks an invariant; the script fails if it is false.


def test_first_performance_wins():  # Defines a reusable step; the following indented lines are its body.
    df = frame([game("u", "v", 0), game("u", "w", 5)])  # Stores the game table for the next step.
    _, first_perf, _ = events.sweep(df)  # Runs this instruction as part of the current step.
    assert first_perf[("u", ("B20", "W"))] == T0        # not day 5


# ---------------------------------------------------------------- trials
def test_adoption_inside_window_counts():  # Defines a reusable step; the following indented lines are its body.
    # a exposes b on day 0; b plays it as White on day 3 -> adopted
    df = frame([game("a", "b", 0), game("b", "z", 3), game("q", "r", 40)])  # Stores the game table for the next step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    row = trials[(trials.player == "b") & (trials.colour == "W")]  # Saves a value named row so the next lines can use it.
    assert len(row) == 1  # Checks an invariant; the script fails if it is false.
    assert row.iloc[0]["adopted"] == 1  # Checks an invariant; the script fails if it is false.


def test_adoption_outside_window_does_not_count():  # Defines a reusable step; the following indented lines are its body.
    # exposure day 0, first play day 20, window 14 -> not an adoption
    df = frame([game("a", "b", 0), game("b", "z", 20), game("q", "r", 60)])  # Stores the game table for the next step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    row = trials[(trials.player == "b") & (trials.colour == "W")]  # Saves a value named row so the next lines can use it.
    assert len(row) == 1  # Checks an invariant; the script fails if it is false.
    assert row.iloc[0]["adopted"] == 0  # Checks an invariant; the script fails if it is false.


def test_trials_censored_when_window_runs_past_the_data():  # A window that does not fit inside the observation period is dropped, not silently scored as a non-adoption.
    """A window that does not fit inside the observation period is dropped,
    not silently scored as a non-adoption."""
    df = frame([game("a", "b", 0), game("c", "e", 1)])   # spans 1 day
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    assert len(trials) == 0  # Checks an invariant; the script fails if it is false.


def test_late_adoption_is_censored_alongside_late_nonadoption():  # Defines a reusable step; the following indented lines are its body.
    # A positive result is not complete follow-up when the 14-day window
    # extends beyond the data. Including only positives biases the rate.
    df = frame([game("a", "b", 0), game("b", "z", 3),  # Stores the game table for the next step.
                game("q", "r", 4)])  # Runs this instruction as part of the current step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    assert trials.empty  # Checks an invariant; the script fails if it is false.


def test_prediction_holds_out_whole_spells_and_uses_earlier_features(monkeypatch):  # Defines a reusable step; the following indented lines are its body.
    from src import predict  # Loads the named parts of this project so this file can use their functions.
    rows = []  # Stores the result rows collected for the output table for the next step.
    for spell in range(30):  # Repeats the next indented steps once for each item.
        for hour in range(6):  # Repeats the next indented steps once for each item.
            rows.append({"player": f"p{spell}", "opening": "B20",  # Part of the value, collection, or call spanning several lines.
                         "colour": "W", "t": T0 + timedelta(hours=spell * 6 + hour),
                         "adopted": spell % 2})
    trials = pd.DataFrame(rows)  # Turns the collected encounters into the table used by later tests.
    checked = []  # Saves a value named checked so the next lines can use it.

    def fake_features(games, data, cutoff):  # Defines a reusable step; the following indented lines are its body.
        assert (data.t > cutoff).all()  # Checks an invariant; the script fails if it is false.
        checked.append(cutoff)  # Adds this item to the list being built.
        return data.copy()  # Gives this answer back to the code that called the function.

    def fake_gbm(train, test, columns):  # Defines a reusable step; the following indented lines are its body.
        train_spells = set(train.player)  # Saves a value named train_spells so the next lines can use it.
        test_spells = set(test.player)  # Saves a value named test_spells so the next lines can use it.
        assert train_spells.isdisjoint(test_spells)  # Checks an invariant; the script fails if it is false.
        return 0.6, 0.6  # Gives this answer back to the code that called the function.

    monkeypatch.setattr(predict.features, "build", fake_features)  # Runs this instruction as part of the current step.
    monkeypatch.setattr(predict, "_gbm", fake_gbm)  # Runs this instruction as part of the current step.
    out = predict.evaluate(pd.DataFrame(), trials, full=False)  # Creates a labelled table from the collected rows.
    assert checked and out["split_method"] == "held-out player-opening-colour spells"  # Checks an invariant; the script fails if it is false.
    assert out["n_train"] + out["n_test"] < len(trials)  # burn-in removed


def test_matching_uses_risk_set_at_exposure_time():  # Defines a reusable step; the following indented lines are its body.
    from src import matching  # Loads the named parts of this project so this file can use their functions.
    df = frame([  # Stores the game table for the next step.
        game("b", "u", -2, eco="C00", wr=2000, br=2200),  # Part of the value, collection, or call spanning several lines.
        game("d", "v", -2, eco="C00", wr=2000, br=2200),  # Part of the value, collection, or call spanning several lines.
        game("c", "z", 0, wr=2000, br=2200),  # c already performed B20/W
        game("a", "b", 1, wr=2200, br=2000),  # b first exposed to B20/W
        game("d", "z", 3, eco="C00", wr=2200, br=2200),  # future rating
        game("e", "d", 4, wr=2200, br=2000),  # d exposed only later
        game("d", "x", 6, wr=2000, br=2200),  # d later adopts B20/W
        game("c", "y", 8, eco="C00", wr=2000, br=2200),  # Part of the value, collection, or call spanning several lines.
        game("b", "h", 10, eco="C00", wr=2000, br=2200),  # Part of the value, collection, or call spanning several lines.
        game("q", "r", 40, wr=2200, br=2200),  # Part of the value, collection, or call spanning several lines.
    ])  # Runs this instruction as part of the current step.
    pairs = matching.build_matched(df, max_trials=None)  # Stores the matched exposed and unexposed player pairs for the next step.
    row = pairs[(pairs.exposed == "b") & (pairs.opening == "B20")  # Saves a value named row so the next lines can use it.
                & (pairs.colour == "W")]  # Runs this instruction as part of the current step.
    assert len(row) == 1  # Checks an invariant; the script fails if it is false.
    assert row.iloc[0].control == "d"  # c is a prior adopter, so not at risk
    assert row.iloc[0].control_crossover == 1  # Checks an invariant; the script fails if it is false.
    assert row.iloc[0].control_adopted == 1  # Checks an invariant; the script fails if it is false.
    assert row.iloc[0].control_pre_games == 1  # Checks an invariant; the script fails if it is false.
    assert row.iloc[0].control_pre_rating == 2000  # Checks an invariant; the script fails if it is false.


def test_player_already_playing_it_is_not_at_risk():  # Defines a reusable step; the following indented lines are its body.
    # b plays it on day 0 as White, is exposed to (X,W) later -> no trial
    df = frame([game("b", "z", 0), game("a", "b", 2), game("q", "r", 40)])  # Stores the game table for the next step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    assert trials[(trials.player == "b") & (trials.colour == "W")].empty  # Checks an invariant; the script fails if it is false.


def test_distinct_exposers_counted_not_repeat_exposures():  # Three games from the same opponent is d=1 with k=3.
    """Three games from the same opponent is d=1 with k=3."""
    df = frame([game("a", "b", 0), game("a", "b", 1), game("a", "b", 2),  # Stores the game table for the next step.
                game("q", "r", 40)])  # Runs this instruction as part of the current step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    row = trials[(trials.player == "b") & (trials.colour == "W")]  # Saves a value named row so the next lines can use it.
    assert row["d"].max() == 1  # Checks an invariant; the script fails if it is false.
    assert row["k"].max() == 3  # Checks an invariant; the script fails if it is false.


def test_three_different_exposers_give_d_three():  # Defines a reusable step; the following indented lines are its body.
    df = frame([game("a", "b", 0), game("c", "b", 1), game("e", "b", 2),  # Stores the game table for the next step.
                game("q", "r", 40)])  # Runs this instruction as part of the current step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    row = trials[(trials.player == "b") & (trials.colour == "W")]  # Saves a value named row so the next lines can use it.
    assert row["d"].max() == 3  # Checks an invariant; the script fails if it is false.


# ------------------------------------------------- structural diversity
def test_structural_diversity_separate_exposers_are_separate_components():  # Two exposers who have never met are two components -> sd = 2.
    """Two exposers who have never met are two components -> sd = 2."""
    df = frame([game("a", "b", 0), game("c", "b", 1), game("q", "r", 40)])  # Stores the game table for the next step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    row = trials[(trials.player == "b") & (trials.colour == "W")]  # Saves a value named row so the next lines can use it.
    assert row["sd"].max() == 2  # Checks an invariant; the script fails if it is false.


def test_structural_diversity_connected_exposers_collapse_to_one():  # If the two exposers have played each other, they are one social source.
    """If the two exposers have played each other, they are one social source."""
    df = frame([game("a", "c", 0),        # a and c know each other
                game("a", "b", 1), game("c", "b", 2), game("q", "r", 40)])  # Runs this instruction as part of the current step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    row = trials[(trials.player == "b") & (trials.colour == "W")]  # Saves a value named row so the next lines can use it.
    assert row["d"].max() == 2          # still two distinct people
    assert row["sd"].max() == 1         # but only one component


def test_structural_diversity_ignores_edges_formed_later():  # The exposure subgraph may only use edges that existed at the time.
    """The exposure subgraph may only use edges that existed at the time."""
    df = frame([game("a", "b", 0), game("c", "b", 1),  # Stores the game table for the next step.
                game("a", "c", 30),      # they meet only AFTER the exposures
                game("q", "r", 60)])  # Runs this instruction as part of the current step.
    trials = events.build_trials(df, window_days=14)  # Stores the exposure-trial table for the next step.
    row = trials[(trials.player == "b") & (trials.colour == "W")]  # Saves a value named row so the next lines can use it.
    assert row["sd"].max() == 2  # Checks an invariant; the script fails if it is false.


# ---------------------------------------------------------------- nulls
def test_shuffling_timestamps_preserves_the_games_themselves():  # Defines a reusable step; the following indented lines are its body.
    import numpy as np  # Loads the number library used for fast calculations.
    df = frame([game("a", "b", i) for i in range(10)])  # Stores the game table for the next step.
    out = nulls.shuffle_timestamps(df, np.random.default_rng(0))  # Stores the output value for the next step.
    assert sorted(out["ts"]) == sorted(df["ts"])  # Checks an invariant; the script fails if it is false.
    assert len(out) == len(df)  # Checks an invariant; the script fails if it is false.


def test_aborted_game_does_not_leak_its_tags_into_the_next():  # Lichess contains games with headers but no movetext.
    """Lichess contains games with headers but no movetext. If the scanner only
    resets after a game WITH moves, the aborted game's ECO and Elo leak into
    the following game and it is analysed under the wrong opening."""
    import tempfile  # Loads code this file needs for the steps below.
    from src import parse  # Loads the named parts of this project so this file can use their functions.

    pgn = (  # Saves a value named pgn so the next lines can use it.
        '[Event "Rated Blitz game"]\n[White "ghost"]\n[ECO "Z99"]\n'
        '[WhiteElo "2500"]\n\n'
        '[Event "Rated Blitz game"]\n[White "real"]\n[Black "opp"]\n'
        '[UTCDate "2016.01.03"]\n[UTCTime "00:00:03"]\n[BlackElo "2002"]\n\n'
        'd4 d5 0-1\n'
    )  # Closes the data structure or function call started above.
    f = Path(tempfile.gettempdir()) / "sna_test_aborted.pgn"  # Saves a value named f so the next lines can use it.
    f.write_text(pgn, encoding="utf-8")  # Saves this result so it can be inspected or reused.

    games = list(parse.iter_games(f))  # Saves a value named games so the next lines can use it.
    assert len(games) == 1                       # the aborted game is dropped
    tags, _ = games[0]  # Runs this instruction as part of the current step.
    assert tags["White"] == "real"  # Checks an invariant; the script fails if it is false.
    assert "ECO" not in tags                     # not inherited from the ghost
    assert "WhiteElo" not in tags  # Checks an invariant; the script fails if it is false.


def test_matching_pool_reaches_the_bottom_of_the_activity_tolerance():  # The activity index is log-spaced at the tolerance ratio, so the lowest acceptable activity can floor two buckets down.
    """The activity index is log-spaced at the tolerance ratio, so the lowest
    acceptable activity can floor two buckets down. Searching only one bucket
    below quietly dropped valid controls and biased the pool upwards."""
    import inspect  # Loads code this file needs for the steps below.
    from src import matching  # Loads the named parts of this project so this file can use their functions.

    src = inspect.getsource(matching.build_matched)  # Saves a value named src so the next lines can use it.
    assert "for da in (-2, -1, 0, 1, 2)" in src, (  # Checks an invariant; the script fails if it is false.
        "activity bucket search is too narrow; controls in [0.75a, 0.8a] "
        "can be missed")


def test_rewire_preserves_degree_and_makes_no_self_loops():  # The proposal's second null: degree-preserving edge rewiring.
    """The proposal's second null: degree-preserving edge rewiring. It has to
    change who played whom while leaving every player's game count alone."""
    import numpy as np  # Loads the number library used for fast calculations.
    from collections import Counter  # Loads containers for counting or collecting game records.

    df = pd.DataFrame({  # Creates a labelled table from the collected rows.
        "white": [f"w{i % 7}" for i in range(60)],
        "black": [f"b{i % 5}" for i in range(60)],
        "ts": pd.date_range("2016-01-01", periods=60, freq="h"),
    })  # Runs this instruction as part of the current step.
    out = nulls.rewire_preserving_degree(df, np.random.default_rng(0))  # Stores the output value for the next step.

    def degrees(d):  # Defines a reusable step; the following indented lines are its body.
        c = Counter()  # Saves a value named c so the next lines can use it.
        for u, v in zip(d.white, d.black):  # Repeats the next indented steps once for each item.
            c[u] += 1  # Adds this amount to the running total.
            c[v] += 1  # Adds this amount to the running total.
        return c  # Gives this answer back to the code that called the function.

    assert degrees(df) == degrees(out)  # Checks an invariant; the script fails if it is false.
    assert (out.white != out.black).all()          # no self-loops
    assert set(zip(df.white, df.black)) != set(zip(out.white, out.black))  # Checks an invariant; the script fails if it is false.


def test_null_honours_granularity():  # The null must build trials the same way the real analysis does.
    """The null must build trials the same way the real analysis does.

    Leaving granularity at the default while the real trials are keyed by ply
    compares a sparse ply world against a dense ECO world and manufactures a
    spurious 'complex contagion' verdict. Same class of bug as the adoption
    window mismatch, so it gets the same guard.
    """
    rows = [game(f"p{d}", f"q{d}", d,  # Stores the result rows collected for the output table for the next step.
                 ply="e4 c5 Nf3 d6" if d % 2 == 0 else "e4 c5 Nc3 Nc6")  # Saves a value named ply so the next lines can use it.
            for d in range(6)]  # Repeats the next indented steps once for each item.
    df = frame(rows)  # Stores the game table for the next step.

    # ply granularity must actually split the single ECO into two behaviours
    eco_keys = {events.behaviour_key(r, "eco") for r in df.itertuples()}  # Saves a value named eco_keys so the next lines can use it.
    ply_keys = {events.behaviour_key(r, "ply") for r in df.itertuples()}  # Saves a value named ply_keys so the next lines can use it.
    assert len(eco_keys) == 1 and len(ply_keys) == 2  # Checks an invariant; the script fails if it is false.

    # and run_null must forward that choice to build_trials, not silently
    # fall back to the configured default
    seen = []  # Stores the set of opponents already counted for the next step.
    real_build = events.build_trials  # Saves a value named real_build so the next lines can use it.

    def spy(frame_, *args, **kwargs):  # Defines a reusable step; the following indented lines are its body.
        seen.append(kwargs.get("granularity"))  # Adds this item to the list being built.
        return real_build(frame_, *args, **kwargs)  # Gives this answer back to the code that called the function.

    events.build_trials = spy  # Saves a value named build_trials so the next lines can use it.
    try:  # Starts an operation that may need error handling.
        nulls.run_null(df, n_reps=1, window_days=2, granularity="ply")  # Runs this instruction as part of the current step.
    finally:  # Runs cleanup whether the operation succeeds or fails.
        events.build_trials = real_build  # Saves a value named build_trials so the next lines can use it.

    assert seen and all(g == "ply" for g in seen), (  # Checks an invariant; the script fails if it is false.
        f"run_null passed granularity={seen} to build_trials, expected 'ply'")  # Runs this instruction as part of the current step.


def test_compare_falls_back_to_binomial_se_with_one_replicate():  # A single replicate has no across-replicate spread.
    """A single replicate has no across-replicate spread. Without a fallback
    every z is NaN and the verdict silently collapses to 'nothing detected'."""
    import numpy as np  # Loads the number library used for fast calculations.
    real = pd.DataFrame({"d": [1, 2], "n": [100, 50], "rate": [0.20, 0.25],  # Creates a labelled table from the collected rows.
                         "lo": [0, 0], "hi": [1, 1]})
    one = pd.DataFrame({"d": [1, 2], "n": [100, 50], "rate": [0.15, 0.24],  # Creates a labelled table from the collected rows.
                        "rate_sd": [np.nan, np.nan]})
    z = nulls.compare(real, one)["z_vs_null"]  # Saves a value named z so the next lines can use it.
    assert z.notna().all()  # Checks an invariant; the script fails if it is false.


# --------------------------------------------------------------- verdict
def test_verdict_needs_the_null_before_it_will_call_complex_contagion():  # The bug this guards: a rising raw curve alone was enough to print 'complex contagion', even though the null reproduced the whole rise.
    """The bug this guards: a rising raw curve alone was enough to print
    'complex contagion', even though the null reproduced the whole rise."""
    rising = pd.DataFrame({"d": [1, 2, 3], "n": [1000] * 3,  # Creates a labelled table from the collected rows.
                           "adopted": [100, 200, 300],
                           "rate": [0.10, 0.20, 0.30],
                           "lo": [0.09, 0.19, 0.29], "hi": [0.11, 0.21, 0.31]})
    tables = {"by_d": rising, "held_k_by_d": pd.DataFrame(  # Creates a labelled table from the collected rows.
        columns=["k", "d", "n", "rate", "lo", "hi"])}  # Saves a value named columns so the next lines can use it.
    v = curve.verdict(tables, None)  # Applies the result rules to the real and shuffled curves.
    assert "complex contagion" != v["verdict"]  # Checks an invariant; the script fails if it is false.
    assert "withheld" in v["verdict"] or "no null" in v["verdict"]  # Checks an invariant; the script fails if it is false.


def test_verdict_reports_simple_when_null_matches_the_rise():  # Defines a reusable step; the following indented lines are its body.
    rising = pd.DataFrame({"d": [1, 2, 3], "n": [1000] * 3,  # Creates a labelled table from the collected rows.
                           "adopted": [100, 200, 300],
                           "rate": [0.10, 0.20, 0.30],
                           "lo": [0.09, 0.19, 0.29], "hi": [0.11, 0.21, 0.31]})
    tables = {"by_d": rising, "held_k_by_d": pd.DataFrame(  # Creates a labelled table from the collected rows.
        columns=["k", "d", "n", "rate", "lo", "hi"])}  # Saves a value named columns so the next lines can use it.
    cmp = pd.DataFrame({"d": [1, 2, 3],  # Creates a labelled table from the collected rows.
                        "rate_real": [0.10, 0.20, 0.30],
                        "rate_null": [0.08, 0.18, 0.30],
                        "lift_over_null": [1.25, 1.11, 1.00],
                        "z_vs_null": [9.0, 5.0, 0.1]})
    v = curve.verdict(tables, cmp)  # Applies the result rules to the real and shuffled curves.
    assert v["excess_over_null_grows_with_d"] is False  # Checks an invariant; the script fails if it is false.
    assert v["verdict"].startswith("simple contagion")  # Checks an invariant; the script fails if it is false.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    raise SystemExit(pytest.main([__file__, "-q"]))  # Stops with an explicit error when this requirement is violated.


def test_saved_run_reopens_and_retries_without_losing_history(monkeypatch):  # Defines a reusable step; the following indented lines are its body.
    from server import runner  # Loads the named parts of this project so this file can use their functions.
    from src import config  # Loads the named parts of this project so this file can use their functions.
    import tempfile  # Loads code this file needs for the steps below.

    with tempfile.TemporaryDirectory(dir=config.RESULTS) as folder:  # Opens a resource and guarantees cleanup when the block ends.
        monkeypatch.setattr(runner, "RUNS_DIR", Path(folder))  # Runs this instruction as part of the current step.
        run = runner.Run("2016-01", None, 3, 14)  # Stores the current analysis run for the next step.
        run.emit("init", month=run.month)  # Appends a structured progress event that the browser can replay.
        run.stage("trials", "running")  # Sets the status shown in the live stage list.
        run.emit("done", ok=False)  # Appends a structured progress event that the browser can replay.
        assert runner.list_runs()[0]["status"] == "failed"  # Checks an invariant; the script fails if it is false.

        runner._RUNS.pop(run.id)  # Runs this instruction as part of the current step.
        reopened = runner.get(run.id)  # Saves a value named reopened so the next lines can use it.
        assert reopened is not None  # Checks an invariant; the script fails if it is false.
        assert reopened.events_path.read_text(encoding="utf-8").count("\n") == 3  # Checks an invariant; the script fails if it is false.

        launched = []  # Saves a value named launched so the next lines can use it.
        monkeypatch.setattr(runner, "_launch", lambda r: launched.append(r.id))  # Adds this item to the list being built.
        retried = runner.resume(run.id)  # Saves a value named retried so the next lines can use it.
        assert retried is not None and launched == [run.id]  # Checks an invariant; the script fails if it is false.
        assert (run.dir / "events_attempt_1.jsonl").exists()  # Checks an invariant; the script fails if it is false.
        assert runner.list_runs()[0]["status"] == "running"  # Checks an invariant; the script fails if it is false.
        runner._RUNS.pop(run.id, None)  # Runs this instruction as part of the current step.

def test_cluster_bootstrap_reports_repeated_players():  # Defines a reusable step; the following indented lines are its body.
    from src import matching  # Loads the named parts of this project so this file can use their functions.

    pairs = pd.DataFrame({  # Creates a labelled table from the collected rows.
        "exposed": ["a", "a", "b", "c", "c", "d"],
        "control": ["b", "c", "a", "d", "a", "b"],
        "exposed_adopted": [1, 1, 0, 1, 0, 1],
        "control_adopted": [0, 0, 0, 0, 0, 1],
        "control_crossover": [0, 1, 0, 0, 1, 0],
        "exposed_pre_rating": [1900] * 6,
        "control_pre_rating": [1901] * 6,
        "exposed_pre_games": [10] * 6,
        "control_pre_games": [9] * 6,
    })  # Runs this instruction as part of the current step.
    first = matching.summarise(pairs, bootstrap_reps=200, seed=3)  # Saves a value named first so the next lines can use it.
    second = matching.summarise(pairs, bootstrap_reps=200, seed=3)  # Saves a value named second so the next lines can use it.
    assert first == second  # Checks an invariant; the script fails if it is false.
    assert first["ci95"][0] <= first["difference"] <= first["ci95"][1]  # Checks an invariant; the script fails if it is false.
    assert first["ci95_method"].startswith("player-cluster")  # Checks an invariant; the script fails if it is false.
    assert first["pre_match_balance"]["control_games_mean"] == 9  # Checks an invariant; the script fails if it is false.


def test_null_run_can_stop_between_replicates():  # Defines a reusable step; the following indented lines are its body.
    from src import nulls  # Loads the named parts of this project so this file can use their functions.
    stopped = nulls.run_null(pd.DataFrame(), n_reps=20, should_stop=lambda: True)  # Creates a labelled table from the collected rows.
    assert stopped.empty  # Checks an invariant; the script fails if it is false.
