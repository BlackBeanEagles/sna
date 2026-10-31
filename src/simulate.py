"""Synthetic Lichess-format PGN with a KNOWN contagion rule.

Build Guide Step 1: prove the pipeline end to end on a small slice before
touching a 30 GB dump. This generator is also the pipeline's unit test --
it plants a complex-contagion signal (adoption hazard rises with the number
of DISTINCT exposers) and the analysis should recover it, while the
timestamp-shuffled null should destroy it.

Usage:  python -m src.simulate --players 600 --games 40000
"""
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import math  # Loads code this file needs for the steps below.
import random  # Loads code this file needs for the steps below.
from datetime import datetime, timedelta  # Loads code this file needs for the steps below.

import chess  # Loads chess rules so the board accepts only legal moves.
import chess.pgn  # Loads chess rules so the board accepts only legal moves.

from . import config  # Loads the named parts of this project so this file can use their functions.

# (ECO, name, SAN move list) -- real openings, legal from the start position.
OPENINGS = [  # Saves a value named OPENINGS so the next lines can use it.
    ("B20", "Sicilian Defense",            ["e4", "c5"]),  # Part of the value, collection, or call spanning several lines.
    ("C00", "French Defense",              ["e4", "e6"]),  # Part of the value, collection, or call spanning several lines.
    ("B10", "Caro-Kann Defense",           ["e4", "c6"]),  # Part of the value, collection, or call spanning several lines.
    ("C20", "King's Pawn Game",            ["e4", "e5"]),  # Part of the value, collection, or call spanning several lines.
    ("B01", "Scandinavian Defense",        ["e4", "d5"]),  # Part of the value, collection, or call spanning several lines.
    ("D00", "Queen's Pawn Game",           ["d4", "d5"]),  # Part of the value, collection, or call spanning several lines.
    ("A45", "Indian Defense",              ["d4", "Nf6"]),  # Part of the value, collection, or call spanning several lines.
    ("A40", "Modern Defense",              ["d4", "g6"]),  # Part of the value, collection, or call spanning several lines.
    ("A04", "Zukertort Opening",           ["Nf3", "d5"]),  # Part of the value, collection, or call spanning several lines.
    ("A10", "English Opening",             ["c4", "e6"]),  # Part of the value, collection, or call spanning several lines.
    ("A00", "Nimzo-Larsen Attack",         ["b3", "e5"]),  # Part of the value, collection, or call spanning several lines.
    ("B00", "Nimzowitsch Defense",         ["e4", "Nc6"]),  # Part of the value, collection, or call spanning several lines.
]  # Closes the data structure or function call started above.
ECOS = [o[0] for o in OPENINGS]  # Saves a value named ECOS so the next lines can use it.
BY_ECO = {o[0]: o for o in OPENINGS}  # Saves a value named BY_ECO so the next lines can use it.

SPEEDS = ["Rapid", "Blitz", "Classical"]  # Saves a value named SPEEDS so the next lines can use it.
TIME_CONTROLS = {"Rapid": "600+0", "Blitz": "180+2", "Classical": "1800+0"}  # Saves a value named TIME_CONTROLS so the next lines can use it.


def adoption_hazard(d: int, *, base: float, gain: float, lam: float) -> float:  # Complex contagion: probability rises with DISTINCT exposers d.
    """Complex contagion: probability rises with DISTINCT exposers d."""
    if d <= 0:  # Runs the next indented steps only when this condition is true.
        return base  # Gives this answer back to the code that called the function.
    return min(1.0, base + gain * (1.0 - math.exp(-lam * d)))  # Gives this answer back to the code that called the function.


def build_population(n_players: int, n_communities: int, rng: random.Random):  # Defines a reusable step; the following indented lines are its body.
    players, community = [], {}  # Runs this instruction as part of the current step.
    for i in range(n_players):  # Repeats the next indented steps once for each item.
        name = f"sim_{i:05d}"  # Saves a value named name so the next lines can use it.
        players.append(name)  # Adds this item to the list being built.
        community[name] = i % n_communities  # Stores this value under its player, opening, or field key.
    rating = {p: int(rng.gauss(2000, 110)) for p in players}  # Saves a value named rating so the next lines can use it.
    for p in players:  # Repeats the next indented steps once for each item.
        rating[p] = max(config.RATING_MIN, min(config.RATING_MAX, rating[p]))  # Stores this value under its player, opening, or field key.
    # heavy-tailed activity: a few players play far more than the rest
    weight = {p: rng.paretovariate(1.6) for p in players}  # Saves a value named weight so the next lines can use it.
    return players, community, rating, weight  # Gives this answer back to the code that called the function.


