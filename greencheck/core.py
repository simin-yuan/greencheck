"""
greencheck.core — the discriminability test.

Central claim of this package:

    A reported number is not a measurement until it has been observed to
    take *different* values on inputs that are known to differ.

Everything else here is machinery for making that claim checkable.

Two levels of testing are provided, and they answer different questions:

1. `discriminate()`  — behavioural. You hand it a callable and a set of
   probe pairs that are known to differ. It reports how many pairs the
   callable actually separates. A callable that collapses every pair is
   not measuring the thing its name implies.

2. `audit_ledger()`  — historical. You hand it a ledger of already-collected
   samples (what an instrument wrote to disk in production). It reports which
   of the known failure signatures are present *without* re-running anything.
   This is the level at which silent instrumentation dies: the callable may be
   fine while the recorded series is a constant, a bare zero, or a single bit
   wearing a score's clothing.

Neither level requires trust in the instrument's own self-report. That is the
point: the instrument is the thing under test, so its opinion of itself is not
admissible evidence.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------

#: The probe callable separated known-different inputs. No signature found.
PASS = "PASS"

#: Zero variance across every sample. The series cannot be distinguished from
#: a constant by any downstream consumer.
CONSTANT = "CONSTANT"

#: The callable returns the same value for a real input and for a degenerate
#: input (empty / missing / contradictory). It is therefore measuring whether
#: the input *exists*, not the property it claims to measure.
IDENTITY = "IDENTITY"

#: `n = 0` and `n > 0 with zero hits` produce the same output. The zero is
#: ambiguous, so a consumer cannot tell "nothing was examined" from
#: "everything was examined and nothing matched".
BARE_ZERO = "BARE_ZERO"

#: All variance in the delivered score traces to a single boolean input.
#: The score is a liveness indicator in a score's clothing.
LIVENESS_BIT = "LIVENESS_BIT"

#: A guard/assertion exists, records itself as healthy, and has never been
#: observed to fire on an input that is known to be positive. Not a defence;
#: an ornament.
DEAD_GATE = "DEAD_GATE"

#: Nothing was audited. An empty ledger is not a passing ledger: an audit with
#: no data has not succeeded, it has not happened. Reported explicitly because
#: the default of returning PASS here would reproduce the exact failure this
#: package exists to catch.
NO_DATA = "NO_DATA"

ALL_VERDICTS = (PASS, CONSTANT, IDENTITY, BARE_ZERO, LIVENESS_BIT, DEAD_GATE, NO_DATA)


@dataclass
class Finding:
    """One detected signature, with the evidence that produced it."""

    verdict: str
    subject: str
    detail: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditResult:
    """Outcome of auditing one recorded series."""

    subject: str
    n_samples: int
    verdicts: List[str]
    findings: List[Finding]
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.verdicts == [PASS]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ok"] = self.ok
        return d


# --------------------------------------------------------------------------
# Level 1 — behavioural discriminability
# --------------------------------------------------------------------------

@dataclass
class ProbePair:
    """Two inputs that are known to differ, plus which dimension they differ in.

    `dimension` is the part that makes this a test rather than a gesture. An
    instrument that separates inputs differing in *quantity* (long text vs
    short text) has shown nothing about whether it measures *content*. Only
    separation along the dimension the instrument claims to measure counts.
    """

    name: str
    left: Any
    right: Any
    dimension: str = "general"
    note: str = ""


def discriminate(
    fn: Callable[[Any], Any],
    pairs: Sequence[ProbePair],
    subject: str = "<callable>",
    tolerance: float = 0.0,
    claimed_dimensions: Optional[Sequence[str]] = None,
) -> AuditResult:
    """Run `fn` over each probe pair and count how many it separates.

    A pair is *separated* when the two outputs differ by more than `tolerance`.

    The verdict is per claimed dimension. If `claimed_dimensions` is given, the
    callable must separate at least one pair within **each** named dimension.
    A callable that collapses every pair inside a dimension it claims to
    measure is reported as IDENTITY for that dimension, even if it separates
    pairs in some other dimension (that is the classic shape: quantity moves,
    content does not).
    """
    rows = []
    by_dim: Dict[str, List[bool]] = {}
    separated = 0
    for p in pairs:
        try:
            lv = fn(p.left)
        except Exception as exc:  # a crash is information, not a pass
            lv = f"<raised {type(exc).__name__}: {exc}>"
        try:
            rv = fn(p.right)
        except Exception as exc:
            rv = f"<raised {type(exc).__name__}: {exc}>"
        differs = _differs(lv, rv, tolerance)
        separated += 1 if differs else 0
        by_dim.setdefault(p.dimension, []).append(differs)
        rows.append(
            {
                "pair": p.name,
                "dimension": p.dimension,
                "left": lv,
                "right": rv,
                "separated": differs,
                "note": p.note,
            }
        )

    dims = list(claimed_dimensions) if claimed_dimensions else list(by_dim)
    dead_dims = [d for d in dims if by_dim.get(d) and not any(by_dim[d])]

    verdicts: List[str] = []
    findings: List[Finding] = []
    if dead_dims:
        verdicts.append(IDENTITY)
        findings.append(
            Finding(
                verdict=IDENTITY,
                subject=subject,
                detail=(
                    f"0/{len(by_dim[dead_dims[0]])} probe pairs separated within the "
                    f"claimed dimension {dead_dims[0]!r}"
                    + (f" (also dead: {', '.join(dead_dims[1:])})" if len(dead_dims) > 1 else "")
                    + ". The instrument responds to something other than what it claims "
                    "to measure."
                ),
                evidence={"dead_dimensions": dead_dims, "pairs": rows},
            )
        )
    elif separated == 0 and pairs:
        verdicts.append(IDENTITY)
        findings.append(
            Finding(
                verdict=IDENTITY,
                subject=subject,
                detail=f"0/{len(pairs)} known-different probe pairs were separated.",
                evidence={"pairs": rows},
            )
        )
    else:
        verdicts.append(PASS)

    return AuditResult(
        subject=subject,
        n_samples=len(pairs),
        verdicts=verdicts,
        findings=findings,
        stats={
            "pairs_separated": separated,
            "pairs_total": len(pairs),
            "separated_by_dimension": {d: sum(v) for d, v in by_dim.items()},
            "pairs": rows,
        },
    )


def _differs(a: Any, b: Any, tolerance: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(float(a)) and math.isnan(float(b)):
            return False
        return abs(float(a) - float(b)) > tolerance
    return a != b


# --------------------------------------------------------------------------
# Level 2 — historical ledger audit
# --------------------------------------------------------------------------

def audit_ledger(
    records: Iterable[Dict[str, Any]],
    field: str = "value",
    subject: Optional[str] = None,
    count_field: Optional[str] = None,
    fresh_field: Optional[str] = None,
) -> AuditResult:
    """Audit an already-recorded series for known failure signatures.

    Parameters
    ----------
    records:
        Iterable of dicts, one per sample, as written by the instrument.
    field:
        Key holding the reported value.
    subject:
        Label for the report.
    count_field:
        Optional key holding the number of items examined for this sample
        (e.g. `sampled`, `n`, `attempts`). Enables BARE_ZERO detection.
    fresh_field:
        Optional key holding a boolean flag thought to be an input
        (e.g. `fresh`). Enables LIVENESS_BIT attribution.

    Returns
    -------
    AuditResult with every signature found, not just the first. Instruments
    tend to be wrong in more than one way at once.
    """
    rows = [r for r in records if isinstance(r, dict) and field in r]
    subject = subject or field
    n = len(rows)
    if n == 0:
        return AuditResult(
            subject=subject,
            n_samples=0,
            verdicts=[NO_DATA],
            findings=[
                Finding(
                    verdict=NO_DATA,
                    subject=subject,
                    detail=(
                        f"0 samples matched the requested field {field!r}. An audit with "
                        "no data has not passed; it has not happened. Reporting this as "
                        "OK would reproduce the failure the audit exists to catch."
                    ),
                    evidence={"field": field},
                )
            ],
            stats={"note": "empty ledger; nothing to audit", "distinct_values": 0},
        )

    values = [r.get(field) for r in rows]
    verdicts: List[str] = []
    findings: List[Finding] = []
    stats: Dict[str, Any] = {"n_samples": n}

    # --- CONSTANT -------------------------------------------------------
    distinct = _distinct(values)
    stats["distinct_values"] = distinct
    stats["value_counts"] = _value_counts(values)
    if distinct == 1:
        verdicts.append(CONSTANT)
        findings.append(
            Finding(
                verdict=CONSTANT,
                subject=subject,
                detail=(
                    f"{n}/{n} samples report the identical value {values[0]!r}. "
                    "Zero variance over the observed window."
                ),
                evidence={"value": values[0], "n": n},
            )
        )

    # --- BARE_ZERO ------------------------------------------------------
    if count_field:
        counts = [r.get(count_field) for r in rows]
        zero_val = _modal_zero_value(values)
        if zero_val is not None:
            bare = [
                i
                for i, (v, c) in enumerate(zip(values, counts))
                if c == 0 and v == zero_val
            ]
            nonzero = [i for i, c in enumerate(counts) if c not in (0, None)]
            if bare and nonzero:
                same = all(values[i] == values[j] for i in bare for j in nonzero
                           if values[j] == zero_val)
                all_bare_same = len({values[i] for i in bare}) == 1
                if same and all_bare_same:
                    verdicts.append(BARE_ZERO)
                    findings.append(
                        Finding(
                            verdict=BARE_ZERO,
                            subject=subject,
                            detail=(
                                f"{len(bare)} of {n} samples examined nothing "
                                f"({count_field}=0) yet reported {zero_val!r} — the same "
                                f"value produced by samples that examined {min(counts[i] for i in nonzero)}+ "
                                "items and matched none. The zero is ambiguous: a consumer "
                                "cannot distinguish 'not examined' from 'examined, no hits'."
                            ),
                            evidence={
                                "zero_count_rows": len(bare),
                                "zero_count_value": zero_val,
                                "min_examined": min(counts[i] for i in nonzero),
                            },
                        )
                    )

    # --- LIVENESS_BIT ---------------------------------------------------
    if fresh_field and distinct > 1:
        attrib = _variance_attribution(rows, field, fresh_field)
        stats["variance_explained_by"] = {fresh_field: attrib}
        if attrib is not None and attrib >= 0.999:
            verdicts.append(LIVENESS_BIT)
            findings.append(
                Finding(
                    verdict=LIVENESS_BIT,
                    subject=subject,
                    detail=(
                        f"100% of the variance in {field!r} is accounted for by the "
                        f"boolean {fresh_field!r} alone. Every other input is constant "
                        "across the ledger, so the score is a liveness indicator, not a "
                        "measurement of the property in its name."
                    ),
                    evidence={"attribution": attrib, "n": n},
                )
            )

    if not verdicts:
        verdicts.append(PASS)

    return AuditResult(
        subject=subject,
        n_samples=n,
        verdicts=verdicts,
        findings=findings,
        stats=stats,
    )


# --------------------------------------------------------------------------
# Level 3 — gate audit (never-fired assertions)
# --------------------------------------------------------------------------

def audit_gate(
    events: Iterable[Dict[str, Any]],
    event_field: str = "event",
    fire_event: str = "block_issued",
    subject: str = "<gate>",
) -> AuditResult:
    """Check whether an assertion has ever actually fired, from raw events.

    An assertion that has recorded itself as healthy N times and has never
    once fired on an input known to be positive is not a defence. The count of
    self-reported health is not evidence; the count of firings is.

    Callers are expected to pair this with a positive control (see
    `docs/METHOD.md`): the firing count only becomes meaningful once someone
    has shown the gate fires *when it should*.

    For aggregated logs, use `audit_gate_counts` instead.
    """
    total = 0
    fired = 0
    registered = 0
    for e in events:
        if not isinstance(e, dict):
            continue
        total += 1
        ev = e.get(event_field)
        if ev == fire_event:
            fired += 1
        if ev in ("registered", "self_change", "logged"):
            registered += 1
    return audit_gate_counts(
        total_events=total,
        firings=fired,
        health_events=registered,
        subject=subject,
    )


def looks_like_daily_aggregate(rows: Sequence[Any]) -> bool:
    """True if these rows count days rather than events.

    The two are easy to confuse and the confusion is silent: reading daily rows
    as event rows turns a sixteen-day window into "16 samples", which is a
    confident number that means nothing. The published dataset in this
    repository is daily, so a tool that cannot read its own published data has a
    defect any reader would hit in the first minute.
    """
    if not rows:
        return False
    first = rows[0]
    if not isinstance(first, dict):
        return False
    return (
        "date" in first
        and "events" in first
        and "firings" in first
        and "event" not in first
    )


def audit_gate_daily(
    rows: Sequence[Dict[str, Any]],
    fire_event: str = "block_issued",
    subject: str = "<gate>",
    health_event: str = "self_change",
) -> Tuple[AuditResult, AuditResult]:
    """Audit a per-day aggregate log, in both windows that matter.

    Returns ``(before_first_fire, whole_window)``.

    The first is the interesting one and the second is the control. Both are
    the same guard: the first covers only the whole days that ended with zero
    firings and before any firing happened, the second covers everything. The
    same code reads DEAD_GATE for the first and PASS for the second, which is
    the point — what changed between them is not the guard but whether anyone
    had ever built it an input it had to reject.

    Whole days rather than timestamps, deliberately. A count of "events before
    the first firing" needs event-level rows to recompute, and only aggregates
    are published here, so that number would be checkable by nobody. Day
    granularity costs one day of precision and buys the reader a for-loop.
    """
    days = [r for r in rows if isinstance(r, dict)]
    if not days:
        raise ValueError("no daily rows to audit")

    # The window that ends before any firing happened at all. Only whole days:
    # the day of the first firing is partly silent and is excluded.
    leading = []
    for row in days:
        if row.get("firings", 0) > 0:
            break
        leading.append(row)

    def _totals(window: Sequence[Dict[str, Any]]):
        events = sum(int(r.get("events", 0)) for r in window)
        firings = sum(int(r.get("firings", 0)) for r in window)
        health = sum(int((r.get("by_event") or {}).get(health_event, 0)) for r in window)
        return events, firings, health

    lead_events, _, lead_health = _totals(leading)
    all_events, all_firings, all_health = _totals(days)

    n_leading = len(leading)
    before = audit_gate_counts(
        total_events=lead_events,
        firings=0,
        health_events=lead_health,
        subject=f"{subject} — {n_leading} full days with zero firings",
        window=[leading[0]["date"], leading[-1]["date"]] if leading else None,
        silent_days_before_first_fire=n_leading or None,
        note=(
            f"Window: {leading[0]['date']} to {leading[-1]['date']}, whole days only."
            if leading
            else ""
        ),
    )
    whole = audit_gate_counts(
        total_events=all_events,
        firings=all_firings,
        health_events=all_health,
        subject=f"{subject} — full window ({len(days)} days)",
        note=(
            f"The path fired {all_firings} times, the first on "
            f"{next((r['date'] for r in days if r.get('firings', 0) > 0), 'n/a')}. "
            "That first firing came from a positive control written specifically "
            "to exercise the path, not from ordinary traffic."
        ),
    )
    return before, whole


def audit_gate_counts(
    total_events: int,
    firings: int,
    health_events: int = 0,
    subject: str = "<gate>",
    first_fire: Optional[str] = None,
    window: Optional[Sequence[str]] = None,
    silent_days_before_first_fire: Optional[int] = None,
    note: str = "",
) -> AuditResult:
    """The aggregate form of `audit_gate`.

    Takes counts rather than events so that a guard log can be audited without
    the log itself being published — the counts support the claim, the raw
    lines carry whatever the operator's environment contained.

    A window with zero firings is reported DEAD_GATE regardless of how many
    times the guard recorded itself healthy. Health is self-reported; firing is
    observed.
    """
    verdicts: List[str] = []
    findings: List[Finding] = []

    if firings == 0 and total_events > 0:
        verdicts.append(DEAD_GATE)
        span = ""
        if silent_days_before_first_fire:
            span = f" across {silent_days_before_first_fire} days"
        elif window and all(window):
            span = f" between {window[0]} and {window[1]}"
        findings.append(
            Finding(
                verdict=DEAD_GATE,
                subject=subject,
                detail=(
                    f"{total_events:,} events recorded{span}, of which "
                    f"{health_events:,} were the guard reporting itself healthy, and the "
                    f"denial path fired 0 times. The assertion has never been observed "
                    "to fire. Its existence is documented; its behaviour is not."
                ),
                evidence={
                    "total_events": total_events,
                    "health_events": health_events,
                    "firings": 0,
                    "note": note,
                },
            )
        )
    else:
        verdicts.append(PASS)
        if note:
            findings.append(
                Finding(
                    verdict=PASS,
                    subject=subject,
                    detail=note,
                    evidence={"total_events": total_events, "firings": firings},
                )
            )

    return AuditResult(
        subject=subject,
        n_samples=total_events,
        verdicts=verdicts,
        findings=findings,
        stats={
            "total_events": total_events,
            "health_events": health_events,
            "firings": firings,
            "first_fire": first_fire,
            "silent_days_before_first_fire": silent_days_before_first_fire,
        },
    )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _distinct(values: Sequence[Any]) -> int:
    seen = []
    for v in values:
        if not any(v == s for s in seen):
            seen.append(v)
    return len(seen)


def _value_counts(values: Sequence[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def _modal_zero_value(values: Sequence[Any]) -> Optional[float]:
    """The numeric value the series reports when nothing matched, if any."""
    for v in values:
        if isinstance(v, (int, float)) and float(v) == 0.0:
            return v
    return None


def _variance_attribution(
    rows: List[Dict[str, Any]], field: str, bool_field: str
) -> Optional[float]:
    """Fraction of variance in `field` explained by the boolean `bool_field`.

    Computed as the between-group variance ratio (eta-squared) for a two-level
    grouping. Returns None when the field is not numeric.
    """
    vals = []
    for r in rows:
        v = r.get(field)
        if isinstance(v, (int, float)) and not math.isnan(float(v)):
            vals.append((float(v), bool(r.get(bool_field))))
    if len(vals) < 2:
        return None
    ys = [v for v, _ in vals]
    mean = sum(ys) / len(ys)
    total = sum((y - mean) ** 2 for y in ys)
    if total == 0:
        return 0.0
    groups: Dict[bool, List[float]] = {}
    for v, b in vals:
        groups.setdefault(b, []).append(v)
    between = 0.0
    for b, g in groups.items():
        gm = sum(g) / len(g)
        between += len(g) * (gm - mean) ** 2
    return between / total


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """Read a JSON-lines file, skipping blanks and unparseable lines."""
    out = []
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


def get_path(record: Dict[str, Any], dotted: str) -> Any:
    """Fetch `a.b.c` out of a nested dict, returning None if absent."""
    cur: Any = record
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur
