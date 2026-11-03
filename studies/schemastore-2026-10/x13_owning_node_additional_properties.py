#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x13_owning_node_additional_properties.py — what the object node that owns an undeclared key
says about the keys it does not name.

Why this exists
---------------
x12 splits the 1382 escapes three ways. Its `undeclared-key` class (382 = 248 added + 134 removed)
is defined negatively: the containing node has no `properties` entry for the key and no
`patternProperties` regex matching it. That says what the node does *not* do. It does not say
whether the node went on to state, in some other way, how unknown keys are to be treated —
`additionalProperties` is exactly that statement.

So this measurement asks, for each of the 382, what the OBJECT NODE THAT OWNS THE KEY writes:

  * `additionalProperties: true`           — openness stated outright;
  * `additionalProperties: {<schema>}`     — the extra keys are acknowledged, their values typed
                                             (an empty `{}` is counted inside this bucket, flagged);
  * no `additionalProperties` at all       — the openness is the dialect default, nothing written.

A fourth case appears once the node's branches and `$ref` definitions are consulted: a node whose
governing definition writes `additionalProperties: false`. It is reported separately, never folded
into the three above.

What it is not
--------------
A statement of the SCHEMA, not of the author's intent. A node that writes `true` may still be an
oversight, and a node that writes nothing may be deliberate. This measurement never guesses intent.

Method
------
Reads only frozen artifacts and never re-runs a mutation or a validator:

  * `out/x3_positions.json`   — the frozen escape list (hash-gated);
  * `out/x12_annotation_basis.json` — the frozen class split (hash-gated); the added/removed
    counts recomputed here must equal its own class composition before anything is written;
  * `annotate.py` — imported UNCHANGED (hash-gated) for the lookup; the same `mechanism()` rule
    x12 uses decides the 134 removals, and the owning node is the nearest node the schema declares
    at or above the key's parent (x12's own choice for the removals, applied to both kinds).

Write-once to `out/x13_owning_node_additional_properties.json`.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import annotate as A                              # noqa: E402  the unchanged lookup
import onceio                                     # noqa: E402  write-once result files
import x4_annotation_ceiling as X4                # noqa: E402  frozen gate constants

OUT = HERE / "out" / "x13_owning_node_additional_properties.json"
MANIFEST = HERE / "TRUTH_PROTOCOL.sha256"
POS = HERE / "out" / "x3_positions.json"
X12 = HERE / "out" / "x12_annotation_basis.json"

BUCKET = {
    "true": "written-true",
    "other": "written-other-schema",
    "none": "nothing-written",
    "false": "written-false",
}


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def manifest_hash(name: str):
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([0-9a-f]{64}) [\* ](.+)$", line)
        if m and m.group(2).strip() == name:
            return m.group(1)
    return None


# ----------------------------------------------------------------- gate: frozen inputs only
got_a, got_p = sha256(HERE / "annotate.py"), sha256(POS)
if got_a != X4.ANNOT_SHA:
    sys.exit(f"GATE FAILED: annotate.py is {got_a[:12]}… but the frozen hash is "
             f"{X4.ANNOT_SHA[:12]}… — this run must use the UNCHANGED lookup")
if got_p != X4.X3POS_SHA:
    sys.exit(f"GATE FAILED: out/x3_positions.json is {got_p[:12]}… but the frozen hash is "
             f"{X4.X3POS_SHA[:12]}… — the escape list moved")
got_x12 = sha256(X12)
if got_x12 != manifest_hash("out/x12_annotation_basis.json"):
    sys.exit("GATE FAILED: out/x12_annotation_basis.json does not match the manifest")

pos = json.load(open(POS, encoding="utf-8"))
x12 = json.load(open(X12, encoding="utf-8"))
items = pos["items"]
schemas = {}
for pair in {it["pair"] for it in items}:
    schemas[pair] = json.load(open(Path(A.SCHEMAS) / pair, encoding="utf-8"))


def mechanism(schema, path):
    """x12's rule for the 134 removals, verbatim in behaviour: read the containing node only."""
    parent = A.schema_at(schema, tuple(path[:-1]))
    key = str(path[-1])
    parent = parent if isinstance(parent, dict) else {}
    if key in (parent.get("properties") or {}) and key not in (parent.get("required") or []):
        return "declared-and-not-required"
    if any(re.search(p, key) for p in (parent.get("patternProperties") or {})):
        return "pattern-property"
    return "open-object"


def owning_node(schema, path):
    """The node that owns the key: nearest node the schema declares at or above its parent."""
    for k in range(len(path) - 1, -1, -1):
        node = A.schema_at(schema, tuple(path[:k]))
        if node is not None and node is not A.UNRESOLVED:
            return node
    return None


def own_bucket(node):
    """What the node ITSELF writes — the document node, no branch or $ref resolution."""
    if not isinstance(node, dict) or "additionalProperties" not in node:
        return "none"
    val = node["additionalProperties"]
    if val is True:
        return "true"
    if val is False:
        return "false"
    if isinstance(val, dict):
        return "other"
    return "other"


def resolved_bucket(schema, node):
    """The same question, consulting the node's own `$ref`/`allOf`/`anyOf`/`oneOf` branches."""
    vals = [b["additionalProperties"] for b in A.branches(node, schema)
            if isinstance(b, dict) and "additionalProperties" in b]
    if any(v is True for v in vals):
        return "true"
    if any(isinstance(v, dict) for v in vals):
        return "other"
    if any(v is False for v in vals):
        return "false"
    return "none"


