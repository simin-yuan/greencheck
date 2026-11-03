#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x3_positions.py — per-mutant schema position + Sourcemeta lint coverage.

Ruling (2026-10-11): the annotator ALWAYS had per-item location ability
(annotate.py::diff / schema_at); what was missing was that the intermediate result
was never stored. So this script imports annotate.py UNCHANGED, reproduces the
frozen stratification, and only then emits positions.

Gate kept by this script (a hard gate, not a warning):
  * annotate.py sha256 must equal ANNOT_SHA below (recorded before any output).
  * re-aggregated CI strata must equal out/strata_ci.json, label by label.
    Any single mismatch -> stop, print the diff, write nothing.

Outputs (write-once): out/x3_positions.json
"""
from __future__ import annotations
import collections
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ANNOT_SHA = "5212471b6b6237069872deefe4dcb492b8bac163adadadfaa7fbc2b75e1128ca"
LINT_JSONL_CANDIDATES = [
    os.path.join(os.environ.get("TMPDIR") or "", "x3_lint_raw.jsonl"),
    r"<redacted-abs-path>",
    os.path.join(HERE, "out", "x3_lint_raw.jsonl"),
]


def find_lint_jsonl():
    for p in LINT_JSONL_CANDIDATES:
        if p and os.path.exists(p):
            return p
    raise SystemExit("STOP: x3_lint_raw.jsonl not found at any of "
                     + " | ".join(repr(p) for p in LINT_JSONL_CANDIDATES))


LINT_JSONL = None                  # resolved in main(), never silently empty

import annotate as A               # UNCHANGED — hash-checked below
from onceio import write_once


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def lint_findings(sch, idx2sch):
    """Rule id -> set of schema-node ids flagged (pointer node, or its container
    when the pointer lands on a scalar). Top-level rules (empty pointer) are
    excluded: they carry no position and would otherwise match everything."""
    if not LINT_JSONL:
        raise SystemExit("STOP: lint input not resolved (refusing to report zero coverage)")
    exact = collections.defaultdict(set)
    n = 0
    for line in open(LINT_JSONL, encoding="utf-8"):
        r = json.loads(line)
        if r["rc"] != 2:
            continue
        root = sch.get(idx2sch.get(r["pair"]))
        if root is None:
            continue
        for e in json.loads(r["out"]).get("errors", []):
            loc = e.get("schemaLocation") or []
            if not loc:
                continue
            node = walk(root, loc)
            if node is None:
                continue
            n += 1
            if isinstance(node, (dict, list)):
                exact[id(node)].add(e["id"])
            else:
                parent = walk(root, loc[:-1])
                if isinstance(parent, (dict, list)):
                    exact[id(parent)].add(e["id"])
    return exact, n


def walk(root, loc):
    node = root
    for st in loc:
        if isinstance(node, dict) and st in node:
            node = node[st]
        elif isinstance(node, list) and isinstance(st, int) and 0 <= st < len(node):
            node = node[st]
        else:
            return None
    return node


def subtree(n, seen=None):
    seen = set() if seen is None else seen
    if id(n) in seen:
        return
    seen.add(id(n))
    yield n
    if isinstance(n, dict):
        for v in n.values():
            yield from subtree(v, seen)
    elif isinstance(n, list):
        for v in n:
            yield from subtree(v, seen)


def main():
    global LINT_JSONL
    LINT_JSONL = find_lint_jsonl()
    print("lint input         :", LINT_JSONL)
    got = sha256(os.path.join(HERE, "annotate.py"))
    print("annotate.py sha256 :", got)
    if got != ANNOT_SHA:
        raise SystemExit("STOP: annotate.py changed since it was recorded "
                         f"(expected {ANNOT_SHA})")

    res = json.load(open(os.path.join(HERE, "out", "results.json"), encoding="utf-8"))
    rows = [r for r in res["rows"] if r.get("mutants_total")]
    ci = json.load(open(os.path.join(HERE, "out", "_xcheck_ci", "ajv.json"),
                       encoding="utf-8"))["results"]
    frozen = json.load(open(os.path.join(HERE, "out", "strata_ci.json"), encoding="utf-8"))

    items, cnt = [], collections.Counter()
    for r in rows:
        inst_path = os.path.join(A.REPO, r["instance"].replace("/", os.sep))
        txt = open(inst_path, encoding="utf-8").read()
        orig = json.loads(txt)
        schema = json.load(open(os.path.join(A.SCHEMAS, r["schema"]), encoding="utf-8"))
        for name, patch in A.gm.build_mutants({"instance.json": txt}):
            content = next(iter(patch.values()))
            if content is None:
                continue
            try:
                mut = json.loads(content)
            except Exception:
                continue
            if ci.get(r["schema"], {}).get(name) != "release":
                continue                       # not released by the CI gate
            if mut == orig:
                cnt["no_op"] += 1
                continue
            changes = [c for c in A.diff(orig, mut)
                       if c[1] in ("removed", "changed", "arrayshrunk", "added")]
            if not changes:
                p, kind, label = None, None, "no-detectable-change"
            else:
                changes.sort(key=lambda c: (len(c[0]), str(c[0])))
                p, kind = changes[0]
                try:
                    o = A.value_at(orig, p) if kind != "removed" else None
                except Exception:
                    o = None
                m = A.value_at(mut, p) if kind != "removed" else None
                label = A.classify(schema, p, kind, o, m)
            # the one layer classify() does not carry: nothing declared at that path
            node = A.schema_at(schema, tuple(p)) if p else None
            if node is A.UNRESOLVED:
                node = None
            if p and node is None:
                label = "UNDECLARED-KEY"
            items.append({
                "pair": r["schema"], "instance": r["instance"], "name": name,
                "op": name.split(":", 1)[0], "kind": kind,
                "path": list(p) if p is not None else None,
                "label": label, "schema_node_found": node is not None,
            })
            cnt[label] += 1

    # ---- HARD GATE: re-aggregated strata must equal the frozen ones ----
    live = collections.Counter(i["label"] for i in items)
    want = frozen["strata"]
    bad = {k: [live.get(k, 0), want.get(k, 0)] for k in set(live) | set(want)
           if live.get(k, 0) != want.get(k, 0)}
    if bad:
        print("STOP: re-aggregated strata != out/strata_ci.json")
        for k, v in bad.items():
            print(f"   {k!r}: mapped={v[0]} frozen={v[1]}")
        raise SystemExit(1)
    if live.get("UNDECLARED-KEY", 0) != frozen["undeclared_key"]:
        raise SystemExit("STOP: UNDECLARED-KEY total != strata_ci.undeclared_key")
    print(f"gate OK: {len(items)} items, {len(live)} strata, "
          f"all equal to out/strata_ci.json (ci_released={frozen['ci_released']})")

    # ---- lint coverage ----
    idx2sch = {}
    for i in range(38):
        pd = json.load(open(os.path.join(HERE, "out", "_xcheck", f"p{i}.json"),
                            encoding="utf-8"))
        idx2sch[i] = pd["schema"]
    names = {i["pair"] for i in items}
    sch = {p: json.load(open(os.path.join(A.SCHEMAS, p), encoding="utf-8")) for p in names}
    exact, n_find = lint_findings(sch, idx2sch)

    cov = collections.Counter()
    by_rule_exact, by_rule_below = collections.Counter(), collections.Counter()
    for it in items:
        root = sch[it["pair"]]
        p = it["path"]
        node = A.schema_at(root, tuple(p)) if p else None
        node = None if node is A.UNRESOLVED else node
        rex = set(exact.get(id(node), ())) if node is not None else set()
        rbelow = set()
        if node is not None:
            for nd in subtree(node):
                rbelow |= exact.get(id(nd), set())
        it["lint_exact"] = sorted(rex)
        it["lint_at_or_below"] = sorted(rbelow)
        cov["exact" if rex else "not_exact"] += 1
        cov["below" if rbelow else "not_below"] += 1
        if it["label"] == "UNDECLARED-KEY":
            cov["undec_exact" if rex else "undec_not_exact"] += 1
        for x in rex:
            by_rule_exact[x] += 1
        for x in rbelow:
            by_rule_below[x] += 1

    n = len(items)
    summary = {
        "population": {"ci_released": frozen["ci_released"], "mapped_items": n,
                       "no_op": cnt.get("no_op", 0)},
        "gate": {"annotate_py_sha256": got, "annot_py_unchanged": True,
                 "strata_equal_to_strata_ci": True, "strata_labels": len(live)},
        "lint_findings_with_position": n_find,
        "coverage": {
            "lint_flags_the_same_node": cov["exact"],
            "lint_flags_nothing_at_that_node": cov["not_exact"],
            "lint_flags_the_same_node_ratio": round(cov["exact"] / n, 6),
            "lint_flags_node_or_below": cov["below"],
            "lint_flags_nothing_node_or_below": cov["not_below"],
            "lint_flags_node_or_below_ratio": round(cov["below"] / n, 6),
        },
        "by_rule_exact": dict(by_rule_exact.most_common()),
        "by_rule_at_or_below": dict(by_rule_below.most_common()),
        "undeclared_key": {"total": live["UNDECLARED-KEY"],
                           "lint_flags_the_same_node": cov["undec_exact"],
                           "lint_flags_nothing": cov["undec_not_exact"],
                           "reading": "a key that no schema keyword declares has no "
                                      "schema position for lint to point at"},
        "reading": {
            "what_this_is": "Sourcemeta's OWN rule set, applied to the schemas that "
                            "produced these escapes",
            "what_this_is_not": "independent evidence about the escapes — lint and "
                                "validate share an implementation (Appendix B §B.9)",
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    write_once(os.path.join(HERE, "out", "x3_positions.json"),
               {"summary": summary, "items": items})
    print("wrote out/x3_positions.json (write-once)")


if __name__ == "__main__":
    main()
