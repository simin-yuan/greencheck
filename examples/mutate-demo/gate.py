#!/usr/bin/env python3
"""A deliberately ordinary gate.

This is the kind of check most projects actually have: it confirms the file
parses, that every required key is present, and that no value is blank. It
reads as thorough. It is the gate under test in this example.

Exit 0 = accepted, non-zero = rejected.
"""
import json
import sys

REQUIRED = ["service", "region", "replicas", "owner"]


def main(path):
    try:
        with open(path, encoding="utf-8") as fh:
            config = json.load(fh)
    except Exception as e:
        print(f"not valid json: {e}")
        return 1

    missing = [k for k in REQUIRED if k not in config]
    if missing:
        print(f"missing keys: {missing}")
        return 1

    for key in REQUIRED:
        if config[key] in ("", None):
            print(f"empty value: {key}")
            return 1

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
