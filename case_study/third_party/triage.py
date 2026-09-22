"""Ask the consumer about three of the mutants the schema accepted.

`run.py` establishes *which* mutants a third-party validator lets through. That
list is a question list, not a finding list — the tool says so itself. This
script settles three of the questions by handing the mutant to the thing that
actually consumes a `package.json`, `npm`, and recording what it says.

    python case_study/third_party/triage.py

Needs `npm` on PATH. The mutants are produced by greencheck's own operators,
selected by name, so they are the same three this case study reports on.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from greencheck import mutate as M  # noqa: E402

INPUTS = Path(tempfile.gettempdir()) / "greencheck-third-party"

CASES = {
    "blank-value on the root version": 'blank-value:package.json:4:"version":',
    "the name line deleted": 'drop-line:package.json:2:"name": "express",',
    "the license line deleted": 'drop-line:package.json:15:"license": "MIT",',
}


def main() -> int:
    if shutil.which("npm") is None:
        print("npm not found on PATH; nothing to ask the consumer.")
        return 2
    instance = INPUTS / "instance"
    if not instance.is_dir():
        print(f"run.py has not fetched the instance yet ({instance}).")
        return 2

    base = M.collect(instance)
    mutants = dict(M.build_mutants(base))
    work = Path(tempfile.mkdtemp(prefix="greencheck-triage-"))
    schema_ok = 0
    npm_ok = 0

    for label, name in CASES.items():
        patch = mutants.get(name)
        if patch is None:
            print(f"[?] {label}: mutant {name!r} not produced from this input")
            continue
        case = work / label.split()[0].replace("-", "_")
        case.mkdir(parents=True, exist_ok=True)
        for rel, content in M.collect(instance).items():
            (case / rel).write_text(content, encoding="utf-8")
        for rel, content in patch.items():
            target = case / rel
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(content, encoding="utf-8")

        gate = subprocess.run(
            [sys.executable, str(HERE / "gate.py"), str(case / "package.json")],
            capture_output=True, text=True,
        )
        npm = subprocess.run(
            ["npm", "pack", "--dry-run"], cwd=case, capture_output=True, text=True,
            shell=(sys.platform == "win32"),
        )
        schema_ok += gate.returncode == 0
        npm_ok += npm.returncode == 0
        first = next((ln for ln in (npm.stderr or "").splitlines() if "error" in ln.lower()),
                     "(no error line)")
        print(f"{label}")
        print(f"    schema (jsonschema + SchemaStore): rc={gate.returncode} "
              f"{'accepts it' if gate.returncode == 0 else 'rejects it'}")
        print(f"    npm pack --dry-run               : rc={npm.returncode} "
              f"{'accepts it' if npm.returncode == 0 else 'refuses it -> ' + first}")
    print(f"\nschema accepted {schema_ok}/{len(CASES)} of these mutants; "
          f"npm accepted {npm_ok}/{len(CASES)}.")
    print("The gap between those two numbers is the finding. The mutants both "
          "accept are not gaps in anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
