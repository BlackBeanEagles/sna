"""Create line-by-line speaking copies of the source for a code presentation.

The .explained.txt files are reference copies, never imported or served. Run
`python scripts/build_annotated_code.py` after changing source code so their
line numbers and explanations stay aligned with the working files.
"""

from __future__ import annotations  # Loads code this file needs for the steps below.

import ast  # Loads code this file needs for the steps below.
import re  # Loads pattern matching for text in game records.
import tokenize  # Loads code this file needs for the steps below.
from io import StringIO  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.


ROOT = Path(__file__).resolve().parents[1]  # Saves a value named ROOT so the next lines can use it.
OUT = ROOT / "presentation_notes" / "code_explained"  # Saves a value named OUT so the next lines can use it.
FOLDERS = ("src", "server", "site", "scripts", "tests")  # Saves a value named FOLDERS so the next lines can use it.
EXTENSIONS = {".py", ".html", ".css"}  # Saves a value named EXTENSIONS so the next lines can use it.

# These are the short sentences to say before opening each important file.
OVERVIEW = {  # Saves a value named OVERVIEW so the next lines can use it.
    "server/app.py": "The browser sends requests here. This file routes them to the runner and streams progress back.",
    "server/runner.py": "This is the live workflow: load games, build trials, measure the network, run checks, and emit results.",
    "server/static/index.html": "This page draws the live dashboard from the runner's JSON events and sends board moves to Python.",
    "src/parse.py": "This reads Lichess PGN records and applies the fixed study filters.",
    "src/events.py": "This turns encounters into exposure trials and first-use outcomes.",
    "src/structure.py": "This constructs the player network and measures communities and centrality.",
    "src/curve.py": "This calculates adoption rates by exposure and applies the verdict rules.",
    "src/nulls.py": "This shuffles game times to build the reference curve for comparison.",
    "src/matching.py": "This compares exposed players with similar players still at risk.",
    "src/features.py": "This builds earlier-only player, repertoire and network features.",
    "src/predict.py": "This tests whether those features improve prediction on held-out player-opening spells.",
    "src/run_pipeline.py": "This is the command-line version of the end-to-end analysis.",
    "site/page.html": "This is the editable findings-page template, using saved report data.",
    "site/build.py": "This embeds the saved results and stylesheet into the local findings page.",
    "tests/test_events.py": "These small known cases check that the trial and comparison logic counts correctly.",
}  # Closes the data structure or function call started above.

TERMS = {  # Saves a value named TERMS so the next lines can use it.
    "df": "game table", "trials": "exposure-trial table", "g": "player graph",
    "k": "total exposure count", "d": "distinct-opponent count",
    "sd": "structural-diversity count", "beh": "opening-and-colour behaviour",
    "t0": "exposure time", "t_end": "last observed game time",
    "cmp": "observed-versus-reference comparison", "null": "shuffled reference",
    "feats": "network features", "report": "saved study results",
    "run": "current analysis run", "out": "output value",
    "exposures": "encounter log keyed by player and behaviour",
    "first_perf": "first-use time for each player and behaviour",
    "edge_first_t": "first meeting time for each opponent pair",
    "parent": "union-find parent list for grouping connected exposers",
    "seen": "set of opponents already counted",
    "distinct": "ordered list of different exposing opponents",
    "adopted": "14-day first-use outcome",
    "rows": "result rows collected for the output table",
    "t": "current game or exposure time",
    "window": "time allowed for a later first use",
    "t0_ns": "comparison time in a fast numeric form",
    "null_df": "same games with their dates shuffled",
    "null_by_d": "reference rates grouped by different opponents",
    "real_by_d": "real rates grouped by different opponents",
    "pairs": "matched exposed and unexposed player pairs",
    "msum": "summary of the matched comparison",
    "tables": "adoption-rate tables for the charts",
    "pred": "held-out prediction results",
    "sans": "moves written in chess notation",
    "fen": "board position in a standard chess format",
}  # Closes the data structure or function call started above.


def function_summaries(source: str) -> dict[int, str]:  # Use the source's own docstrings when explaining function definitions.
    """Use the source's own docstrings when explaining function definitions."""
    try:  # Starts an operation that may need error handling.
        tree = ast.parse(source)  # Saves a value named tree so the next lines can use it.
    except SyntaxError:  # Handles this specific failure without hiding other errors.
        return {}  # Gives this answer back to the code that called the function.
    result = {}  # Saves a value named result so the next lines can use it.
    for node in ast.walk(tree):  # Repeats the next indented steps once for each item.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):  # Runs the next indented steps only when this condition is true.
            doc = ast.get_docstring(node) or ""  # Saves a value named doc so the next lines can use it.
            first = " ".join(doc.strip().split("\n\n", 1)[0].split()) if doc.strip() else ""  # Saves a value named first so the next lines can use it.
            if first:  # Runs the next indented steps only when this condition is true.
                result[node.lineno] = first.split(". ", 1)[0].rstrip(".") + "."  # Stores this value under its player, opening, or field key.
    return result  # Gives this answer back to the code that called the function.


def documentation_lines(source: str) -> set[int]:  # Docstrings and comments explain themselves; annotate executable lines.
    """Docstrings and comments explain themselves; annotate executable lines."""
    covered = set()  # Saves a value named covered so the next lines can use it.
    try:  # Starts an operation that may need error handling.
        for token in tokenize.generate_tokens(StringIO(source).readline):  # Repeats the next indented steps once for each item.
            if token.type in (tokenize.STRING, tokenize.COMMENT):  # Runs the next indented steps only when this condition is true.
                # A standalone string is a module/function docstring; an
                # ordinary literal inside code is left to the code note.
                standalone_comment = (token.type == tokenize.COMMENT and  # Saves a value named standalone_comment so the next lines can use it.
                                      not source.splitlines()[token.start[0] - 1][:token.start[1]].strip())  # Runs this instruction as part of the current step.
                if standalone_comment or (token.type == tokenize.STRING and  # Runs the next indented steps only when this condition is true.
                                          ("\n" in token.string or token.start[1] <= 4)):  # Part of the value, collection, or call spanning several lines.
                    covered.update(range(token.start[0], token.end[0] + 1))  # Adds this item to the collection being built.
    except tokenize.TokenError:  # Handles this specific failure without hiding other errors.
        pass  # Leaves this branch intentionally without extra work.
    return covered  # Gives this answer back to the code that called the function.


