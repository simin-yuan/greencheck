#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent check of the study numbers.

Nothing here trusts study.py's aggregate columns:

1. every mutant is rebuilt from scratch and its text-category recounted;
2. every judged mutant is re-judged with ONE CLI invocation per instance (no JSONL
   batching), so a misparsed batch entry number would show up as a disagreement;
3. every baseline is re-judged the same way;
4. class counts, the allOf-base stratum and every headline number are recomputed
   from out/escapes.jsonl + the specs, then written to out/summary.json.

Exit 0 only if every check agrees.
"""
from __future__ import annotations

import csv
import json
import os
import statistics as st
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "<redacted-abs-path>")
import greencheck.mutate as gm                                  # noqa: E402
from study import CLI, CP, build_cases, run_gate                # noqa: E402

CLASSES = {"undeclared-key", "declared-optional-removed", "value-level", "ANOMALY", "unresolved"}


def judge_one(spec_path, entrypoint, text):
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=os.path.join(HERE, "out"))
    os.close(fd)
    try:
        open(tmp, "w", encoding="utf-8").write(text)
        r = subprocess.run([CLI, "validate", spec_path.replace("\\", "/"), tmp,
                            "--entrypoint", entrypoint, "--color", "never"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            return "ACCEPT"
        if r.returncode == 2:
            return "REJECT"
        return f"ENGINE-ERROR({r.returncode})"
    finally:
        os.unlink(tmp)


def main():
    sample = json.load(open(os.path.join(HERE, "out", "sample.json"), encoding="utf-8"))
    cases = [c for c in build_cases(sample)]
    rows = list(csv.DictReader(open(os.path.join(HERE, "out", "cases.csv"), encoding="utf-8")))
    escapes = [json.loads(l) for l in open(os.path.join(HERE, "out", "escapes.jsonl"), encoding="utf-8")]
    problems = []

    by_key = {(r["spec"], r["schema"]): r for r in rows}
    if len(cases) != len(rows):
        problems.append(f"cases rebuilt {len(cases)} != csv rows {len(rows)}")
    if len(by_key) != len(rows):
        problems.append("duplicate (spec, schema) rows in cases.csv")

    claimed_escape = Counter((e["spec"], e["schema"], e["mutant"]) for e in escapes if e["class"] != "DIVERGENCE")
    rejudged = Counter()
    checked = 0

    for c in cases:
        rec = by_key.get((c["spec"], c["schema"]))
        if rec is None:
            problems.append(f"missing row {c['spec']}/{c['schema']}")
            continue
        if rec["baseline"] == "SKIPPED-OVER-CAP":
            continue
        base_v = judge_one(c["spec_path"], c["entrypoint"], c["text"])
        # ENGINE-ERROR carries the exit code; the csv keeps the bare class.
        if base_v.split("(")[0] != rec["baseline"]:
            problems.append(f"baseline {c['spec']}/{c['schema']}: rerun {base_v} vs csv {rec['baseline']}")
        if rec["baseline"] != "ACCEPT":
            continue

        judged, pb, noop = [], 0, 0
        for name, patch in gm.build_mutants({"instance.json": c["text"]}):
            content = next(iter(patch.values()))
            if content is None or not content.strip():
                pb += 1
                continue
            try:
                inst = json.loads(content)
            except Exception:                                      # noqa: BLE001
                pb += 1
                continue
            if inst == c["example"]:
                noop += 1
                continue
            judged.append((name, content))
        if len(judged) + pb + noop != int(rec["mutants"]):
            problems.append(f"{c['spec']}/{c['schema']}: mutant recount {len(judged)+pb+noop} != {rec['mutants']}")
        if pb != int(rec["parse_broken"]) or noop != int(rec["no_op"]):
            problems.append(f"{c['spec']}/{c['schema']}: parse_broken/no_op {pb}/{noop} != csv")
        for name, content in judged:
            v = judge_one(c["spec_path"], c["entrypoint"], content)
            checked += 1
            if v == "ACCEPT":
                rejudged[(c["spec"], c["schema"], name)] += 1
        print(f"  re-judged {len(judged):4d}  {c['spec'][:36]:<36} {c['schema'][:26]}")

    miss = claimed_escape - rejudged
    extra = rejudged - claimed_escape
    if miss:
        problems.append(f"{len(miss)} claimed escapes not reproduced: {list(miss)[:3]}")
    if extra:
        problems.append(f"{len(extra)} escapes found on rerun but absent from the report: {list(extra)[:3]}")

    # ---- class counts and the allOf-base stratum
    esc_rows = [e for e in escapes if e["class"] != "DIVERGENCE"]
    bad_cls = [e for e in esc_rows if e["class"] not in CLASSES]
    if bad_cls:
        problems.append(f"{len(bad_cls)} escape rows outside the declared classes")
    cls = Counter(e["class"] for e in esc_rows)

    base_of = {}
    for s in sample["specs"]:
        doc = json.load(open(os.path.join(HERE, s["path"]), encoding="utf-8"))
        schemas = ((doc.get("components") or {}).get("schemas") or {})
        bases = set()
        for owner, node in schemas.items():
            stack = [node]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    for arm in cur.get("allOf") or []:
                        if isinstance(arm, dict) and isinstance(arm.get("$ref"), str) \
                                and arm["$ref"].startswith(CP):
                            name = arm["$ref"][len(CP):]
                            if name != owner:
                                bases.add(name)
                    stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
                elif isinstance(cur, list):
                    stack.extend(cur)
        base_of[s["name"]] = bases

    in_base = [e for e in esc_rows if e["owner"] in base_of.get(e["spec"], set())]

    tot_mut = sum(int(r["mutants"]) for r in rows)
    judged = sum(int(r["escaped"]) + int(r["schema_rejected"]) + int(r["engine_error"]) for r in rows)
    pb = sum(int(r["parse_broken"]) for r in rows)
    noop = sum(int(r["no_op"]) for r in rows)
    if tot_mut != judged + pb + noop:
        problems.append(f"mutants {tot_mut} != judged {judged} + parse_broken {pb} + no_op {noop}")
    if judged != checked:
        problems.append(f"judged in csv {judged} != re-judged {checked}")
    if sum(cls.values()) != int(sum(int(r["escaped"]) for r in rows)):
        problems.append("class rows != escaped total")

    rates = [int(r["escaped"]) / (int(r["escaped"]) + int(r["schema_rejected"]))
             for r in rows if int(r["escaped"]) + int(r["schema_rejected"]) > 0]
    per_spec = {}
    for r in rows:
        d = per_spec.setdefault(r["spec"], {"cases": 0, "escaped": 0, "judged": 0})
        d["cases"] += 1
        d["escaped"] += int(r["escaped"])
        d["judged"] += int(r["escaped"]) + int(r["schema_rejected"])

    summary = {
        "specs_sampled": len(sample["specs"]),
        "specs_contributing_cases": len({c["spec"] for c in cases}),
        "cases": len(cases),
        "baseline": dict(Counter(r["baseline"] for r in rows)),
        "mutants": tot_mut,
        "parse_broken": pb,
        "parse_broken_share": round(pb / tot_mut, 4),
        "no_op": noop,
        "judged": judged,
        "escaped": sum(int(r["escaped"]) for r in rows),
        "schema_rejected": sum(int(r["schema_rejected"]) for r in rows),
        "engine_error": sum(int(r["engine_error"]) for r in rows),
        "escape_rate_pooled": round(sum(int(r["escaped"]) for r in rows) / judged, 4),
        "escape_rate_median_case": round(st.median(rates), 4) if rates else None,
        "cases_with_judged": len(rates),
        "classes": dict(cls),
        "allof_base_escapes": len(in_base),
        "allof_base_share": round(len(in_base) / len(esc_rows), 4),
        "xcheck_compared": sum(int(r["xcheck_compared"]) for r in rows),
        "xcheck_divergence": sum(int(r["xcheck_divergence"]) for r in rows),
        "xcheck_error": sum(int(r["xcheck_error"]) for r in rows),
        "per_spec": per_spec,
        "rejudged_instances": checked,
        "rejudge_mismatches": len(miss) + len(extra),
    }
    json.dump(summary, open(os.path.join(HERE, "out", "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("\nall checks agree")


if __name__ == "__main__":
    main()
