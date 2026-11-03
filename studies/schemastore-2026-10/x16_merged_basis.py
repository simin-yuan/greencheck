#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x16_merged_basis.py — the merged basis: a removed key the schema DOES declare, once the node's own
chain is followed, is not an undeclared key.

What changed and why
--------------------
x12 split the 584 removal escapes three ways by reading the CONTAINING NODE AT ITS OWN LEVEL:
368 declared-and-not-required, 82 pattern-property, 134 "the node never mentions the key" — and the
134 were moved into the `undeclared-key` class, raising the needs-annotation basis from 798 to 932.

x15 then asked why the original instance ever passed for those 134, and followed each node's own
`$ref`/`allOf`/`anyOf`/`oneOf` chain. For 49 of them the key IS declared, as an optional property, in
the definition the node resolves to — the same `properties` + missing-`required` pair that puts 368
escapes in `already-expressed`. The `undeclared-key` label was therefore true only of the node's own
level, not of what the node resolves to.

This script applies the same standard x12 used, at the same depth the proposal itself requires
("annotate the definition; `$ref` must be resolved"): a key declared under `properties` and absent
from `required` — whether written on the node or in the definition the node's own chain reaches — is
a stated absence, not an undeclared key. The 11 that declare the key only inside one arm of a
multi-arm `anyOf`/`oneOf` are judged by that same rule and nothing else: the arm is recorded as
provenance, no separate rule is invented for them.

So 49 escapes move from `undeclared-key` to `already-expressed`: the excluded class becomes
368 + 82 + 49 = 499 and the needs-annotation basis becomes 1382 - 499 = 883 (= 248 + 85 + 550).
The number moves in the proposal's favour, which is exactly why the reason is recorded here and in
the write-up: the class label was loose, the merge is the same measurement applied consistently.

Gates
-----
Pass 1 re-runs x12's own algorithm (`mechanism()` verbatim) with the merge OFF and requires the frozen
x12 numbers to come out — 450 excluded, 932 needed, 867 coverable, 65 unreachable, class composition
248 + 134, and x4's per-keyword/per-stratum counts on the unfiltered 1382 — and re-derives x13's
owning-node tables, requiring the frozen 283/84/15 and 256/85/24/17. So the merge is provably the
only difference from the frozen artifacts. Frozen inputs only, all hash-gated; no mutation, no
validator, no engine is re-run. Write-once to out/x16_merged_basis.json.

Quartiles: statistics.quantiles(xs, n=4, method="inclusive") — an unstated estimator is not
reproducible.

Run history: the first run of this script wrote the artifact with a `total` field in
open_question_readings.sourcemeta_jsonschema_632 that added the value-level class a second time
(1331); the field was mis-specified, not the measurement. That artifact was moved to
_superseded/x16_merged_basis_first_run.json and this run's output is the registered one; the
before/after figures in the field now reproduce the number the write-up already carried (823).
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import annotate as A                              # noqa: E402  the unchanged lookup
import x4_annotation_ceiling as X4                # noqa: E402  the single judgment source
import x6_annotation_write_sites as X6            # noqa: E402  site helpers; main() is guarded

