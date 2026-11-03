#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, unedited, every field the article quotes from x16_merged_basis.json.

The article's §7 numbers previously came from x12_annotation_basis.json, whose
"needs an annotation" population is 932; the article's other numbers come from
x16, whose population is 883. Two denominators in one article is the failure this
file exists to prevent. Everything below is read from x16 and printed as-is.

    python x16_numbers.py        # -> x16_numbers.out
"""
from __future__ import annotations

import json
import os
import sys

X16 = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                   "schemastore-2026-10", "out", "x16_merged_basis.json")


def main() -> int:
    s = json.load(open(X16, encoding="utf-8"))["summary"]

    pop = s["population"]
    print("population")
    for k in ("escaped_mutants", "already_expressed", "needs_annotation",
              "coverable", "unreachable", "unreachable_by_reason", "schemas", "write_sites"):
        print(f"  {k:24} {json.dumps(pop[k], ensure_ascii=False)}")

    print("\nclasses")
    for name, c in s["classes"].items():
        print(f"  {name:18} escapes={c['escapes']}  keyword={c['keyword']}  "
              f"composition={json.dumps(c.get('composition'), ensure_ascii=False)}")

    sh = s["sites_to_half"]
    print("\nsites_to_half")
    for k in ("unit", "n_schemas_with_needed_escapes", "n_reaching_half",
              "min", "q1", "median", "q3", "max", "distribution", "estimator"):
        print(f"  {k:32} {json.dumps(sh[k], ensure_ascii=False)}")
    print(f"  schemas_without_needed_escapes  {json.dumps(s['schemas_without_needed_escapes'], ensure_ascii=False)}")

    bw = s["by_write_site"]
    print("\nby_write_site")
    print(f"  annotation_acts_total      {bw['annotation_acts_total']}")
    print(f"  annotated_nodes_total      {bw['annotated_nodes_total']}")
    print(f"  acts_covering_exactly_one  {bw['acts_covering_exactly_one']}")
    print(f"  largest_single_act         {json.dumps(bw['largest_single_act'], ensure_ascii=False)}")
    for n in ("1", "10", "20", "50"):
        c = bw["annotation_acts"]["cumulative_at"].get(n)
        if c:
            print(f"  cumulative_at[{n:>2}]         {json.dumps(c, ensure_ascii=False)}")

    bi = s["by_instance_path"]
    print("\nby_instance_path")
    print(f"  annotation_acts_total      {bi['annotation_acts_total']}")
    print(f"  largest_single_act         {json.dumps(bi['largest_single_act'], ensure_ascii=False)}")
    for n in ("10", "20", "50"):
        c = bi["annotation_acts"]["cumulative_at"].get(n)
        if c:
            print(f"  cumulative_at[{n:>2}]         {json.dumps(c, ensure_ascii=False)}")

    # the three identities the article leans on
    print("\nidentities")
    print(f"  already_expressed + needs_annotation = {pop['already_expressed'] + pop['needs_annotation']}"
          f"  (escaped_mutants {pop['escaped_mutants']})")
    print(f"  classes: {s['classes']['already-expressed']['escapes']} + "
          f"{s['classes']['undeclared-key']['escapes']} + {s['classes']['unconstrained-value']['escapes'] if 'unconstrained-value' in s['classes'] else '?'}")
    print(f"  needs_annotation - unreachable = {pop['needs_annotation'] - pop['unreachable']}  "
          f"(coverable {pop['coverable']})")
    print(f"  escaped - unreachable = {pop['escaped_mutants'] - pop['unreachable']}  "
          f"(= 499 already stated + 818 annotated)")
    ok = (pop["already_expressed"] + pop["needs_annotation"] == pop["escaped_mutants"]
          and pop["needs_annotation"] - pop["unreachable"] == pop["coverable"]
          and pop["already_expressed"] + pop["needs_annotation"] - pop["unreachable"]
              == pop["escaped_mutants"] - pop["unreachable"])
    print("  all hold" if ok else "  MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