def pick_opponent(u, players, community, weight, rng, p_within=0.8):  # Defines a reusable step; the following indented lines are its body.
    for _ in range(40):  # Repeats the next indented steps once for each item.
        v = rng.choices(players, weights=[weight[p] for p in players], k=1)[0]  # Saves a value named v so the next lines can use it.
        if v == u:  # Runs the next indented steps only when this condition is true.
            continue  # Skips this item and moves to the next loop iteration.
        if community[v] == community[u]:  # Runs the next indented steps only when this condition is true.
            if rng.random() < p_within:  # Runs the next indented steps only when this condition is true.
                return v  # Gives this answer back to the code that called the function.
        elif rng.random() < (1 - p_within):  # Runs the next indented steps only when this condition is true.
            return v  # Gives this answer back to the code that called the function.
    return v  # Gives this answer back to the code that called the function.


def play_out(eco: str, rng: random.Random, extra_plies: int = 12) -> str:  # SAN movetext: the book line plus random legal continuation.
    """SAN movetext: the book line plus random legal continuation."""
    board = chess.Board()  # Saves a value named board so the next lines can use it.
    sans = []  # Stores the moves written in chess notation for the next step.
    for san in BY_ECO[eco][2]:  # Repeats the next indented steps once for each item.
        board.push_san(san)  # Runs this instruction as part of the current step.
        sans.append(san)  # Adds this item to the list being built.
    for _ in range(extra_plies):  # Repeats the next indented steps once for each item.
        moves = list(board.legal_moves)  # Saves a value named moves so the next lines can use it.
        if not moves:  # Runs the next indented steps only when this condition is true.
            break  # Ends the current loop.
        mv = rng.choice(moves)  # Saves a value named mv so the next lines can use it.
        sans.append(board.san(mv))  # Adds this item to the list being built.
        board.push(mv)  # Runs this instruction as part of the current step.
    return " ".join(sans)  # Gives this answer back to the code that called the function.


