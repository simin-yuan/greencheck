#!/usr/bin/env python3
"""
case_study/run_case_study.py — reproduce every table in the paper.

    python case_study/run_case_study.py

Reads the anonymised datasets in data/ and writes:
    case_study/results/CASE_STUDY.md
    case_study/results/tables.json

The data are real. They were recorded by an automated self-assessment job and
a safety gate on a long-running autonomous agent, then anonymised by
tools/anonymise.py. Nothing here is synthetic, and no value was edited: only
field *names* were neutralised before publication.

Scope note. The production implementations of the three instruments under test
are not part of this repository. Conclusions below are drawn from the recorded
ledgers alone, which is the stronger form of evidence anyway: a ledger is what
the instrument actually emitted, whereas re-running a reimplementation would
only show what a reimplementation does.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from greencheck import audit_gate, audit_gate_counts, audit_ledger, get_path, load_jsonl, __version__  # noqa: E402
from greencheck.report import render_markdown  # noqa: E402

DATA = os.path.join(ROOT, "data")
OUT = os.path.join(HERE, "results")


def audit_ledger_paths(field, subject, count_field=None, fresh_field=None):
    rows = load_jsonl(os.path.join(DATA, "ledger_metric_samples.jsonl"))
    projected = []
    for r in rows:
        item = {"value": get_path(r, field)}
        if count_field:
            item["_count"] = get_path(r, count_field)
        if fresh_field:
            item["_fresh"] = get_path(r, fresh_field)
        projected.append(item)
    return audit_ledger(
        projected,
        field="value",
        subject=subject,
        count_field="_count" if count_field else None,
        fresh_field="_fresh" if fresh_field else None,
    )


def main() -> int:
    os.makedirs(OUT, exist_ok=True)

    ledger = load_jsonl(os.path.join(DATA, "ledger_metric_samples.jsonl"))
    gate_daily = load_jsonl(os.path.join(DATA, "gate_daily.jsonl"))
    gate_summary = json.load(open(os.path.join(DATA, "gate_summary.json"), encoding="utf-8"))

    # --- the three instruments declared by the self-assessment job ---------
    results = [
        audit_ledger_paths(
            "identity.identity_score",
            "self_assessment.identity_score",
            count_field="identity.anchors_total",
        ),
        audit_ledger_paths(
            "memory_recall.recall_rate",
            "self_assessment.memory_recall.recall_rate",
            count_field="memory_recall.sampled",
        ),
        audit_ledger_paths(
            "reflection.reflection_score",
            "self_assessment.reflection_score",
            fresh_field="reflection.fresh",
        ),
        audit_ledger_paths(
            "overall",
            "self_assessment.overall (composite)",
            fresh_field="reflection.fresh",
        ),
    ]

    # --- the guard ---------------------------------------------------------
    # Two windows, because the interesting fact is not the total firing count
    # but the fact that the count was zero for the entire period before anyone
    # constructed an input the guard was known to have to block.
    pre_total = gate_summary["events_before_first_fire"]
    pre_health = gate_summary["event_totals_before_first_fire"].get("self_change", 0)
    gate_dead = audit_gate_counts(
        total_events=pre_total,
        firings=0,
        health_events=pre_health,
        subject="guard denial path — before any positive control",
        window=[gate_summary["window_start_utc"], gate_summary["first_fire_utc"]],
        silent_days_before_first_fire=gate_summary["days_with_zero_firings_before_first_fire"],
    )
    gate_all = audit_gate_counts(
        total_events=gate_summary["total_events"],
        firings=gate_summary["total_firings"],
        health_events=gate_summary["event_totals"].get("self_change", 0),
        subject="guard denial path — full window",
        first_fire=gate_summary["first_fire_utc"],
        note=(
            f"The path has fired {gate_summary['total_firings']} times, the first at "
            f"{gate_summary['first_fire_utc']}. That first firing was produced by a positive "
            "control written specifically to exercise the path, not by ordinary traffic."
        ),
    )
    gate_results = [gate_dead, gate_all]
    all_results = results + gate_results

    # --- composite picture -------------------------------------------------
    n_samples = len(ledger)
    identity_vals = [get_path(r, "identity.identity_score") for r in ledger]
    recall_vals = [get_path(r, "memory_recall.recall_rate") for r in ledger]
    sampled_vals = [get_path(r, "memory_recall.sampled") for r in ledger]
    overall_vals = [get_path(r, "overall") for r in ledger]

    headline = {
        "ledger_samples": n_samples,
        "ledger_window": [ledger[0].get("ts"), ledger[-1].get("ts")] if ledger else [],
        "identity_score_distinct": len(set(map(str, identity_vals))),
        "identity_score_value": sorted(set(map(str, identity_vals))),
        "recall_rate_distinct": len(set(map(str, recall_vals))),
        "samples_examining_nothing": sum(1 for v in sampled_vals if v == 0),
        "overall_distinct": len(set(map(str, overall_vals))),
        "gate_events": gate_summary["total_events"],
        "gate_firings": gate_summary["total_firings"],
        "gate_days_covered": gate_summary["days_covered"],
        "gate_silent_days_before_first_fire": gate_summary["days_with_zero_firings_before_first_fire"],
        "gate_first_fire_utc": gate_summary["first_fire_utc"],
    }

    # --- render ------------------------------------------------------------
    lines = []
    lines.append("# Case study: self-reported instruments on a long-running autonomous agent")
    lines.append("")
    lines.append(f"Generated by `case_study/run_case_study.py` (greencheck {__version__}).")
    lines.append("")
    lines.append("## Data")
    lines.append("")
    lines.append(f"- **Metric ledger** — {n_samples} samples recorded in production, "
                 f"{headline['ledger_window'][0]} → {headline['ledger_window'][1]}.")
    lines.append(f"- **Guard log** — {gate_summary['total_events']} events over "
                 f"{gate_summary['days_covered']} days, aggregated to daily counts before release.")
    lines.append("")
    lines.append("Every instrument below was written and deployed by the agent itself, to check")
    lines.append("itself. No external observer chose them, their inputs, or their thresholds.")
    lines.append("That is the condition under test.")
    lines.append("")
    lines.append("## Result summary")
    lines.append("")
    lines.append("| instrument | n | verdict |")
    lines.append("|---|---:|---|")
    for r in all_results:
        v = "PASS" if r.ok else "; ".join(r.verdicts)
        lines.append(f"| `{r.subject}` | {r.n_samples:,} | **{v}** |")
    lines.append("")
    lines.append(render_markdown(all_results, title="Findings in detail", level=2))
    lines.append("")
    lines.append("## What the failures have in common")
    lines.append("")
    lines.append("Each instrument was correct code. None crashed. None returned nonsense.")
    lines.append("Each produced a number on schedule, and each number was read.")
    lines.append("What none of them did was vary with the thing it was named after:")
    lines.append("")
    lines.append("- `identity_score` reported 1.0 in every one of the 84 samples. A constant")
    lines.append("  cannot carry information about anything.")
    lines.append(f"- `recall_rate` reported 0.0 in every sample. {headline['samples_examining_nothing']} of")
    lines.append("  those samples examined nothing at all, and reported the same value as samples")
    lines.append("  that examined eight items and matched none.")
    lines.append("- `overall` and `reflection_score` each took two values across the ledger, and")
    lines.append("  the split between them is exactly the split on one boolean. Neither is an")
    lines.append("  independent finding: they are the same bit, reported twice.")
    lines.append(f"- The guard logged {pre_health:,} healthy events over")
    lines.append(f"  {gate_summary['days_with_zero_firings_before_first_fire']} days and fired 0 times.")
    lines.append("")
    lines.append("## Falsifiers")
    lines.append("")
    lines.append("These results are stated so that they can be wrong:")
    lines.append("")
    lines.append("1. If any instrument above is shown to separate inputs within the dimension it")
    lines.append("   claims to measure, the corresponding finding is false.")
    lines.append("2. If the guard is shown to have fired before "
                 f"{gate_summary['first_fire_utc']} on an input that should have been")
    lines.append("   blocked, the DEAD_GATE finding is false.")
    lines.append("3. If the anonymisation changed any value (as opposed to a field name), every")
    lines.append("   number here is void. `tools/anonymise.py` is the only transform applied;")
    lines.append("   it rewrites keys and aggregates the guard log, and its leak check is mandatory.")
    lines.append("")

    md = "\n".join(lines)
    with open(os.path.join(OUT, "CASE_STUDY.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md + "\n")

    payload = {
        "mdt_version": __version__,
        "headline": headline,
        "metric_results": [r.to_dict() for r in results],
        "gate_results": [g.to_dict() for g in gate_results],
    }
    with open(os.path.join(OUT, "tables.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote {os.path.join(OUT, 'CASE_STUDY.md')}")
    print(f"wrote {os.path.join(OUT, 'tables.json')}")
    print()
    print(f"ledger samples        : {n_samples}")
    print(f"identity_score values : {headline['identity_score_value']} ({headline['identity_score_distinct']} distinct)")
    print(f"recall_rate distinct  : {headline['recall_rate_distinct']}")
    print(f"overall distinct      : {headline['overall_distinct']}")
    print(f"gate events / firings : {headline['gate_events']} / {headline['gate_firings']}")
    print(f"gate silent days      : {headline['gate_silent_days_before_first_fire']}")
    flagged = sum(1 for r in all_results if not r.ok)
    print(f"instruments flagged   : {flagged}/{len(all_results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