def describe_python(line: str, number: int, summaries: dict[int, str]) -> str:  # Defines a reusable step; the following indented lines are its body.
    s = line.strip()  # Saves a value named s so the next lines can use it.
    special = (  # Saves a value named special so the next lines can use it.
        ("df = df.sort_values(\"ts\")", "Puts games in time order so earlier encounters cannot use future information."),  # Orders the rows by this field before the next calculation.
        ("key_col =", "Chooses whether the behaviour is an ECO opening or a more specific opening line."),  # Chooses whether the behaviour is an ECO opening or a more specific opening line.
        ("t_end = df[\"ts\"].max()", "Finds the last game date; a trial needs enough time after it to observe the outcome."),  # Part of the value, collection, or call spanning several lines.
        ("if t + window > t_end", "Skips late encounters because we cannot observe a full follow-up period for them."),  # Skips late encounters because we cannot observe a full follow-up period for them.
        ("trials = pd.DataFrame(rows", "Turns the collected encounters into the table used by later tests."),  # Turns the collected encounters into the table used by later tests.
        ("out[\"ts\"] = rng.permutation", "Mixes up game dates but keeps the players and opening in each game."),  # Randomly reassigns game timestamps while keeping each game's players and opening.
        ("null_df =", "Creates one shuffled-date version of the same games."),  # Creates one shuffled-date version of the same games.
        ("tb = curve.analyse(trials)", "Recalculates the adoption curve from these shuffled-date trials."),  # Recalculates the adoption curve from these shuffled-date trials.
        ("valid = peers[eligible_until", "Keeps only comparison players who had not yet seen or played this opening."),  # Keeps only comparison players who had not yet seen or played this opening.
        ("treat = int(", "Records whether the exposed player first used the opening during follow-up."),  # Records whether the exposed player first used the opening during follow-up.
        ("c_adopt =", "Finds when the comparison player first used the opening."),  # Finds when the comparison player first used the opening.
        ("c_exposed =", "Finds when the comparison player later encountered the opening."),  # Finds when the comparison player later encountered the opening.
        ("g = structure.build_graph", "Connects players who faced each other in the selected games."),  # Connects players who faced each other in the selected games.
        ("tables = curve.analyse(trials)", "Calculates adoption rates for different exposure counts."),  # Calculates adoption rates for different exposure counts.
        ("v = curve.verdict", "Applies the result rules to the real and shuffled curves."),  # Applies the result rules to the real and shuffled curves.
        ("if run.predict", "Runs the slower prediction check only when the presenter chooses it."),  # Runs the slower prediction check only when the presenter chooses it.
        ("board_demo_payload()", "Loads saved real games for the board without starting a new analysis."),  # Loads saved real games for the board without starting a new analysis.
        ("e = frozenset((w, b))", "Makes an unordered opponent pair, so White–Black order cannot create two links."),  # Makes an unordered opponent pair, so White–Black order cannot create two links.
        ("if e not in edge_first_t", "Adds only the first meeting time for this opponent pair."),  # Adds only the first meeting time for this opponent pair.
        ("for actor, observer, colour", "Processes both sides of each game as a performance and an exposure."),  # Processes both sides of each game as a performance and an exposure.
        ("first_perf.setdefault", "Records first use without overwriting it on later games."),  # Records first use without overwriting it on later games.
        ("exposures[(observer, beh)].append", "Adds an exposure event for the player who watched the opponent play this behaviour."),  # Adds an exposure event for the player who watched the opponent play this behaviour.
        ("parent[i] = parent[parent[i]]", "Shortens the search path while finding a connected exposer group."),  # Shortens the search path while finding a connected exposer group.
        ("parent[ri] = rj", "Joins two exposer groups after finding a link between them."),  # Joins two exposer groups after finding a link between them.
        ("len({find(i) for i in range(n)})", "Counts how many separate social sources the exposing opponents form."),  # Counts how many separate social sources the exposing opponents form.
        ("if exposer not in seen", "Counts a repeat opponent once for d, even if they played many games."),  # Counts a repeat opponent once for d, even if they played many games.
        ("seen.add(exposer)", "Marks this opponent as already included in the distinct count."),  # Marks this opponent as already included in the distinct count.
        ("distinct.append(exposer)", "Keeps this new opponent for the structural-diversity calculation."),  # Keeps this new opponent for the structural-diversity calculation.
        ("if adopt_t is not None and adopt_t <= t", "Stops creating trials after the player has already performed this behaviour."),  # Stops creating trials after the player has already performed this behaviour.
        ("edge_first_t[e] = ts", "Remembers when these two players first met, so later structure uses only past links."),  # Remembers when these two players first met, so later structure uses only past links.
        ("t + window > t_end", "Excludes late encounters that cannot receive a complete follow-up window."),  # Excludes late encounters that cannot receive a complete follow-up window.
        ("adopted = int(", "Marks adoption only when first use occurs after exposure and within the follow-up window."),  # Marks adoption only when first use occurs after exposure and within the follow-up window.
        ("sd = _components", "Counts independent groups among the distinct exposing opponents."),  # Counts independent groups among the distinct exposing opponents.
        ("rng.permutation", "Randomly reassigns game timestamps while keeping each game's players and opening."),  # Randomly reassigns game timestamps while keeping each game's players and opening.
        ("lift_over_null", "Compares the observed adoption rate with the shuffled-time reference rate."),  # Compares the observed adoption rate with the shuffled-time reference rate.
        ("roc_auc_score", "Measures how well the model ranks adopters above non-adopters on held-out data."),  # Measures how well the model ranks adopters above non-adopters on held-out data.
        ("GroupShuffleSplit", "Keeps whole player-opening-colour spells together in train or test data."),  # Keeps whole player-opening-colour spells together in train or test data.
        (".predict_proba", "Gets each trial's predicted probability of later adoption."),  # Gets each trial's predicted probability of later adoption.
        (".groupby(", "Groups rows sharing these keys before counting or averaging them."),  # Groups rows sharing these keys before counting or averaging them.
        (".merge(", "Joins two tables on shared identifiers so their columns can be compared."),  # Joins two tables on shared identifiers so their columns can be compared.
        (".value_counts(", "Counts how often each player or opening occurs."),  # Counts how often each player or opening occurs.
        (".sort_values(", "Orders the rows by this field before the next calculation."),  # Orders the rows by this field before the next calculation.
        (".clip(", "Caps large counts into the final chart bucket, such as six or more opponents."),  # Caps large counts into the final chart bucket, such as six or more opponents.
        (".to_dict(", "Converts table values into JSON-friendly records for a report or UI event."),  # Converts table values into JSON-friendly records for a report or UI event.
        ("json.loads(", "Decodes saved JSON text into Python data."),  # Decodes saved JSON text into Python data.
        ("json.dumps(", "Encodes Python values as JSON for saving or sending to the browser."),  # Encodes Python values as JSON for saving or sending to the browser.
        ("run.emit(", "Appends a structured progress event that the browser can replay."),  # Appends a structured progress event that the browser can replay.
        ("run.stage(", "Sets the status shown in the live stage list."),  # Sets the status shown in the live stage list.
        ("run.log(", "Adds a short explanation to the live progress log."),  # Adds a short explanation to the live progress log.
        ("pd.DataFrame(", "Creates a labelled table from the collected rows."),  # Creates a labelled table from the collected rows.
        ("nx.community.louvain_communities", "Finds groups of players with relatively dense internal connections."),  # Finds groups of players with relatively dense internal connections.
        ("nx.betweenness_centrality", "Estimates how often players bridge shortest routes through the graph."),  # Estimates how often players bridge shortest routes through the graph.
        ("nx.core_number", "Measures how deeply each player lies in a mutually connected core."),  # Measures how deeply each player lies in a mutually connected core.
        ("first_exp_ns", "Tracks when a control player was first exposed, so matching uses only people still at risk."),  # Tracks when a control player was first exposed, so matching uses only people still at risk.
        ("first_perf_ns", "Tracks first performance time to exclude people who already adopted before matching."),  # Tracks first performance time to exclude people who already adopted before matching.
    )  # Closes the data structure or function call started above.
    for needle, explanation in special:  # Repeats the next indented steps once for each item.
        if needle in s:  # Runs the next indented steps only when this condition is true.
            return explanation  # Gives this answer back to the code that called the function.
    if s.startswith(("from ", "import ")):  # Runs the next indented steps only when this condition is true.
        module = s.split()[1].split(".")[0]  # Saves a value named module so the next lines can use it.
        if s.startswith("from . import") or s.startswith("from src import") or s.startswith("from server import"):
            return "Loads the named parts of this project so this file can use their functions."
        if module == "pathlib":
            return "Loads Path to find and save project files."
        if module == "json":
            return "Loads JSON tools for saved results and browser messages."
        if module == "argparse":
            return "Loads the tool that reads command-line choices."
        if module == "collections":
            return "Loads containers for counting or collecting game records."
        if module == "re":
            return "Loads pattern matching for text in game records."
        if module in {"pandas", "pd"}:  # Runs the next indented steps only when this condition is true.
            return "Loads the table library used to store games and trials."  # Gives this answer back to the code that called the function.
        if module in {"numpy", "np"}:  # Runs the next indented steps only when this condition is true.
            return "Loads the number library used for fast calculations."  # Gives this answer back to the code that called the function.
        if module in {"networkx", "nx"}:  # Runs the next indented steps only when this condition is true.
            return "Loads the library used to build and measure player links."  # Gives this answer back to the code that called the function.
        if module in {"chess"}:  # Runs the next indented steps only when this condition is true.
            return "Loads chess rules so the board accepts only legal moves."  # Gives this answer back to the code that called the function.
        return "Loads code this file needs for the steps below."  # Gives this answer back to the code that called the function.
    if s.startswith("class "):  # Runs the next indented steps only when this condition is true.
        return summaries.get(number, "Defines an object used by this module.")  # Gives this answer back to the code that called the function.
    if s.startswith(("def ", "async def ")):  # Runs the next indented steps only when this condition is true.
        return summaries.get(number, "Defines a reusable step; the following indented lines are its body.")  # Gives this answer back to the code that called the function.
    if s.startswith("if __name__"):  # Runs the next indented steps only when this condition is true.
        return "Runs the command-line entry point only when this file is executed directly."  # Gives this answer back to the code that called the function.
    if s.startswith("if ") or s.startswith("elif "):  # Runs the next indented steps only when this condition is true.
        if "not len(" in s or "len(" in s and "<" in s:  # Checks whether enough records exist for a trustworthy next step.
            return "Checks whether enough records exist for a trustworthy next step."  # Gives this answer back to the code that called the function.
        if "stopped()" in s:  # Stops the analysis when the user has cancelled the live run.
            return "Stops the analysis when the user has cancelled the live run."  # Gives this answer back to the code that called the function.
        if "adopt_t" in s:  # Checks whether this player had already adopted before the current exposure.
            return "Checks whether this player had already adopted before the current exposure."  # Gives this answer back to the code that called the function.
        return "Runs the next indented steps only when this condition is true."  # Gives this answer back to the code that called the function.
    if s.startswith("else:"):  # Runs the next indented steps only when this condition is true.
        return "Handles the alternative when the preceding condition was false."  # Gives this answer back to the code that called the function.
    if s.startswith("for "):  # Runs the next indented steps only when this condition is true.
        return "Repeats the next indented steps once for each item."  # Gives this answer back to the code that called the function.
    if s.startswith("while "):  # Runs the next indented steps only when this condition is true.
        return "Repeats the indented block until this condition stops holding."  # Gives this answer back to the code that called the function.
    if s.startswith("with "):  # Runs the next indented steps only when this condition is true.
        return "Opens a resource and guarantees cleanup when the block ends."  # Gives this answer back to the code that called the function.
    if s.startswith("try:"):  # Runs the next indented steps only when this condition is true.
        return "Starts an operation that may need error handling."  # Gives this answer back to the code that called the function.
    if s.startswith("except "):  # Runs the next indented steps only when this condition is true.
        return "Handles this specific failure without hiding other errors."  # Gives this answer back to the code that called the function.
    if s.startswith("finally:"):  # Runs the next indented steps only when this condition is true.
        return "Runs cleanup whether the operation succeeds or fails."  # Gives this answer back to the code that called the function.
    if s.startswith("return "):  # Runs the next indented steps only when this condition is true.
        return "Gives this answer back to the code that called the function."  # Gives this answer back to the code that called the function.
    if s == "return":  # Runs the next indented steps only when this condition is true.
        return "Stops this function here."  # Gives this answer back to the code that called the function.
    if s.startswith("raise "):  # Runs the next indented steps only when this condition is true.
        return "Stops with an explicit error when this requirement is violated."  # Gives this answer back to the code that called the function.
    if s == "continue":  # Runs the next indented steps only when this condition is true.
        return "Skips this item and moves to the next loop iteration."  # Gives this answer back to the code that called the function.
    if s == "break":  # Runs the next indented steps only when this condition is true.
        return "Ends the current loop."  # Gives this answer back to the code that called the function.
    if s.startswith("assert "):  # Runs the next indented steps only when this condition is true.
        return "Checks an invariant; the script fails if it is false."  # Gives this answer back to the code that called the function.
    if s.startswith("print("):  # Runs the next indented steps only when this condition is true.
        return "Prints this reading so a command-line run can be followed."  # Gives this answer back to the code that called the function.
    if ".to_parquet(" in s:  # Runs the next indented steps only when this condition is true.
        return "Saves a compact table for later analysis stages."  # Gives this answer back to the code that called the function.
    if ".to_csv(" in s:  # Runs the next indented steps only when this condition is true.
        return "Writes a result table that can be inspected or downloaded."  # Gives this answer back to the code that called the function.
    if "read_parquet(" in s:  # Runs the next indented steps only when this condition is true.
        return "Loads a previously prepared game or trial table."  # Gives this answer back to the code that called the function.
    if "run.emit(" in s:  # Appends a structured progress event that the browser can replay.
        return "Records a JSON event so the live dashboard can update or replay it."  # Gives this answer back to the code that called the function.
    if "run.stage(" in s:  # Sets the status shown in the live stage list.
        return "Updates the visible progress stage of the live run."  # Gives this answer back to the code that called the function.
    if "run.log(" in s:  # Adds a short explanation to the live progress log.
        return "Adds a human-readable message to the live run log."  # Gives this answer back to the code that called the function.
    if s.startswith(("ap.add_argument(", "parser.add_argument(")):  # Runs the next indented steps only when this condition is true.
        return "Defines a command-line option for this script."  # Gives this answer back to the code that called the function.
    if s in {"}", "]", ")", "},", "],", "),"}:  # Runs the next indented steps only when this condition is true.
        return "Closes the data structure or function call started above."  # Gives this answer back to the code that called the function.
    m = re.match(r"([A-Za-z_][\w.]*)\s*(?::[^=]+)?=\s*", s)  # Saves a value named m so the next lines can use it.
    if m:  # Runs the next indented steps only when this condition is true.
        name = m.group(1).split(".")[-1]  # Saves a value named name so the next lines can use it.
        meaning = TERMS.get(name)  # Saves a value named meaning so the next lines can use it.
        return f"Stores the {meaning} for the next step." if meaning else f"Saves a value named `{name}` so the next lines can use it."  # Gives this answer back to the code that called the function.
    if s.startswith("@"):  # Runs the next indented steps only when this condition is true.
        return "Configures the function or class immediately below it."  # Gives this answer back to the code that called the function.
    if s.startswith(("elif", "case ")):  # Runs the next indented steps only when this condition is true.
        return "Handles this alternative case."  # Gives this answer back to the code that called the function.
    if s.startswith(("pass", "...")):  # Runs the next indented steps only when this condition is true.
        return "Leaves this branch intentionally without extra work."  # Gives this answer back to the code that called the function.
    if s.startswith(("[", "(", "{", "\"", "'")) or s.endswith((",", "(", "[", "{")):  # Runs the next indented steps only when this condition is true.
        return "Part of the value, collection, or call spanning several lines."  # Gives this answer back to the code that called the function.
    if ".append(" in s:
        return "Adds this item to the list being built."
    if ".add(" in s or ".update(" in s:
        return "Adds this item to the collection being built."
    if ".write_text(" in s or ".to_parquet(" in s or ".to_csv(" in s:
        return "Saves this result so it can be inspected or reused."
    if ".mkdir(" in s:
        return "Creates the folder needed for saved outputs."
    if "+=" in s:
        return "Adds this amount to the running total."
    if re.match(r"[\w.]+\[.+\]\s*=", s):
        return "Stores this value under its player, opening, or field key."
    if s.startswith(("zip(", "enumerate(", "list(", "set(")):
        return "Prepares values that the following loop will read."
    if s.endswith((",", "(", "[", "{")):
        return "Provides one more input to this calculation."
    return "Runs this instruction as part of the current step."  # Gives this answer back to the code that called the function.


