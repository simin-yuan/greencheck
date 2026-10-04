"""Run greencheck's mutation loop against a validator we did not write.

Third-party inputs, pinned by commit, downloaded at run time:

  instance : expressjs/express  package.json
  validator: SchemaStore       package.json schema, driven through jsonschema

The gate command is passed to `greencheck mutate`, which runs it once per
mutant and reports which mutants it let through.

    pip install jsonschema
    python case_study/third_party/run.py

Artifacts written to `results/` are redacted before they land: absolute paths
become `<path>`, and e-mail addresses that the borrowed file itself contains
(they arrive inside mutant names, which quote the line they deleted) become
`<redacted-email>`. Publishing someone else's contributors' addresses is not a
side effect this repository is willing to have.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
INPUTS = Path(tempfile.gettempdir()) / "greencheck-third-party"
RESULTS = HERE / "results"
GATE_CMD = "python case_study/third_party/gate.py {target}/package.json"

EXPRESS_SHA = "9a34acf03cb818ff3f8bc40e44176e277a25cbb9"
SCHEMASTORE_SHA = "95515978468ac0373ed052151745715c05c32fd5"
URLS = {
    "instance/package.json": (
        f"https://raw.githubusercontent.com/expressjs/express/{EXPRESS_SHA}/package.json"
    ),
    "package.schema.json": (
        "https://raw.githubusercontent.com/SchemaStore/schemastore/"
        f"{SCHEMASTORE_SHA}/src/schemas/json/package.json"
    ),
}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
PATH = re.compile(r"(?<![\w])(?:[A-Za-z]:[\/]|\\)[^\s\"'<>]*")


def redact(text: str) -> str:
    return EMAIL.sub("<redacted-email>", PATH.sub("<path>", text))


def fetch() -> None:
    for rel, url in URLS.items():
        dest = INPUTS / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=60) as response:  # noqa: S310 - pinned https URLs
            dest.write_bytes(response.read())
        print(f"fetched {rel} ({dest.stat().st_size} bytes) -> {dest}")


def main() -> int:
    fetch()
    RESULTS.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS / "mutate-report.json"
    cmd = [
        sys.executable, "-m", "greencheck.cli", "mutate",
        "--gate", GATE_CMD,
        "--target", str(INPUTS / "instance"),
        "--report", str(report_path),
    ]
    shown = GATE_CMD.replace("{target}", "<workdir>")
    print("$ python -m greencheck.cli mutate --gate \"%s\" --target <downloads>/instance"
          % shown)
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    output = redact((proc.stdout or "") + (proc.stderr or ""))
    (RESULTS / "mutate-output.txt").write_text(output, encoding="utf-8")
    print(output)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["gate"] = GATE_CMD
    report["target"] = "<downloads>/instance"
    for key in ("caught", "escaped"):
        report[key] = [redact(name) for name in report.get(key, [])]
    for item in report.get("escaped_detail", []):
        item["mutant"] = redact(item["mutant"])
    report["redacted"] = (
        "absolute paths replaced with <path>; e-mail addresses taken from the "
        "borrowed instance file replaced with <redacted-email>"
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("mutate exit code:", proc.returncode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
