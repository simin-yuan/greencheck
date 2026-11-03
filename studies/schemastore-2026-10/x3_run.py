#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x3_run.py — 附录 B 主运行：第三引擎（Sourcemeta jsonschema v17.2.0）重判 1791 条冻结变异。

预注册见 TRUTH_PROTOCOL_APPENDIX_B.md（sha256 94cfa281…，已钉进 TRUTH_PROTOCOL.sha256）。
规则不得在此处偏离：判定只认 rc（0=valid / 2=invalid / 其它=ENGINE-ERROR）；
基线不干净的对排除；两次运行（-F 与不带 -F）。

输入（只读）：out/_xcheck/p{0..37}.json
产物（一次写入）：out/x3_sourcemeta.json, out/x3_baseline.json
"""
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from onceio import write_once  # noqa: E402

BIN = ("<redacted-abs-path>"
       "jsonschema-17.2.0-windows-x86_64/bin/jsonschema.exe")
# E5: 该 CLI 在 MSYS 下读不了非 ASCII 路径 -> 输入暂存到纯 ASCII 路径
STAGE_ROOT = r"<redacted-abs-path>"
NP = 38
SETTINGS = {"fmt_assert": ["-F"], "fmt_annot": []}


def run_one(schema_rel, inst_rel, setting_flags):
    """返回 (rc, stdout, stderr)。cwd 恒为 STAGE_ROOT（ASCII），只传相对路径。"""
    cmd = [BIN, "validate", schema_rel, inst_rel, "--json"] + setting_flags
    try:
        p = subprocess.run(cmd, cwd=STAGE_ROOT, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return (-99, "", "TIMEOUT")
    return (p.returncode,
            p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def main():
    if os.path.exists(STAGE_ROOT):
        shutil.rmtree(STAGE_ROOT)
    os.makedirs(STAGE_ROOT)

    pairs = []
    for i in range(NP):
        d = json.load(open(f"{BASE}/out/_xcheck/p{i}.json", encoding="utf-8"))
        pairs.append(d)

    # ---- 暂存（字节级复制，内容不变；E5） ----
    jobs_inst = []   # (pair_i, kind, mid, rel_path)
    for i, d in enumerate(pairs):
        pd = os.path.join(STAGE_ROOT, f"p{i}")
        os.makedirs(pd, exist_ok=True)
        for src, dst in ((f"{BASE}/repo/src/schemas/json/{d['schema']}", f"p{i}/s.json"),):
            shutil.copyfile(src, os.path.join(STAGE_ROOT, dst))
        # E7: `d["instance"]` holds a PATH inside the repo clone, not the instance text.
        # v1 staged the path string as if it were the document, so every baseline was rc=6.
        shutil.copyfile(os.path.join(BASE, "repo", d["instance"]),
                        os.path.join(STAGE_ROOT, f"p{i}/base.json"))
        for m in d["mutants"]:
            with open(os.path.join(STAGE_ROOT, f"p{i}/m{m['id']}.json"), "w", encoding="utf-8") as f:
                f.write(m["text"])
            jobs_inst.append((i, "mutant", m["id"], f"p{i}/m{m['id']}.json"))
        jobs_inst.append((i, "baseline", None, f"p{i}/base.json"))

    # ---- 逐条跑，两次设置 ----
    tasks = [(i, kind, mid, rel, sk, fl)
             for (i, kind, mid, rel) in jobs_inst
             for sk, fl in SETTINGS.items()]
    print(f"invocations: {len(tasks)} (={len(jobs_inst)} items x {len(SETTINGS)} settings)")

    results = {}
    done = 0
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(run_one, f"p{i}/s.json", rel, fl): (i, kind, mid, sk)
                for (i, kind, mid, rel, sk, fl) in tasks}
        for fut in cf.as_completed(futs):
            i, kind, mid, sk = futs[fut]
            rc, out, err = fut.result()
            results[(i, kind, mid, sk)] = (rc, out, err)
            done += 1
            if done % 400 == 0:
                print(f"  {done}/{len(tasks)}")

    def verdict(rc):
        return {0: "valid", 2: "invalid"}.get(rc, f"ENGINE-ERROR(rc={rc})")

    # ---- 基线（B.4） ----
    baseline = {}
    excluded = []
    for i, d in enumerate(pairs):
        row = {"schema": d["schema"], "pair_index": i}
        for sk in SETTINGS:
            rc = results[(i, "baseline", None, sk)][0]
            row[sk] = {"rc": rc, "verdict": verdict(rc)}
        row["clean"] = all(row[sk]["verdict"] == "valid" for sk in SETTINGS)
        rcs = {row[sk]["rc"] for sk in SETTINGS}
        if row["clean"]:
            row["exclusion"] = None
        elif 4 in rcs:
            row["exclusion"] = "engine_refuses_schema(rc=4)"
        elif 2 in rcs:
            row["exclusion"] = "baseline_invalid(rc=2)"
        else:
            row["exclusion"] = "baseline_engine_error"
        baseline[d["schema"]] = row
        if not row["clean"]:
            excluded.append(d["schema"])
    print("\nbaseline clean: %d/%d | excluded: %s"
          % (sum(1 for v in baseline.values() if v["clean"]), len(pairs), excluded or "none"))

    # ---- 逐条判定 ----
    rows = []
    eng_err = {}
    for i, d in enumerate(pairs):
        for m in d["mutants"]:
            r = {"pair_index": i, "schema": d["schema"], "mid": m["id"], "name": m["name"],
                 "py": m.get("py")}
            for sk in SETTINGS:
                rc, out, err = results[(i, "mutant", m["id"], sk)]
                r[sk] = verdict(rc)
                r[sk + "_rc"] = rc
                if rc not in (0, 2):
                    eng_err[(i, m["id"], sk)] = (out[:400] + err[:400])
                elif out.strip():
                    r[sk + "_errors"] = out
            rows.append(r)

    print(f"mutant rows: {len(rows)} | ENGINE-ERROR cells: {len(eng_err)}")
    for k, v in list(eng_err.items())[:5]:
        print("   ", k, v[:160])

    write_once(f"{BASE}/out/x3_baseline_v2.json", {
        "tool": "sourcemeta/jsonschema v17.2.0 windows-x86_64",
        "rule": "B.4 — a pair whose pristine instance is not clean under BOTH settings is excluded",
        "baseline_source": "repo/<instance path field> copied byte-for-byte (E7)",
        "pairs": baseline, "excluded": excluded,
    })
    write_once(f"{BASE}/out/x3_sourcemeta_v2.json", {
        "tool": "sourcemeta/jsonschema v17.2.0 windows-x86_64",
        "settings": SETTINGS, "rows": rows,
        "engine_error": {str(k): v for k, v in eng_err.items()},
    })
    print("wrote out/x3_baseline_v2.json, out/x3_sourcemeta_v2.json")


if __name__ == "__main__":
    main()