def simulate(n_players=600, n_games=40000, days=30, n_communities=6,  # Write PGN with a planted distinct-opponent adoption rule.
             base=0.0015, gain=0.06, lam=0.55, seed=config.RANDOM_SEED,  # Saves a value named base so the next lines can use it.
             out_path=None):  # Saves a value named out_path so the next lines can use it.
    """Write PGN with a planted distinct-opponent adoption rule.

    Use this to check whether the pipeline can detect a rule we know was put
    into the data. It is separate from the real January 2016 study.
    """
    rng = random.Random(seed)  # Saves a value named rng so the next lines can use it.
    players, community, rating, weight = build_population(n_players, n_communities, rng)  # Runs this instruction as part of the current step.

    # repertoire[(player, colour)] -> set of ECOs the player will actually play
    repertoire = {}  # Saves a value named repertoire so the next lines can use it.
    for p in players:  # Repeats the next indented steps once for each item.
        for c in "WB":  # Repeats the next indented steps once for each item.
            repertoire[(p, c)] = set(rng.sample(ECOS, k=rng.choice([1, 1, 2])))  # Stores this value under its player, opening, or field key.
    # exposers[(player, eco, colour)] -> set of distinct opponents seen playing it
    exposers: dict[tuple[str, str, str], set[str]] = {}  # Saves a value named exposers so the next lines can use it.

    start = datetime(2026, 3, 1, 0, 0, 0)  # Saves a value named start so the next lines can use it.
    out_path = out_path or (config.RAW / "simulated.pgn")  # Saves a value named out_path so the next lines can use it.
    n_written = 0  # Saves a value named n_written so the next lines can use it.

    with open(out_path, "w", encoding="utf-8") as fh:  # Opens a resource and guarantees cleanup when the block ends.
        for g in range(n_games):  # Repeats the next indented steps once for each item.
            ts = start + timedelta(seconds=int(g / n_games * days * 86400)  # Saves a value named ts so the next lines can use it.
                                   + rng.randint(0, 60))  # Runs this instruction as part of the current step.
            u = rng.choices(players, weights=[weight[p] for p in players], k=1)[0]  # Saves a value named u so the next lines can use it.
            v = pick_opponent(u, players, community, weight, rng)  # Saves a value named v so the next lines can use it.
            white, black = (u, v) if rng.random() < 0.5 else (v, u)  # Runs this instruction as part of the current step.

            # the ECO of a game is jointly produced: whoever "leads" it here
            chooser, chooser_colour = (white, "W") if rng.random() < 0.5 else (black, "B")  # Runs this instruction as part of the current step.
            eco = rng.choice(sorted(repertoire[(chooser, chooser_colour)]))  # Saves a value named eco so the next lines can use it.

            # --- exposure + adoption (ground truth) ------------------------
            for actor, observer, colour in ((white, black, "W"), (black, white, "B")):  # Processes both sides of each game as a performance and an exposure.
                key = (observer, eco, colour)  # Saves a value named key so the next lines can use it.
                seen = exposers.setdefault(key, set())  # Stores the set of opponents already counted for the next step.
                seen.add(actor)  # Adds this item to the collection being built.
                if eco not in repertoire[(observer, colour)]:  # Runs the next indented steps only when this condition is true.
                    if rng.random() < adoption_hazard(len(seen), base=base,  # Checks whether enough records exist for a trustworthy next step.
                                                      gain=gain, lam=lam):  # Saves a value named gain so the next lines can use it.
                        repertoire[(observer, colour)].add(eco)  # Adds this item to the collection being built.

            speed = rng.choices(SPEEDS, weights=[0.5, 0.35, 0.15], k=1)[0]  # Saves a value named speed so the next lines can use it.
            result = rng.choices(["1-0", "0-1", "1/2-1/2"], weights=[.49, .46, .05], k=1)[0]  # Saves a value named result so the next lines can use it.
            fh.write(  # Part of the value, collection, or call spanning several lines.
                f'[Event "Rated {speed} game"]\n'  # Runs this instruction as part of the current step.
                f'[Site "https://lichess.org/sim{g:07d}"]\n'  # Runs this instruction as part of the current step.
                f'[Date "{ts:%Y.%m.%d}"]\n'  # Runs this instruction as part of the current step.
                f'[White "{white}"]\n[Black "{black}"]\n'  # Runs this instruction as part of the current step.
                f'[Result "{result}"]\n'  # Runs this instruction as part of the current step.
                f'[UTCDate "{ts:%Y.%m.%d}"]\n[UTCTime "{ts:%H:%M:%S}"]\n'  # Runs this instruction as part of the current step.
                f'[WhiteElo "{rating[white]}"]\n[BlackElo "{rating[black]}"]\n'  # Runs this instruction as part of the current step.
                f'[ECO "{eco}"]\n[Opening "{BY_ECO[eco][1]}"]\n'  # Runs this instruction as part of the current step.
                f'[TimeControl "{TIME_CONTROLS[speed]}"]\n'  # Runs this instruction as part of the current step.
                f'[Termination "Normal"]\n\n'  # Runs this instruction as part of the current step.
                f'{play_out(eco, rng)} {result}\n\n'  # Runs this instruction as part of the current step.
            )  # Closes the data structure or function call started above.
            n_written += 1  # Adds this amount to the running total.

    return {"path": out_path, "games": n_written, "players": n_players,  # Gives this answer back to the code that called the function.
            "ground_truth": {"base": base, "gain": gain, "lam": lam,
                             "rule": "complex contagion in distinct exposers d"}}


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--players", type=int, default=600)  # Defines a command-line option for this script.
    ap.add_argument("--games", type=int, default=40000)  # Defines a command-line option for this script.
    ap.add_argument("--days", type=int, default=30)  # Defines a command-line option for this script.
    ap.add_argument("--seed", type=int, default=config.RANDOM_SEED)  # Defines a command-line option for this script.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    info = simulate(n_players=a.players, n_games=a.games, days=a.days, seed=a.seed)  # Saves a value named info so the next lines can use it.
    print(f"wrote {info['games']} games -> {info['path']}")  # Prints this reading so a command-line run can be followed.
