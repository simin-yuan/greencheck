#!/usr/bin/env python3
"""
tools/anonymise.py — turn private production logs into publishable datasets.

Run this where the raw logs live. The raw logs are never copied into this
repository, and the paths to them are supplied as arguments rather than
hard-coded, so that nothing about the private environment travels with the
published artefact.

    python tools/anonymise.py \
        --ledger  /path/to/private/metric_ledger.jsonl \
        --gate    /path/to/private/gate_log.jsonl \
        --out     data/

What it produces
----------------
data/ledger_metric_samples.jsonl   one line per recorded sample, field names
                                   neutralised, values untouched
data/gate_daily.jsonl              per-day aggregate counts of a guard log
data/gate_summary.json             aggregate totals plus first-fire time

What it deliberately does NOT produce
-------------------------------------
Any line of the original guard log. Those lines embed file paths, account
names, message text and place names. Only aggregate counts leave this script.

This two-tier rule is the point: a published dataset should carry the
*statistics that support the claim*, not the raw material that happened to be
lying around when the claim was made.
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Field-name neutralisation.
#
# Only names are changed. No value, timestamp or count is altered. Any
# downstream analysis that works on the original data works on this data.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Operator-specific privacy configuration.
#
# The names being replaced are themselves the sensitive part, which is why the
# mapping does not live in this repository. Supply it with `--renames`: a JSON
# object of {"private_field_name": "published_field_name"}. Supply additional
# patterns with `--forbid-file`: one regex per line, covering operator-specific
# strings such as personal names, place names, internal service names and
# account handles. Both files are gitignored; see tools/*.local.example.*.
# ---------------------------------------------------------------------------
FIELD_RENAMES: Dict[str, str] = {}

#: Patterns that are unsafe to publish regardless of who the operator is:
#: filesystem layouts, credentials, hosts. Generic, so they ship with the tool.
GENERIC_FORBIDDEN_PATTERNS = [
    r"(?<![A-Za-z])[A-Za-z]:[\\/]",                       # Windows drive paths
    r"/(?:Users|home)/[^/\s\"\']+",           # POSIX home directories
    r"\\\\[A-Za-z0-9._-]+\\",              # UNC shares
    r"[\w.+-]+@[\w-]+\.[\w.]{2,}",           # e-mail addresses
    r"\b(?:sk|ghp|gho|github_pat|xox[bpoa])[-_][A-Za-z0-9_-]{10,}",  # tokens
    r"-----BEGIN [A-Z ]+-----",               # PEM blocks
    r"\b\d{1,3}(?:\.\d{1,3}){3}\b",           # bare IPv4
]

#: Populated from --forbid-file at run time.
OPERATOR_FORBIDDEN_PATTERNS: List[str] = []


def load_renames(path: Optional[str]) -> Dict[str, str]:
    """Read the private field-name mapping. Missing file => no renames."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return {str(k): str(v) for k, v in json.load(fh).items()}


