"""Create line-by-line speaking copies of the source for a code presentation.

The .explained.txt files are reference copies, never imported or served. Run
`python scripts/build_annotated_code.py` after changing source code so their
line numbers and explanations stay aligned with the working files.
"""

from __future__ import annotations

import ast
import re
import tokenize
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation_notes" / "code_explained"
FOLDERS = ("src", "server", "site", "scripts", "tests")
EXTENSIONS = {".py", ".html", ".css"}

# These are the short sentences to say before opening each important file.
OVERVIEW = {
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
}

TERMS = {
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
}


def function_summaries(source: str) -> dict[int, str]:
    """Use the source's own docstrings when explaining function definitions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node) or ""
            first = " ".join(doc.strip().split("\n\n", 1)[0].split()) if doc.strip() else ""
            if first:
                result[node.lineno] = first.split(". ", 1)[0].rstrip(".") + "."
    return result


def documentation_lines(source: str) -> set[int]:
    """Docstrings and comments explain themselves; annotate executable lines."""
    covered = set()
    try:
        for token in tokenize.generate_tokens(StringIO(source).readline):
            if token.type in (tokenize.STRING, tokenize.COMMENT):
                # A standalone string is a module/function docstring; an
                # ordinary literal inside code is left to the code note.
                standalone_comment = (token.type == tokenize.COMMENT and
                                      not source.splitlines()[token.start[0] - 1][:token.start[1]].strip())
                if standalone_comment or (token.type == tokenize.STRING and
                                          ("\n" in token.string or token.start[1] <= 4)):
                    covered.update(range(token.start[0], token.end[0] + 1))
    except tokenize.TokenError:
        pass
    return covered


def describe_python(line: str, number: int, summaries: dict[int, str]) -> str:
    s = line.strip()
    special = (
        ("e = frozenset((w, b))", "Makes an unordered opponent pair, so White–Black order cannot create two links."),
        ("if e not in edge_first_t", "Adds only the first meeting time for this opponent pair."),
        ("for actor, observer, colour", "Processes both sides of each game as a performance and an exposure."),
        ("first_perf.setdefault", "Records first use without overwriting it on later games."),
        ("exposures[(observer, beh)].append", "Adds an exposure event for the player who watched the opponent play this behaviour."),
        ("parent[i] = parent[parent[i]]", "Shortens the search path while finding a connected exposer group."),
        ("parent[ri] = rj", "Joins two exposer groups after finding a link between them."),
        ("len({find(i) for i in range(n)})", "Counts how many separate social sources the exposing opponents form."),
        ("if exposer not in seen", "Counts a repeat opponent once for d, even if they played many games."),
        ("seen.add(exposer)", "Marks this opponent as already included in the distinct count."),
        ("distinct.append(exposer)", "Keeps this new opponent for the structural-diversity calculation."),
        ("if adopt_t is not None and adopt_t <= t", "Stops creating trials after the player has already performed this behaviour."),
        ("edge_first_t[e] = ts", "Remembers when these two players first met, so later structure uses only past links."),
        ("t + window > t_end", "Excludes late encounters that cannot receive a complete follow-up window."),
        ("adopted = int(", "Marks adoption only when first use occurs after exposure and within the follow-up window."),
        ("sd = _components", "Counts independent groups among the distinct exposing opponents."),
        ("rng.permutation", "Randomly reassigns game timestamps while keeping each game's players and opening."),
        ("lift_over_null", "Compares the observed adoption rate with the shuffled-time reference rate."),
        ("roc_auc_score", "Measures how well the model ranks adopters above non-adopters on held-out data."),
        ("GroupShuffleSplit", "Keeps whole player-opening-colour spells together in train or test data."),
        (".predict_proba", "Gets each trial's predicted probability of later adoption."),
        (".groupby(", "Groups rows sharing these keys before counting or averaging them."),
        (".merge(", "Joins two tables on shared identifiers so their columns can be compared."),
        (".value_counts(", "Counts how often each player or opening occurs."),
        (".sort_values(", "Orders the rows by this field before the next calculation."),
        (".clip(", "Caps large counts into the final chart bucket, such as six or more opponents."),
        (".to_dict(", "Converts table values into JSON-friendly records for a report or UI event."),
        ("json.loads(", "Decodes saved JSON text into Python data."),
        ("json.dumps(", "Encodes Python values as JSON for saving or sending to the browser."),
        ("run.emit(", "Appends a structured progress event that the browser can replay."),
        ("run.stage(", "Sets the status shown in the live stage list."),
        ("run.log(", "Adds a short explanation to the live progress log."),
        ("pd.DataFrame(", "Creates a labelled table from the collected rows."),
        ("nx.community.louvain_communities", "Finds groups of players with relatively dense internal connections."),
        ("nx.betweenness_centrality", "Estimates how often players bridge shortest routes through the graph."),
        ("nx.core_number", "Measures how deeply each player lies in a mutually connected core."),
        ("first_exp_ns", "Tracks when a control player was first exposed, so matching uses only people still at risk."),
        ("first_perf_ns", "Tracks first performance time to exclude people who already adopted before matching."),
    )
    for needle, explanation in special:
        if needle in s:
            return explanation
    if s.startswith(("from ", "import ")):
        return "Imports a library or project module needed below."
    if s.startswith("class "):
        return summaries.get(number, "Defines an object used by this module.")
    if s.startswith(("def ", "async def ")):
        return summaries.get(number, "Defines a reusable step; the following indented lines are its body.")
    if s.startswith("if __name__"):
        return "Runs the command-line entry point only when this file is executed directly."
    if s.startswith("if ") or s.startswith("elif "):
        if "not len(" in s or "len(" in s and "<" in s:
            return "Checks whether enough records exist for a trustworthy next step."
        if "stopped()" in s:
            return "Stops the analysis when the user has cancelled the live run."
        if "adopt_t" in s:
            return "Checks whether this player had already adopted before the current exposure."
        return "Checks this condition before running the next indented block."
    if s.startswith("else:"):
        return "Handles the alternative when the preceding condition was false."
    if s.startswith("for "):
        return "Processes each item from this collection in turn."
    if s.startswith("while "):
        return "Repeats the indented block until this condition stops holding."
    if s.startswith("with "):
        return "Opens a resource and guarantees cleanup when the block ends."
    if s.startswith("try:"):
        return "Starts an operation that may need error handling."
    if s.startswith("except "):
        return "Handles this specific failure without hiding other errors."
    if s.startswith("finally:"):
        return "Runs cleanup whether the operation succeeds or fails."
    if s.startswith("return "):
        return "Hands this result back to the stage that called this function."
    if s == "return":
        return "Stops this function here."
    if s.startswith("raise "):
        return "Stops with an explicit error when this requirement is violated."
    if s == "continue":
        return "Skips this item and moves to the next loop iteration."
    if s == "break":
        return "Ends the current loop."
    if s.startswith("assert "):
        return "Checks an invariant; the script fails if it is false."
    if s.startswith("print("):
        return "Prints this reading so a command-line run can be followed."
    if ".to_parquet(" in s:
        return "Saves a compact table for later analysis stages."
    if ".to_csv(" in s:
        return "Writes a result table that can be inspected or downloaded."
    if "read_parquet(" in s:
        return "Loads a previously prepared game or trial table."
    if "run.emit(" in s:
        return "Records a JSON event so the live dashboard can update or replay it."
    if "run.stage(" in s:
        return "Updates the visible progress stage of the live run."
    if "run.log(" in s:
        return "Adds a human-readable message to the live run log."
    if s.startswith(("ap.add_argument(", "parser.add_argument(")):
        return "Defines a command-line option for this script."
    if s in {"}", "]", ")", "},", "],", "),"}:
        return "Closes the data structure or function call started above."
    m = re.match(r"([A-Za-z_][\w.]*)\s*(?::[^=]+)?=\s*", s)
    if m:
        name = m.group(1).split(".")[-1]
        meaning = TERMS.get(name)
        return f"Calculates or stores the {meaning} for this stage." if meaning else f"Keeps this intermediate result under the name `{name}`."
    if s.startswith("@"):
        return "Configures the function or class immediately below it."
    if s.startswith(("elif", "case ")):
        return "Handles this alternative case."
    if s.startswith(("pass", "...")):
        return "Leaves this branch intentionally without extra work."
    if s.startswith(("[", "(", "{", "\"", "'")) or s.endswith((",", "(", "[", "{")):
        return "Part of the value, collection, or call spanning several lines."
    return "Continues the current calculation or control flow."


def describe_web(line: str, suffix: str) -> str:
    s = line.strip()
    if s.startswith(("<!--", "/*", "*", "//")):
        return "Existing developer note about this section."
    if s.startswith("</") or s in {"}", "};", "});", "</script>"}:
        return "Closes the preceding element or code block."
    if s.startswith("<script"):
        return "Starts the browser-side code for interaction and charts."
    if s.startswith("<style"):
        return "Starts styles used to lay out and colour the page."
    if s.startswith("<"):
        tag = re.match(r"<([\w-]+)", s)
        return f"Adds the `{tag.group(1)}` page element shown or read by the browser." if tag else "Defines page structure."
    if suffix == ".css":
        if s.endswith("{"):
            return "Starts the style rules for this page element or state."
        if ":" in s:
            prop = s.split(":", 1)[0].strip()
            return f"Sets `{prop}` for the current page element."
        return "Continues the current style rule."
    if re.search(r"(?:async )?function\s+[\w$]+", s):
        return "Defines a browser function used by a chart, control, or live event."
    if "fetch(" in s:
        return "Calls a local server API and handles its response."
    if "addEventListener(" in s:
        return "Responds to a user action or browser event."
    if s.startswith("case "):
        return "Handles one type of progress event sent by the Python runner."
    if "textContent" in s or "innerHTML" in s:
        return "Updates visible text or markup on the page."
    if "appendChild(" in s:
        return "Adds a newly built visual element to the page."
    if "setAttribute(" in s:
        return "Sets an element property used for display or accessibility."
    if s.startswith(("if ", "if(", "else", "for ", "for(", "while ")):
        return "Controls which browser steps run or repeats them for data items."
    if s.startswith(("var ", "let ", "const ")):
        return "Keeps a value used by the page's next steps."
    if s.startswith("return "):
        return "Hands the calculated value back to the calling function."
    return "Continues the page structure, styling, or browser logic above."


def main() -> None:
    count = 0
    for folder in FOLDERS:
        for source in (ROOT / folder).rglob("*"):
            if not source.is_file() or source.suffix not in EXTENSIONS:
                continue
            relative = source.relative_to(ROOT)
            raw = source.read_text(encoding="utf-8")
            summaries = function_summaries(raw) if source.suffix == ".py" else {}
            documented = documentation_lines(raw) if source.suffix == ".py" else set()
            key = relative.as_posix()
            title = OVERVIEW.get(key, f"Reference copy of {key}; follow the line numbers while presenting.")
            lines = [f"SOURCE: {key}", f"SAY FIRST: {title}",
                     "Each numbered source line is followed by a plain-English comment.",
                     "These files are speaking references; run the originals in src/, server/, site/ and scripts/.", ""]
            for number, line in enumerate(raw.splitlines(), 1):
                lines.append(f"{number:04d} | {line}".rstrip())
                if line.strip() and number not in documented:
                    explanation = (describe_python(line, number, summaries)
                                   if source.suffix == ".py"
                                   else describe_web(line, source.suffix))
                    lines.append(f"     # {explanation}")
            target = OUT / relative.parent / (relative.name + ".explained.txt")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            count += 1
    print(f"Built line-by-line references for {count} source files in {OUT}")


if __name__ == "__main__":
    main()
