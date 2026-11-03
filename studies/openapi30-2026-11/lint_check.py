#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does the Sourcemeta CLI lint catch the examples that contradict their own schema?

Runs `jsonschema lint --json` over the six documents of interest and records, per file:
exit code, whether the run produced JSON at all, every rule id it emitted, whether any
rule id or message mentions examples, and the raw text output for the record.

Five documents:
  * three that contain an example rejected by its own schema (isendpro, personio,
    vtex Subscriptions);
  * two that the CLI refuses to read at all (lgtm, vtex Marketplace).

    python lint_check.py
"""
from __future__ import annotations

import json
import os
import subprocess
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = "jsonschema"
OUT = os.path.join(HERE, "out", "lint")

FILES = [
    ("isendpro.com_1.1.1.json", "example rejected: /sms string vs array"),
    ("personio.de_personnel_1.0.json", "examples rejected: /attendances/0/comment, /comment"),
    ("vtex.local_Subscriptions-API-(v2)_1.0.json", "example rejected: /orderCustomDataAppId"),
    ("lgtm.com_v1.0.json", "document refused by validate (exit 4)"),
    ("vtex.local_Marketplace-Protocol_1.0.json", "document refused by validate (exit 4)"),
]


def run(name):
    path = os.path.join(HERE, "specs", name)
    r = subprocess.run([CLI, "lint", path, "--json", "--color", "never"],
                       capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace")
    err = (r.stderr or b"").decode("utf-8", "replace")
    text = subprocess.run([CLI, "lint", path, "--color", "never"],
                          capture_output=True)
    txt = (text.stdout or b"").decode("utf-8", "replace") + \
          (text.stderr or b"").decode("utf-8", "replace")
    return r.returncode, out, err, txt


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = {}
    for name, why in FILES:
        rc, out, err, txt = run(name)
        with open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(txt)
        with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out or err)

        ids, hits = Counter(), []
        try:
            data = json.loads(out)
        except Exception:                                          # noqa: BLE001
            data = None
        if isinstance(data, dict):
            for e in data.get("errors") or []:
                rid = e.get("id") or "<no id>"
                ids[rid] += 1
                blob = json.dumps(e, ensure_ascii=False).lower()
                if "example" in blob:
                    hits.append({"id": rid, "message": e.get("message"),
                                 "schemaLocation": e.get("schemaLocation")})

        summary[name] = {
            "why": why, "exit": rc, "json_parsed": isinstance(data, dict),
            "valid": data.get("valid") if isinstance(data, dict) else None,
            "health": data.get("health") if isinstance(data, dict) else None,
            "rules": dict(ids), "example_hits": hits,
            "stderr_head": err.strip().splitlines()[:3],
        }
        print(f"== {name}  ({why})")
        print(f"   exit={rc}  json={'yes' if isinstance(data, dict) else 'no'}"
              f"  valid={summary[name]['valid']}  health={summary[name]['health']}"
              f"  rules={len(ids)}  total findings={sum(ids.values())}")
        if err.strip():
            print(f"   stderr: {err.strip().splitlines()[0][:120]}")
        if hits:
            for h in hits[:6]:
                print(f"   EXAMPLE RULE: {h['id']}  at {h['schemaLocation']}: {h['message']}")
        else:
            print("   EXAMPLE RULE: none")
        ex_ids = [k for k in ids if "example" in k.lower()]
        print(f"   rule ids mentioning example: {ex_ids if ex_ids else 'none'}")
        print()

    json.dump(summary, open(os.path.join(HERE, "out", "lint_summary.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
