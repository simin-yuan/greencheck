"""The gate under test: SchemaStore's official package.json schema, via jsonschema.

Nothing here is ours except the glue. The schema is third-party, the validator
is third-party, the instance is third-party. This file exists so that
`greencheck mutate` has a command it can call once per mutant.

Exit code 0 = the schema accepted the file, 1 = it rejected it.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator, validators

SCHEMA = Path(tempfile.gettempdir()) / "greencheck-third-party" / "package.schema.json"


def main() -> int:
    if not SCHEMA.exists():
        print(f"run.py has not fetched the schema yet: {SCHEMA}", file=sys.stderr)
        return 2
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    instance = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    cls = validators.validator_for(schema, default=Draft202012Validator)
    errors = sorted(cls(schema).iter_errors(instance), key=str)
    for err in errors:
        print(f"INVALID {list(err.path)}: {err.message}")
    print("valid" if not errors else "invalid")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
