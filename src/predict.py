"""Step 7b -- the held-out predictive check.

Two logistic models, trained on the first TRAIN_FRACTION of the observation
period and scored by AUC on the later held-out period:

    baseline : opening popularity + player rating (+ activity)
    network  : baseline + exposure count k + distinct exposers d
               + structural diversity sd + degree/kcore/betweenness

If the network features carry real information, the AUC gap is positive on
data the model has never seen, in a period strictly after training.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config

BASELINE = ["popularity", "rating", "activity"]
NETWORK = BASELINE + ["k", "d", "sd", "degree", "kcore", "betweenness"]


def _fit_auc(train: pd.DataFrame, test: pd.DataFrame, cols: list[str]):
    if train["adopted"].nunique() < 2 or test["adopted"].nunique() < 2:
        return None
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, C=1.0, random_state=config.RANDOM_SEED),
    )
    model.fit(train[cols].fillna(0.0), train["adopted"])
    p = model.predict_proba(test[cols].fillna(0.0))[:, 1]
    coefs = dict(zip(cols, np.round(model[-1].coef_[0], 4)))
    return roc_auc_score(test["adopted"], p), coefs


def run(trials_path: Path, features_path: Path):
    trials = pd.read_parquet(trials_path)
    feats = pd.read_parquet(features_path)
    df = trials.merge(feats, on="player", how="left")

    cut = df["t"].quantile(config.TRAIN_FRACTION)
    train, test = df[df["t"] <= cut], df[df["t"] > cut]
    out = {"n_train": len(train), "n_test": len(test), "split_at": str(cut)}

    base = _fit_auc(train, test, BASELINE)
    net = _fit_auc(train, test, NETWORK)
    if base and net:
        out["auc_baseline"] = round(float(base[0]), 4)
        out["auc_network"] = round(float(net[0]), 4)
        out["auc_gain"] = round(float(net[0] - base[0]), 4)
        out["network_coefficients"] = net[1]
    else:
        out["error"] = "not enough class variation in one of the splits"
    pd.DataFrame([{k: v for k, v in out.items() if k != "network_coefficients"}]
                 ).to_csv(config.TABLES / "predictive_auc.csv", index=False)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", default=str(config.PROCESSED / "trials.parquet"))
    ap.add_argument("--features", default=str(config.PROCESSED / "node_features.parquet"))
    a = ap.parse_args()
    for k, v in run(Path(a.trials), Path(a.features)).items():
        print(f"{k}: {v}")
