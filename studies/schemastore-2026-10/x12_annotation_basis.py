#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x11_annotation_basis.py — the measurement on the corrected basis.

What changed and why
--------------------
The earlier scripts (x8/x9/x10) excluded all 584 removal escapes from the workload, on the ground
that "a declared key not listed in `required` may be absent, so `required` already states the
intent". Reading the 584 against the schemas shows they are not one mechanism:

  * 368 — the key IS declared under the containing node and is not listed in `required`. Here the
    author's own `properties`/`required` pair states the intent; an extra annotation would restate
    it. (Same for a mapping/pattern node: 82 escapes where the key matches a `patternProperties`
    regex, i.e. the node says "these entries come and go".)
  * 134 — the containing node never mentions the key at all: no `properties` entry, no pattern that
    matches it. Nothing in the schema expressed an opinion, so this is *not* "already expressed";
    it is an undeclared key, the same phenomenon as an added key the schema never declared. The
    annotation that answers it is `x-open-object` on the containing object node.

So the excluded class is 368 + 82 = **450**, and the 134 move into the `x-open-object` class
alongside the 248 added-undeclared-key escapes. Needs-annotation therefore rises from 798 to **932**,
and every number below is computed on that basis.

Judgment source: `x4_annotation_ceiling.placement()` for the non-removal escapes (unchanged), and
for the 134 the containing object node, which is the node whose openness is in question. Hard gate
before writing: this run's per-keyword and per-stratum counts must equal the frozen x4 artifact on
the UNFILTERED 1382, so the basis change is provably the only difference. Frozen inputs only, all
hash-gated — no mutation, no validator, no engine is re-run.

Quartiles: statistics.quantiles(xs, n=4, method="inclusive") — an unstated estimator is not
reproducible. Write-once to out/x12_annotation_basis.json.

x12 differs from x11 in ONE labelling detail, no number moves: x11 kept the full 584-item mechanism
breakdown inside the "already-expressed" class's `composition`, so that class's parts summed to 584
while the class itself holds 450. x12 lists only the two mechanisms that are actually in the class
and moves the whole breakdown to a top-level `removal_breakdown`. Every count below is identical to
x11's; x11 is recorded superseded in the hash manifest.
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

OUT = HERE / "out" / "x12_annotation_basis.json"
MANIFEST = HERE / "TRUTH_PROTOCOL.sha256"
SPOT = HERE / "out" / "a_layer_truth.json"
SPLIT = HERE / "out" / "a_layer_split_v2.json"
K1, K2, RES = X4.K1, X4.K2, X4.RES
REMOVAL = "removed-optional"
QUARTILE_METHOD = 'statistics.quantiles(xs, n=4, method="inclusive")'
FROZEN = ["out/x3_positions.json", "out/x4_annotation_ceiling.json",
          "out/x6_annotation_write_sites.json", "out/a_layer_truth.json",
          "out/a_layer_split_v2.json"]


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
items = pos["items"]
schemas = {}
for pair in {i["pair"] for i in items}:
    with open(A.SCHEMAS + "/" + pair, encoding="utf-8") as fh:
        schemas[pair] = json.load(fh)
index = {p: X6.document_index(s) for p, s in schemas.items()}


def mechanism(schema, path):
    """Why is a removed key's absence permitted? Read from the containing node only."""
    parent = A.schema_at(schema, tuple(path[:-1]))
    key = str(path[-1])
    parent = parent if isinstance(parent, dict) else {}
    if key in (parent.get("properties") or {}) and key not in (parent.get("required") or []):
        return "declared-and-not-required"
    if any(re.search(p, key) for p in (parent.get("patternProperties") or {})):
        return "pattern-property"
    return "open-object"


# ---- pass 1: unfiltered, gated against the frozen x4 (proves the basis is the only change)
kw_counts, per_stratum = collections.Counter(), collections.defaultdict(collections.Counter)
for it in items:
    kw, _ = X4.placement(schemas[it["pair"]], it["path"], it["label"])
    kw_counts[kw] += 1
    per_stratum[it["label"]][kw] += 1
exp_kw = {k["name"]: k["covers"] for k in x4["keywords"]}
exp_kw[X4.RES] = x4["upper_bound"]["not_coverable"]
if dict(kw_counts) != exp_kw:
    sys.exit(f"STOP: per-keyword counts differ from the frozen artifact\n"
             f"  this run: {dict(kw_counts)}\n  frozen  : {exp_kw}")
