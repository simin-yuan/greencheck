#!/usr/bin/env python3
"""Install the built wheel into a throwaway environment and run the installed command.

Why this exists as a script rather than as a few lines of shell in the workflow
file: the shell version used `/tmp/...` and `$RUNNER_TEMP/...` and `/dev/null`,
which is fine on Linux and macOS and produced exit 127 on Windows. A check that
only works on the machine it was written on is not a check.

The defect this catches is specific and it has happened: `greencheck/skills/`
once lived outside the package, so `greencheck skills` worked in a checkout and
failed for every user who installed the package. Nothing in the unit tests
noticed, because the unit tests read the files from the source tree.

Usage:
    python tools/smoke_install.py dist

Exits 0 only if all of the following hold, in a virtualenv that has nothing in
it but this wheel:
    greencheck --version    prints the version in pyproject.toml
    greencheck skills       lists five skills
    greencheck demo         runs to completion and prints a verdict
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile
import venv

REPO = pathlib.Path(__file__).resolve().parent.parent

# Windows gives a Python 3.9 process a cp1252 stdout when it is writing to a
# pipe rather than a console. The CLI under test prints an em-dash, so printing
# its output raised UnicodeEncodeError and the check failed on Windows only.
# The encoding of this script's own output is not something the check should
# depend on.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover — old interpreters
        pass


def declared_version() -> str:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "(.*)"', text, re.M)
    if not m:
        raise SystemExit("could not read version from pyproject.toml")
    return m.group(1)


def bin_dir(env: pathlib.Path) -> pathlib.Path:
    """Windows puts console scripts in Scripts/, everything else in bin/."""
    return env / ("Scripts" if sys.platform == "win32" else "bin")


def find_wheel(dist: pathlib.Path) -> pathlib.Path:
    wheels = sorted(dist.glob("*.whl"))
    if not wheels:
        raise SystemExit(f"no wheel in {dist} — build first")
    return wheels[-1]


def run(argv: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kw,
    )


def main(argv: list[str]) -> int:
    dist = pathlib.Path(argv[1] if len(argv) > 1 else "dist").resolve()
    wheel = find_wheel(dist)
    expected = declared_version()

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gc-smoke-"))
    env = tmp / "venv"
    print(f"wheel      : {wheel.name}")
    print(f"version    : {expected}")
    print(f"venv       : {env}")

    venv.EnvBuilder(with_pip=True, clear=True).create(env)
    python = bin_dir(env) / ("python.exe" if sys.platform == "win32" else "python")
    if not python.exists():  # some layouts keep the real interpreter elsewhere
        alt = env / ("python.exe" if sys.platform == "win32" else "bin/python3")
        python = alt if alt.exists() else python

    install = run([str(python), "-m", "pip", "install", "--quiet", "--no-input", str(wheel)])
    if install.returncode != 0:
        print("FAIL: pip install of the wheel failed", file=sys.stderr)
        print(install.stdout, install.stderr, file=sys.stderr)
        return 1

    # A bare `pip list` here is the point of the whole script: if the package
    # dragged a dependency in, the "no dependencies on purpose" claim is false.
    freeze = run([str(python), "-m", "pip", "freeze"])
    installed = [
        line.split("==")[0].lower()
        for line in freeze.stdout.splitlines()
        if "==" in line
    ]
    extra = [p for p in installed if p not in {"greencheck", "pip", "setuptools", "wheel"}]
    print(f"installed  : {', '.join(installed) or '(nothing)'}")
    if extra:
        print(f"FAIL: the wheel pulled in dependencies: {extra}", file=sys.stderr)
        return 1

    script = bin_dir(env) / ("greencheck.exe" if sys.platform == "win32" else "greencheck")
    if not script.exists():
        print(f"FAIL: no console script at {script}", file=sys.stderr)
        return 1

    failures: list[str] = []

    version = run([str(script), "--version"])
    print(f"\n$ greencheck --version\n{version.stdout.strip()}{version.stderr.strip()}")
    if version.returncode != 0 or expected not in version.stdout + version.stderr:
        failures.append(f"--version did not report {expected}")

    skills = run([str(script), "skills"])
    print(f"\n$ greencheck skills\n{skills.stdout.strip()}")
    if skills.returncode != 0:
        failures.append("skills exited non-zero")
    for name in ("positive-control", "dimension-scope", "dead-check", "bare-zero", "measurement-or-decoration"):
        if name not in skills.stdout:
            failures.append(f"skills did not list {name} — is skills/ inside the package?")

    demo = run([str(script), "demo"])
    tail = "\n".join(demo.stdout.strip().splitlines()[-4:])
    print(f"\n$ greencheck demo\n{tail}")
    if demo.returncode != 0 or not demo.stdout.strip():
        failures.append("demo exited non-zero or printed nothing")

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK — the wheel installs clean, carries no dependencies, and the installed command works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
