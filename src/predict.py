"""Step 7b -- the held-out predictive check.

Train on the first TRAIN_FRACTION of the month, score on the rest. Every
feature is rebuilt from games before the split (src/features.py), so nothing
about the held-out period leaks into training.

The question is not "can adoption be predicted?" but "what explains it?", so
the models are nested and the gaps are the result:

    BASELINE    popularity, rating, activity
    REPERTOIRE  + how close the opening sits to what the player already plays
    NETWORK     + exposure counts, diversity, and centrality

and then the network block is taken apart, because it bundles two claims that
mean opposite things here: how MANY opponents played it at you (exposure,
which simple contagion says matters) versus how DIVERSE they were (which is
what complex contagion requires).

A linear model is the wrong tool for this: fitted with logistic regression all
three sit near chance and the richer models score *worse* out of sample. The
relationships are not linear. Gradient boosting is the primary model here;
`logistic_*` is reported alongside so the difference is on the record rather
than hidden by a model choice.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config, features, parse

NESTED = {
    "baseline": features.BASELINE,
    "repertoire": features.REPERTOIRE,
    "network": features.NETWORK,
}

# what each part of the network block is worth on its own
DECOMPOSE = {
    "plus_k_only": features.REPERTOIRE + ["k"],
    "plus_diversity_only": features.REPERTOIRE + ["d", "sd"],
    "plus_centrality_only": features.REPERTOIRE + ["degree", "kcore", "betweenness"],
}


def _gbm(train, test, cols):
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06,
                                       random_state=config.RANDOM_SEED)
    m.fit(train[cols], train["adopted"])
    return (roc_auc_score(test["adopted"], m.predict_proba(test[cols])[:, 1]),
            roc_auc_score(train["adopted"], m.predict_proba(train[cols])[:, 1]))


def _logistic(train, test, cols):
    m = make_pipeline(StandardScaler(),
                      LogisticRegression(max_iter=2000,
                                         random_state=config.RANDOM_SEED))
    m.fit(train[cols].fillna(0.0), train["adopted"])
    return roc_auc_score(test["adopted"],
                         m.predict_proba(test[cols].fillna(0.0))[:, 1])


def evaluate(games: pd.DataFrame, trials: pd.DataFrame,
             full: bool = True) -> dict:
    """The whole check, on data already in memory.

    `run()` is the file-based entry point; the live console holds the frames
    already and calls this directly, so both go through identical code.

    `full=False` fits only the three nested models, skipping the network-block
    decomposition and the logistic comparison. That is nine model fits down to
    three. The console runs inside a process already holding the games, the
    trials, the graph and the cached slice, and the full version pushed it to
    9 GB and into the pagefile; the decomposition belongs in the CLI, where
    nothing else is resident.
    """
    split = trials["t"].quantile(config.TRAIN_FRACTION)
    data = features.build(games, trials, split)
    train, test = data[data["t"] <= split], data[data["t"] > split]
    if train["adopted"].nunique() < 2 or test["adopted"].nunique() < 2:
        return {"error": "not enough class variation in one of the splits"}

    out = {
        "n_train": int(len(train)), "n_test": int(len(test)),
        "split_at": str(split), "leakage_free": True,
        "base_rate_train": round(float(train["adopted"].mean()), 4),
        "base_rate_test": round(float(test["adopted"].mean()), 4),
    }

    auc = {}
    for name, cols in NESTED.items():
        te, tr = _gbm(train, test, cols)
        auc[name] = te
        out[f"auc_{name}"] = round(float(te), 4)
        out[f"train_auc_{name}"] = round(float(tr), 4)
        if full:
            out[f"logistic_{name}"] = round(float(_logistic(train, test, cols)), 4)

    out["gain_repertoire_over_baseline"] = round(auc["repertoire"] - auc["baseline"], 4)
    out["gain_network_over_repertoire"] = round(auc["network"] - auc["repertoire"], 4)

    if full:
        for name, cols in DECOMPOSE.items():
            te, _ = _gbm(train, test, cols)
            out[f"auc_{name}"] = round(float(te), 4)
            out[f"gain_{name}"] = round(float(te - auc["repertoire"]), 4)
        exposure_gain = max(out["gain_plus_k_only"], out["gain_plus_diversity_only"])
        out["reading"] = (
            f"repertoire proximity is worth {out['gain_repertoire_over_baseline']:+.4f} "
            f"AUC over the baseline; knowing who played the opening at the player adds "
            f"at most {exposure_gain:+.4f} on top of it")
    else:
        out["reading"] = (
            f"repertoire proximity is worth {out['gain_repertoire_over_baseline']:+.4f} "
            f"AUC over the baseline; social exposure and centrality together add "
            f"{out['gain_network_over_repertoire']:+.4f} on top of it")

    return out


def run(trials_path: Path, games_path: Path) -> dict:
    out = evaluate(parse.load_games(games_path), pd.read_parquet(trials_path))
    pd.DataFrame([out]).to_csv(config.TABLES / "predictive_auc.csv", index=False)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", default=str(config.PROCESSED / "trials.parquet"))
    ap.add_argument("--games", default=str(config.INTERIM / "games.parquet"))
    a = ap.parse_args()
    for k, v in run(Path(a.trials), Path(a.games)).items():
        print(f"{k}: {v}")