def load_forbidden(path: Optional[str]) -> List[str]:
    """Read extra privacy patterns, one regex per line, '#' comments allowed."""
    if not path or not os.path.exists(path):
        return []
    out: List[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


def rename_keys(obj: Any, mapping: Optional[Dict[str, str]] = None) -> Any:
    """Recursively neutralise field names. Values pass through untouched.

    This is the whole of the ledger transform: keys change, numbers do not.
    Any analysis that worked on the original works on the output.
    """
    m = FIELD_RENAMES if mapping is None else mapping
    if isinstance(obj, dict):
        return {m.get(k, k): rename_keys(v, m) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rename_keys(v, m) for v in obj]
    return obj


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> int:
    n = 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def build_gate_aggregates(events: List[Dict[str, Any]]):
    """Reduce a guard log to per-day counts plus a headline summary."""
    daily: "collections.Counter[str]" = collections.Counter()
    daily_fired: "collections.Counter[str]" = collections.Counter()
    daily_event: Dict[str, "collections.Counter[str]"] = {}
    event_totals: "collections.Counter[str]" = collections.Counter()
    tool_totals: "collections.Counter[str]" = collections.Counter()
    first_fire = None
    first_ts = None
    last_ts = None

    for e in events:
        ev = e.get("event")
        event_totals[ev] += 1
        if e.get("tool"):
            tool_totals[e["tool"]] += 1
        ts = e.get("ts")
        if not isinstance(ts, (int, float)):
            continue
        day = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%d")
        daily[day] += 1
        daily_event.setdefault(day, collections.Counter())[ev] += 1
        if first_ts is None or ts < first_ts:
            first_ts = ts
        if last_ts is None or ts > last_ts:
            last_ts = ts
        if ev == "block_issued":
            daily_fired[day] += 1
            if first_fire is None or ts < first_fire:
                first_fire = ts

    rows = []
    for day in sorted(daily):
        rows.append(
            {
                "date": day,
                "events": daily[day],
                "firings": daily_fired.get(day, 0),
                "by_event": dict(sorted(daily_event.get(day, {}).items())),
            }
        )

    summary = {
        "total_events": len(events),
        "event_totals": dict(sorted(event_totals.items())),
        "tool_totals": dict(sorted(tool_totals.items(), key=lambda kv: -kv[1])),
        "window_start_utc": _iso(first_ts),
        "window_end_utc": _iso(last_ts),
        "days_covered": len(daily),
        "total_firings": sum(daily_fired.values()),
        "days_with_zero_firings_before_first_fire": _zero_days_before_first(daily, daily_fired, first_fire),
        "events_before_first_fire": _events_before_first(events, first_fire),
        "event_totals_before_first_fire": _totals_before_first(events, first_fire),
        "first_fire_utc": _iso(first_fire),
    }
    return rows, summary


def _totals_before_first(events, first_fire):
    """Breakdown of the events recorded before the guard ever fired."""
    c: "collections.Counter[str]" = collections.Counter()
    if first_fire is None:
        for e in events:
            c[e.get("event")] += 1
        return dict(sorted(c.items()))
    for e in events:
        ts = e.get("ts")
        if isinstance(ts, (int, float)) and ts < first_fire:
            c[e.get("event")] += 1
    return dict(sorted(c.items()))


def _events_before_first(events, first_fire):
    """How many events were recorded before the guard ever fired.

    This is the number that matters for a DEAD_GATE finding: a guard that has
    been watching for N events and has never once acted is not a live defence,
    no matter how many of those events it logged as healthy.
    """
    if first_fire is None:
        return len(events)
    n = 0
    for e in events:
        ts = e.get("ts")
        if isinstance(ts, (int, float)) and ts < first_fire:
            n += 1
    return n


def _zero_days_before_first(daily, daily_fired, first_fire):
    if first_fire is None:
        return len(daily)
    first_day = _dt.datetime.fromtimestamp(first_fire, _dt.timezone.utc).strftime("%Y-%m-%d")
    return sum(1 for d in daily if d < first_day)


def _iso(ts):
    if ts is None:
        return None
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).isoformat()