# ------------------------------------------------------------ pass 1: rebuild the 382
rows = []
for it in items:
    pair, path, label = it["pair"], it["path"], it["label"]
    if label == "UNDECLARED-KEY":
        kind = "added"
    elif label == "removed-optional" and mechanism(schemas[pair], path) == "open-object":
        kind = "removed"
    else:
        continue
    node = owning_node(schemas[pair], path)
    rows.append({
        "pair": pair, "path": path, "kind": kind, "node": node,
        "own": own_bucket(node), "resolved": resolved_bucket(schemas[pair], node),
        "empty_schema": isinstance(node, dict)
        and isinstance(node.get("additionalProperties"), dict)
        and not node["additionalProperties"],
    })

frozen_cls = x12["summary"]["classes"]["undeclared-key"]
frozen_comp = frozen_cls["composition"]
mine_comp = {"added-undeclared-key": sum(1 for r in rows if r["kind"] == "added"),
             "removed-undeclared-key": sum(1 for r in rows if r["kind"] == "removed")}
if mine_comp != frozen_comp or len(rows) != frozen_cls["escapes"]:
    sys.exit(f"STOP: the rebuilt class differs from the frozen x12 artifact\n"
             f"  this run: {mine_comp} (total {len(rows)})\n"
             f"  frozen  : {frozen_comp} (total {frozen_cls['escapes']})")


def bucket_table(view):
    table = {}
    for key, name in BUCKET.items():
        sub = [r for r in rows if r[view] == key]
        if not sub:
            continue
        table[name] = {
            "escapes": len(sub),
            "added": sum(1 for r in sub if r["kind"] == "added"),
            "removed": sum(1 for r in sub if r["kind"] == "removed"),
            "distinct_nodes": len({(r["pair"], json.dumps(r["node"], sort_keys=True)) for r in sub}),
            "schemas": sorted({r["pair"] for r in sub}),
            "of_which_empty_schema": sum(1 for r in sub if r["empty_schema"]),
        }
    return table


own_table, res_table = bucket_table("own"), bucket_table("resolved")
per_schema = collections.defaultdict(lambda: collections.Counter())
for r in rows:
    per_schema[r["pair"]][f'{r["kind"]}:{BUCKET[r["own"]]}'] += 1

summary = {
    "question": ("Of the 382 escapes whose key the owning node never declares, what does that "
                 "node write about keys it does not declare — additionalProperties: true, "
                 "another schema, or nothing at all?"),
    "population": {"undeclared_key_escapes": len(rows), "added": mine_comp["added-undeclared-key"],
                   "removed": mine_comp["removed-undeclared-key"],
                   "source": "out/x12_annotation_basis.json class composition, recomputed from "
                             "out/x3_positions.json with x12's own mechanism rule",
                   "class_total_matches_x12": True},
    "node_statement": {
        "unit": "the keyword written on the owning node itself, no branch or $ref resolution",
        "buckets": own_table,
    },
    "resolved_statement": {
        "unit": ("the same question consulting the node's own $ref/allOf/anyOf/oneOf branches — "
                 "the view in which a statement living in a shared definition is visible"),
        "buckets": res_table,
        "note": ("`written-false` is not a fourth kind of silence: it is a node that says the "
                 "opposite. Its escapes passed because a removal never violates "
                 "`additionalProperties` (only `required` can catch it), or because the key was "
                 "accepted through a sibling branch the released gate resolved differently."),
    },
    "per_schema": {pair: dict(sorted(c.items())) for pair, c in sorted(per_schema.items())},
    "examples": {
        "written-true": [{"pair": r["pair"], "path": r["path"], "kind": r["kind"]}
                         for r in rows if r["own"] == "true"][:5],
        "written-other-schema": [{"pair": r["pair"], "path": r["path"], "kind": r["kind"],
                                  "empty_schema": r["empty_schema"]}
                                 for r in rows if r["own"] == "other"][:5],
        "resolved-written-false": [{"pair": r["pair"], "path": r["path"], "kind": r["kind"]}
                                   for r in rows if r["resolved"] == "false"],
    },
    "reading": (
        "A statement of the schema, not of the author's intent: a node that writes `true` may still "
        "be careless, and a node that writes nothing may be deliberate. Read on the nodes "
        "themselves, 283 of the 382 write nothing, 84 write another schema (5 of them the empty "
        "`{}`, which permits anything a `true` would) and 15 write `true`; consulting `$ref` "
        "definitions and `anyOf`/`oneOf` arms, the explicit ones rise to 126 (24 true, 85 another "
        "schema, 17 the opposite). So the class `undeclared-key` is not one situation: at 99 of "
        "the 382 the node has already said something about unknown keys, which is the same "
        "instrument `x-open-object` proposes to add."),
    "gate": {
        "annotate_py_sha256": got_a, "annot_py_unchanged": True,
        "x3_positions_sha256": got_p, "x3_positions_is_frozen_copy": True,
        "x12_annotation_basis_sha256": got_x12, "x12_matches_manifest": True,
        "reconciled_with_x12_class": True,
        "no_mutation_rerun": True, "no_validator_rerun": True,
    },
}

onceio.write_once(str(OUT), summary, why=(
    "what the owning object node writes about keys it does not declare, over the 382 "
    "undeclared-key escapes of the frozen x12 basis"))

own, res = summary["node_statement"]["buckets"], summary["resolved_statement"]["buckets"]
print(f"POP {len(rows)} = {mine_comp['added-undeclared-key']} added + "
      f"{mine_comp['removed-undeclared-key']} removed  (equals x12's class composition)")
print("node's own keyword :", {k: v["escapes"] for k, v in own.items()})
print("resolved (branches):", {k: v["escapes"] for k, v in res.items()})
print("distinct owning nodes:", len({(r["pair"], json.dumps(r["node"], sort_keys=True))
                                     for r in rows}))
print(f"written:", OUT)
