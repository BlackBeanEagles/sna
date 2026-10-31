"""Wrap the artifact fragment (site/page.html) into a standalone HTML document.

The published Artifact supplies its own <!doctype>/<head>/reset at publish time,
so page.html is a fragment: it starts at <title> and has no document shell. To
serve the same page from localhost we add that shell back, reproducing the
publish skeleton so the page looks identical either way.

    python site/build.py        # regenerates site/index.html
"""
import json  # Loads JSON tools for saved results and browser messages.
from pathlib import Path  # Loads Path to find and save project files.

SITE = Path(__file__).resolve().parent  # Saves a value named SITE so the next lines can use it.

# Mirrors what the Artifact publish skeleton injects, so local and published
# renders match: light color-scheme, zero body margin, 14px system stack,
# responsive images, and a [hidden] that actually wins.
SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>
  :root{
    color-scheme: light dark;
    padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }
  body{ margin:0; font:14px/1.5 system-ui, -apple-system, sans-serif; background:#fafaf9; }
  img{ max-width:100%; }
  [hidden]{ display:none !important; }
</style>
__FRAGMENT__
</head>
<body>
</body>
</html>
"""


def build() -> Path:  # Combine page, stylesheet and saved report into the static findings page.
    """Combine page, stylesheet and saved report into the static findings page.

    This is a build step, not a new analysis: numbers come from report.json.
    Re-run it after editing page.html or style.css for the local /findings view.
    """
    fragment = (SITE / "page.html").read_text(encoding="utf-8")  # Saves a value named fragment so the next lines can use it.
    fragment = fragment.replace("__SITE_CSS__", (SITE / "style.css").read_text(encoding="utf-8"))  # Saves a value named fragment so the next lines can use it.
    report = json.loads((SITE.parent / "results" / "report.json").read_text(encoding="utf-8"))  # Decodes saved JSON text into Python data.
    # Escape angle brackets before embedding JSON in an inline script.
    embedded = json.dumps(report, separators=(",", ":")).replace("<", "\\u003c")  # Encodes Python values as JSON for saving or sending to the browser.
    fragment = fragment.replace("__REPORT_JSON__", embedded)  # Saves a value named fragment so the next lines can use it.

    # The fragment mixes head content with body content.
    marker = fragment.find('<div class="topbar"')  # Saves a value named marker so the next lines can use it.
    if marker == -1:  # Runs the next indented steps only when this condition is true.
        raise ValueError("site/page.html is missing its topbar body marker")  # Stops with an explicit error when this requirement is violated.
    head_part, body_part = fragment[:marker], fragment[marker:]  # Runs this instruction as part of the current step.

    # plain replace, not %-formatting: the skeleton's CSS contains "100%"
    out = SKELETON.replace("__FRAGMENT__", head_part.strip())  # Stores the output value for the next step.
    out = out.replace("<body>\n</body>", "<body>\n" + body_part.strip() + "\n</body>")  # Stores the output value for the next step.

    dest = SITE / "index.html"  # Saves a value named dest so the next lines can use it.
    dest.write_text(out, encoding="utf-8")  # Saves this result so it can be inspected or reused.
    return dest  # Gives this answer back to the code that called the function.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    p = build()  # Saves a value named p so the next lines can use it.
    print(f"built {p}  ({p.stat().st_size:,} bytes)")  # Prints this reading so a command-line run can be followed.