def leak_check(paths: List[str], patterns: Optional[List[str]] = None) -> List[tuple]:
    """Fail loudly if a forbidden pattern survived into published output.

    A gate, not a scrubber: a hit fails the run rather than emitting a
    "cleaned" file that is not clean. Returns (path, pattern, sample) triples.
    """
    if patterns is None:
        patterns = list(GENERIC_FORBIDDEN_PATTERNS) + list(OPERATOR_FORBIDDEN_PATTERNS)
    hits: List[tuple] = []
    for p in paths:
        try:
            text = open(p, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                hits.append((p, pat, m.group(0)[:40]))
    return hits


#: One trigger per generic pattern. If the gate cannot fire on these, a clean
#: result means nothing — the same argument the package makes about guards.
_SELF_TEST_PROBES = [
    "C:\\probe\\leak",
    "/Users/probe/leak",
    "\\\\probe-host\\share\\leak",
    "probe@example.invalid",
    "sk-probe0000000000",
    "-----BEGIN PROBE-----",
    "192.0.2.7",
]


def self_test() -> int:
    """Positive control for the privacy gate.

    A gate that has never been observed to fire is not a gate; that is the
    DEAD_GATE verdict, and it applies to this tool as much as to anything it
    audits. Runs every generic pattern against an input that provably contains
    its trigger and fails if any pattern stays silent.
    """
    import tempfile

    fd, tmp = tempfile.mkstemp(suffix=".probe.txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(_SELF_TEST_PROBES) + "\n")
        hits = leak_check([tmp], patterns=GENERIC_FORBIDDEN_PATTERNS)
        caught = {h[1] for h in hits}
    finally:
        os.unlink(tmp)

    silent = [pat for pat in GENERIC_FORBIDDEN_PATTERNS if pat not in caught]
    print(f"[self-test] generic patterns={len(GENERIC_FORBIDDEN_PATTERNS)} "
          f"fired={len(caught)}")
    if silent:
        print("[self-test] FAILED — patterns that never fired:", file=sys.stderr)
        for pat in silent:
            print(f"    {pat}", file=sys.stderr)
        return 1
    if not OPERATOR_FORBIDDEN_PATTERNS:
        print("[self-test] WARNING: no operator patterns loaded; only generic "
              "shapes are being checked", file=sys.stderr)
    else:
        print(f"[self-test] operator patterns loaded: {len(OPERATOR_FORBIDDEN_PATTERNS)}")
    print("[self-test] PASS — the leak gate fires on known-positive input")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--ledger", help="private per-sample metric ledger (JSONL)")
    ap.add_argument("--gate", help="private guard log (JSONL)")
    ap.add_argument("--out", default="data", help="output directory")
    ap.add_argument(
        "--renames",
        default=os.path.join(os.path.dirname(__file__), "field_renames.local.json"),
        help="JSON {private_field: published_field} (gitignored)",
    )
    ap.add_argument(
        "--forbid-file",
        default=os.path.join(os.path.dirname(__file__), "forbidden.local.txt"),
        help="extra privacy patterns, one regex per line (gitignored)",
    )
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="positive control for the privacy gate itself; then exit",
    )
    args = ap.parse_args(argv)

    global OPERATOR_FORBIDDEN_PATTERNS
    renames = load_renames(args.renames)
    OPERATOR_FORBIDDEN_PATTERNS = load_forbidden(args.forbid_file)

    if args.self_test:
        return self_test()
    if not renames:
        print(f"note: no rename map at {args.renames}; field names pass through")
    produced: List[str] = []

    if args.ledger:
        rows = load_jsonl(args.ledger)
        clean = [rename_keys(r, renames) for r in rows]
        out = os.path.join(args.out, "ledger_metric_samples.jsonl")
        n = write_jsonl(out, clean)
        produced.append(out)
        print(f"[ledger] {n} samples -> {out}")

    if args.gate:
        events = load_jsonl(args.gate)
        daily, summary = build_gate_aggregates(events)
        dout = os.path.join(args.out, "gate_daily.jsonl")
        write_jsonl(dout, daily)
        produced.append(dout)
        sout = os.path.join(args.out, "gate_summary.json")
        with open(sout, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        produced.append(sout)
        print(f"[gate] {summary['total_events']} events -> {len(daily)} daily rows")
        print(f"[gate] firings={summary['total_firings']} "
              f"first_fire={summary['first_fire_utc']} "
              f"silent_days_before={summary['days_with_zero_firings_before_first_fire']}")

    if not produced:
        ap.error("nothing to do: pass --ledger and/or --gate")

    if self_test() != 0:
        print("\nrefusing to certify a run whose own gate cannot fire", file=sys.stderr)
        return 1

    hits = leak_check(produced)
    if hits:
        print("\nLEAK CHECK FAILED — output contains forbidden substrings:", file=sys.stderr)
        for path, pattern, sample in hits:
            print(f"  {path}: /{pattern}/ matched {sample!r}", file=sys.stderr)
        return 1
    n_pat = len(GENERIC_FORBIDDEN_PATTERNS) + len(OPERATOR_FORBIDDEN_PATTERNS)
    print(f"\nleak check: clean ({len(produced)} files, {n_pat} patterns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
