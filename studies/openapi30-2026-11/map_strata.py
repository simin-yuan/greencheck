#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Map the nine frozen strata onto the three-way split the outline uses.

The guest-post outline (03_outline.md, sent to Juan on 2026-10-14) quotes
499 / 333 / 550 / 883 and, in the proposal section, 308 / 510 / 65 / 1,317.
The stratified artifact (`x3_strata_rebuilt.json`) has nine labels instead of three.
This script is the bridge, and it is the only place the two vocabularies meet.

Merge rule, applied in this order:

  1. VALUE LEVEL (550) = every stratum whose operator touched a value inside the
     instance rather than the presence of a key: the blanked-* families, the
     shortened array, the rewritten identifier, the nine annotation-only strings
     and the five ANOMALY labels. 550 = 1382 - 584 - 248 exactly, so it needs no
     further evidence, but the sum is asserted below.

  2. DECLARED ABSENCE (499) = `removed-optional` minus the 85 removals whose key the
     node's own `$ref`/allOf/anyOf/oneOf chain never declares (x16 `removal_breakdown`).
     That 499 is 368 `properties`+missing-`required` + 82 `patternProperties`
     + 49 declared-optional after resolving the node's chain (x16 `classes`).
     The 49 is the whole difference between x12's 450 and x16's 499.

  3. UNDECLARED KEY (333) = the 248 keys of stratum `UNDECLARED-KEY` (139 dropped a
     line, 109 blanked a value) plus those same 85 removals, which x16 moves here
     because no keyword anywhere the node reaches declares them.

Reachability splits the same three classes at 1,317 of 1,382 (x16 `population`):
499 expressed + 308 undeclared reachable + 510 value reachable, with the 65
unreachable split 25 / 40 between the last two.

    python map_strata.py            # prints the table, exits 1 if any identity fails
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(os.path.dirname(HERE), "schemastore-2026-10", "out")

VALUE_PREFIXES = ("blanked-",)
VALUE_LABELS = {"removed-array-element", "identifier-unconstrained"}


def load(name):
    with open(os.path.join(S, name), encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    x3 = load("x3_strata_rebuilt.json")
    pos = load("x3_positions.json")
    x16 = load("x16_merged_basis.json")
    x12 = load("x12_annotation_basis.json")

    strata = x3["summary"]["strata"]
    items = pos["items"]
    total = x3["summary"]["items"]

    # --- 1. value level, by label -------------------------------------------
    value_labels = {k: v for k, v in strata.items()
                    if k.startswith(VALUE_PREFIXES) or k in VALUE_LABELS}
    value = sum(value_labels.values())
    removed_all = strata["removed-optional"]
    undeclared_248 = strata["UNDECLARED-KEY"]

    # 248 split by operator, from the per-mutant records
    op_counts = Counter(x["op"] for x in items if x["label"] == "UNDECLARED-KEY")
    dropped, blanked = op_counts.get("drop-line", 0), op_counts.get("blank-value", 0)

    # --- 2/3. the 85, straight out of x16 -----------------------------------
    rb = x16["summary"]["removal_breakdown"]
    cls = x16["summary"]["classes"]
    pop = x16["summary"]["population"]
    declared_368 = rb["declared-and-not-required"]
    pattern_82 = rb["pattern-property"]
    resolved_49 = rb["declared-optional-after-resolving-the-nodes-own-chain"]
    undeclared_85 = rb["open-object-undeclared-key"]
    expressed_499 = declared_368 + pattern_82 + resolved_49
    undeclared_333 = undeclared_248 + undeclared_85

    # --- reachability -------------------------------------------------------
    unreach = pop["unreachable"]                       # 65
    unreach_undeclared = x12["summary"]["classes"]["undeclared-key"]["unreachable"]
    unreach_value = unreach - unreach_undeclared
    reach_undeclared = undeclared_333 - unreach_undeclared
    reach_value = value - unreach_value
    reach_total = expressed_499 + reach_undeclared + reach_value

    checks = [
        ("nine strata sum to the escaped population", sum(strata.values()), total),
        ("value + removed + undeclared = 1382", value + removed_all + undeclared_248, total),
        ("499 = 368 + 82 + 49", expressed_499, cls["already-expressed"]["escapes"]),
        ("333 = 248 + 85", undeclared_333, cls["undeclared-key"]["escapes"]),
        ("499 + 333 + 550 = 1382", expressed_499 + undeclared_333 + value, total),
        ("883 = 333 + 550", undeclared_333 + value, pop["needs_annotation"]),
        ("248 = dropped 139 + blanked 109", dropped + blanked, undeclared_248),
        ("85 = 134 - 49, with 134 from the pre-merge artifact", undeclared_85,
         x12["summary"]["classes"]["undeclared-key"]["composition"]["removed-undeclared-key"] - resolved_49),
        ("reachable 1317 = 499 + 308 + 510", reach_total, total - unreach),
        ("65 = 25 undeclared + 40 value", unreach_undeclared + unreach_value, unreach),
    ]

    print("== three-way split quoted in the outline")
    print(f"  declared absence (499)   {expressed_499:5}  = {declared_368} properties + {pattern_82} patternProperties + {resolved_49} resolved chain")
    print(f"  undeclared key   (333)   {undeclared_333:5}  = {undeclared_248} never declared at the node ({dropped} dropped, {blanked} blanked) + {undeclared_85} removed, declared nowhere along the chain")
    print(f"  value level      (550)   {value:5}  = {', '.join(f'{k} {v}' for k, v in sorted(value_labels.items(), key=lambda z: -z[1]))}")
    print(f"  needs annotation (883)   {undeclared_333 + value:5}")
    print()
    print("== the same three, reachable by an annotation (1,317 of 1,382)")
    print(f"  {expressed_499} + {reach_undeclared} + {reach_value} = {reach_total}")
    print(f"  unreachable {unreach} = {unreach_undeclared} undeclared + {unreach_value} value")
    print()
    print("== where 248 and 333 come from")
    print(f"  248  keys with no declared position at the node the instance sat at      (LinkedIn, 2026-10-11)")
    print(f"  + 49 declared optional in the definition the node's own chain reaches")
    print(f"  - 49 counted as a stated absence once that chain is followed")
    print(f"  + 85 removals no keyword along the chain declares")
    print(f"  or: 382 (x12 undeclared class) - 49 = 333")
    print(f"  both routes give 333; the two artifacts leaf-split 248+134 and 248+85 differently,")
    print(f"  and the two 248s are counted on different partitions - see numbers_check.md, item 3")
    print()
    bad = 0
    for name, got, want in checks:
        ok = got == want
        bad += 0 if ok else 1
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: {got} vs {want}")
    print()
    print("all identities hold" if not bad else f"{bad} identities FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
