#!/usr/bin/env python3
"""
tools/leakscan.py — scan every publishable file for operator-specific strings.

    python tools/leakscan.py [repo_root]

Exit code 0 means clean. Any hit not on the allow-list fails the run.

This is the second, independent check. `tools/anonymise.py` guards the files it
*writes*; this guards the whole tree, including files that were never produced
by the pipeline (README, docs, code comments). A privacy claim resting on a
single check is a claim resting on a single point of failure.

Each allow-list entry states *why* the match is expected. An entry without a
reason is how a real leak gets permanently whitelisted.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

#: Matches that have been individually reviewed and are expected.
#:
#: path -> exactly which matched strings are cleared *for that file*. A blanket
#: per-file pass would also clear a real leak that landed in the same file
#: later, which defeats the point of scanning it.
ALLOW: "dict[str, tuple[str, ...]]" = {
    # The pattern table and the self-test probes live in this file. It must
    # contain one example of every shape the scanner looks for — that is what
    # makes it able to detect anything, so every match here is by design.
    "tools/anonymise.py": ("*",),
    # "Simon" is the authorized public byline for this project (owner decision,
    # 2026-09-22) and the only operator identifier cleared for publication. It
    # stays in the forbidden list so that any *other* occurrence — a new one, in
    # these files or anywhere else — still fails the scan.
    "LICENSE": ("Simon",),
    "pyproject.toml": ("Simon",),
    "README.md": ("Simon",),
    "CITATION.cff": ("Simon",),
    # This file's own allow table has to name the cleared byline in order to
    # clear it elsewhere. Only that exact literal is cleared here.
    "tools/leakscan.py": ("Simon",),
}

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "build", "dist"}
SKIP_FILES = {
    # The operator config itself: it exists to hold the strings being kept out
    # of publication, and it is gitignored.
    "tools/forbidden.local.txt",
    "tools/field_renames.local.json",
}


def patterns(repo: pathlib.Path) -> "list[str]":
    sys.path.insert(0, str(repo))
    from tools.anonymise import GENERIC_FORBIDDEN_PATTERNS, load_forbidden

    pats = list(GENERIC_FORBIDDEN_PATTERNS)
    pats += load_forbidden(str(repo / "tools" / "forbidden.local.txt"))
    return pats


def main(argv: "list[str] | None" = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    repo = pathlib.Path(argv[0] if argv else ".").resolve()

    pats = patterns(repo)
    print(f"patterns in force: {len(pats)}")
    if len(pats) < 7:
        print("refusing to certify: the generic pattern set did not load", file=sys.stderr)
        return 1

    hits = []
    scanned = 0
    for p in sorted(repo.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(repo).as_posix()
        if any(part in SKIP_DIRS for part in p.parts) or rel in SKIP_FILES:
            continue
        scanned += 1
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in pats:
            for m in re.finditer(pat, text, re.I):
                hits.append((rel, pat, m.group(0)[:40]))

    print(f"scanned {scanned} files")
    real = 0
    for rel, pat, sample in hits:
        cleared = ALLOW.get(rel, ())
        if "*" in cleared or sample.lower() in tuple(c.lower() for c in cleared):
            print(f"  allowed  {rel}: {sample!r}")
            continue
        real += 1
        print(f"  LEAK     {rel}: {pat} -> {sample!r}")

    print(f"total hits {len(hits)}, unreviewed {real}")
    if real:
        print("FAIL", file=sys.stderr)
        return 1
    print("PASS — no unreviewed matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
