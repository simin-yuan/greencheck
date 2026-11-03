#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Annotate every RELEASED mutant with the *schema-side* reason it slipped through.

Why: the escape rate alone answers "which probe fires most", not "which gap in
the schema is most common". This pass re-derives each escaped mutant in-process,
diffs it against the original instance to find the changed location, resolves the
applicable schema node for that location (properties/items/$ref/allOf), and asks
which schema-side constraint was absent.

Categories (schema-side):
  removed-optional            a property line was deleted; the key is not required
  removed-required (ANOMALY)  a required key was deleted yet still accepted
  removed-array-element       an array element was deleted; no minItems
  blanked-annotation-string   emptied a description/title/default/... (pure metadata)
  blanked-string-unconstrained emptied a string with no minLength/pattern/enum/format
  blanked-string-constrained (ANOMALY) emptied a constrained string, still accepted
  blanked-number-unconstrained number -> 0, no minimum/enum/const
  blanked-bool-unconstrained   true -> false, no const/enum
  identifier-unconstrained     break-ref changed a token; no enum/const/pattern
  identifier-constrained (ANOMALY)
  other / unresolved

ANOMALY = the schema *did* carry a keyword that should have caught it; those are
the only rows that can be called probable gaps without a consumer.
"""
from __future__ import annotations
import json
import os
import re
import sys
import collections

UNRESOLVED = object()   # a $ref we could not resolve offline (≠ "no schema applies")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "repo")
SCHEMAS = os.path.join(REPO, "src", "schemas", "json")
sys.path.insert(0, HERE)


def _greencheck():
    for c in (os.environ.get("GREENCHECK_REPO"), "<redacted-abs-path>",
              os.path.join(HERE, "greencheck")):
        if c and os.path.isfile(os.path.join(c, "greencheck", "mutate.py")):
            return c
    raise SystemExit("greencheck not found")


sys.path.insert(0, _greencheck())
import greencheck.mutate as gm  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("gate_json", os.path.join(HERE, "gate_json.py"))
gj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gj)

ANNOT = {"description", "title", "$comment", "comment", "default", "examples", "$schema"}
STR_CONSTRAINT = {"minLength", "enum", "const", "pattern", "format"}
NUM_CONSTRAINT = {"minimum", "exclusiveMinimum", "multipleOf", "enum", "const"}
BOOL_CONSTRAINT = {"const", "enum"}


# ---- structural diff ------------------------------------------------------

def diff(orig, mut, path=()):
    if isinstance(orig, dict) and isinstance(mut, dict):
        for k in orig:
            if k not in mut:
                yield (path + (k,), "removed")
            else:
                yield from diff(orig[k], mut[k], path + (k,))
        for k in mut:
            if k not in orig:
                yield (path + (k,), "added")
    elif isinstance(orig, list) and isinstance(mut, list):
        if len(mut) < len(orig):
            yield (path, "arrayshrunk")
        elif len(mut) == len(orig):
            for i, (a, b) in enumerate(zip(orig, mut)):
                yield from diff(a, b, path + (i,))
    else:
        if orig != mut:
            yield (path, "changed")


def value_at(inst, path):
    node = inst
    for s in path:
        node = node[s]
    return node


# ---- schema navigation ----------------------------------------------------

def deref(node, root, depth=0):
    """Resolve `#/...` $refs and KEEP sibling keywords. draft-07 says a $ref
    replaces its siblings, but for the question asked here ("did the schema
    declare anything that could have caught this?") keeping them is strictly
    more informative and never loses a constraint."""
    if not isinstance(node, dict) or depth > 12:
        return node
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str):
            return UNRESOLVED
        if not ref.startswith("#/"):
            return UNRESOLVED             # external / file $ref: unresolvable offline
        tgt = root
        try:
            for part in ref[2:].split("/"):
                tgt = tgt[part.replace("~1", "/").replace("~0", "~")]
        except Exception:
            return UNRESOLVED
        resolved = deref(tgt, root, depth + 1)
        sib = {k: v for k, v in node.items() if k != "$ref"}
        if sib and isinstance(resolved, dict):
            merged = dict(resolved)
            merged.update(sib)
            return merged
        return resolved
    return node


def branches(node, root, depth=0):
    """Every schema object constraining this node: the node itself plus all
    allOf / anyOf / oneOf branches. anyOf/oneOf are included because the
    question is "could the schema have caught this", not "must it have"."""
    node = deref(node, root)
    if not isinstance(node, dict) or depth > 8:
        return []
    out = [node]
    for kw in ("allOf", "anyOf", "oneOf"):
        for sub in node.get(kw) or []:
            out.extend(branches(sub, root, depth + 1))
    return out


def has_kw(node, kw, root):
    return any(kw in b for b in branches(node, root))


def has_any(node, kws, root):
    return any(kw in b for b in branches(node, root) for kw in kws)


def required_of(node, root):
    out = set()
    for b in branches(node, root):
        r = b.get("required")
        if isinstance(r, list):
            out |= set(r)
    return out


def child(node, step, root):
    """Descend one instance-path step. Handles properties, patternProperties
    (regex keyed maps like `^\\d+$`), items (schema *or* tuple form) and
    additionalProperties; when several branches match, their union is returned
    so no constraint is lost. patternProperties was the missing piece that made
    `schema_at` return None on nested maps."""
    cands = []
    for b in branches(node, root):
        props = b.get("properties")
        if isinstance(step, str) and isinstance(props, dict) and step in props:
            cands.append(deref(props[step], root))
            continue
        if isinstance(step, str):
            pp = b.get("patternProperties")
            if isinstance(pp, dict):
                hit = False
                for pat, sub in pp.items():
                    try:
                        if re.search(pat, step):
                            cands.append(deref(sub, root))
                            hit = True
                    except re.error:
                        pass
                if hit:
                    continue
        if isinstance(step, int):
            it = b.get("items")
            if isinstance(it, dict):
                cands.append(deref(it, root))
                continue
            if isinstance(it, list) and 0 <= step < len(it):
                cands.append(deref(it[step], root))
                continue
    cands = [c for c in cands if c is not None]
    if any(c is UNRESOLVED for c in cands):
        return UNRESOLVED
    if not cands and isinstance(step, str):
        for b in branches(node, root):
            ap = b.get("additionalProperties")
            if isinstance(ap, dict):
                c = deref(ap, root)
                if c is UNRESOLVED:
                    return UNRESOLVED
                if c is not None:
                    cands.append(c)
    if not cands:
        return None                       # no keyword applies to this key: unconstrained
    return cands[0] if len(cands) == 1 else {"allOf": cands}


def schema_at(root, path):
    node = root
    for step in path:
        node = child(node, step, root)
        if node is None or node is UNRESOLVED:
            return node
    return node


def present(leaf, kws, root, val):
    """Keywords declared anywhere on the resolved node, each tagged with WHY the
    perturbed value still passed:
      value-satisfies  the value itself satisfies the keyword (0 vs minimum:0)
      other-branch     the keyword sits in an anyOf/oneOf arm this value doesn't take
      non-enforced     the releasing gate does not assert this keyword (format)
    Without the tag the bucket is meaningless: a declared keyword whose value
    still validates is not a gap."""
    if leaf is None or leaf is UNRESOLVED:
        return []
    from jsonschema import Draft7Validator
    out = []
    for b in branches(leaf, root):
        for kw in kws:
            if kw not in b:
                continue
            if kw == "format":
                out.append("format:non-enforced")
                continue
            try:
                ok = not list(Draft7Validator({kw: b[kw]}).iter_errors(val))
            except Exception:
                ok = None
            out.append(f"{kw}:{'value-satisfies' if ok else 'other-branch'}")
    return sorted(set(out))


def classify(root, path, kind, orig_val, mut_val):
    parent = schema_at(root, path[:-1]) if path else root
    leaf = schema_at(root, path)
    key = path[-1] if path and isinstance(path[-1], str) else None

    if kind == "removed" and key is not None:
        if parent is UNRESOLVED:
            return "removed-unresolved-path"
        if parent is None:
            return "removed-optional"      # no schema owns this key: unconstrained
        if key in required_of(parent, root):
            return "removed-required (ANOMALY)"
        return "removed-optional"
    if kind == "added":
        return "added-key (ANOMALY)"
    if kind == "arrayshrunk":
        if leaf is not None and has_kw(leaf, "minItems", root):
            return "array (ANOMALY)"
        return "removed-array-element"
    if kind == "changed":
        if key in ANNOT:
            return "blanked-annotation-string"
        if leaf is UNRESOLVED:
            return "changed-unresolved-path"
        if isinstance(orig_val, bool):
            f = present(leaf, BOOL_CONSTRAINT, root, mut_val)
            return f"blanked-bool-declared[{'/'.join(f)}] (ANOMALY)" if f else "blanked-bool-unconstrained"
        if isinstance(orig_val, (int, float)) and not isinstance(orig_val, bool) and mut_val == 0:
            f = present(leaf, NUM_CONSTRAINT, root, mut_val)
            return f"blanked-number-declared[{'/'.join(f)}] (ANOMALY)" if f else "blanked-number-unconstrained"
        if isinstance(orig_val, str) and mut_val == "":
            f = present(leaf, STR_CONSTRAINT, root, mut_val)
            return f"blanked-string-declared[{'/'.join(f)}] (ANOMALY)" if f else "blanked-string-unconstrained"
        if isinstance(orig_val, str):
            f = present(leaf, STR_CONSTRAINT, root, mut_val)
            return f"identifier-declared[{'/'.join(f)}] (ANOMALY)" if f else "identifier-unconstrained"
    return "other"


def main():
    res = json.load(open(os.path.join(HERE, "out", "results.json"), encoding="utf-8"))
    rows = [r for r in res["rows"] if r.get("mutants_total")]
    from jsonschema import validators
    cnt = collections.Counter()
    by_op = collections.defaultdict(collections.Counter)
    per_pair = []
    escapes_total = 0
    for r in rows:
        schema_path = os.path.join(SCHEMAS, r["schema"])
        inst_path = os.path.join(REPO, r["instance"].replace("/", os.sep))
        base = {"instance.json": open(inst_path, encoding="utf-8").read()}
        orig = json.loads(base["instance.json"])
        schema = json.load(open(schema_path, encoding="utf-8"))
        V = validators.validator_for(schema)
        v = V(schema, registry=gj._make_registry(os.path.abspath(SCHEMAS)))
        pair = collections.Counter()
        for name, patch in gm.build_mutants(base):
            content = next(iter(patch.values()))
            if content is None:
                continue
            try:
                mut = json.loads(content)
            except Exception:
                continue
            if list(v.iter_errors(mut)):
                continue                      # caught: not an escape
            if mut == orig:
                cnt["no_op"] += 1             # blank-value on an already-blank value
                continue
            escapes_total += 1
            op = name.split(":", 1)[0]
            changes = [c for c in diff(orig, mut) if c[1] in ("removed", "changed", "arrayshrunk", "added")]
            if not changes:
                cnt["no-detectable-change"] += 1
                pair["no-detectable-change"] += 1
                by_op[op]["no-detectable-change"] += 1
                continue
            # classify by the shallowest change
            changes.sort(key=lambda c: (len(c[0]), str(c[0])))
            p, kind = changes[0]
            try:
                o = value_at(orig, p) if kind != "removed" else None
            except Exception:
                o = None
            m = value_at(mut, p) if kind != "removed" else None
            label = classify(schema, p, kind, o, m)
            cnt[label] += 1
            pair[label] += 1
            by_op[op][label] += 1
        per_pair.append((r["schema"], sum(pair.values())))
    out = {"escapes_total": escapes_total, "categories": dict(cnt.most_common()),
           "by_operator": {k: dict(v.most_common()) for k, v in by_op.items()}}
    json.dump(out, open(os.path.join(HERE, "out", "annotation.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    extras = sum(v for k, v in cnt.items() if k != "no_op")
    print("escapes classified:", extras, "of", escapes_total)
    print(f"  (no-op mutants skipped: {cnt.get('no_op', 0)})")
    print()
    for k, n in cnt.most_common():
        print(f"  {n:>5}  {100*n/max(extras,1):5.1f}%  {k}")
    print()
    print("by operator:")
    for op, d in by_op.items():
        print(" ", op, dict(d.most_common()))
    print("wrote out/annotation.json")


if __name__ == "__main__":
    main()
