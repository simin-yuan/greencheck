#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static statistics for the "base class deliberately left open" question.

No mutation operators are added here. This only reads the schemas.

Scope A — the 85 entry schemas the mutation ran on: how many inherit a base via their own allOf.
Scope B — every component schema in the 20 sampled documents, because scope A comes out empty:
          the base-class question has to be asked of the documents, not of the corpus.
Scope C — the lint-shaped question: object schemas that declare properties but never say which
          are required, counted per document, because a rule would run per document.

    python static_stats.py
"""
from __future__ import annotations

import csv
import json
import os
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "schemastore-2026-10"))
from study import CP, branches, resolve, required_of                # noqa: E402


def allof_base_refs(node, doc):
    """Component names referenced from this node's own allOf arms."""
    out = []
    for b, _o in branches(node, doc):
        if not isinstance(b, dict):
            continue
        for arm in b.get("allOf") or []:
            if isinstance(arm, dict) and isinstance(arm.get("$ref"), str) \
                    and arm["$ref"].startswith(CP):
                out.append(arm["$ref"][len(CP):])
    return sorted(set(out))


def ap_kind(node, doc):
    vals = []
    for b, _o in branches(node, doc):
        if isinstance(b, dict) and "additionalProperties" in b:
            vals.append(b["additionalProperties"])
    if not vals:
        return "absent"
    if any(v is False for v in vals):
        return "false"
    if any(isinstance(v, dict) for v in vals):
        return "schema"
    if any(v is True for v in vals):
        return "true"
    return "other"


def has_properties(node, doc):
    for b, _o in branches(node, doc):
        if isinstance(b, dict) and b.get("properties"):
            return True
    return False


def main():
    sample = json.load(open(os.path.join(HERE, "out", "sample.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(HERE, "out", "cases.csv"), encoding="utf-8")))
    docs = {}
    for s in sample["specs"]:
        docs[s["name"]] = json.load(open(os.path.join(HERE, s["path"]), encoding="utf-8"))

    # Scope A
    a_inherit = []
    for r in rows:
        doc = docs[r["spec"]]
        sch = doc["components"]["schemas"][r["schema"]]
        refs = allof_base_refs(sch, doc)
        if refs:
            a_inherit.append((r["spec"], r["schema"], refs))
    print("== A. the corpus the mutation ran on")
    print(f"entry schemas: {len(rows)}")
    print(f"entry schemas whose own allOf references a component base: {len(a_inherit)}")
    for s, n, refs in a_inherit[:8]:
        print(f"  {s} / {n} -> {refs}")

    # Scope B
    bases = {}
    allof_schemas = 0
    for name, doc in docs.items():
        schemas = ((doc.get("components") or {}).get("schemas") or {})
        for sname, node in schemas.items():
            if not isinstance(node, dict):
                continue
            if "allOf" in node:
                allof_schemas += 1
            for b in allof_base_refs(node, doc):
                tgt = schemas.get(b)
                if tgt is None:
                    continue
                bases[(name, b)] = {
                    "ap": ap_kind(tgt, doc),
                    "props": has_properties(tgt, doc),
                    "req": bool(required_of(tgt, doc)),
                }
    kinds = Counter(v["ap"] for v in bases.values())
    print("\n== B. all 20 documents, every component schema")
    print(f"component schemas using allOf: {allof_schemas}")
    print(f"distinct base schemas reached through allOf: {len(bases)}")
    print("additionalProperties on those bases:")
    for k in ("absent", "true", "schema", "false", "other"):
        if kinds.get(k):
            print(f"  {k:<8} {kinds.get(k, 0)}")
    print(f"bases declaring properties: {sum(1 for v in bases.values() if v['props'])}")
    print(f"bases declaring required:   {sum(1 for v in bases.values() if v['req'])}")

    # Scope C
    tot = with_props = props_no_req = props_no_req_allof = 0
    per_doc = {}
    for name, doc in docs.items():
        schemas = ((doc.get("components") or {}).get("schemas") or {})
        d_tot = d_hit = 0
        for sname, node in schemas.items():
            if not isinstance(node, dict):
                continue
            tot += 1
            d_tot += 1
            hp = has_properties(node, doc)
            if hp:
                with_props += 1
            if hp and not required_of(node, doc):
                props_no_req += 1
                d_hit += 1
                if "allOf" in node:
                    props_no_req_allof += 1
        per_doc[name] = {"schemas": d_tot, "props_no_required": d_hit}
    print("\n== C. object schemas that never say which properties are required")
    print(f"component schemas: {tot}")
    print(f"declare properties (own or via allOf): {with_props}")
    print(f"declare properties and no required at all: {props_no_req}"
          f"  ({props_no_req / tot:.1%} of all component schemas)")
    print(f"  of which composite (allOf): {props_no_req_allof}")
    for name, v in sorted(per_doc.items(), key=lambda kv: -kv[1]["props_no_required"])[:8]:
        print(f"  {name[:44]:<44} {v['props_no_required']:4d} / {v['schemas']:4d}")

    json.dump({"A": {"entry_schemas": len(rows), "with_allof_base": len(a_inherit)},
               "B": {"allof_schemas": allof_schemas, "distinct_bases": len(bases),
                     "additionalProperties": dict(kinds),
                     "bases_with_properties": sum(1 for v in bases.values() if v["props"]),
                     "bases_with_required": sum(1 for v in bases.values() if v["req"])},
               "C": {"component_schemas": tot, "with_properties": with_props,
                     "properties_without_required": props_no_req,
                     "share": props_no_req / tot if tot else 0,
                     "of_which_allof": props_no_req_allof,
                     "per_doc": per_doc}},
              open(os.path.join(HERE, "out", "bases.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
