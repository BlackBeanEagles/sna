"""Synthetic Lichess-format PGN with a KNOWN contagion rule.

Build Guide Step 1: prove the pipeline end to end on a small slice before
touching a 30 GB dump. This generator is also the pipeline's unit test --
it plants a complex-contagion signal (adoption hazard rises with the number
of DISTINCT exposers) and the analysis should recover it, while the
timestamp-shuffled null should destroy it.

Usage:  python -m src.simulate --players 600 --games 40000
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta

import chess
import chess.pgn

from . import config

# (ECO, name, SAN move list) -- real openings, legal from the start position.
OPENINGS = [
    ("B20", "Sicilian Defense",            ["e4", "c5"]),
    ("C00", "French Defense",              ["e4", "e6"]),
    ("B10", "Caro-Kann Defense",           ["e4", "c6"]),
    ("C20", "King's Pawn Game",            ["e4", "e5"]),
    ("B01", "Scandinavian Defense",        ["e4", "d5"]),
    ("D00", "Queen's Pawn Game",           ["d4", "d5"]),
    ("A45", "Indian Defense",              ["d4", "Nf6"]),
    ("A40", "Modern Defense",              ["d4", "g6"]),
    ("A04", "Zukertort Opening",           ["Nf3", "d5"]),
    ("A10", "English Opening",             ["c4", "e6"]),
    ("A00", "Nimzo-Larsen Attack",         ["b3", "e5"]),
    ("B00", "Nimzowitsch Defense",         ["e4", "Nc6"]),
]
ECOS = [o[0] for o in OPENINGS]
BY_ECO = {o[0]: o for o in OPENINGS}

SPEEDS = ["Rapid", "Blitz", "Classical"]
TIME_CONTROLS = {"Rapid": "600+0", "Blitz": "180+2", "Classical": "1800+0"}


def adoption_hazard(d: int, *, base: float, gain: float, lam: float) -> float:
    """Complex contagion: probability rises with DISTINCT exposers d."""
    if d <= 0:
        return base
    return min(1.0, base + gain * (1.0 - math.exp(-lam * d)))


def build_population(n_players: int, n_communities: int, rng: random.Random):
    players, community = [], {}
    for i in range(n_players):
        name = f"sim_{i:05d}"
        players.append(name)
        community[name] = i % n_communities
    rating = {p: int(rng.gauss(2000, 110)) for p in players}
    for p in players:
        rating[p] = max(config.RATING_MIN, min(config.RATING_MAX, rating[p]))
    # heavy-tailed activity: a few players play far more than the rest
    weight = {p: rng.paretovariate(1.6) for p in players}
    return players, community, rating, weight


def pick_opponent(u, players, community, weight, rng, p_within=0.8):
    for _ in range(40):
        v = rng.choices(players, weights=[weight[p] for p in players], k=1)[0]
        if v == u:
            continue
        if community[v] == community[u]:
            if rng.random() < p_within:
                return v
        elif rng.random() < (1 - p_within):
            return v
    return v


def play_out(eco: str, rng: random.Random, extra_plies: int = 12) -> str:
    """SAN movetext: the book line plus random legal continuation."""
    board = chess.Board()
    sans = []
    for san in BY_ECO[eco][2]:
        board.push_san(san)
        sans.append(san)
    for _ in range(extra_plies):
        moves = list(board.legal_moves)
        if not moves:
            break
        mv = rng.choice(moves)
        sans.append(board.san(mv))
        board.push(mv)
    return " ".join(sans)


def simulate(n_players=600, n_games=40000, days=30, n_communities=6,
             base=0.0015, gain=0.06, lam=0.55, seed=config.RANDOM_SEED,
             out_path=None):
    rng = random.Random(seed)
    players, community, rating, weight = build_population(n_players, n_communities, rng)

    # repertoire[(player, colour)] -> set of ECOs the player will actually play
    repertoire = {}
    for p in players:
        for c in "WB":
            repertoire[(p, c)] = set(rng.sample(ECOS, k=rng.choice([1, 1, 2])))
    # exposers[(player, eco, colour)] -> set of distinct opponents seen playing it
    exposers: dict[tuple[str, str, str], set[str]] = {}

    start = datetime(2026, 3, 1, 0, 0, 0)
    out_path = out_path or (config.RAW / "simulated.pgn")
    n_written = 0

    with open(out_path, "w", encoding="utf-8") as fh:
        for g in range(n_games):
            ts = start + timedelta(seconds=int(g / n_games * days * 86400)
                                   + rng.randint(0, 60))
            u = rng.choices(players, weights=[weight[p] for p in players], k=1)[0]
            v = pick_opponent(u, players, community, weight, rng)
            white, black = (u, v) if rng.random() < 0.5 else (v, u)

            # the ECO of a game is jointly produced: whoever "leads" it here
            chooser, chooser_colour = (white, "W") if rng.random() < 0.5 else (black, "B")
            eco = rng.choice(sorted(repertoire[(chooser, chooser_colour)]))

            # --- exposure + adoption (ground truth) ------------------------
            for actor, observer, colour in ((white, black, "W"), (black, white, "B")):
                key = (observer, eco, colour)
                seen = exposers.setdefault(key, set())
                seen.add(actor)
                if eco not in repertoire[(observer, colour)]:
                    if rng.random() < adoption_hazard(len(seen), base=base,
                                                      gain=gain, lam=lam):
                        repertoire[(observer, colour)].add(eco)

            speed = rng.choices(SPEEDS, weights=[0.5, 0.35, 0.15], k=1)[0]
            result = rng.choices(["1-0", "0-1", "1/2-1/2"], weights=[.49, .46, .05], k=1)[0]
            fh.write(
                f'[Event "Rated {speed} game"]\n'
                f'[Site "https://lichess.org/sim{g:07d}"]\n'
                f'[Date "{ts:%Y.%m.%d}"]\n'
                f'[White "{white}"]\n[Black "{black}"]\n'
                f'[Result "{result}"]\n'
                f'[UTCDate "{ts:%Y.%m.%d}"]\n[UTCTime "{ts:%H:%M:%S}"]\n'
                f'[WhiteElo "{rating[white]}"]\n[BlackElo "{rating[black]}"]\n'
                f'[ECO "{eco}"]\n[Opening "{BY_ECO[eco][1]}"]\n'
                f'[TimeControl "{TIME_CONTROLS[speed]}"]\n'
                f'[Termination "Normal"]\n\n'
                f'{play_out(eco, rng)} {result}\n\n'
            )
            n_written += 1

    return {"path": out_path, "games": n_written, "players": n_players,
            "ground_truth": {"base": base, "gain": gain, "lam": lam,
                             "rule": "complex contagion in distinct exposers d"}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=600)
    ap.add_argument("--games", type=int, default=40000)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    a = ap.parse_args()
    info = simulate(n_players=a.players, n_games=a.games, days=a.days, seed=a.seed)
    print(f"wrote {info['games']} games -> {info['path']}")
