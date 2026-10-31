"""Step 7b -- the held-out predictive check.

Use an initial observation period to build fixed background features, then
hold out entire player-opening-colour spells. A 14-day outcome window in a
31-day archive leaves too little time for a clean temporal train/test split;
grouping spells prevents one adoption from appearing in both sets.

The question is not "can adoption be predicted?" but "what explains it?", so
the models are nested and the gaps are the result:

    BASELINE    popularity, rating, activity
    REPERTOIRE  + how close the opening sits to what the player already plays
    NETWORK     + exposure counts, diversity, and centrality

and then the network block is taken apart, because it bundles two claims that
mean opposite things here: how MANY opponents played it at you (exposure,
which simple contagion says matters) versus how DIVERSE they were (which is
what complex contagion requires).

Gradient boosting is the primary model. Logistic regression is reported
alongside as a simpler comparison. The held-out model gaps are descriptive:
they do not establish that an opponent caused adoption.
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
from pathlib import Path  # Loads Path to find and save project files.

import pandas as pd  # Loads the table library used to store games and trials.
from sklearn.ensemble import HistGradientBoostingClassifier  # Loads code this file needs for the steps below.
from sklearn.linear_model import LogisticRegression  # Loads code this file needs for the steps below.
from sklearn.metrics import roc_auc_score  # Measures how well the model ranks adopters above non-adopters on held-out data.
from sklearn.model_selection import GroupShuffleSplit  # Keeps whole player-opening-colour spells together in train or test data.
from sklearn.pipeline import make_pipeline  # Loads code this file needs for the steps below.
from sklearn.preprocessing import StandardScaler  # Loads code this file needs for the steps below.

from . import config, features, parse  # Loads the named parts of this project so this file can use their functions.

NESTED = {  # Saves a value named NESTED so the next lines can use it.
    "baseline": features.BASELINE,
    "repertoire": features.REPERTOIRE,
    "network": features.NETWORK,
}  # Closes the data structure or function call started above.

# what each part of the network block is worth on its own
DECOMPOSE = {  # Saves a value named DECOMPOSE so the next lines can use it.
    "plus_k_only": features.REPERTOIRE + ["k"],
    "plus_diversity_only": features.REPERTOIRE + ["d", "sd"],
    "plus_centrality_only": features.REPERTOIRE + ["degree", "kcore", "betweenness"],
}  # Closes the data structure or function call started above.


def _gbm(train, test, cols):  # Defines a reusable step; the following indented lines are its body.
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,  # Saves a value named m so the next lines can use it.
                                       random_state=config.RANDOM_SEED)  # Saves a value named random_state so the next lines can use it.
    m.fit(train[cols], train["adopted"])  # Runs this instruction as part of the current step.
    return (roc_auc_score(test["adopted"], m.predict_proba(test[cols])[:, 1]),  # Measures how well the model ranks adopters above non-adopters on held-out data.
            roc_auc_score(train["adopted"], m.predict_proba(train[cols])[:, 1]))  # Measures how well the model ranks adopters above non-adopters on held-out data.


def _logistic(train, test, cols):  # Defines a reusable step; the following indented lines are its body.
    m = make_pipeline(StandardScaler(),  # Saves a value named m so the next lines can use it.
                      LogisticRegression(max_iter=2000,  # Part of the value, collection, or call spanning several lines.
                                         random_state=config.RANDOM_SEED))  # Saves a value named random_state so the next lines can use it.
    m.fit(train[cols].fillna(0.0), train["adopted"])  # Runs this instruction as part of the current step.
    return roc_auc_score(test["adopted"],  # Measures how well the model ranks adopters above non-adopters on held-out data.
                         m.predict_proba(test[cols].fillna(0.0))[:, 1])  # Gets each trial's predicted probability of later adoption.


def evaluate(games: pd.DataFrame, trials: pd.DataFrame,  # The whole check, on data already in memory.
             full: bool = True) -> dict:  # Saves a value named full so the next lines can use it.
    """The whole check, on data already in memory.

    `run()` is the file-based entry point; the live console holds the frames
    already and calls this directly, so both go through identical code.

    `full=False` fits only the three nested models, skipping the network-block
    decomposition and the logistic comparison. That is nine model fits down to
    three. The console runs inside a process already holding the games, the
    trials, the graph and the cached slice, and the full version pushed it to
    9 GB and into the pagefile; the decomposition belongs in the CLI, where
    nothing else is resident.

    Presentation point: compare held-out AUC for baseline, then repertoire,
    then network features. An AUC gain shows predictive signal, not causation.
    """
    # The initial 20% supplies background features. Every evaluated trial
    # occurs later, so even training rows cannot see their own outcomes.
    feature_cutoff = trials["t"].quantile(0.20)  # Saves a value named feature_cutoff so the next lines can use it.
    eligible = trials.loc[trials["t"] > feature_cutoff].copy()  # Saves a value named eligible so the next lines can use it.
    if len(eligible) < 100:  # Checks whether enough records exist for a trustworthy next step.
        return {"error": "not enough trials after the feature cutoff"}  # Gives this answer back to the code that called the function.
    data = features.build(games, eligible, feature_cutoff)  # Saves a value named data so the next lines can use it.
    groups = pd.MultiIndex.from_frame(  # Saves a value named groups so the next lines can use it.
        data[["player", "opening", "colour"]]).factorize()[0]  # Runs this instruction as part of the current step.
    splitter = GroupShuffleSplit(n_splits=1,  # Keeps whole player-opening-colour spells together in train or test data.
                                 test_size=1 - config.TRAIN_FRACTION,  # Saves a value named test_size so the next lines can use it.
                                 random_state=config.RANDOM_SEED)  # Saves a value named random_state so the next lines can use it.
    train_idx, test_idx = next(splitter.split(data, data["adopted"], groups))  # Runs this instruction as part of the current step.
    train, test = data.iloc[train_idx], data.iloc[test_idx]  # Runs this instruction as part of the current step.
    if train["adopted"].nunique() < 2 or test["adopted"].nunique() < 2:  # Runs the next indented steps only when this condition is true.
        return {"error": "not enough class variation in one of the splits"}  # Gives this answer back to the code that called the function.

    out = {  # Stores the output value for the next step.
        "n_train": int(len(train)), "n_test": int(len(test)),
        "split_method": "held-out player-opening-colour spells",
        "feature_cutoff": str(feature_cutoff), "leakage_free": True,
        "base_rate_train": round(float(train["adopted"].mean()), 4),
        "base_rate_test": round(float(test["adopted"].mean()), 4),
    }  # Closes the data structure or function call started above.

    auc = {}  # Saves a value named auc so the next lines can use it.
    for name, cols in NESTED.items():  # Repeats the next indented steps once for each item.
        te, tr = _gbm(train, test, cols)  # Runs this instruction as part of the current step.
        auc[name] = te  # Stores this value under its player, opening, or field key.
        out[f"auc_{name}"] = round(float(te), 4)  # Stores this value under its player, opening, or field key.
        out[f"train_auc_{name}"] = round(float(tr), 4)  # Stores this value under its player, opening, or field key.
        if full:  # Runs the next indented steps only when this condition is true.
            out[f"logistic_{name}"] = round(float(_logistic(train, test, cols)), 4)  # Stores this value under its player, opening, or field key.

    out["gain_repertoire_over_baseline"] = round(auc["repertoire"] - auc["baseline"], 4)  # Stores this value under its player, opening, or field key.
    out["gain_network_over_repertoire"] = round(auc["network"] - auc["repertoire"], 4)  # Stores this value under its player, opening, or field key.

    if full:  # Runs the next indented steps only when this condition is true.
        for name, cols in DECOMPOSE.items():  # Repeats the next indented steps once for each item.
            te, _ = _gbm(train, test, cols)  # Runs this instruction as part of the current step.
            out[f"auc_{name}"] = round(float(te), 4)  # Stores this value under its player, opening, or field key.
            out[f"gain_{name}"] = round(float(te - auc["repertoire"]), 4)  # Stores this value under its player, opening, or field key.
        exposure_gain = max(out["gain_plus_k_only"], out["gain_plus_diversity_only"])  # Saves a value named exposure_gain so the next lines can use it.
        out["reading"] = (  # Part of the value, collection, or call spanning several lines.
            f"repertoire proximity is worth {out['gain_repertoire_over_baseline']:+.4f} "  # Runs this instruction as part of the current step.
            f"AUC over the baseline; knowing who played the opening at the player adds "  # Runs this instruction as part of the current step.
            f"at most {exposure_gain:+.4f} on top of it")  # Runs this instruction as part of the current step.
    else:  # Handles the alternative when the preceding condition was false.
        out["reading"] = (  # Part of the value, collection, or call spanning several lines.
            f"repertoire proximity is worth {out['gain_repertoire_over_baseline']:+.4f} "  # Runs this instruction as part of the current step.
            f"AUC over the baseline; social exposure and centrality together add "  # Runs this instruction as part of the current step.
            f"{out['gain_network_over_repertoire']:+.4f} on top of it")  # Runs this instruction as part of the current step.

    return out  # Gives this answer back to the code that called the function.


def run(trials_path: Path, games_path: Path) -> dict:  # Defines a reusable step; the following indented lines are its body.
    out = evaluate(parse.load_games(games_path), pd.read_parquet(trials_path))  # Loads a previously prepared game or trial table.
    pd.DataFrame([out]).to_csv(config.TABLES / "predictive_auc.csv", index=False)  # Creates a labelled table from the collected rows.
    return out  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--trials", default=str(config.PROCESSED / "trials.parquet"))  # Defines a command-line option for this script.
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    for k, v in run(Path(a.trials), Path(a.games)).items():  # Repeats the next indented steps once for each item.
        print(f"{k}: {v}")  # Prints this reading so a command-line run can be followed.
