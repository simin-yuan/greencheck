#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenAPI 3.0 example-as-seed mutation study (see METHOD.md, frozen before the run).

    python study.py             # full run over out/sample.json
    python study.py --limit 3   # smoke test on the first 3 specs

Writes out/cases.csv, out/escapes.jsonl, out/results.json.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.environ.get("JSONSCHEMA_CLI") or \
    "jsonschema"
GREENCHECK = os.environ.get("GREENCHECK_REPO") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_EXAMPLE_BYTES = 8192
UNRESOLVED = object()

sys.path.insert(0, GREENCHECK)
import greencheck.mutate as gm  # noqa: E402

CP = "#/components/schemas/"


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


# ---------------------------------------------------------------- gate

def run_gate(spec_path, entrypoint, texts):
    """Judge texts against one entrypoint. Returns list of 'ACCEPT'|'REJECT'|'ENGINE-ERROR'.

    One CLI invocation for the whole batch (JSONL), per METHOD.md. Instruments carry
    no verdicts of their own - other than this CLI - so the exit code alone is not the
    reading; the per-entry `fail:` lines are, cross-checked against the summary line.
    """
    if not texts:
        return [], ""
    fd, tmp = tempfile.mkstemp(suffix=".jsonl", dir=os.path.join(HERE, "out"))
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            for t in texts:
                fh.write(json.dumps(json.loads(t), ensure_ascii=False, separators=(",", ":")) + "\n")
        cmd = [CLI, "validate", spec_path.replace("\\", "/"), tmp,
               "--entrypoint", entrypoint, "--continue", "--color", "never"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        failed = {int(m.group(1)) for m in re.finditer(r"^fail: .*?\(entry #(\d+)\)", out, re.M)}
        summary = re.search(r"(\d+) validated, (\d+) passed, (\d+) failed", out)
        if not summary:
            return ["ENGINE-ERROR"] * len(texts), out
        n_validated, _npass, nfail = (int(x) for x in summary.groups())
        if n_validated != len(texts):
            raise SystemExit(f"gate saw {n_validated} of {len(texts)} entrie<redacted-abs-path>]}")
        if len(failed) != nfail:
            raise SystemExit(f"fail lines ({len(failed)}) != summary failed ({nfail}):\n{out[-2000:]}")
        return [("REJECT" if i + 1 in failed else "ACCEPT") for i in range(len(texts))], out
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------- schema navigation

def _ptr(root, ref):
    tgt = root
    try:
        for part in ref[2:].split("/"):
            tgt = tgt[part.replace("~1", "/").replace("~0", "~")]
    except Exception:                                             # noqa: BLE001
        return UNRESOLVED
    return tgt


def resolve(node, root, depth=0):
    """($ref -> target, keeping siblings) plus the component name it came from."""
    if not isinstance(node, dict) or depth > 12:
        return node, None
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node, None
    name = ref[len(CP):] if ref.startswith(CP) and ref.count("/") == 3 else None
    if not ref.startswith("#/"):
        return UNRESOLVED, None
    tgt = _ptr(root, ref)
    if tgt is UNRESOLVED:
        return UNRESOLVED, None
    r, o = resolve(tgt, root, depth + 1)
    sib = {k: v for k, v in node.items() if k != "$ref"}
    if sib and isinstance(r, dict):
        m = dict(r)
        m.update(sib)
        r = m
    return r, (name or o)


def branches(node, root, depth=0):
    n, o = resolve(node, root)
    if n is UNRESOLVED:
        return [(UNRESOLVED, None)]
    if not isinstance(n, dict) or depth > 8:
        return [(n, o)] if isinstance(n, dict) else []
    out = [(n, o)]
    for kw in ("allOf", "anyOf", "oneOf"):
        for sub in n.get(kw) or []:
            out.extend(branches(sub, root, depth + 1))
    return out


def child(node, step, root):
    cands = []
    unresolved_seen = False
    for b, _bo in branches(node, root):
        if b is UNRESOLVED:
            unresolved_seen = True
            continue
        props = b.get("properties")
        if isinstance(step, str) and isinstance(props, dict) and step in props:
            cands.append(resolve(props[step], root))
            continue
        if isinstance(step, str):
            pp = b.get("patternProperties")
            if isinstance(pp, dict):
                hit = False
                for pat, sub in pp.items():
                    try:
                        if re.search(pat, step):
                            cands.append(resolve(sub, root))
                            hit = True
                    except re.error:
                        pass
                if hit:
                    continue
        if isinstance(step, int):
            it = b.get("items")
            if isinstance(it, dict):
                cands.append(resolve(it, root))
                continue
            if isinstance(it, list) and 0 <= step < len(it):
                cands.append(resolve(it[step], root))
                continue
    if any(c[0] is UNRESOLVED for c in cands):
        return UNRESOLVED, None
    if not cands and isinstance(step, str):
        for b, _bo in branches(node, root):
            if b is UNRESOLVED:
                continue
            ap = b.get("additionalProperties")
            if isinstance(ap, dict):
                c = resolve(ap, root)
                if c[0] is UNRESOLVED:
                    unresolved_seen = True
                    continue
                if c[0] is not None:
                    cands.append(c)
    if not cands:
        # "nothing declares this key" is only sayable if nothing was unreachable:
        # an unresolvable $ref may well declare it.
        return (UNRESOLVED, None) if unresolved_seen else (None, None)
    if len(cands) == 1:
        return cands[0]
    origins = [o for _n, o in cands if o]
    return {"allOf": [n for n, _o in cands]}, (origins[0] if origins else None)


def schema_at(docroot, start, path):
    """Resolve `path` from `start`, with $refs resolved against the whole document."""
    node, origin = start, None
    for step in path:
        node, o = child(node, step, docroot)
        if o:
            origin = o
        if node is None or node is UNRESOLVED:
            return node, origin
    return node, origin


def declared_key(node, key, root):
    """Is `key` named by properties / matched by patternProperties anywhere above?"""
    for b, _o in branches(node, root):
        if b is UNRESOLVED:
            continue
        props = b.get("properties")
        if isinstance(props, dict) and key in props:
            return True
        pp = b.get("patternProperties")
        if isinstance(pp, dict):
            for pat in pp:
                try:
                    if re.search(pat, key):
                        return True
                except re.error:
                    pass
    return False


def required_of(node, root):
    out = set()
    for b, _o in branches(node, root):
        if b is UNRESOLVED:
            continue
        r = b.get("required")
        if isinstance(r, list):
            out |= set(r)
    return out


def constraints(node, root):
    """All keywords declared on the node, tagged with whether the mutated value
    violates them independently (violated -> a keyword existed and should have fired)."""
    out = []
    for b, _o in branches(node, root):
        if b is UNRESOLVED:
            continue
        for kw in ("minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
                   "exclusiveMaximum", "multipleOf", "pattern", "enum", "const", "format",
                   "minItems", "maxItems", "minProperties"):
            if kw in b:
                out.append((kw, b[kw]))
    return out


def violates(kw, spec, val):
    """Does `val` violate this single keyword? None = cannot decide here."""
    try:
        if kw == "minLength":
            return isinstance(val, str) and len(val) < spec
        if kw == "maxLength":
            return isinstance(val, str) and len(val) > spec
        if kw == "minimum":
            return isinstance(val, (int, float)) and not isinstance(val, bool) and val < spec
        if kw == "maximum":
            return isinstance(val, (int, float)) and not isinstance(val, bool) and val > spec
        if kw in ("exclusiveMinimum", "exclusiveMaximum"):        # OAS 3.0 uses booleans
            return None
        if kw == "multipleOf":
            return isinstance(val, (int, float)) and not isinstance(val, bool) and \
                round(val / spec, 10) % 1 != 0
        if kw == "pattern":
            return isinstance(val, str) and re.search(spec, val) is None
        if kw == "enum":
            return val not in spec
        if kw == "const":
            return val != spec
        if kw == "minItems":
            return isinstance(val, list) and len(val) < spec
        if kw == "maxItems":
            return isinstance(val, list) and len(val) > spec
        if kw == "minProperties":
            return isinstance(val, dict) and len(val) < spec
        if kw == "format":
            return None
    except Exception:                                             # noqa: BLE001
        return None
    return None


# ---------------------------------------------------------------- diff / classify

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


def classify(docroot, entry_schema, path, kind, oval, mval):
    """-> (class, detail). Mutual exclusive; see METHOD.md strata."""
    parent = schema_at(docroot, entry_schema, path[:-1]) if path else (entry_schema, None)
    leaf, origin = schema_at(docroot, entry_schema, path)
    key = path[-1] if path and isinstance(path[-1], str) else None

    if kind == "removed":
        if parent[0] is UNRESOLVED:
            return "unresolved", "removed-unresolved"
        if parent[0] is None or key is None:
            return "undeclared-key", "container-not-declared"
        if key in required_of(parent[0], docroot):
            return "ANOMALY", "removed-required"
        if declared_key(parent[0], key, docroot):
            return "declared-optional-removed", "declared,not-required"
        return "undeclared-key", "container-declared,key-not"

    if kind in ("arrayshrunk", "added"):
        if leaf is UNRESOLVED:
            return "unresolved", kind
        if kind == "added":
            return "ANOMALY", "added-key"
        bad = [(k, v) for k, v in constraints(leaf, docroot) if violates(k, v, mval)]
        return ("ANOMALY" if bad else "value-level"), f"{kind}|{'/'.join(k for k, _ in bad) or 'no-minItems'}"

    if kind == "changed":
        if leaf is UNRESOLVED:
            return "unresolved", "changed-unresolved"
        if leaf is None:
            return "undeclared-key", "value-on-undeclared-path"
        bad = [(k, v) for k, v in constraints(leaf, docroot) if violates(k, v, mval) is True]
        if bad:
            return "ANOMALY", "declared-and-violated:" + "/".join(k for k, _ in bad)
        if isinstance(oval, bool):
            detail = "bool"
        elif isinstance(oval, (int, float)) and mval == 0:
            detail = "number->0"
        elif isinstance(oval, str) and mval == "":
            detail = "string->empty"
        elif isinstance(oval, str):
            detail = "identifier"
        else:
            detail = type(oval).__name__
        return "value-level", detail

    return "other", kind


# ---------------------------------------------------------------- OAS30 cross-check

def rewrite_for_oas30(doc, name):
    """Embed components under definitions and rewrite #/components/schemas/X refs."""
    comps = ((doc.get("components") or {}).get("schemas") or {})
    s = json.dumps(comps, ensure_ascii=False)
    s = re.sub(r'"#/components/schemas/([^"]+)"',
               lambda m: json.dumps("#/definitions/" + m.group(1).replace("~", "~0").replace("/", "~1")),
               s)
    defs = json.loads(s)
    root = {"$ref": "#/definitions/" + name.replace("~", "~0").replace("/", "~1"),
            "definitions": defs}
    leftover = len(re.findall(r'"\$ref"\s*:\s*"(?!\#/)', s)) + len(re.findall(r'"\$ref"\s*:\s*"\#/(?!definitions/)', s))
    return root, leftover


# ---------------------------------------------------------------- driver

def build_cases(sample, limit=None):
    cases = []
    specs = sample["specs"][:limit] if limit else sample["specs"]
    for r in specs:
        p = os.path.join(HERE, r["path"])
        doc = json.load(open(p, encoding="utf-8"))
        schemas = ((doc.get("components") or {}).get("schemas") or {})
        # v2: the per-spec cap was decided in METHOD_v2.md, before the run.
        for name in (r.get("chosen") or sorted(schemas)):
            node = schemas[name]
            if not isinstance(node, dict) or "example" not in node:
                continue
            text = json.dumps(node["example"], indent=2, ensure_ascii=False)
            size = len(text.encode("utf-8"))
            cases.append({"spec": r["name"], "spec_path": p, "spec_sha256": r["sha256"],
                          "schema": name, "entrypoint": CP + name,
                          "example": node["example"], "text": text, "bytes": size,
                          "over_cap": size > MAX_EXAMPLE_BYTES})
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    sample = json.load(open(os.path.join(HERE, "out", "sample.json"), encoding="utf-8"))
    cases = build_cases(sample, args.limit)
    print(f"cases with a top-level example: {len(cases)} "
          f"(over {MAX_EXAMPLE_BYTES}B: {sum(c['over_cap'] for c in cases)})")

    # negative control: a synthetic document with a required property, judged through
    # the same JSONL path. One entry must pass and one must fail - both directions of
    # the verdict mapping are exercised in a single call, or nothing downstream counts.
    ctl_doc = os.path.join(HERE, "out", "_control.json")
    json.dump({"openapi": "3.0.0", "info": {"title": "control", "version": "1"},
               "paths": {},
               "components": {"schemas": {"Ctl": {"type": "object", "required": ["id"],
                                                  "properties": {"id": {"type": "string"}}}}}},
              open(ctl_doc, "w", encoding="utf-8"))
    verdict, _out = run_gate(ctl_doc, CP + "Ctl", ['{"id": "x"}', '{"nope": 1}'])
    if verdict != ["ACCEPT", "REJECT"]:
        raise SystemExit(f"negative control failed: {verdict} - gate is not reading instances")

    rows, escapes = [], []
    for c in cases:
        rec = {"spec": c["spec"], "schema": c["schema"], "bytes": c["bytes"],
               "over_cap": c["over_cap"], "baseline": None, "mutants": 0,
               "parse_broken": 0, "no_op": 0, "schema_rejected": 0, "escaped": 0,
               "engine_error": 0, "xcheck_divergence": 0, "xcheck_compared": 0, "xcheck_error": 0}
        if c["over_cap"]:
            rec["baseline"] = "SKIPPED-OVER-CAP"
            rows.append(rec)
            continue
        v, out = run_gate(c["spec_path"], c["entrypoint"], [c["text"]])
        rec["baseline"] = v[0]
        if rec["baseline"] != "ACCEPT":
            rows.append(rec)
            continue

        base = {"instance.json": c["text"]}
        orig = c["example"]
        judged, meta = [], []
        for name, patch in gm.build_mutants(base):
            content = next(iter(patch.values()))
            if content is None or not content.strip():
                rec["parse_broken"] += 1
                meta.append((name, "parse_broken", None))
                continue
            try:
                inst = json.loads(content)
            except Exception:                                     # noqa: BLE001
                rec["parse_broken"] += 1
                meta.append((name, "parse_broken", None))
                continue
            if inst == orig:
                rec["no_op"] += 1
                meta.append((name, "no_op", None))
                continue
            judged.append(content)
            meta.append((name, "judged", inst))
        rec["mutants"] = len(meta)

        verdicts, _o = run_gate(c["spec_path"], c["entrypoint"], judged) if judged else ([], "")
        vit = iter(verdicts)
        doc = json.load(open(c["spec_path"], encoding="utf-8"))
        entry_schema = doc["components"]["schemas"][c["schema"]]
        oas = None
        try:
            from openapi_schema_validator import OAS30Validator
            oas_root, leftover = rewrite_for_oas30(doc, c["schema"])
            oas = (OAS30Validator(oas_root), leftover)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  [xcheck unavailable] {exc}")

        for name, state, inst in meta:
            if state != "judged":
                continue
            verdict = next(vit, "ENGINE-ERROR")
            if verdict == "ENGINE-ERROR":
                rec["engine_error"] += 1
                continue
            if verdict == "REJECT":
                rec["schema_rejected"] += 1
            else:
                rec["escaped"] += 1
                changes = [ch for ch in diff(orig, inst) if ch[1] in ("removed", "changed", "arrayshrunk", "added")]
                changes.sort(key=lambda ch: (len(ch[0]), str(ch[0])))
                if not changes:
                    cls, detail, path, origin = "ANOMALY", "no-detectable-change", (), None
                else:
                    path, kind = changes[0]
                    try:
                        oval = value_at(orig, path) if kind != "removed" else None
                        mval = value_at(inst, path) if kind != "removed" else None
                    except Exception:                             # noqa: BLE001
                        oval = mval = None
                    cls, detail = classify(doc, entry_schema, path, kind, oval, mval)
                    _leaf, origin = schema_at(doc, entry_schema, path)
                escapes.append({"spec": c["spec"], "schema": c["schema"], "op": name.split(":", 1)[0],
                                "mutant": name, "path": [p for p in path], "class": cls,
                                "detail": detail, "owner": origin})
            # cross-check
            if oas is not None and inst is not None:
                try:
                    oas_ok = not list(oas[0].iter_errors(inst))
                    rec["xcheck_compared"] += 1
                    if (oas_ok and verdict == "REJECT") or ((not oas_ok) and verdict == "ACCEPT"):
                        rec["xcheck_divergence"] += 1
                        escapes.append({"spec": c["spec"], "schema": c["schema"], "op": name.split(":", 1)[0],
                                        "mutant": name, "path": [], "class": "DIVERGENCE",
                                        "detail": f"sourcemeta={verdict}, oas30={'ACCEPT' if oas_ok else 'REJECT'}",
                                        "owner": None})
                except Exception:                                 # noqa: BLE001
                    rec["xcheck_error"] = rec.get("xcheck_error", 0) + 1
        rows.append(rec)
        print(f"  {c['spec'][:38]:<38} {c['schema'][:28]:<28} base=ACCEPT mut={rec['mutants']:3d} "
              f"rej={rec['schema_rejected']:3d} esc={rec['escaped']:3d} "
              f"xdiv={rec['xcheck_divergence']:2d}")

    with open(os.path.join(HERE, "out", "cases.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(HERE, "out", "escapes.jsonl"), "w", encoding="utf-8") as fh:
        for e in escapes:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    json.dump({"rows": rows}, open(os.path.join(HERE, "out", "results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nwrote out/cases.csv ({len(rows)} cases), out/escapes.jsonl ({len(escapes)} rows)")


if __name__ == "__main__":
    main()