for lab, c in x4["per_stratum"].items():
    if dict(per_stratum[lab]) != c:
        sys.exit(f"STOP: stratum {lab} differs from the frozen artifact")

# ---- pass 2: the corrected basis
acts = collections.Counter()          # (pair, write-site pointer, keyword) -> escapes
inst = collections.Counter()          # (pair, instance-path pointer, keyword) -> escapes
cls = collections.Counter()           # class membership
mech_count = collections.Counter()    # composition of the 584 removals
excl = collections.Counter()          # reasons an escape needs no annotation
needed_kw = collections.Counter()
need_why = collections.Counter()      # why a needed escape is still unreachable
per_schema_needed = collections.Counter()
per_schema_block = collections.defaultdict(collections.Counter)

for it in items:
    pair, path, label = it["pair"], it["path"], it["label"]
    schema = schemas[pair]
    if label == REMOVAL:
        m = mechanism(schema, path)
        mech_count[m] += 1
        if m in ("declared-and-not-required", "pattern-property"):
            cls["already-expressed"] += 1
            excl[m] += 1
            continue
        # open-object: the schema never mentioned the key — an undeclared key, x-open-object
        kw, node, why = K1, A.schema_at(schema, tuple(path[:-1])), None
        if not isinstance(node, dict):
            why = "containing-node-not-located"
    else:
        kw, reason = X4.placement(schema, path, label)
        if kw == RES:
            cls["value-unconstrained" if "(ANOMALY)" not in label
                and label != "blanked-annotation-string" else "unconstrained-value"] += 1
            needed_kw[RES] += 1
            need_why[reason] += 1
            cls["needs-annotation"] += 1
            per_schema_needed[pair] += 1
            per_schema_block[pair][reason] += 1
            continue
        node, why = X6.annotation_node(schema, path), None
        if node is None:
            why = "annotation-node-not-located"
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
NEEDED = cls["needs-annotation"]
COVERABLE = needed_kw[K1] + needed_kw[K2]
UNREACHABLE = needed_kw[RES]
EXCLUDED = cls["already-expressed"]
if EXCLUDED != 450 or EXCLUDED + NEEDED != ALL:
    sys.exit(f"STOP: basis does not reconcile — excluded {EXCLUDED}, needed {NEEDED}, all {ALL}")
if COVERABLE + UNREACHABLE != NEEDED:
    sys.exit("STOP: coverable + unreachable != needed")

by_schema_sites = collections.defaultdict(list)
for (pair, _node, _kw), c in acts.items():
    by_schema_sites[pair].append(c)