OUT = HERE / "out" / "x16_merged_basis.json"
MANIFEST = HERE / "TRUTH_PROTOCOL.sha256"
SPOT = HERE / "out" / "a_layer_truth.json"
SPLIT = HERE / "out" / "a_layer_split_v2.json"
K1, K2, RES = X4.K1, X4.K2, X4.RES
REMOVAL = "removed-optional"
DECLARED_ARM = "declared-only-inside-a-multi-arm-anyOf/oneOf-arm"
DECLARED_PLAIN = "declared-optional-through-the-nodes-own-chain"
MERGED_MECH = "declared-optional-after-resolving-the-nodes-own-chain"
QUARTILE_METHOD = 'statistics.quantiles(xs, n=4, method="inclusive")'
FROZEN = ["out/x3_positions.json", "out/x4_annotation_ceiling.json",
          "out/x6_annotation_write_sites.json", "out/a_layer_truth.json",
          "out/a_layer_split_v2.json", "out/x12_annotation_basis.json",
          "out/x13_owning_node_additional_properties.json",
          "out/x15_removed_key_whence.json"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_hash(name: str):
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([0-9a-f]{64}) [\* ](.+)$", line)
        if m and m.group(2).strip() == name:
            return m.group(1)
    return None


def gate(rel: str) -> str:
    want, got = manifest_hash(rel), sha256(HERE / rel)
    if want is None or want != got:
        sys.exit(f"GATE FAILED: {rel} is {got[:12]}… but the frozen manifest says "
                 f"{str(want)[:12]}… — refusing to write")
    return got


gates = {rel: gate(rel) for rel in FROZEN}
_a = sha256(HERE / "annotate.py")
if _a != X4.ANNOT_SHA:
    sys.exit(f"GATE FAILED: annotate.py is {_a[:12]}… not {X4.ANNOT_SHA[:12]}… — refusing to write")
gates["annotate.py"] = _a

pos = json.loads((HERE / "out" / "x3_positions.json").read_text(encoding="utf-8"))
x4 = json.loads((HERE / "out" / "x4_annotation_ceiling.json").read_text(encoding="utf-8"))["summary"]
x12 = json.loads((HERE / "out" / "x12_annotation_basis.json").read_text(encoding="utf-8"))["summary"]
x13 = json.loads((HERE / "out" / "x13_owning_node_additional_properties.json")
                 .read_text(encoding="utf-8"))
x15 = json.loads((HERE / "out" / "x15_removed_key_whence.json").read_text(encoding="utf-8"))
items = pos["items"]
schemas = {}
for pair in {i["pair"] for i in items}:
    with open(A.SCHEMAS + "/" + pair, encoding="utf-8") as fh:
        schemas[pair] = json.load(fh)
index = {p: X6.document_index(s) for p, s in schemas.items()}


def mechanism(schema, path):
    """x12's rule for the removals, verbatim in behaviour: read the containing node only."""
    parent = A.schema_at(schema, tuple(path[:-1]))
    key = str(path[-1])
    parent = parent if isinstance(parent, dict) else {}
    if key in (parent.get("properties") or {}) and key not in (parent.get("required") or []):
        return "declared-and-not-required"
    if any(re.search(p, key) for p in (parent.get("patternProperties") or {})):
        return "pattern-property"
    return "open-object"


def owning_node(schema, path):
    """x13's rule: the node that owns the key — nearest node the schema declares at or above it."""
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


# ------------------------------------------- the 49, read from the frozen x15 artifact, not re-derived
DECLARED_49 = {(c["pair"], tuple(c["path"])) for c in x15["cases"]
               if c["governing"] in (DECLARED_PLAIN, DECLARED_ARM)}
ARM_11 = {(c["pair"], tuple(c["path"])) for c in x15["cases"] if c["governing"] == DECLARED_ARM}
if len(x15["cases"]) != 134 or len(DECLARED_49) != 49 or len(ARM_11) != 11:
    sys.exit(f"STOP: x15 says {len(x15['cases'])} removals, {len(DECLARED_49)} declared, "
             f"{len(ARM_11)} inside an arm — the artifact is not the one this script was written for")
REMOVAL = "removed-optional"
removal_rows = {(i["pair"], tuple(i["path"])) for i in items
                if i["label"] == REMOVAL
                and mechanism(schemas[i["pair"]], i["path"]) == "open-object"}
if not DECLARED_49 <= removal_rows:
    sys.exit("STOP: some of x15's 49 are not open-object removals on this basis")


def measure(merged: bool):
    """x12's measurement, with the merge as the only switch."""
    cls = collections.Counter()
    mech_count = collections.Counter()
    excl = collections.Counter()
    needed_kw = collections.Counter()
    need_why = collections.Counter()
    per_schema_needed = collections.Counter()
    per_schema_block = collections.defaultdict(collections.Counter)
    acts = collections.Counter()
    inst = collections.Counter()
    rows = []                                   # the undeclared-key class, rebuilt

    def add_row(pair, path, kind, schema):
        onode = owning_node(schema, path)
        rows.append({"pair": pair, "path": path, "kind": kind, "own": own_bucket(onode),
                     "resolved": resolved_bucket(schema, onode),
                     "node": json.dumps(onode, sort_keys=True),
                     "empty_schema": isinstance(onode, dict)
                     and isinstance(onode.get("additionalProperties"), dict)
                     and not onode["additionalProperties"]})

    for it in items:
        pair, path, label = it["pair"], it["path"], it["label"]
        schema = schemas[pair]
        if label == REMOVAL:
            m = mechanism(schema, path)
            if merged and (pair, tuple(path)) in DECLARED_49:
                mech_count[MERGED_MECH] += 1
                excl[MERGED_MECH] += 1
                cls["already-expressed"] += 1
                continue
            mech_count[m] += 1
            if m != "open-object":
                excl[m] += 1
                cls["already-expressed"] += 1
                continue
            add_row(pair, path, "removed", schema)
            kw, node, why = K1, A.schema_at(schema, tuple(path[:-1])), None
            if not isinstance(node, dict):
                why = "containing-node-not-located"
        else:
            kind = "added" if label == "UNDECLARED-KEY" else None
            kw, reason = X4.placement(schema, path, label)
            if kw == RES:
                needed_kw[RES] += 1
                need_why[reason] += 1
                cls["needs-annotation"] += 1
                per_schema_needed[pair] += 1
                per_schema_block[pair][reason] += 1
                if kind is not None:            # an unreachable undeclared key is still a member
                    add_row(pair, path, kind, schema)
                continue
            node, why = X6.annotation_node(schema, path), None
            if node is None:
                why = "annotation-node-not-located"
            if kind is not None:
                add_row(pair, path, kind, schema)
        cls["needs-annotation"] += 1
        needed_kw[kw] += 1
        per_schema_needed[pair] += 1
        if why is not None:
            need_why[why] += 1
            per_schema_block[pair][why] += 1
            continue
        doc_ptr = index[pair].get(id(node))
        acts[(pair, doc_ptr if doc_ptr is not None else X6.pointer(path), kw)] += 1
        inst[(pair, X6.pointer(path), kw)] += 1

    ALL = len(items)
    EXCLUDED = cls["already-expressed"]
    NEEDED = cls["needs-annotation"]
    COVERABLE = needed_kw[K1] + needed_kw[K2]
    UNREACHABLE = needed_kw[RES]
    added = sum(1 for r in rows if r["kind"] == "added")
    removed = sum(1 for r in rows if r["kind"] == "removed")
    if EXCLUDED + NEEDED != ALL or COVERABLE + UNREACHABLE != NEEDED \
            or removed != mech_count["open-object"]:
        sys.exit(f"STOP: basis does not reconcile (excluded {EXCLUDED}, needed {NEEDED}, all {ALL}, "
                 f"coverable {COVERABLE}, unreachable {UNREACHABLE}, removed {removed})")

    by_schema_sites = collections.defaultdict(list)
    for (pair, _node, _kw), c in acts.items():
        by_schema_sites[pair].append(c)
    top20 = sorted(acts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    top20_sites = collections.Counter(k[0] for k, _ in top20)
    top20_esc = collections.Counter()
    for (pair, _node, _kw), c in top20:
        top20_esc[pair] += c
    spread = sorted(({"schema": k, "sites": v, "escapes": top20_esc[k]}
                     for k, v in top20_sites.items()),
                    key=lambda d: (-d["sites"], -d["escapes"], d["schema"]))
    cum20 = sum(top20_esc.values())

    per_schema, blocked = [], []
    for sch in sorted(per_schema_needed):
        n = per_schema_needed[sch]
        ordered = sorted(by_schema_sites.get(sch, []), reverse=True)
        cum, k = 0, None
        for idx, v in enumerate(ordered, 1):
            cum += v
            if cum * 2 >= n:
                k = idx
                break
        per_schema.append({"schema": sch, "needed_escapes": n, "write_sites": len(ordered),
                           "covered_by_write_sites": sum(ordered), "sites_to_half": k,
                           "unreachable": sum(per_schema_block[sch].values()),
                           "unreachable_reasons": dict(per_schema_block[sch])})
        if k is None:
            blocked.append({"schema": sch, "needed_escapes": n, "write_sites": len(ordered),
                            "covered_by_write_sites": sum(ordered),
                            "unreachable": sum(per_schema_block[sch].values()),
                            "unreachable_reasons": dict(per_schema_block[sch]),
                            "why": "fewer than half of this schema's needed escapes sit at a site an "
                                   "annotation can be written on"})
    half = sorted(r["sites_to_half"] for r in per_schema if r["sites_to_half"] is not None)
    q = statistics.quantiles(half, n=4, method="inclusive")
    needed_counts = [r["needed_escapes"] for r in per_schema]
    none_needed = sorted(s for s in {i["pair"] for i in items} if s not in per_schema_needed)

    def table(view):
        out = {}
        for key, name in (("true", "written-true"), ("other", "written-other-schema"),
                          ("none", "nothing-written"), ("false", "written-false")):
            sub = [r for r in rows if r[view] == key]
            if not sub:
                continue
            out[name] = {
                "escapes": len(sub),
                "added": sum(1 for r in sub if r["kind"] == "added"),
                "removed": sum(1 for r in sub if r["kind"] == "removed"),
                "distinct_nodes": len({(r["pair"], r["node"]) for r in sub}),
                "schemas": sorted({r["pair"] for r in sub}),
                "of_which_empty_schema": sum(1 for r in sub if r["empty_schema"]),
            }
        return out

    value_level = sum(1 for it in items
                      if it["label"] not in (REMOVAL, "UNDECLARED-KEY"))
    return {
        "all": ALL, "excluded": EXCLUDED, "needed": NEEDED, "coverable": COVERABLE,
        "unreachable": UNREACHABLE, "mech": mech_count, "excl": excl, "added": added,
        "removed": removed, "classes_undeclared": added + removed, "value_level": value_level,
        "coverable_k1": needed_kw[K1], "coverable_k2": needed_kw[K2],
        "need_why": need_why, "acts": acts, "inst": inst, "per_schema": per_schema,
        "blocked": blocked, "half": half, "quartiles": q, "needed_counts": needed_counts,
        "none_needed": none_needed, "spread": spread, "cum20": cum20,
        "own_table": table("own"), "res_table": table("resolved"), "rows": len(rows),
        "by_schema_sites": by_schema_sites,
    }


def curve_numbers(m):
    acts, inst = m["acts"], m["inst"]
    return {
        "by_write_site": X6.curve(acts, m["coverable"], m["needed"],
                                  lambda pair, node, kw, c: {"schema": pair, "node": node,
                                                             "keyword": kw, "covers": c}),
        "by_instance_path": X6.curve(inst, m["coverable"], m["needed"],
                                     lambda pair, node, kw, c: {"schema": pair, "node": node,
                                                                "keyword": kw, "covers": c}),
    }


# ---------------------------------------------------------------- pass 1: the frozen x12 basis
kw_counts, per_stratum = collections.Counter(), collections.defaultdict(collections.Counter)
for it in items:
    kw, _ = X4.placement(schemas[it["pair"]], it["path"], it["label"])
    kw_counts[kw] += 1
    per_stratum[it["label"]][kw] += 1
exp_kw = {k["name"]: k["covers"] for k in x4["keywords"]}
exp_kw[RES] = x4["upper_bound"]["not_coverable"]
if dict(kw_counts) != exp_kw:
    sys.exit(f"STOP: per-keyword counts differ from the frozen x4 artifact\n"
             f"  this run: {dict(kw_counts)}\n  frozen  : {exp_kw}")
for lab, c in x4["per_stratum"].items():
    if dict(per_stratum[lab]) != c:
        sys.exit("STOP: a stratum differs from the frozen x4 artifact")

old = measure(merged=False)
fp = x12["population"]
fc = x12["classes"]
if (old["excluded"], old["needed"], old["coverable"], old["unreachable"], old["acts"] and len(old["acts"])) \
        != (fp["already_expressed"], fp["needs_annotation"], fp["coverable"], fp["unreachable"],
            fp["write_sites"]):
    sys.exit(f"STOP: the merge-off run does not reproduce the frozen x12 basis\n"
             f"  this run: excluded {old['excluded']}, needed {old['needed']}, "
             f"coverable {old['coverable']}, unreachable {old['unreachable']}, "
             f"sites {len(old['acts'])}\n"
             f"  frozen  : excluded {fp['already_expressed']}, needed {fp['needs_annotation']}, "
             f"coverable {fp['coverable']}, unreachable {fp['unreachable']}, "
             f"sites {fp['write_sites']}")
if (old["classes_undeclared"], old["added"], old["removed"]) != \
        (fc["undeclared-key"]["escapes"], fc["undeclared-key"]["composition"]["added-undeclared-key"],
         fc["undeclared-key"]["composition"]["removed-undeclared-key"]):
    sys.exit("STOP: the merge-off run does not reproduce x12's undeclared-key class")
if (old["mech"]["declared-and-not-required"], old["mech"]["pattern-property"]) != \
        (fc["already-expressed"]["composition"]["declared-and-not-required"],
         fc["already-expressed"]["composition"]["pattern-property"]):
    sys.exit("STOP: the merge-off run does not reproduce x12's already-expressed composition")
if old["own_table"] != x13["node_statement"]["buckets"] \
        or {k: v for k, v in old["res_table"].items()} != x13["resolved_statement"]["buckets"]:
    sys.exit("STOP: the merge-off run does not reproduce x13's owning-node tables")

# ---------------------------------------------------------------- pass 2: the merged basis
new = measure(merged=True)
if (new["excluded"], new["needed"], new["coverable"], new["unreachable"]) != \
        (499, 883, 818, 65):
    sys.exit(f"STOP: the merged basis is not the one this script was written for: excluded "
             f"{new['excluded']}, needed {new['needed']}, coverable {new['coverable']}, "
             f"unreachable {new['unreachable']}")
curves = curve_numbers(new)
old_curves = curve_numbers(old)
explicit = (new["res_table"].get("written-true", {}).get("escapes", 0)
            + new["res_table"].get("written-other-schema", {}).get("escapes", 0))
old_explicit = (old["res_table"].get("written-true", {}).get("escapes", 0)
                + old["res_table"].get("written-other-schema", {}).get("escapes", 0))
VALUE = new["value_level"]
if VALUE != 550 or new["value_level"] != old["value_level"]:
    sys.exit(f"STOP: the value-level class is {VALUE}, expected the unchanged 550")

truth = json.loads(SPOT.read_text(encoding="utf-8"))
caught_by_op = collections.Counter()
sampled = 0
for blk in truth["pairs"].values():
    sampled += blk["n"]
    for c in blk["cases"]:
        if c["caught"] or c["status"] != "ACCEPT":
            caught_by_op[c["name"].split(":")[0]] += 1
split_ops = json.loads(SPLIT.read_text(encoding="utf-8"))["operators_seen"]
spot = {"sampled_cases": sampled,
        "deletions_released_and_accepted": split_ops["drop-line"],
        "deletions_rejected": caught_by_op["drop-line"],
        "deletions_sampled": split_ops["drop-line"] + caught_by_op["drop-line"],
        "blank_values_released": split_ops["blank-value"],
        "source": "out/a_layer_truth.json + out/a_layer_split_v2.json"}

def stats(m, cv):
    """The six measurements x12 froze — computed once, used for the old-basis gate and the summary."""
    c_acts = cv["by_write_site"]["annotation_acts"]
    return {
        "by_write_site": cv["by_write_site"],
        "by_instance_path": cv["by_instance_path"],
        "top20_spread": {"n_schemas": len(m["spread"]), "escapes": m["cum20"],
                         "by_schema": m["spread"],
                         "top3_escapes": sum(d["escapes"] for d in m["spread"][:3]),
                         "top3_share": round(sum(d["escapes"] for d in m["spread"][:3])
                                             / m["cum20"], 6)},
        "sites_to_half": {
            "unit": "write sites to classify >= 50% of that schema's own needed escapes",
            "n_schemas_with_needed_escapes": len(m["per_schema"]),
            "n_reaching_half": len(m["half"]), "n_not_reaching_half": len(m["blocked"]),
            "not_reaching_half": m["blocked"],
            "min": m["half"][0], "q1": m["quartiles"][0], "median": statistics.median(m["half"]),
            "q3": m["quartiles"][2], "max": m["half"][-1],
            "distribution": {str(k): c for k, c in sorted(collections.Counter(m["half"]).items())},
            "estimator": QUARTILE_METHOD},
        "needed_escapes_per_schema": {"min": min(m["needed_counts"]),
                                      "median": statistics.median(m["needed_counts"]),
                                      "max": max(m["needed_counts"])},
        "schemas_without_needed_escapes": {"n": len(m["none_needed"]), "list": m["none_needed"]},
    }


_old_stats = stats(old, old_curves)
_stats_mismatch = {k: {"this_run": _old_stats[k], "frozen": x12[k]}
                   for k in _old_stats if _old_stats[k] != x12.get(k)}
if _stats_mismatch:
    for k, d in list(_stats_mismatch.items())[:2]:
        sys.exit(f"STOP: the merge-off run does not reproduce x12's {k}\n"
                 f"  this run: {json.dumps(d['this_run'], ensure_ascii=False)[:600]}\n"
                 f"  frozen  : {json.dumps(d['frozen'], ensure_ascii=False)[:600]}")
S = stats(new, curves)

M = new["mech"]
classes = {
    "already-expressed": {
        "escapes": new["excluded"], "share_of_all": round(new["excluded"] / new["all"], 6),
        "keyword": None,
        "composition": {"declared-and-not-required": M["declared-and-not-required"],
                        "pattern-property": M["pattern-property"],
                        MERGED_MECH: M[MERGED_MECH]},
        "merged_from_undeclared_key": {
            "escapes": M[MERGED_MECH],
            "declared_along_a_chain_with_no_multi_arm_choice": M[MERGED_MECH] - len(ARM_11),
            "declared_only_inside_one_arm_of_a_multi_arm_anyOf_oneOf": len(ARM_11),
            "which_standard": ("the same `properties` + missing-`required` rule x12 used for the "
                               "368, applied to the definition the node's own $ref/allOf/anyOf/"
                               "oneOf chain reaches — no separate rule for the 11"),
            "why": ("x15 asked why the ORIGINAL instance passed for the 134 removals; for these 49 "
                    "the key is declared, as an optional property, in the definition the node "
                    "resolves to, so it was never an `additional` key and its absence is exactly "
                    "what the schema states"),
        },
        "why": ("`required` is the instrument the author already used to say a declared key may be "
                "omitted, and a mapping/`patternProperties` node says its entries come and go; an "
                "annotation on top would restate either. The real tools agree — of the sampled "
                "deletion mutants every one that ran was accepted, apart from two where the "
                "remaining configuration genuinely stopped working."),
        "real_tool_spot_check": spot,
    },
    "undeclared-key": {
        "escapes": new["classes_undeclared"], "keyword": K1,
        "composition": {"added-undeclared-key": new["added"], "removed-undeclared-key": new["removed"]},
        "coverable": new["coverable_k1"],
        "unreachable": per_stratum["UNDECLARED-KEY"][RES],
        "why": ("the schema never mentions the key — whether the instance gained it or lost it — so "
                "nothing expressed an opinion; the containing node's openness is the statement "
                "`x-open-object` records"),
    },
    "unconstrained-value": {
        "escapes": VALUE, "keyword": K2,
        "coverable": new["coverable_k2"], "unreachable": new["unreachable"] - per_stratum["UNDECLARED-KEY"][RES],
        "why": ("nothing constrains the perturbed value; `x-open-value` records that the openness "
                "is deliberate, or the author writes the missing constraint"),
    },
}

summary = {
    "question": ("What does the basis become when a removed key that the node's own chain declares "
                 "— optionally — is counted as stated rather than undeclared?"),
    "answer": (f"x12's 450 already-expressed and 382 undeclared-key become 499 and "
               f"{new['classes_undeclared']}: the {M[MERGED_MECH]} removals x15 showed are declared "
               f"as optional properties in the definition the node resolves to "
               f"({len(ARM_11)} of them only inside one arm of a multi-arm anyOf/oneOf) move into "
               f"`already-expressed` under the same rule that put the 368 there. Needs-annotation "
               f"falls 932 → {new['needed']} (= {new['classes_undeclared']} + {VALUE}); coverable "
               f"falls 867 → {new['coverable']}; the unreachable 65 is unchanged. The number moves "
               f"in the proposal's favour, and the reason is that the class label was reading the "
               f"node's own level only — not that a threshold was relaxed."),
    "gate": gates,
    "population": {"escaped_mutants": new["all"], "already_expressed": new["excluded"],
                   "needs_annotation": new["needed"],
                   "needs_share_of_all": round(new["needed"] / new["all"], 6),
                   "coverable": new["coverable"],
                   "coverable_ratio": round(new["coverable"] / new["needed"], 6),
                   "unreachable": new["unreachable"],
                   "unreachable_ratio": round(new["unreachable"] / new["needed"], 6),
                   "unreachable_by_reason": dict(new["need_why"].most_common()),
                   "schemas": len(new["per_schema"]), "write_sites": len(new["acts"])},
    "classes": classes,
    "removal_breakdown": {
        "removed-optional-escapes": 584,
        "declared-and-not-required": M["declared-and-not-required"],
        "pattern-property": M["pattern-property"],
        MERGED_MECH: M[MERGED_MECH],
        "open-object-undeclared-key": M["open-object"],
        "note": ("the 584 removals read against the schemas: 368 state the absence through "
                 "`properties` plus a missing `required`, 82 match a `patternProperties` regex, and "
                 f"85 are declared nowhere the node's own chain reaches — those carry work. The "
                 f"{M[MERGED_MECH]} x15 found declared in the resolved definition are a stated "
                 "absence like the 368."),
    },
    "undeclared_class_statement": {
        "unit": ("what the object node owning an undeclared key writes about the keys it does not "
                 "declare — the x13 view, recomputed on the merged class"),
        "node_statement": new["own_table"],
        "resolved_statement": new["res_table"],
        "moved_from_the_old_382": {
            "old_class": old["classes_undeclared"], "now": new["classes_undeclared"],
            "node_level_before": {k: v["escapes"] for k, v in old["own_table"].items()},
            "node_level_after": {k: v["escapes"] for k, v in new["own_table"].items()},
            "resolved_before": {k: v["escapes"] for k, v in old["res_table"].items()},
            "resolved_after": {k: v["escapes"] for k, v in new["res_table"].items()},
            "explicit_before": old_explicit, "explicit_after": explicit,
            "note": ("a statement of the schema, not of the author's intent; `written-false` is not "
                     "a fourth kind of silence but the opposite statement"),
        },
        "open_question_readings": {
            "strict": {"basis": ["undeclared-key", "unconstrained-value"],
                       "declaration_standard": {"stated": new["excluded"], "decide": new["needed"]}},
            "sourcemeta_jsonschema_632": {
                "note": ("counting only an explicit `additionalProperties: true` or a written "
                         "schema as a statement about unknown keys"),
                "stated_in_the_undeclared_class": explicit,
                "still_undeclared": new["classes_undeclared"] - explicit,
                "needs_decision_total": new["needed"] - explicit,
                "of_which_value_level": VALUE,
                "formula": ("needs_decision_total = (undeclared-key - explicit) + "
                            "unconstrained-value"),
                "before_merge": {"stated_in_the_undeclared_class": old_explicit,
                                 "needs_decision_total": old["needed"] - old_explicit,
                                 "as_documented_in_the_write_up": 823},
            },
        },
    },
    **S,
    "reconciliation_with_frozen": {
        "basis_merge_is_the_only_difference": True,
        "x12_merge_off": {k: old[k] for k in ("excluded", "needed", "coverable", "unreachable")},
        "x12_frozen": {k: fp[k] for k in ("already_expressed", "needs_annotation", "coverable",
                                          "unreachable")},
        "x13_merge_off_reproduced": True,
        "write_sites_before": len(old["acts"]), "write_sites_after": len(new["acts"]),
    },
    "reading": ("The permitted absences are not work: once the node's own chain is followed, 499 "
                "escapes state their own absence and 883 need a decision, of which 65 no annotation "
                "expresses. The class `undeclared-key` is now exactly the keys no keyword anywhere "
                "the node reaches governs."),
}

assert sum(classes[c]["escapes"] for c in classes) == new["all"]
assert sum(classes["already-expressed"]["composition"].values()) == new["excluded"]
assert sum(M.values()) == 584
assert classes["undeclared-key"]["coverable"] + classes["undeclared-key"]["unreachable"] \
    == classes["undeclared-key"]["escapes"]
assert classes["unconstrained-value"]["coverable"] + classes["unconstrained-value"]["unreachable"] \
    == classes["unconstrained-value"]["escapes"]
assert new["coverable"] == sum(classes[c]["coverable"] for c in ("undeclared-key", "unconstrained-value"))
assert sum(r["covered_by_write_sites"] for r in new["per_schema"]) == new["coverable"]
assert sum(r["needed_escapes"] for r in new["per_schema"]) == new["needed"]
assert new["cum20"] == summary["by_write_site"]["annotation_acts"]["cumulative_at"]["20"]["escaped_mutants"]
assert old["excluded"] + M[MERGED_MECH] == new["excluded"]
assert old["classes_undeclared"] == new["classes_undeclared"] + M[MERGED_MECH]
# the merge-off #632 reading must land on the number the write-up already carried
assert summary["undeclared_class_statement"]["open_question_readings"]["sourcemeta_jsonschema_632"][
    "before_merge"]["needs_decision_total"] == 823, "STOP: the merge-off #632 reading is not 823"
assert new["needed"] - explicit == (new["classes_undeclared"] - explicit) + VALUE
assert old["excluded"] == 450 and old["classes_undeclared"] == 382 and old["value_level"] == 550

if OUT.exists():
    sys.exit(f"REFUSING TO OVERWRITE {OUT.name} — results are write-once "
             f"(existing sha256 {sha256(OUT)[:12]}…)")
tmp = OUT.with_suffix(".json.part")
tmp.write_text(json.dumps({"summary": summary, "per_schema": new["per_schema"]},
                          ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
tmp.replace(OUT)

P, C = summary["population"], summary["classes"]
c_acts = summary["by_write_site"]["annotation_acts"]
ip = summary["by_instance_path"]["annotation_acts"]
print(f"wrote {OUT.name}  sha256 {sha256(OUT)[:12]}…")
print(f"gate: merge OFF reproduces x12 ({old['excluded']}/{old['needed']}/{old['coverable']}/"
      f"{old['unreachable']}, sites {len(old['acts'])}) and x13's node/resolved tables")
print(f"merged: already expressed {new['excluded']} = {M['declared-and-not-required']} + "
      f"{M['pattern-property']} + {M[MERGED_MECH]} (x15's {len(DECLARED_49)}, {len(ARM_11)} in an arm)")
print(f"needs annotation {new['needed']}: {K1} {C['undeclared-key']['escapes']} "
      f"(added {new['added']} + removed {new['removed']}) | {K2} {C['unconstrained-value']['escapes']}")
print(f"coverable {new['coverable']} ({P['coverable_ratio']:.2%}); unreachable {new['unreachable']} "
      f"({P['unreachable_ratio']:.2%}) reasons {P['unreachable_by_reason']}")
print(f"undeclared class node view : {[ (k, v['escapes']) for k, v in new['own_table'].items() ]}")
print(f"undeclared class resolved  : {[ (k, v['escapes']) for k, v in new['res_table'].items() ]} "
      f"-> explicit {explicit} (was {old_explicit}), #632 reading decides "
      f"{new['needed'] - explicit} (was {old['needed'] - old_explicit}) = "
      f"{new['classes_undeclared'] - explicit} undeclared + {VALUE} value level")
for n in ("1", "3", "5", "10", "20", "50", "100", "200"):
    if n in c_acts["cumulative_at"]:
        r = c_acts["cumulative_at"][n]
        print(f"  top {n:>3} sites -> {r['escaped_mutants']:>3} ({r['of_all_escapes']:.2%} of needed, "
              f"{r['of_reachable']:.2%} of coverable)")
for t in ("10%", "25%", "50%", "75%", "90%"):
    if t in c_acts["annotations_needed_for"]:
        r = c_acts["annotations_needed_for"][t]
        print(f"  {t}: {r['annotations']} sites -> {r['escaped_mutants']} escapes")
print(f"  sites total {summary['by_write_site']['annotation_acts_total']} / "
      f"nodes {summary['by_write_site']['annotated_nodes_total']} / "
      f"single-cover {summary['by_write_site']['acts_covering_exactly_one']} / "
      f"largest {summary['by_write_site']['largest_single_act']['covers']}")
print(f"  instance-path view: {summary['by_instance_path']['annotation_acts_total']} acts")
sp, st = summary["top20_spread"], summary["sites_to_half"]
print(f"(a) top-20 sites span {sp['n_schemas']} schemas, {sp['escapes']} escapes; top3 = "
      f"{sp['top3_escapes']} ({sp['top3_share']:.1%})")
print(f"(b) sites to half: min {st['min']} Q1 {st['q1']} median {st['median']} Q3 {st['q3']} "
      f"max {st['max']} ({st['n_reaching_half']}/{st['n_schemas_with_needed_escapes']})")
print(f"    needed per schema median {summary['needed_escapes_per_schema']['median']} "
      f"(min {summary['needed_escapes_per_schema']['min']}, "
      f"max {summary['needed_escapes_per_schema']['max']})")
