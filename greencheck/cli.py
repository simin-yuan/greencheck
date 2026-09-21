"""greencheck.cli — command line entry point.

    greencheck audit examples/ledger.jsonl --field identity.identity_score --count memory_recall.sampled
    greencheck gate  examples/gate_events.jsonl --fire-event block_issued
    greencheck demo
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import __version__
from .core import audit_gate, audit_ledger, get_path, load_jsonl
from .report import render_markdown, render_text, to_dicts


def _project(rows, field, count_field=None, fresh_field=None):
    """Flatten dotted paths into the flat keys core.audit_ledger expects."""
    out = []
    for r in rows:
        item = {"value": get_path(r, field)}
        if count_field:
            item["_count"] = get_path(r, count_field)
        if fresh_field:
            item["_fresh"] = get_path(r, fresh_field)
        out.append(item)
    return out


def cmd_audit(args) -> int:
    rows = load_jsonl(args.ledger)
    if not rows:
        print(f"no records in {args.ledger}", file=sys.stderr)
        return 2
    projected = _project(rows, args.field, args.count, args.fresh)
    result = audit_ledger(
        projected,
        field="value",
        subject=args.field,
        count_field="_count" if args.count else None,
        fresh_field="_fresh" if args.fresh else None,
    )
    if args.json:
        print(json.dumps([result.to_dict()], indent=2, ensure_ascii=False))
    else:
        print(render_text([result], title=f"ledger audit — {args.ledger}"))
    return 0 if result.ok else 1


def cmd_gate(args) -> int:
    events = load_jsonl(args.events)
    if not events:
        print(f"no events in {args.events}", file=sys.stderr)
        return 2
    result = audit_gate(events, fire_event=args.fire_event, subject=args.events)
    if args.json:
        print(json.dumps([result.to_dict()], indent=2, ensure_ascii=False))
    else:
        print(render_text([result], title=f"gate audit — {args.events}"))
    return 0 if result.ok else 1


def cmd_demo(args) -> int:
    """Self-contained demonstration: one clean instrument, two broken ones."""
    from .core import ProbePair, discriminate

    # --- three instruments that all look plausible in a dashboard -----------
    def content_length(x):
        """Honest: responds to the property it is named after."""
        return len(str(x))

    def content_presence_score(x):
        """Dishonest: named for content, responds only to whether input exists."""
        return 1.0 if x else 0.0

    def always_one(x):
        """The degenerate control: no input affects it."""
        return 1.0

    # --- probe pairs, tagged by the dimension they vary ---------------------
    pairs = [
        ProbePair(
            "rich text vs degenerate text",
            "the quick brown fox jumps",
            "aaaa",
            dimension="content",
            note="both non-empty; content differs",
        ),
        ProbePair(
            "text present vs absent",
            "hello",
            "",
            dimension="presence",
            note="existence differs; content dimension held out",
        ),
    ]

    results = [
        discriminate(content_length, pairs, subject="content_length", claimed_dimensions=["content"]),
        discriminate(content_presence_score, pairs, subject="content_presence_score", claimed_dimensions=["content"]),
        discriminate(always_one, pairs, subject="always_one (control)", claimed_dimensions=["content"]),
    ]
    print(render_text(results, title="greencheck demo — discriminate()"))
    print()
    print("Note: content_presence_score separates the presence pair (1/2 pairs")
    print("separated overall) yet is still reported FAIL, because it collapses")
    print("every pair in the dimension it claims to measure.")
    print()
    ledger = [
        {"value": 1.0, "n": 5}, {"value": 1.0, "n": 5}, {"value": 1.0, "n": 5},
        {"value": 1.0, "n": 0}, {"value": 1.0, "n": 0},
    ]
    r = audit_ledger(ledger, field="value", count_field="n", subject="demo.identity_score")
    print(render_text([r], title="greencheck demo — audit_ledger()"))
    return 0


def _skills_root() -> pathlib.Path:
    """Locate the bundled skills directory.

    Sits next to the package in a checkout. The search is forgiving so that an
    installed copy still finds it wherever the data files landed.
    """
    here = pathlib.Path(__file__).resolve().parent
    for cand in (here.parent / "skills", here / "skills"):
        if cand.is_dir():
            return cand
    return here.parent / "skills"


def _frontmatter_description(path: pathlib.Path) -> str:
    """Pull `description:` out of a SKILL.md YAML frontmatter block."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    block = text[3:end] if end != -1 else text[3:]
    for line in block.splitlines():
        if line.lower().startswith("description:"):
            return line.split(":", 1)[1].strip()
    return ""


def cmd_skills(args) -> int:
    """List the bundled skills, or print one in full so an agent can read it."""
    root = _skills_root()
    if not root.is_dir():
        print(f"no skills directory at {root}", file=sys.stderr)
        return 2
    entries = sorted(p for p in root.iterdir() if (p / "SKILL.md").is_file())
    if not entries:
        print(f"no skills found in {root}", file=sys.stderr)
        return 2

    if args.name:
        target = root / args.name / "SKILL.md"
        if not target.is_file():
            print(f"no skill named {args.name!r}", file=sys.stderr)
            print("available: " + ", ".join(p.name for p in entries), file=sys.stderr)
            return 2
        print(target.read_text(encoding="utf-8"))
        return 0

    if args.json:
        print(json.dumps(
            [{"name": p.name, "description": _frontmatter_description(p / "SKILL.md")}
             for p in entries],
            indent=2, ensure_ascii=False))
        return 0

    print(f"greencheck skills — {len(entries)} available\n")
    width = max(len(p.name) for p in entries)
    for p in entries:
        desc = _frontmatter_description(p / "SKILL.md")
        if len(desc) > 96:
            desc = desc[:93] + "..."
        print(f"  {p.name:<{width}}  {desc}")
    print()
    print("Read one in full:   greencheck skills <name>")
    print("These are plain SKILL.md files with YAML frontmatter, the format used")
    print("by most agent harnesses. Point your agent at the skills/ directory.")
    return 0


def cmd_mutate(args) -> int:
    """Delegate to the mutation engine, which owns its own argument parser.

    `mutate` takes a gate command plus its own flags, so the subparser collects
    everything after it verbatim rather than trying to re-declare those flags.
    """
    from .mutate import main as mutate_main

    return mutate_main(args.args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="greencheck", description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="version", version=f"greencheck {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit a recorded metric ledger")
    a.add_argument("ledger")
    a.add_argument("--field", required=True, help="dotted path to the value")
    a.add_argument("--count", help="dotted path to the number of items examined")
    a.add_argument("--fresh", help="dotted path to a boolean input to attribute variance to")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_audit)

    g = sub.add_parser("gate", help="check whether an assertion has ever fired")
    g.add_argument("events")
    g.add_argument("--fire-event", default="block_issued")
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_gate)

    d = sub.add_parser("demo", help="run the built-in demonstration")
    d.set_defaults(func=cmd_demo)

    s = sub.add_parser("skills", help="list the bundled agent skills, or print one in full")
    s.add_argument("name", nargs="?", help="skill name to print in full")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_skills)

    m = sub.add_parser("mutate", help="does your gate actually say no? mutate the input, run the gate")
    m.set_defaults(func=None)

    # `mutate` takes its own flags (--gate, --target, ...). REMAINDER does not
    # capture option-likes, so parse known args here and hand the rest to the
    # mutation engine, which owns that argument surface.
    args, rest = ap.parse_known_args(argv)
    if getattr(args, "cmd", None) == "mutate":
        from .mutate import main as mutate_main

        return mutate_main(rest)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