top20 = sorted(acts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
top20_sites = collections.Counter(k[0] for k, _ in top20)
top20_esc = collections.Counter()
for (pair, _node, _kw), c in top20:
    top20_esc[pair] += c
spread = sorted(({"schema": k, "sites": v, "escapes": top20_esc[k]} for k, v in top20_sites.items()),
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
all_schemas = collections.Counter(i["pair"] for i in items)
none_needed = sorted(s for s in all_schemas if s not in per_schema_needed)

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

classes = {
    "already-expressed": {
        "escapes": EXCLUDED, "share_of_all": round(EXCLUDED / ALL, 6), "keyword": None,
        "composition": {"declared-and-not-required": mech_count["declared-and-not-required"],
                        "pattern-property": mech_count["pattern-property"]},
        "why": ("`required` is the instrument the author already used to say a declared key may be "
                "omitted, and a mapping/`patternProperties` node says its entries come and go; an "
                "annotation on top would restate either. The real tools agree — of the sampled "
                "deletion mutants every one that ran was accepted, apart from two where the "
                "remaining configuration genuinely stopped working."),
        "real_tool_spot_check": spot,
    },
    "undeclared-key": {
        "escapes": per_stratum["UNDECLARED-KEY"][K1] + per_stratum["UNDECLARED-KEY"][RES]
                   + mech_count["open-object"],
        "keyword": K1,
        "composition": {"added-undeclared-key": per_stratum["UNDECLARED-KEY"][K1]
                                                   + per_stratum["UNDECLARED-KEY"][RES],
                        "removed-undeclared-key": mech_count["open-object"]},
        "coverable": needed_kw[K1], "unreachable": per_stratum["UNDECLARED-KEY"][RES],
        "why": ("the schema never mentions the key — whether the instance gained it or lost it — so "
                "nothing expressed an opinion; the containing node's openness is the statement "
                "`x-open-object` records"),
    },
    "unconstrained-value": {
        "escapes": sum(per_stratum[l][K2] + per_stratum[l][RES] for l in per_stratum
                       if l not in (REMOVAL, "UNDECLARED-KEY")),
        "keyword": K2,
        "coverable": needed_kw[K2], "unreachable": UNREACHABLE - per_stratum["UNDECLARED-KEY"][RES],
        "why": ("nothing constrains the perturbed value; `x-open-value` records that the openness "
                "is deliberate, or the author writes the missing constraint"),
    },
}

summary = {
    "what": ("the workload measurement on the corrected basis: a removed key needs no annotation "
             "only when the schema stated the absence (declared-and-not-required, or a mapping "
             "node); a removed key the schema never mentioned is an undeclared key like any other"),
    "gate": gates,
    "population": {"escaped_mutants": ALL, "already_expressed": EXCLUDED,
                   "needs_annotation": NEEDED, "needs_share_of_all": round(NEEDED / ALL, 6),
                   "coverable": COVERABLE, "coverable_ratio": round(COVERABLE / NEEDED, 6),
                   "unreachable": UNREACHABLE,
                   "unreachable_ratio": round(UNREACHABLE / NEEDED, 6),
                   "unreachable_by_reason": dict(need_why.most_common()),
                   "schemas": len(per_schema), "write_sites": len(acts)},
    "classes": classes,
    "removal_breakdown": {
        "removed-optional-escapes": 584,
        "declared-and-not-required": mech_count["declared-and-not-required"],
        "pattern-property": mech_count["pattern-property"],
        "open-object-undeclared-key": mech_count["open-object"],
        "moved_into": classes["undeclared-key"]["keyword"],
        "note": ("reading the 584 removals against the schemas: 368 state the absence through "
                 "`properties` plus a missing `required` entry, 82 match a `patternProperties` "
                 "regex, and 134 are keys the containing node never mentions — those are "
                 "undeclared keys and carry work"),
    },
    "by_write_site": X6.curve(acts, COVERABLE, NEEDED, lambda pair, node, kw, c: {
        "schema": pair, "node": node, "keyword": kw, "covers": c}),
    "by_instance_path": X6.curve(inst, COVERABLE, NEEDED, lambda pair, node, kw, c: {
        "schema": pair, "node": node, "keyword": kw, "covers": c}),
    "top20_spread": {"n_schemas": len(spread), "escapes": cum20, "by_schema": spread,
                     "top3_escapes": sum(d["escapes"] for d in spread[:3]),
                     "top3_share": round(sum(d["escapes"] for d in spread[:3]) / cum20, 6)},
    "sites_to_half": {
        "unit": "write sites to classify >= 50% of that schema's own needed escapes",
        "n_schemas_with_needed_escapes": len(per_schema), "n_reaching_half": len(half),
        "n_not_reaching_half": len(blocked), "not_reaching_half": blocked,
        "min": half[0], "q1": q[0], "median": statistics.median(half), "q3": q[2], "max": half[-1],
        "distribution": {str(k): c for k, c in sorted(collections.Counter(half).items())},
        "estimator": QUARTILE_METHOD},
    "needed_escapes_per_schema": {"min": min(needed_counts), "median": statistics.median(needed_counts),
                                  "max": max(needed_counts)},
    "schemas_without_needed_escapes": {"n": len(none_needed), "list": none_needed},
    "reading": ("On this basis the annotation question is about the undeclared keys and the "
                "unconstrained values. The permitted absences are not work; the keys the schema "
                "never mentions are."),
}

assert sum(classes[c]["escapes"] for c in classes) == ALL
assert sum(classes["already-expressed"]["composition"].values()) == EXCLUDED
assert sum(mech_count.values()) == 584
assert mech_count["declared-and-not-required"] + mech_count["pattern-property"] == EXCLUDED
assert classes["undeclared-key"]["coverable"] + per_stratum["UNDECLARED-KEY"][RES] \
    == classes["undeclared-key"]["escapes"]
assert classes["unconstrained-value"]["coverable"] + classes["unconstrained-value"]["unreachable"] \
    == classes["unconstrained-value"]["escapes"]
assert COVERABLE == sum(classes[c]["coverable"] for c in ("undeclared-key", "unconstrained-value"))
assert sum(r["covered_by_write_sites"] for r in per_schema) == COVERABLE
assert sum(r["needed_escapes"] for r in per_schema) == NEEDED
assert cum20 == summary["by_write_site"]["annotation_acts"]["cumulative_at"]["20"]["escaped_mutants"]

if OUT.exists():
    sys.exit(f"REFUSING TO OVERWRITE {OUT.name} — results are write-once "
             f"(existing sha256 {sha256(OUT)[:12]}…)")
tmp = OUT.with_suffix(".json.part")
tmp.write_text(json.dumps({"summary": summary, "per_schema": per_schema}, ensure_ascii=False,
                          indent=1) + "\n", encoding="utf-8", newline="\n")
tmp.replace(OUT)

P = summary["population"]
C = summary["classes"]
curve = summary["by_write_site"]
c_acts = curve["annotation_acts"]
ip = summary["by_instance_path"]["annotation_acts"]
print(f"wrote {OUT.name}  sha256 {sha256(OUT)[:12]}…")
print(f"basis: already expressed {EXCLUDED} ({EXCLUDED/ALL:.2%}) = "
      f"{mech_count['declared-and-not-required']} declared-and-not-required + "
      f"{mech_count['pattern-property']} pattern-property; "
      f"open-object removals moved in: {mech_count['open-object']}")
print(f"needs annotation {NEEDED} ({NEEDED/ALL:.2%}): {K1} {C['undeclared-key']['escapes']} "
      f"(added {C['undeclared-key']['composition']['added-undeclared-key']} + removed "
      f"{C['undeclared-key']['composition']['removed-undeclared-key']}) | "
      f"{K2} {C['unconstrained-value']['escapes']}")
print(f"coverable {COVERABLE} ({P['coverable_ratio']:.2%} of needed); unreachable {UNREACHABLE} "
      f"({P['unreachable_ratio']:.2%}) reasons {P['unreachable_by_reason']}")
for n in ("1", "3", "5", "10", "20"):
    r = c_acts["cumulative_at"][n]
    print(f"  top {n:>2} sites -> {r['escaped_mutants']:>3} ({r['of_all_escapes']:.2%} of needed, "
          f"{r['of_reachable']:.2%} of coverable)")
for t in ("50%", "75%", "90%"):
    r = c_acts["annotations_needed_for"][t]
    print(f"  {t}: {r['annotations']} sites -> {r['escaped_mutants']} escapes")
print(f"  sites total {curve['annotation_acts_total']} / nodes {curve['annotated_nodes_total']} / "
      f"single-cover {curve['acts_covering_exactly_one']} / largest {curve['largest_single_act']['covers']}")
print(f"  same population, one site per use: {summary['by_instance_path']['annotation_acts_total']} "
      f"acts, top 20 cover {ip['cumulative_at']['20']['escaped_mutants']} "
      f"({ip['cumulative_at']['20']['of_all_escapes']:.2%})")
sp = summary["top20_spread"]
print(f"(a) top-20 sites span {sp['n_schemas']} schemas, {sp['escapes']} escapes; top3 = "
      f"{sp['top3_escapes']} ({sp['top3_share']:.1%})")
st = summary["sites_to_half"]
print(f"(b) sites to half a schema: min {st['min']} Q1 {st['q1']} median {st['median']} "
      f"Q3 {st['q3']} max {st['max']} "
      f"({st['n_reaching_half']}/{st['n_schemas_with_needed_escapes']} reach it)")
print(f"    distribution {st['distribution']}; needed per schema median "
      f"{summary['needed_escapes_per_schema']['median']} "
      f"(min {summary['needed_escapes_per_schema']['min']}, max "
      f"{summary['needed_escapes_per_schema']['max']})")
for b in st["not_reaching_half"]:
    print(f"    cannot reach half: {b['schema']} — {b['unreachable']} of its {b['needed_escapes']} "
          f"need-escapes unreachable {b['unreachable_reasons']}")
print(f"schemas with no needed escapes: {none_needed}")
print(f"spot check: {spot['deletions_released_and_accepted']}/{spot['deletions_sampled']} deletions "
      f"accepted, {spot['deletions_rejected']} rejected; blank-value released "
      f"{spot['blank_values_released']}")
