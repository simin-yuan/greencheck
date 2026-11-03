#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-check the study's gate against ajv — the engine SchemaStore's own CI uses.

The study's gate is Python `jsonschema`; SchemaStore's CI is ajv (Node). Two
implementations can disagree, so this dumps the same judged mutant set, validates
it with ajv (formats off, strict off — mirroring the Python gate), and reports
every disagreement.

Usage:  python xcheck.py            (dump -> node -> compare)
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "repo")
SCHEMAS = os.path.join(REPO, "src", "schemas", "json")
OUT = os.path.join(HERE, "out")
XC = os.path.join(OUT, "_xcheck")
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
_s = importlib.util.spec_from_file_location("gate_json", os.path.join(HERE, "gate_json.py"))
gj = importlib.util.module_from_spec(_s)
_s.loader.exec_module(gj)


def dump():
    os.makedirs(XC, exist_ok=True)
    for f in os.listdir(XC):
        if f.startswith(("p", "ajv")):
            os.remove(os.path.join(XC, f))
    res = json.load(open(os.path.join(OUT, "results.json"), encoding="utf-8"))
    rows = [r for r in res["rows"] if r.get("mutants_total")]
    from jsonschema import validators
    n = 0
    for i, r in enumerate(rows):
        spath = os.path.join(SCHEMAS, r["schema"])
        schema = json.load(open(spath, encoding="utf-8"))
        base = {"instance.json": open(os.path.join(REPO, r["instance"].replace("/", os.sep)),
                                      encoding="utf-8").read()}
        orig = json.loads(base["instance.json"])
        V = validators.validator_for(schema)
        v = V(schema, registry=gj._make_registry(os.path.abspath(SCHEMAS)))
        muts = []
        for name, patch in gm.build_mutants(base):
            content = next(iter(patch.values()))
            if content is None:
                continue
            try:
                inst = json.loads(content)
            except Exception:
                continue
            if inst == orig:
                continue                       # no-op: not a mutation
            muts.append({"id": len(muts), "name": name,
                         "py": "reject" if list(v.iter_errors(inst)) else "release",
                         "text": content})
        json.dump({"schema": r["schema"], "instance": r["instance"], "mutants": muts},
                  open(os.path.join(XC, f"p{i}.json"), "w", encoding="utf-8"), ensure_ascii=False)
        n += len(muts)
    print(f"dumped {n} judged mutants over {len(rows)} pairs -> {XC}")
    return len(rows)


def run_node():
    r = subprocess.run(["node", os.path.join(HERE, "xcheck_ajv.js"), REPO, XC],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit("node failed")


def compare(npairs):
    ajv = json.load(open(os.path.join(XC, "ajv.json"), encoding="utf-8"))
    tot = collections.Counter()
    div = []
    per_pair = {}
    for i in range(npairs):
        m = json.load(open(os.path.join(XC, f"p{i}.json"), encoding="utf-8"))
        a = ajv.get(str(i))
        if a is None or a.get("error"):
            tot["pair_compile_error"] += 1
            per_pair[m["schema"]] = {"status": "ajv-error", "detail": (a or {}).get("error", "no result")}
            continue
        verd = a["verdicts"]
        pd = collections.Counter()
        for mu in m["mutants"]:
            av = verd.get(str(mu["id"]))
            if av is None:
                tot["missing"] += 1
                continue
            tot["judged"] += 1
            pd[av] += 1
            if av != mu["py"]:
                tot["divergence"] += 1
                if len(div) < 25:
                    div.append({"schema": m["schema"], "mutant": mu["name"],
                                "python": mu["py"], "ajv": av})
        per_pair[m["schema"]] = {"status": "ok", "python": dict(pd) if False else None,
                                 "ajv": dict(pd)}
    out = {"judged_total": tot["judged"], "divergences": tot["divergence"],
           "pair_compile_errors": tot["pair_compile_error"],
           "examples": div, "per_pair": per_pair}
    json.dump(out, open(os.path.join(XC, "compare.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nengine cross-check: {tot['judged']} mutants judged by both engines; "
          f"DIVERGENCES = {tot['divergence']}   (ajv pair compile errors: {tot['pair_compile_error']})")
    for d in div[:10]:
        print("  DIVERGE", d)
    if tot["pair_compile_error"]:
        print("  pairs ajv could not compile:")
        for k, v in per_pair.items():
            if v["status"] != "ok":
                print("   ", k, str(v["detail"])[:120])


if __name__ == "__main__":
    import re
    if "--compare-only" in sys.argv:
        n = len([f for f in os.listdir(XC) if re.match(r"^p\d+\.json$", f)])
    else:
        n = dump()
    run_node()
    compare(n)
