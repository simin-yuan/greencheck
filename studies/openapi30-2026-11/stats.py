#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every number the report quotes, printed from the artifacts (never typed by hand)."""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "schemastore-2026-10"))
import greencheck.mutate as gm                                   # noqa: E402
from study import build_cases, constraints, required_of           # noqa: E402


def main():
    sample = json.load(open(os.path.join(HERE, "out", "sample.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(HERE, "out", "cases.csv"), encoding="utf-8")))
    esc = [json.loads(l) for l in open(os.path.join(HERE, "out", "escapes.jsonl"), encoding="utf-8")]
    summ = json.load(open(os.path.join(HERE, "out", "summary.json"), encoding="utf-8"))
    cases = build_cases(sample)

    file_ops = sum(1 for c in cases
                   for name, patch in gm.build_mutants({"i": c["text"]})
                   if name.split(":")[0] in ("drop-file", "empty-file"))
    doc_parse_broken = summ["parse_broken"] - file_ops

    intent = Counter()
    for r in rows:
        doc = json.load(open(next(s["path"] for s in sample["specs"] if s["name"] == r["spec"]), encoding="utf-8"))
        sch = doc["components"]["schemas"][r["schema"]]
        kws = [k for k, _ in constraints(sch, doc)]
        intent["schemas"] += 1
        intent["required (any branch)"] += bool(required_of(sch, doc))
        intent["enum/const"] += ("enum" in kws or "const" in kws)
        intent["minLength/maxLength/pattern"] += any(k in kws for k in ("minLength", "maxLength", "pattern"))
        intent["its own properties"] += bool(sch.get("properties"))

    vacuous = [r for r in rows if int(r["escaped"]) and int(r["escaped"]) == int(r["escaped"]) + int(r["schema_rejected"])]
    judged_cases = [r for r in rows if int(r["escaped"]) + int(r["schema_rejected"]) > 0]

    print("== baseline (example against its own schema)")
    for k, v in Counter(r["baseline"] for r in rows).most_common():
        print(f"{k:14} {v}")
    broken = sorted({r["spec"] for r in rows if r["baseline"] == "ENGINE-ERROR"})
    print(f"documents the CLI refused to read at all: {len(broken)} -> {broken}")

    print("\n== headline")
    for k in ("specs_sampled", "specs_contributing_cases", "cases", "baseline", "mutants",
              "parse_broken", "parse_broken_share", "judged", "escaped", "schema_rejected",
              "engine_error", "escape_rate_pooled", "escape_rate_median_case", "cases_with_judged",
              "classes", "allof_base_escapes", "allof_base_share", "xcheck_compared",
              "xcheck_divergence", "xcheck_error"):
        print(f"{k:28} {summ[k]}")

    print("\n== parse-broken split")
    print(f"file-level (drop-file / empty-file)  {file_ops}")
    print(f"json syntax broken by drop-line      {doc_parse_broken}")

    print("\n== intent density of the entry schemas")
    for k, v in intent.items():
        print(f"{k:28} {v}")

    print("\n== cases where every judged mutant escaped")
    print(f"{len(vacuous)} of {len(judged_cases)} cases with a judged mutant")

    print("\n== per spec")
    for spec, d in sorted(summ["per_spec"].items(), key=lambda kv: -kv[1]["judged"]):
        rate = d["escaped"] / d["judged"] if d["judged"] else float("nan")
        print(f"{spec[:44]:<44} cases={d['cases']:3d} judged={d['judged']:4d} esc={d['escaped']:4d} rate={rate:.3f}")

    print("\n== example escape rows by class")
    seen = set()
    for e in esc:
        if e["class"] == "DIVERGENCE" or e["class"] in seen:
            continue
        seen.add(e["class"])
        print(f"{e['class']:<26} {e['spec']} / {e['schema']} / {'/'.join(map(str, e['path']))} ({e['detail']})")


if __name__ == "__main__":
    main()
