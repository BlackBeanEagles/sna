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
from __future__ import annotations  # Loads code this file needs for the steps below.

import argparse  # Loads the tool that reads command-line choices.
import shutil  # Loads code this file needs for the steps below.
import subprocess  # Loads code this file needs for the steps below.
import sys  # Loads code this file needs for the steps below.
import tempfile  # Loads code this file needs for the steps below.
from pathlib import Path  # Loads Path to find and save project files.

SHIM = "\\usepackage[T1]{fontenc}\n"  # Saves a value named SHIM so the next lines can use it.
ANCHOR = "\\usepackage{times}"  # Saves a value named ANCHOR so the next lines can use it.


def build(tex: Path, engine: Path) -> Path:  # Compile a temporary copy so the submitted LaTeX source stays intact.
    """Compile a temporary copy so the submitted LaTeX source stays intact."""
    src = tex.read_text(encoding="utf-8")  # Saves a value named src so the next lines can use it.
    if ANCHOR not in src:  # Runs the next indented steps only when this condition is true.
        sys.exit(f"expected {ANCHOR!r} in {tex}")  # Runs this instruction as part of the current step.
    if "fontenc" in src:  # Runs the next indented steps only when this condition is true.
        print("note: source already loads fontenc; compiling as-is")  # Prints this reading so a command-line run can be followed.
        shimmed = src  # Saves a value named shimmed so the next lines can use it.
    else:  # Handles the alternative when the preceding condition was false.
        shimmed = src.replace(ANCHOR, SHIM + ANCHOR, 1)  # Saves a value named shimmed so the next lines can use it.

    with tempfile.TemporaryDirectory() as td:  # Opens a resource and guarantees cleanup when the block ends.
        work = Path(td)  # Saves a value named work so the next lines can use it.
        (work / tex.name).write_text(shimmed, encoding="utf-8")  # Part of the value, collection, or call spanning several lines.
        figs = tex.parent / "figures"  # Saves a value named figs so the next lines can use it.
        if figs.is_dir():  # Runs the next indented steps only when this condition is true.
            shutil.copytree(figs, work / "figures")  # Runs this instruction as part of the current step.

        r = subprocess.run(  # Saves a value named r so the next lines can use it.
            [str(engine), "-X", "compile", tex.name, "--outdir", "."],  # Part of the value, collection, or call spanning several lines.
            cwd=work, capture_output=True, text=True)  # Saves a value named cwd so the next lines can use it.
        log = (r.stdout or "") + (r.stderr or "")  # Saves a value named log so the next lines can use it.
        for line in log.splitlines():  # Repeats the next indented steps once for each item.
            if any(w in line.lower() for w in ("overfull", "underfull", "error")):  # Runs the next indented steps only when this condition is true.
                print("  " + line.strip())  # Prints this reading so a command-line run can be followed.
        pdf = work / (tex.stem + ".pdf")  # Saves a value named pdf so the next lines can use it.
        if r.returncode != 0 or not pdf.exists():  # Runs the next indented steps only when this condition is true.
            print(log[-2000:])  # Prints this reading so a command-line run can be followed.
            sys.exit("compile failed")  # Runs this instruction as part of the current step.

        dest = tex.with_suffix(".pdf")  # Saves a value named dest so the next lines can use it.
        shutil.copy(pdf, dest)  # Runs this instruction as part of the current step.
        return dest  # Gives this answer back to the code that called the function.


def check_fonts(pdf: Path):  # Defines a reusable step; the following indented lines are its body.
    try:  # Starts an operation that may need error handling.
        import pymupdf  # Loads code this file needs for the steps below.
    except ImportError:  # Handles this specific failure without hiding other errors.
        print("(install pymupdf to verify the embedded fonts)")  # Prints this reading so a command-line run can be followed.
        return  # Stops this function here.
    doc = pymupdf.open(pdf)  # Saves a value named doc so the next lines can use it.
    fonts = sorted({f[3] for p in doc for f in p.get_fonts(full=True)})  # Saves a value named fonts so the next lines can use it.
    print(f"\n{pdf.name}: {doc.page_count} pages")  # Prints this reading so a command-line run can be followed.
    print("embedded fonts:")  # Prints this reading so a command-line run can be followed.
    for f in fonts:  # Repeats the next indented steps once for each item.
        print("  " + f)  # Prints this reading so a command-line run can be followed.
    has_bold = any("Medi" in f or "Bold" in f for f in fonts)  # Saves a value named has_bold so the next lines can use it.
    has_ital = any("Ital" in f for f in fonts)  # Saves a value named has_ital so the next lines can use it.
    print(f"\nbold face present   : {has_bold}")  # Prints this reading so a command-line run can be followed.
    print(f"italic face present : {has_ital}")  # Prints this reading so a command-line run can be followed.
    if not (has_bold and has_ital):  # Runs the next indented steps only when this condition is true.
        sys.exit("!! bold/italic missing -- the document would render flat")  # Runs this instruction as part of the current step.


if __name__ == "__main__":  # Runs the command-line entry point only when this file is executed directly.
    ap = argparse.ArgumentParser()  # Saves a value named ap so the next lines can use it.
    ap.add_argument("--tex", required=True)  # Defines a command-line option for this script.
    ap.add_argument("--engine", default=None,  # Defines a command-line option for this script.
                    help="path to the tectonic binary")  # Saves a value named help so the next lines can use it.
    a = ap.parse_args()  # Saves a value named a so the next lines can use it.
    engine = Path(a.engine) if a.engine else (  # Saves a value named engine so the next lines can use it.
        Path(tempfile.gettempdir()) / "tectonic_bin" / "tectonic.exe")  # Runs this instruction as part of the current step.
    if not engine.exists():  # Runs the next indented steps only when this condition is true.
        sys.exit(f"no LaTeX engine at {engine}")  # Runs this instruction as part of the current step.
    check_fonts(build(Path(a.tex).resolve(), engine))  # Runs this instruction as part of the current step.
