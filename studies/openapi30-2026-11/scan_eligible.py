#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eligibility scan: which OpenAPI 3.0 documents in APIs.guru carry an example worth seeding from?

Reads every document in the frame once, counts component schemas at /components/schemas/<Name>
with a top-level `example` that serialises to <= 8192 bytes, then throws the document away.
Only the 20 sampled documents are kept under specs/.

    python scan_eligible.py --scan     # ~1700 downloads; writes out/eligible.json
    python scan_eligible.py --sample   # picks 20 with seed 20261103 and downloads them
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261103
MAX_EXAMPLE_BYTES = 8192
N = 20
CAP_PER_SPEC = 5
V1 = os.environ.get("V1_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            os.pardir, "schemastore-2026-10", "out")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def fetch(url, dest_dir):
    fd, tmp = tempfile.mkstemp(dir=dest_dir, suffix=".json")
    os.close(fd)
    req = urllib.request.Request(url, headers={"User-Agent": "greencheck-study/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as fh:
            shutil.copyfileobj(r, fh)
        return tmp
    except Exception:                                             # noqa: BLE001
        os.unlink(tmp)
        raise


def count_examples(path):
    doc = json.load(open(path, encoding="utf-8"))
    schemas = ((doc.get("components") or {}).get("schemas") or {})
    names = []
    for name, node in schemas.items():
        if isinstance(node, dict) and "example" in node:
            text = json.dumps(node["example"], indent=2, ensure_ascii=False)
            if len(text.encode("utf-8")) <= MAX_EXAMPLE_BYTES:
                names.append(name)
    return names, (doc.get("openapi") or "")


def scan(frame):
    tmpdir = os.path.join(HERE, "out", "_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    done = [0]

    def one(item):
        name, url = item
        try:
            p = fetch(url, tmpdir)
            try:
                names, ver = count_examples(p)
            finally:
                os.unlink(p)
            done[0] += 1
            if done[0] % 100 == 0:
                print(f"  {done[0]}/{len(frame)}", flush=True)
            return {"name": name, "url": url, "openapi": ver, "examples": names,
                    "n": len(names)}
        except Exception as exc:                                  # noqa: BLE001
            done[0] += 1
            return {"name": name, "url": url, "error": str(exc)[:200], "examples": [], "n": 0}

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(one, frame))
    shutil.rmtree(tmpdir, ignore_errors=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args()
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "specs"), exist_ok=True)

    idx = os.path.join(HERE, "list.json")
    if not os.path.exists(idx):
        fetch("https://api.apis.guru/v2/list.json", HERE)
    if not os.path.exists(idx):
        raise SystemExit("list.json: not shipped and not fetchable")
    data = json.load(open(idx, encoding="utf-8"))
    frame = sorted((f"{p}/{v}", info["swaggerUrl"])
                   for p, meta in data.items()
                   for v, info in (meta.get("versions") or {}).items()
                   if str(info.get("openapiVer", "")).startswith("3.0")
                   and str(info.get("swaggerUrl", "")).endswith(".json"))

    if args.scan:
        print(f"frame: {len(frame)}; scanning ...")
        rows = scan(frame)
        elig = [r for r in rows if r["n"] > 0]
        err = [r for r in rows if "error" in r]
        json.dump({"index_sha256": sha256(idx), "frame_size": len(frame),
                   "eligible": len(elig), "errors": len(err), "rows": rows},
                  open(os.path.join(HERE, "out", "eligible.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"eligible specs: {len(elig)} / {len(frame)}  (fetch errors: {len(err)})")
        print(f"cases available: {sum(r['n'] for r in elig)}")
        return

    doc = json.load(open(os.path.join(HERE, "out", "eligible.json"), encoding="utf-8"))
    elig = sorted(r["name"] for r in doc["rows"] if r["n"] > 0)
    picked = sorted(random.Random(SEED).sample(elig, N))
    by_name = {r["name"]: r for r in doc["rows"]}
    specs = []
    for name in picked:
        url = by_name[name]["url"]
        dest = os.path.join(HERE, "specs", name.replace("/", "_").replace(":", "_") + ".json")
        if not os.path.exists(dest):
            tmp = fetch(url, os.path.join(HERE, "out"))
            shutil.move(tmp, dest)
        names = sorted(by_name[name]["examples"])
        if len(names) > CAP_PER_SPEC:
            names = sorted(random.Random(SEED).sample(names, CAP_PER_SPEC))
        specs.append({"name": name, "url": url, "path": os.path.relpath(dest, HERE),
                      "sha256": sha256(dest), "bytes": os.path.getsize(dest),
                      "openapi": by_name[name]["openapi"],
                      "eligible_schemas": by_name[name]["n"], "chosen": names})
        print(f"  {name[:44]:<44} eligible={by_name[name]['n']:3d} chosen={len(names)}")
    json.dump({"index_sha256": doc["index_sha256"], "seed": SEED, "n": N,
               "cap_per_spec": CAP_PER_SPEC, "frame_size": doc["frame_size"],
               "eligible_size": len(elig), "specs": specs},
              open(os.path.join(HERE, "out", "sample.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nwrote out/sample.json: {len(specs)} specs, {sum(len(s['chosen']) for s in specs)} cases")


if __name__ == "__main__":
    main()
