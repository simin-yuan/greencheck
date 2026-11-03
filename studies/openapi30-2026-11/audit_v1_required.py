#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit of the v1 headline claim: "none of the 91 entry schemas declares required".

Two readings are counted separately, because they answer different questions:

  root-level   required visible on the entry schema's own object node after
               resolving $ref and folding allOf/anyOf/oneOf at that level — this is
               what decides whether a missing property can be caught;
  anywhere     any `required` anywhere in the resolved tree, at any depth.

Also prints three verbatim excerpts straight from the spec files (not reserialised),
and the judge's identity + version so the report can state what actually judged.

    python audit_v1_required.py
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = os.environ.get("V1_DIR") or "<redacted-abs-path>"
sys.path.insert(0, V1)
sys.path.insert(0, "<redacted-abs-path>")
from study import CLI, branches, resolve                        # noqa: E402


def walk(node, root, path="", depth=0, seen=None):
    """Every `required` in the resolved tree, with its path."""
    out = []
    if seen is None:
        seen = set()
    if depth > 12:
        return out
    n, _o = resolve(node, root)
    if not isinstance(n, dict) or id(n) in seen:
        return out
    seen.add(id(n))
    if isinstance(n.get("required"), list) and n["required"]:
        out.append((path or "/", n["required"]))
    for kw in ("properties", "patternProperties", "items", "additionalProperties",
               "allOf", "anyOf", "oneOf", "not"):
        sub = n.get(kw)
        if isinstance(sub, dict):
            for k, v in sub.items():
                out.extend(walk(v, root, f"{path}/{kw}/{k}", depth + 1, seen))
        elif isinstance(sub, list):
            for i, v in enumerate(sub):
                out.extend(walk(v, root, f"{path}/{kw}/{i}", depth + 1, seen))
    return out


def raw_excerpt(text, name):
    """Verbatim slice of the spec file around "components/schemas/<name>", one line."""
    i = text.find(f'"{name}"')
    return text[i:i + 320] if i >= 0 else "<not found>"


def main():
    sample = json.load(open(os.path.join(V1, "out", "sample.json"), encoding="utf-8"))
    rows = list(csv.DictReader(open(os.path.join(V1, "out", "cases.csv"), encoding="utf-8")))
    ver = subprocess.run([CLI, "--version"], capture_output=True, text=True).stdout.strip()

    root_req, deeper_req, none = [], [], []
    for r in rows:
        p = next(s["path"] for s in sample["specs"] if s["name"] == r["spec"])
        doc = json.load(open(os.path.join(V1, p), encoding="utf-8"))
        sch = doc["components"]["schemas"][r["schema"]]
        at_root = [x for b, _o in branches(sch, doc) for x in (b.get("required") or []) if isinstance(b, dict)]
        deep = walk(sch, doc)
        if at_root:
            root_req.append((r["spec"], r["schema"], at_root))
        elif deep:
            deeper_req.append((r["spec"], r["schema"], deep))
        else:
            none.append((r["spec"], r["schema"]))

    print(f"judge: {CLI}")
    print(f"judge version: {ver}")
    print(f"cases: {len(rows)}")
    print(f"required on the root object node: {len(root_req)}")
    print(f"required only deeper in the tree:  {len(deeper_req)}")
    print(f"no required anywhere:              {len(none)}")
    for spec, name, req in root_req[:10]:
        print(f"  ROOT  {spec} / {name}: {req}")
    for spec, name, deep in deeper_req[:10]:
        print(f"  DEEP  {spec} / {name}: {[d[1] for d in deep][:3]}")

    print("\n--- verbatim excerpts")
    shown = 0
    for spec, name in (root_req or none):
        p = next(s["path"] for s in sample["specs"] if s["name"] == spec)
        text = open(os.path.join(V1, p), encoding="utf-8").read()
        print(f"[{spec} / {name}]\n{raw_excerpt(text, name)}\n")
        shown += 1
        if shown == 3:
            break

    json.dump({"judge": CLI, "version": ver, "cases": len(rows),
               "required_root": len(root_req), "required_deeper": len(deeper_req),
               "required_none": len(none),
               "root_list": [[s, n, q] for s, n, q in root_req],
               "deep_list": [[s, n, [[d[0], d[1]] for d in ds]] for s, n, ds in deeper_req]},
              open(os.path.join(HERE, "out", "audit_v1_required.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    main()