def describe_web(line: str, suffix: str) -> str:  # Defines a reusable step; the following indented lines are its body.
    s = line.strip()  # Saves a value named s so the next lines can use it.
    if s.startswith(("<!--", "/*", "*", "//")):  # Runs the next indented steps only when this condition is true.
        return "Existing developer note about this section."  # Gives this answer back to the code that called the function.
    if s.startswith("</") or s in {"}", "};", "});", "</script>"}:  # Runs the next indented steps only when this condition is true.
        return "Closes the preceding element or code block."  # Gives this answer back to the code that called the function.
    if s.startswith("<script"):  # Runs the next indented steps only when this condition is true.
        return "Starts the browser-side code for interaction and charts."  # Gives this answer back to the code that called the function.
    if s.startswith("<style"):  # Runs the next indented steps only when this condition is true.
        return "Starts styles used to lay out and colour the page."  # Gives this answer back to the code that called the function.
    if s.startswith("<"):  # Runs the next indented steps only when this condition is true.
        tag = re.match(r"<([\w-]+)", s)  # Saves a value named tag so the next lines can use it.
        return f"Adds the `{tag.group(1)}` page element shown or read by the browser." if tag else "Defines page structure."  # Gives this answer back to the code that called the function.
    if suffix == ".css":  # Runs the next indented steps only when this condition is true.
        if s.endswith("{"):  # Runs the next indented steps only when this condition is true.
            return "Starts the style rules for this page element or state."  # Gives this answer back to the code that called the function.
        if ":" in s:  # Runs the next indented steps only when this condition is true.
            prop = s.split(":", 1)[0].strip()  # Saves a value named prop so the next lines can use it.
            return f"Sets `{prop}` for the current page element."  # Gives this answer back to the code that called the function.
        return "Continues the current style rule."  # Gives this answer back to the code that called the function.
    if re.search(r"(?:async )?function\s+[\w$]+", s):  # Runs the next indented steps only when this condition is true.
        return "Defines a browser function used by a chart, control, or live event."  # Gives this answer back to the code that called the function.
    if "fetch(" in s:  # Runs the next indented steps only when this condition is true.
        return "Calls a local server API and handles its response."  # Gives this answer back to the code that called the function.
    if "addEventListener(" in s:  # Runs the next indented steps only when this condition is true.
        return "Responds to a user action or browser event."  # Gives this answer back to the code that called the function.
    if s.startswith("case "):  # Runs the next indented steps only when this condition is true.
        return "Handles one type of progress event sent by the Python runner."  # Gives this answer back to the code that called the function.
    if "textContent" in s or "innerHTML" in s:  # Runs the next indented steps only when this condition is true.
        return "Updates visible text or markup on the page."  # Gives this answer back to the code that called the function.
    if "appendChild(" in s:  # Runs the next indented steps only when this condition is true.
        return "Adds a newly built visual element to the page."  # Gives this answer back to the code that called the function.
    if "setAttribute(" in s:  # Runs the next indented steps only when this condition is true.
        return "Sets an element property used for display or accessibility."  # Gives this answer back to the code that called the function.
    if s.startswith(("if ", "if(", "else", "for ", "for(", "while ")):  # Runs the next indented steps only when this condition is true.
        return "Controls which browser steps run or repeats them for data items."  # Gives this answer back to the code that called the function.
    if s.startswith(("var ", "let ", "const ")):  # Runs the next indented steps only when this condition is true.
        return "Keeps a value used by the page's next steps."  # Gives this answer back to the code that called the function.
    if s.startswith("return "):  # Runs the next indented steps only when this condition is true.
        return "Hands the calculated value back to the calling function."  # Gives this answer back to the code that called the function.
    return "Continues the page structure, styling, or browser logic above."  # Gives this answer back to the code that called the function.


