"""Wrap the artifact fragment (site/page.html) into a standalone HTML document.

The published Artifact supplies its own <!doctype>/<head>/reset at publish time,
so page.html is a fragment: it starts at <title> and has no document shell. To
serve the same page from localhost we add that shell back, reproducing the
publish skeleton so the page looks identical either way.

    python site/build.py        # regenerates site/index.html
"""
import json
from pathlib import Path

SITE = Path(__file__).resolve().parent

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


def build() -> Path:
    fragment = (SITE / "page.html").read_text(encoding="utf-8")
    fragment = fragment.replace("__SITE_CSS__", (SITE / "style.css").read_text(encoding="utf-8"))
    report = json.loads((SITE.parent / "results" / "report.json").read_text(encoding="utf-8"))
    # Escape angle brackets before embedding JSON in an inline script.
    embedded = json.dumps(report, separators=(",", ":")).replace("<", "\\u003c")
    fragment = fragment.replace("__REPORT_JSON__", embedded)

    # The fragment mixes head content with body content.
    marker = fragment.find('<div class="topbar"')
    if marker == -1:
        raise ValueError("site/page.html is missing its topbar body marker")
    head_part, body_part = fragment[:marker], fragment[marker:]

    # plain replace, not %-formatting: the skeleton's CSS contains "100%"
    out = SKELETON.replace("__FRAGMENT__", head_part.strip())
    out = out.replace("<body>\n</body>", "<body>\n" + body_part.strip() + "\n</body>")

    dest = SITE / "index.html"
    dest.write_text(out, encoding="utf-8")
    return dest


if __name__ == "__main__":
    p = build()
    print(f"built {p}  ({p.stat().st_size:,} bytes)")
