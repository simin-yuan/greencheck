"""greencheck.mutate — does your gate actually say no?

The most common failure of a validator, a linter, a schema check or a CI gate is
not that it has a bug. It is that **it has never rejected anything, and everyone
assumes it is covering them anyway**. A green pipeline reads as "the code is
clean". It can just as easily mean "the check never ran".

The only way to show a gate works is not to watch it pass. It is to hand it an
input that MUST be rejected and see whether it dares to say no.

This automates that: it mutates your input N ways, runs your gate once per
mutant, and reports which mutants it caught and which it let through.

It does not decide whether a leaked mutant is a real blind spot. It moves you
from "I think my gate is strict" to "I know it let these eight things through".

    greencheck mutate --gate "python validate.py {target}" --target ./data
    greencheck mutate --gate "pytest -q {target}" --target ./fixtures --workers 4

Exit codes:
    0 = every mutant was caught (no visible blind spot under these mutations)
    1 = some mutants were not caught (all written to --report for review)
    2 = usage or environment error
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

__version__ = "1.0.0"

# Only text files are mutated; anything else is skipped.
TEXT_EXT = {
    ".md", ".markdown", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".csv", ".tsv", ".sql", ".py", ".js", ".ts", ".java", ".kt", ".go", ".rs",
    ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".sh", ".xml", ".html", ".properties",
}

# Binary / size guard rail.
MAX_FILE_BYTES = 512 * 1024


# ---------------------------------------------------------------------------
# Mutation operators. Each takes {relative path: text} and yields
# (name, patch) where patch is a {relative path: new text or None} overlay.
#
# Design principle for every operator: the input it produces should be
# **obviously wrong to a human**. If the gate has no reaction to it at all,
# that is worth a look.
# ---------------------------------------------------------------------------

def _lines(text: str):
    return text.splitlines(keepends=True)


def _join(lines) -> str:
    return "".join(lines)


def _snippet(s: str, n: int = 28) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n] + "..."


def op_drop_file(files):
    """Delete an entire file. Almost every gate should scream."""
    for rel in sorted(files):
        yield (f"drop-file:{rel}", {rel: None})


def op_empty_file(files):
    """Empty a file out."""
    for rel, txt in sorted(files.items()):
        if txt.strip():
            yield (f"empty-file:{rel}", {rel: ""})


def op_drop_section(files):
    """Drop a markdown '## ' section, or a top-level YAML/INI key block."""
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        heads = [i for i, l in enumerate(lines)
                 if re.match(r"^#{1,3}\s+\S", l) or re.match(r"^[A-Za-z_][\w.\-]*\s*:", l)]
        for i in heads:
            j = i + 1
            while j < len(lines) and not (
                re.match(r"^#{1,3}\s+\S", lines[j]) or re.match(r"^[A-Za-z_][\w.\-]*\s*:", lines[j])
            ):
                j += 1
            if j - i >= 2:  # needs at least a key plus a value to count as a block
                yield (f"drop-section:{rel}#{_snippet(lines[i])}",
                       {rel: _join(lines[:i] + lines[j:])})


def op_drop_line(files):
    """Delete one line at a time (skipping blanks and comments)."""
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        for i, l in enumerate(lines):
            if l.strip() and not l.lstrip().startswith("#") and not l.lstrip().startswith("//"):
                yield (f"drop-line:{rel}:{i + 1}:{_snippet(l)}",
                       {rel: _join(lines[:i] + lines[i + 1:])})


def op_blank_value(files):
    """Blank out a scalar value, producing "the field is there but empty".

    Handles both `key: value` and `"key": "value"`, and keeps the surrounding
    quotes when the original was quoted so that a JSON or YAML document stays
    syntactically valid. Invalidate the syntax and you end up testing the
    parser instead of the gate.
    """
    pat = re.compile(
        r"""^(\s*["']?[A-Za-z_][\w.\-]*["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,]+)(\s*,?\s*)$"""
    )
    for rel, txt in sorted(files.items()):
        lines = _lines(txt)
        for i, l in enumerate(lines):
            m = pat.match(l)
            if not m:
                continue
            val = m.group(2)
            if len(val) >= 2 and val[0] in ("\"", "'") and val[-1] == val[0]:
                newval = val[0] + val[-1]          # "" or '', quotes preserved
            elif val in ("true", "false"):
                newval = "false"                    # keep it boolean
            elif re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", val):
                newval = "0"                        # keep it numeric
            elif val in ("null", "~", "None", ""):
                continue  # already empty; nothing to learn from this mutant
            else:
                newval = ""                         # bare word (YAML) -> empty
            yield (f"blank-value:{rel}:{i + 1}:{m.group(1).strip()}",
                   {rel: _join(lines[:i] + [m.group(1) + newval + m.group(3) + "\n"]
                               + lines[i + 1:])})


def op_break_reference(files):
    """Change one character of an identifier, creating a dangling reference.

    This is the class most often missed: the reference is broken while the
    syntax stays perfectly legal, so any check that only validates syntax or
    shape waves it through.
    """
    for rel, txt in sorted(files.items()):
        for m in re.finditer(r"\b([A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+)\b", txt):
            tok = m.group(1)
            broken = tok[:-1] + ("Z" if tok[-1] != "Z" else "Y")
            if broken == tok:
                continue
            yield (f"break-ref:{rel}:{tok}->{broken}",
                   {rel: txt.replace(tok, broken, 1)})


def op_dup_id(files):
    """Duplicate the first heading id, producing a redefinition."""
    for rel, txt in sorted(files.items()):
        m = re.search(r"^#{1,3}\s+(\S+)", txt, re.M)
        if m:
            tok = m.group(1)
            yield (f"dup-id:{rel}:{tok}", {rel: txt + f"\n## {tok}\n"})


OPERATORS = [
    op_drop_file,
    op_empty_file,
    op_drop_section,
    op_drop_line,
    op_blank_value,
    op_break_reference,
    op_dup_id,
]


# ---------------------------------------------------------------------------

def collect(target: Path) -> "dict[str, str]":
    out: "dict[str, str]" = {}
    for p in sorted(target.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            out[str(p.relative_to(target)).replace("\\", "/")] = p.read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def build_mutants(base, limit=None):
    """Expand every operator over the baseline, de-duplicating identical patches."""
    mutants = []
    seen = set()
    for op in OPERATORS:
        for name, patch in op(base):
            h = hashlib.sha1(repr(sorted(patch.items())).encode()).hexdigest()[:12]
            if h in seen:
                continue
            seen.add(h)
            mutants.append((name, patch))
            if limit and len(mutants) >= limit:
                return mutants
    return mutants


def apply_mutant(base_dir: Path, work: Path, patch) -> None:
    """Copy the baseline to `work`, then overlay the patch. None means delete."""
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(base_dir, work)
    for rel, content in patch.items():
        fp = work / rel
        if content is None:
            if fp.exists():
                fp.unlink()
        else:
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")


def run_gate(gate: str, target: Path, workdir: Path, timeout: int):
    cmd = gate.replace("{target}", str(target))
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(workdir), timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -9, f"[greencheck] gate timed out after {timeout}s"
    except OSError as e:
        return -1, f"[greencheck] could not start the gate: {e}"


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="greencheck mutate",
        description="Does your gate actually say no? Mutate the input, run the gate per "
                    "mutant, report what it let through.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  greencheck mutate --gate \"python validate.py {target}\" --target ./data\n"
               "  greencheck mutate --gate \"pytest -q {target}\" --target ./fixtures --timeout 60\n")
    ap.add_argument("--gate", required=True,
                    help="your gate command. {target} is replaced with the mutated input path.")
    ap.add_argument("--target", required=True, help="baseline input directory (must pass the gate).")
    ap.add_argument("--workdir", default=".", help="working directory for the gate (default: cwd).")
    ap.add_argument("--timeout", type=int, default=120, help="per-run timeout in seconds.")
    ap.add_argument("--workers", type=int, default=4, help="parallelism (default 4).")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of mutants (debugging).")
    ap.add_argument("--report", default="greencheck-mutate-report.json", help="report output path.")
    ap.add_argument("--keep", action="store_true", help="keep the escaped mutants for inspection.")
    ap.add_argument("--json", action="store_true", help="emit the report to stdout as JSON.")
    a = ap.parse_args(argv)

    target = Path(a.target).resolve()
    if not target.is_dir():
        print(f"[error] --target is not a directory: {target}", file=sys.stderr)
        return 2

    base = collect(target)
    if not base:
        print(f"[error] no mutable text files under {target}", file=sys.stderr)
        return 2

    if not a.json:
        print("=" * 70)
        print("greencheck mutate - does your gate actually say no?")
        print("=" * 70)
        print(f"baseline   : {target}  ({len(base)} files)")

    # Step 0: confirm the baseline itself passes. A gate that rejects clean
    # input cannot tell you anything about the mutants.
    with tempfile.TemporaryDirectory(prefix="greencheck-base-") as tmp:
        dummy = Path(tmp) / "baseline-input"
        apply_mutant(target, dummy, {})
        rc0, out0 = run_gate(a.gate, dummy, Path(a.workdir).resolve(), a.timeout)

    if not a.json:
        state = "PASS (baseline is clean, mutating)" if rc0 == 0 else \
                "WARN - the baseline does not pass; results below are not evidence"
        print(f"baseline rc: {rc0}  {state}")
        if rc0 != 0:
            print("\n  first 400 chars of the baseline output:")
            for l in out0.splitlines()[:12]:
                print("   ", l[:160])
            print("\n  A gate that rejects clean input cannot measure anything. "
                  "Get it to pass the baseline first.")

    mutants = build_mutants(base, a.limit)
    if not mutants:
        print("[error] no mutants generated - the input may be too simple.", file=sys.stderr)
        return 2
    if not a.json:
        print(f"mutants    : {len(mutants)}")
        print(f"gate       : {a.gate}\n")
        print("-" * 70)

    caught, missed, errors = [], [], []

    def one(idx, item):
        name, patch = item
        # Deterministic workdir per mutant (an index, not hash(), so the same
        # input always produces the same layout and PYTHONHASHSEED is irrelevant).
        wd = Path(tmp_root) / f"m{idx:05d}"
        try:
            apply_mutant(target, wd, patch)
            rc, out = run_gate(a.gate, wd, Path(a.workdir).resolve(), a.timeout)
            return (name, rc, out, patch)
        except Exception as e:  # a mutant that fails to build must not kill the run
            return (name, None, str(e), patch)

    with tempfile.TemporaryDirectory(prefix="greencheck-mut-") as tmpm:
        tmp_root = Path(tmpm)
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            for name, rc, out, patch in ex.map(lambda t: one(*t), enumerate(mutants)):
                if rc is None:
                    errors.append((name, out))
                    tag = "BUILD-ERR"
                elif rc != 0:
                    caught.append((name, rc, out))
                    tag = "caught"
                else:
                    missed.append((name, out))
                    tag = "* ESCAPED"
                if not a.json:
                    print(f"  {tag:>10}  {name}")

    total = len(caught) + len(missed)
    if not a.json:
        print("-" * 70)
        print(f"caught {len(caught)} / {total}"
              + (f"   build errors {len(errors)}" if errors else ""))

        if missed:
            print(f"\nmutants that were NOT caught ({len(missed)}) - your visible blind spots:")
            for name, _ in missed:
                print(f"  *  {name}")
            print("\n  Note: an escaped mutant is not automatically a defect - some")
            print("  mutations are semantically legal. But every line deserves an")
            print("  answer to: if this had happened, why didn't my gate care?")

    report = {
        "greencheck_mutate_version": __version__,
        "gate": a.gate,
        "target": str(target),
        "baseline_exit_code": rc0,
        "baseline_ok": rc0 == 0,
        "files": len(base),
        "mutants_total": len(mutants),
        "caught_count": len(caught),
        "escaped_count": len(missed),
        "caught": [n for n, _, _ in caught],
        "escaped": [n for n, _ in missed],
        "build_errors": [n for n, _ in errors],
        "escaped_detail": [{"mutant": n, "gate_output_head": o[:600]} for n, o in missed],
    }
    Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"\nreport written: {a.report}")

    if a.keep and missed:
        keepdir = Path("greencheck-escaped")
        keepdir.mkdir(exist_ok=True)
        by_name = dict(mutants)
        for n, _ in missed:
            d = keepdir / re.sub(r"[^A-Za-z0-9_.-]+", "_", n)[:80]
            apply_mutant(target, d, by_name[n])
        if not a.json:
            print(f"escaped mutants kept in: {keepdir}/")

    if not a.json:
        print("=" * 70)
    if rc0 != 0:
        if not a.json:
            print("verdict: the baseline fails, so this run is not evidence about the gate.")
        return 1
    if missed:
        if not a.json:
            print(f"verdict: the gate had no reaction to {len(missed)}/{total} mutants "
                  "- it has a visible blind spot.")
        return 1
    if not a.json:
        print(f"verdict: all {total} mutants were caught - no blind spot found this round.")
        print("         (That is still not 'the gate is correct'. It is only 'it said no")
        print("          to every input in this particular set'.)")
        print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