def main() -> None:  # Defines a reusable step; the following indented lines are its body.
    count = 0  # Saves a value named count so the next lines can use it.
    for folder in FOLDERS:  # Repeats the next indented steps once for each item.
        for source in (ROOT / folder).rglob("*"):  # Repeats the next indented steps once for each item.
            if not source.is_file() or source.suffix not in EXTENSIONS:  # Runs the next indented steps only when this condition is true.
                continue  # Skips this item and moves to the next loop iteration.
            relative = source.relative_to(ROOT)  # Saves a value named relative so the next lines can use it.
            raw = source.read_text(encoding="utf-8")  # Saves a value named raw so the next lines can use it.
            summaries = function_summaries(raw) if source.suffix == ".py" else {}  # Saves a value named summaries so the next lines can use it.
            documented = documentation_lines(raw) if source.suffix == ".py" else set()  # Saves a value named documented so the next lines can use it.
            key = relative.as_posix()  # Saves a value named key so the next lines can use it.
            title = OVERVIEW.get(key, f"Reference copy of {key}; follow the line numbers while presenting.")  # Saves a value named title so the next lines can use it.
            lines = [f"SOURCE: {key}", f"SAY FIRST: {title}",  # Saves a value named lines so the next lines can use it.
                     "Each numbered code line has a plain-English comment beside it.",
                     "These files are speaking references; run the originals in src/, server/, site/ and scripts/.", ""]
            in_block_note = False  # Remember when an existing web comment spans several lines.
            for number, line in enumerate(raw.splitlines(), 1):  # Repeats the next indented steps once for each item.
                lines.append(f"{number:04d} | {line}".rstrip())  # Adds this item to the list being built.
                web_note = (source.suffix != ".py" and (in_block_note or line.lstrip().startswith(("/*", "*", "//", "<!--")) or " // " in line))
                if line.strip() and number not in documented and not web_note and not (source.suffix == ".py" and "  # " in line):  # Add a side note only when the source has none.
                    explanation = (describe_python(line, number, summaries)  # Saves a value named explanation so the next lines can use it.
                                   if source.suffix == ".py"  # Runs the next indented steps only when this condition is true.
                                   else describe_web(line, source.suffix))  # Runs this instruction as part of the current step.
                    # The reference is plain text, so the same-line note is safe
                    # for HTML, CSS and JavaScript as well as Python.
                    lines[-1] += f"    // {explanation}"  # Places the explanation beside this source line.
                if source.suffix != ".py":  # Track CSS, JS and HTML block comments in the reading copy.
                    if "/*" in line and "*/" not in line or "<!--" in line and "-->" not in line:
                        in_block_note = True
                    if "*/" in line or "-->" in line:
                        in_block_note = False
            target = OUT / relative.parent / (relative.name + ".explained.txt")  # Saves a value named target so the next lines can use it.
            target.parent.mkdir(parents=True, exist_ok=True)  # Creates the folder needed for saved outputs.
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")  # Saves this result so it can be inspected or reused.
            count += 1  # Adds this amount to the running total.
    print(f"Built line-by-line references for {count} source files in {OUT}")  # Prints this reading so a command-line run can be followed.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    main()  # Runs this instruction as part of the current step.
