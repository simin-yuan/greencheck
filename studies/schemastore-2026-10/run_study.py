#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SchemaStore x greencheck mutation study — one command, fully local.

Question: sample real schemas from SchemaStore, run greencheck's mutation engine
against each one's own validator gate, and measure what fraction of broken
instances the schema *releases* (accepts) and which mutation class leaks most.

METHOD (fixed, documented, deterministic)
-----------------------------------------
Source  : a SchemaStore/schemastore checkout, pinned to COMMIT below.
          Uses src/schemas/json/<stem>.json and src/test/<dir>/<instance>.
Candidate a schema is a candidate iff its own test dir src/test/<stem>/ (EXACT name
set       match — SchemaStore maps schemaName->schemaId via cli.js:236/262) holds
          >=1 *.json file; the instance used is the lexicographically first one.
          src/test/* are positive tests: they must validate, so the baseline gate
          must ACCEPT. A pair whose baseline fails (or whose schema errors on the
          local engine) is skipped and its reason recorded.
Size cap: instances larger than --max-bytes (default 8192) are excluded, so the
          line-mutation classes stay bounded and comparable across pairs.
Sample  : random.Random(SEED).sample(sorted(candidates), N)  — deterministic.
Gate    : gate_json.py, the `jsonschema` engine (validator_for -> auto-dialect),
          SchemaStore absolute $refs resolved from the local checkout (no network).
Run     : greencheck's real mutate CLI, one gate invocation per mutant.
          A mutant ESCAPED when the gate still exits 0 (schema ACCEPTS a mutated
          instance). A mutant is CAUGHT when the gate exits non-zero.
Metrics : escaped_ratio = escaped / (caught + escaped); escape rate per operator
          class (drop-file / empty-file / drop-section / drop-line / blank-value /
          break-ref / dup-id).

Reproducible:
    python run_study.py            # uses ./repo, 40 pairs, seed 20261011
    python run_study.py --bootstrap   # (re)extract ./repo from --bare first

Everything is written under --out. Nothing is pushed anywhere.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# Pinned SchemaStore revision (commit exists upstream: SchemaStore/schemastore).
SCHEMASTORE_COMMIT = "778278bb947af933582e6423fddeaf0c1cb97fc8"
SCHEMASTORE_COMMIT_DATE = "2026-09-26T22:45:07Z"
SCHEMASTORE_URL = "https://github.com/SchemaStore/schemastore.git"
# Bare clone location. Prefer $SCHEMASTORE_BARE, then a local copy if present,
# else a portable path next to this script (and auto-clone from SCHEMASTORE_URL).
_LOCAL_BARE = "<redacted-abs-path>"
DEFAULT_BARE = (os.environ.get("SCHEMASTORE_BARE")
                or (_LOCAL_BARE if os.path.isdir(_LOCAL_BARE)
                    else os.path.join(HERE, "_schemastore.git")))

OPERATORS = ["drop-file", "empty-file", "drop-section", "drop-line",
             "blank-value", "break-ref", "dup-id"]


def op_of(name: str) -> str:
    return name.split(":", 1)[0]


def find_greencheck() -> str:
    for cand in (os.environ.get("GREENCHECK_REPO"),
                 "<redacted-abs-path>",
                 os.path.join(HERE, "greencheck")):
        if cand and os.path.isfile(os.path.join(cand, "greencheck", "mutate.py")):
            return cand
    raise SystemExit("greencheck checkout not found; set GREENCHECK_REPO")


def _load_gate_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gate_json", os.path.join(HERE, "gate_json.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def decompose(pair_dir, schema_path, gj):
    """Second pass over the SAME mutants greencheck generated, run in-process:
    split the set into parse-broken / schema-rejected / schema-accepted.

    The CLI already tells us accepted(=escaped) vs rejected, but a rejection can
    come from the JSON parser rather than from the schema. This separates them so
    'released' is not diluted by mutants the schema never had to judge, and it
    doubles as a cross-check on the CLI's escaped count."""
    from pathlib import Path
    from jsonschema import validators
    import greencheck.mutate as gm

    base = gm.collect(Path(pair_dir))
    base_obj = {}
    for rel, txt in base.items():
        try:
            base_obj[rel] = json.loads(txt)
        except Exception:
            base_obj[rel] = None
    mutants = gm.build_mutants(base)
    schema = json.load(open(schema_path, encoding="utf-8"))
    V = validators.validator_for(schema)
    v = V(schema, registry=gj._make_registry(os.path.dirname(os.path.abspath(schema_path))))

    out = {"mutants": len(mutants), "parse_broken": 0, "semantic_reject": 0,
           "escaped_ip": 0, "no_op": 0, "gate_env": 0, "by_op": {}}
    for name, patch in mutants:
        op = op_of(name)
        rel = next(iter(patch))
        content = patch[rel]
        d = out["by_op"].setdefault(op, {"total": 0, "escaped_ip": 0, "parse_broken": 0,
                                         "semantic_reject": 0, "no_op": 0, "gate_env": 0})
        d["total"] += 1
        if content is None:
            cls = "parse_broken"
        else:
            try:
                inst = json.loads(content)
            except Exception:
                cls = "parse_broken"
            else:
                # blank-value emits a NO-OP mutant when the value is already in the
                # blank state (0 -> 0, false -> false): it parses back identical to
                # the original, so it is not a mutation at all yet greencheck counts
                # it as escaped. Keep it out of the escape numerator.
                if base_obj.get(rel) is not None and inst == base_obj[rel]:
                    cls = "no_op"
                else:
                    try:
                        cls = "semantic_reject" if list(v.iter_errors(inst)) else "escaped_ip"
                    except Exception:
                        cls = "gate_env"
        out[cls] += 1
        d[cls] += 1
    return out


def bootstrap_repo(bare: str, dest: str) -> None:
    """Extract src/schemas/json + src/test from a bare SchemaStore clone.

    Pinned: archive SCHEMASTORE_COMMIT (NOT HEAD) and assert the object exists —
    a bare clone whose HEAD moves must not silently change the tree.
    """
    if not os.path.isdir(bare):
        print(f"cloning {SCHEMASTORE_URL} -> {bare} (bare)")
        subprocess.run(["git", "clone", "--bare", SCHEMASTORE_URL, bare], check=True)
    rev = subprocess.run(["git", "--git-dir=" + bare, "rev-parse",
                          SCHEMASTORE_COMMIT + "^{commit}"],
                         capture_output=True, text=True)
    if rev.returncode != 0 or rev.stdout.strip() != SCHEMASTORE_COMMIT:
        raise SystemExit(f"pinned commit {SCHEMASTORE_COMMIT} not found in {bare}: "
                         f"get it with `git clone {SCHEMASTORE_URL}`")
    os.makedirs(dest, exist_ok=True)
    tar = os.path.join(HERE, "schemastore_src.tar")
    with open(tar, "wb") as fh:
        subprocess.run(["git", "--git-dir=" + bare, "archive", SCHEMASTORE_COMMIT,
                        "src/schemas/json", "src/test"],
                       check=True, stdout=fh)
    subprocess.run(["tar", "-xf", tar, "-C", dest], check=True)


def build_candidates(repo: str, max_bytes: int):
    schemas_dir = os.path.join(repo, "src", "schemas", "json")
    test_dir = os.path.join(repo, "src", "test")
    schemas = sorted(f for f in os.listdir(schemas_dir) if f.endswith(".json"))
    tdirs = sorted(d for d in os.listdir(test_dir)
                   if os.path.isdir(os.path.join(test_dir, d)))
    cands, skipped = [], []
    for s in schemas:
        stem = s[:-5]
        jsons = []
        # SchemaStore's own harness maps a schema to its test dir by EXACT name:
        #   schemaId = schemaName.replace('.json','')   (cli.js:236)
        #   positiveTestDir = TestPositiveDir/schemaId  (cli.js:262)
        # A prefix match here would confuse e.g. `github-workflow` with
        # `github-workflow-template-properties`, so use exact equality only.
        d = os.path.join(test_dir, stem)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                fp = os.path.join(d, f)
                if os.path.isfile(fp) and f.endswith(".json"):
                    jsons.append(fp)
        if not jsons:
            continue
        inst = jsons[0]
        sz = os.path.getsize(inst)
        if sz > max_bytes:
            skipped.append((s, inst, sz, "over_size_cap"))
            continue
        cands.append((s, os.path.relpath(inst, repo).replace("\\", "/"), sz))
    return cands, skipped


def run_pair(pair_dir, schema_path, gate_py, greencheck_repo, workers, timeout):
    """Run greencheck's mutate CLI for one (schema, instance). Return report dict."""
    gate = '"%s" "%s" {target} "%s"' % (sys.executable, gate_py, schema_path)
    cmd = [sys.executable, "-m", "greencheck.cli", "mutate",
           "--gate", gate, "--target", pair_dir, "--workers", str(workers),
           "--report", os.path.join(pair_dir, "..", "report.json"), "--json"]
    env = dict(os.environ, PYTHONPATH=greencheck_repo)
    p = subprocess.run(cmd, capture_output=True, text=False, cwd=HERE,
                       env=env, timeout=timeout)
    out = (p.stdout or b"").decode("utf-8", "replace")
    start = out.find("{")
    if start < 0:
        return {"error": "no json report", "stdout": out[-800:],
                "stderr": (p.stderr or b"").decode("utf-8", "replace")[-800:]}
    return json.loads(out[start:])


def aggregate(rows, seed=20261011):
    tot = sum(r["mutants_total"] for r in rows)
    esc = sum(r["escaped_count"] for r in rows)
    caught = sum(r["caught_count"] for r in rows)
    per_op_tot = {o: 0 for o in OPERATORS}
    per_op_esc = {o: 0 for o in OPERATORS}
    for r in rows:
        rep = r["report"]
        for n in rep.get("caught", []):
            if op_of(n) in per_op_tot:
                per_op_tot[op_of(n)] += 1
        for n in rep.get("escaped", []):
            if op_of(n) in per_op_tot:
                per_op_tot[op_of(n)] += 1
                per_op_esc[op_of(n)] += 1
    op_table = []
    for o in OPERATORS:
        t, e = per_op_tot[o], per_op_esc[o]
        op_table.append({"operator": o, "mutants": t, "escaped": e,
                         "escape_rate": (e / t) if t else None})
    dec = {"mutants": 0, "parse_broken": 0, "semantic_reject": 0,
           "escaped_ip": 0, "no_op": 0, "gate_env": 0}
    mism = 0
    dec_err = 0
    pair_judged = []
    for r in rows:
        d = r.get("decomp") or {}
        if "escaped_ip" not in d:
            dec_err += 1
            continue
        for k in dec:
            dec[k] += d.get(k, 0)
        if d.get("escaped_ip", 0) + d.get("no_op", 0) != r["escaped_count"]:
            mism += 1
        judged = d.get("escaped_ip", 0) + d.get("semantic_reject", 0)
        if judged:
            pair_judged.append((d.get("escaped_ip", 0), judged))
    rates = sorted(r["escaped_count"] / r["mutants_total"]
                   for r in rows if r.get("mutants_total"))

    def _med(xs):
        n = len(xs)
        if not n:
            return None
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    pair_stats = {"n": len(rates), "median_escape_rate": _med(rates),
                  "p25": rates[len(rates) // 4] if rates else None,
                  "p75": rates[(3 * len(rates)) // 4] if rates else None,
                  "min": rates[0] if rates else None,
                  "max": rates[-1] if rates else None}

    # Primary metric: release rate among mutants the schema actually JUDGED
    # (parse-ok and not a no-op). 45.8% of mutants die in the JSON parser and
    # never reach the schema, so they must not sit in the denominator.
    judged_total = dec["escaped_ip"] + dec["semantic_reject"]
    escaped_effective = dec["escaped_ip"]
    primary = escaped_effective / judged_total if judged_total else None

    # Cluster bootstrap over PAIRS: the pair is the independent unit (mutants in
    # one pair share an instance and a schema). Fixed seed -> deterministic.
    ci = [None, None]
    if pair_judged:
        rb = random.Random(0xB007)
        boots, k = [], len(pair_judged)
        for _ in range(5000):
            e = n = 0
            for _ in range(k):
                ee, nn = pair_judged[rb.randrange(k)]
                e += ee
                n += nn
            if n:
                boots.append(e / n)
        boots.sort()
        if boots:
            ci = [boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]]
    judged_rates = sorted(e / n for e, n in pair_judged)

    return {"pairs": len(rows), "mutants_total": tot, "caught": caught,
            "escaped": esc, "escaped_ratio": (esc / tot) if tot else None,
            "escapes_effective": escaped_effective, "judged_total": judged_total,
            "escaped_ratio_judged": primary, "escaped_ratio_judged_ci95": ci,
            "no_op_mutants": dec["no_op"],
            "by_operator": op_table, "decomposition": dec,
            "cli_vs_inproc_escape_mismatch": mism, "decomposition_errors": dec_err,
            "pair_escape_rate": pair_stats,
            "pair_escape_rate_judged": {"n": len(judged_rates), "median": _med(judged_rates),
                                        "p25": judged_rates[len(judged_rates) // 4] if judged_rates else None,
                                        "p75": judged_rates[(3 * len(judged_rates)) // 4] if judged_rates else None}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.join(HERE, "repo"))
    ap.add_argument("--bare", default=DEFAULT_BARE)
    ap.add_argument("--bootstrap", action="store_true")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--max-bytes", type=int, default=8192)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--force", action="store_true",
                    help="allow running into a non-empty --out (overwrites artefacts)")
    a = ap.parse_args()

    # --- source preparation is its own step: --bootstrap must NOT also run the study
    if a.bootstrap or not os.path.isdir(os.path.join(a.repo, "src")):
        print("extracting SchemaStore tree ->", a.repo, flush=True)
        bootstrap_repo(a.bare, a.repo)
    if a.bootstrap:
        print("--bootstrap: source tree ready; NOT running the study.", flush=True)
        return 0

    # --- guard: a run must never silently clobber a previous run's artefacts
    if os.path.isdir(a.out) and os.listdir(a.out) and not a.force:
        print("REFUSING to run: --out '%s' is not empty. Point --out at a fresh "
              "directory, or pass --force to overwrite." % a.out, flush=True)
        return 3

    greencheck_repo = find_greencheck()
    gc_version = subprocess.run([sys.executable, "-m", "greencheck.cli", "--version"],
                                capture_output=True, text=True, cwd=HERE,
                                env=dict(os.environ, PYTHONPATH=greencheck_repo)).stdout.strip()
    gate_py = os.path.join(HERE, "gate_json.py")
    gj_mod = _load_gate_module()
    if greencheck_repo not in sys.path:
        sys.path.insert(0, greencheck_repo)

    cands, skipped = build_candidates(a.repo, a.max_bytes)
    cands_sorted = sorted(cands)
    n = min(a.n, len(cands_sorted))
    rng = random.Random(a.seed)
    sample = rng.sample(cands_sorted, n)
    sample.sort()

    os.makedirs(a.out, exist_ok=True)
    # --- per-run scratch: two runs can never share (and corrupt) a _work directory
    run_id = "%s_%d" % (time.strftime("%Y%m%d-%H%M%S"), os.getpid())
    work = os.path.join(a.out, "_work_" + run_id)
    print(f"schemastore @ {SCHEMASTORE_COMMIT[:12]}  greencheck {gc_version}", flush=True)
    print(f"run_id={run_id}  work={work}", flush=True)
    print(f"candidates={len(cands)}  size-capped-out={len(skipped)}  "
          f"sample={n}  seed={a.seed}", flush=True)

    rows, t0 = [], time.time()
    for i, (schema, rel_inst, sz) in enumerate(sample, 1):
        pair_dir = os.path.join(work, "%03d" % i)
        os.makedirs(pair_dir, exist_ok=True)
        src = os.path.join(a.repo, rel_inst)
        with open(src, "rb") as fh:
            data = fh.read()
        with open(os.path.join(pair_dir, "instance.json"), "wb") as fh:
            fh.write(data)
        schema_path = os.path.join(a.repo, "src", "schemas", "json", schema)
        try:
            rep = run_pair(pair_dir, schema_path, gate_py, greencheck_repo,
                           a.workers, a.timeout)
        except subprocess.TimeoutExpired:
            rep = {"error": "timeout"}
        row = {"schema": schema, "instance": rel_inst, "instance_bytes": sz}
        if "error" in rep or not rep.get("baseline_ok"):
            row["skipped"] = rep.get("error") or "baseline_failed"
            row["baseline_exit_code"] = rep.get("baseline_exit_code")
            print(f"  [{i:>2}/{n}] SKIP  {schema}  ({row['skipped']})", flush=True)
        else:
            row.update({"mutants_total": rep["mutants_total"],
                        "caught_count": rep["caught_count"],
                        "escaped_count": rep["escaped_count"],
                        "report": rep})
            try:
                row["decomp"] = decompose(pair_dir, schema_path, gj_mod)
            except Exception as e:
                row["decomp"] = {"error": f"{type(e).__name__}: {e}"}
            print(f"  [{i:>2}/{n}] ok    {schema}  "
                  f"mutants={rep['mutants_total']} escaped={rep['escaped_count']}", flush=True)
        rows.append(row)

    ok_rows = [r for r in rows if "report" in r]
    agg = aggregate(ok_rows, a.seed)
    import importlib.metadata as _md
    gc_commit = subprocess.run(["git", "-C", greencheck_repo, "rev-parse", "HEAD"],
                               capture_output=True, text=True).stdout.strip()
    agg.update({"greencheck": gc_version, "greencheck_commit": gc_commit,
                "jsonschema": _md.version("jsonschema"),
                "seed": a.seed, "n_requested": a.n,
                "schemastore_commit": SCHEMASTORE_COMMIT,
                "schemastore_commit_date": SCHEMASTORE_COMMIT_DATE,
                "max_bytes": a.max_bytes, "elapsed_sec": round(time.time() - t0, 1),
                "python": sys.version.split()[0],
                "skipped": [{"schema": r["schema"], "reason": r["skipped"]}
                            for r in rows if "skipped" in r]})

    with open(os.path.join(a.out, "results.json"), "w", encoding="utf-8") as fh:
        json.dump({"aggregate": agg, "rows": rows}, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(a.out, "samples.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["schema", "instance", "instance_bytes", "mutants", "caught",
                    "escaped", "escape_rate", "skipped"])
        for r in rows:
            if "report" in r:
                rt = r["escaped_count"] / r["mutants_total"] if r["mutants_total"] else ""
                w.writerow([r["schema"], r["instance"], r["instance_bytes"],
                            r["mutants_total"], r["caught_count"], r["escaped_count"],
                            f"{rt:.4f}" if rt != "" else "", ""])
            else:
                w.writerow([r["schema"], r["instance"], r["instance_bytes"], "", "", "", "",
                            r["skipped"]])

    print("\n" + "=" * 66)
    print(f"pairs run            : {agg['pairs']}  (skipped {len(agg['skipped'])})")
    print(f"mutants total        : {agg['mutants_total']}")
    print(f"caught               : {agg['caught']}")
    print(f"escaped (released)   : {agg['escaped']}")
    if agg["escaped_ratio"] is not None:
        print(f"escaped ratio        : {agg['escaped_ratio']*100:.1f}%   (raw: released/total)")
    d = agg["decomposition"]
    print(f"  parse-broken       : {d['parse_broken']}  (rejected by the JSON parser)")
    print(f"  no-op mutants      : {d['no_op']}  (value already blank: 0->0, false->false)")
    print(f"  semantic reject    : {d['semantic_reject']}  (rejected by a schema keyword)")
    print(f"  released           : {d['escaped_ip']}  (schema accepted a broken instance)")
    if agg["escaped_ratio_judged"] is not None:
        lo, hi = agg["escaped_ratio_judged_ci95"]
        print(f"PRIMARY release rate : {agg['escaped_ratio_judged']*100:.1f}%  "
              f"({agg['escapes_effective']}/{agg['judged_total']} judged)  "
              f"95% CI [{lo*100:.1f}%, {hi*100:.1f}%] (pair cluster bootstrap)")
    pj = agg["pair_escape_rate_judged"]
    if pj["n"]:
        print(f"  per-pair (judged)  : median {pj['median']*100:.1f}%  "
              f"p25 {pj['p25']*100:.1f}%  p75 {pj['p75']*100:.1f}%  (n={pj['n']})")
    ps = agg["pair_escape_rate"]
    if ps["n"]:
        print(f"  per-pair (raw)     : median {ps['median_escape_rate']*100:.1f}%  "
              f"p25 {ps['p25']*100:.1f}%  p75 {ps['p75']*100:.1f}%")
    print(f"  CLI vs in-proc escape mismatch pairs: {agg['cli_vs_inproc_escape_mismatch']}"
          f"   (decomposition errors: {agg['decomposition_errors']})")
    print("escape rate by operator class:")
    for o in agg["by_operator"]:
        rate = "n/a" if o["escape_rate"] is None else f"{o['escape_rate']*100:5.1f}%"
        print(f"    {o['operator']:<13} {o['escaped']:>5}/{o['mutants']:<5} {rate}")
    print(f"wrote {a.out}/results.json + samples.csv   ({agg['elapsed_sec']}s)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
