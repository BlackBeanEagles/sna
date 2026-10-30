"""Compile the proposal to PDF without altering the submitted source.

The proposal must keep the course template's preamble byte for byte. That
preamble relies on pdfLaTeX: `\\usepackage{times}` maps to the Type-1 Times
fonts through OT1/T1 encoding. A Unicode engine (XeTeX, which is what the
portable Tectonic binary runs) never selects those mappings, so every \\textbf
and \\textit silently falls back to the regular face -- headings, the title
table labels, the methodology sub-headings, every journal name.

So: compile a throwaway copy with `\\usepackage[T1]{fontenc}` inserted. That
single line only restores the font mapping pdfLaTeX would have used anyway,
so the PDF matches what the unmodified source produces on Overleaf, and the
file that gets submitted is untouched.

    python scripts/build_proposal_pdf.py --tex ../SNA_Proposal/SNA_Proposal.tex
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SHIM = "\\usepackage[T1]{fontenc}\n"
ANCHOR = "\\usepackage{times}"


def build(tex: Path, engine: Path) -> Path:
    """Compile a temporary copy so the submitted LaTeX source stays intact."""
    src = tex.read_text(encoding="utf-8")
    if ANCHOR not in src:
        sys.exit(f"expected {ANCHOR!r} in {tex}")
    if "fontenc" in src:
        print("note: source already loads fontenc; compiling as-is")
        shimmed = src
    else:
        shimmed = src.replace(ANCHOR, SHIM + ANCHOR, 1)

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        (work / tex.name).write_text(shimmed, encoding="utf-8")
        figs = tex.parent / "figures"
        if figs.is_dir():
            shutil.copytree(figs, work / "figures")

        r = subprocess.run(
            [str(engine), "-X", "compile", tex.name, "--outdir", "."],
            cwd=work, capture_output=True, text=True)
        log = (r.stdout or "") + (r.stderr or "")
        for line in log.splitlines():
            if any(w in line.lower() for w in ("overfull", "underfull", "error")):
                print("  " + line.strip())
        pdf = work / (tex.stem + ".pdf")
        if r.returncode != 0 or not pdf.exists():
            print(log[-2000:])
            sys.exit("compile failed")

        dest = tex.with_suffix(".pdf")
        shutil.copy(pdf, dest)
        return dest


def check_fonts(pdf: Path):
    try:
        import pymupdf
    except ImportError:
        print("(install pymupdf to verify the embedded fonts)")
        return
    doc = pymupdf.open(pdf)
    fonts = sorted({f[3] for p in doc for f in p.get_fonts(full=True)})
    print(f"\n{pdf.name}: {doc.page_count} pages")
    print("embedded fonts:")
    for f in fonts:
        print("  " + f)
    has_bold = any("Medi" in f or "Bold" in f for f in fonts)
    has_ital = any("Ital" in f for f in fonts)
    print(f"\nbold face present   : {has_bold}")
    print(f"italic face present : {has_ital}")
    if not (has_bold and has_ital):
        sys.exit("!! bold/italic missing -- the document would render flat")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", required=True)
    ap.add_argument("--engine", default=None,
                    help="path to the tectonic binary")
    a = ap.parse_args()
    engine = Path(a.engine) if a.engine else (
        Path(tempfile.gettempdir()) / "tectonic_bin" / "tectonic.exe")
    if not engine.exists():
        sys.exit(f"no LaTeX engine at {engine}")
    check_fonts(build(Path(a.tex).resolve(), engine))
