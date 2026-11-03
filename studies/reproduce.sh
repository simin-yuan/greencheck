#!/usr/bin/env bash
# Reproduce every number in "What a JSON Schema accepts isn't always what it meant".
#
#   ./studies/reproduce.sh            offline: re-derive the numbers from the shipped artifacts
#   ./studies/reproduce.sh --fetch    full: re-download the sample and re-run the mutation study
#
# Environment:
#   PYTHON           interpreter to use (default: python3)
#   JSONSCHEMA_CLI   path to the Sourcemeta CLI (default: jsonschema on PATH)
#                    https://github.com/sourcemeta/jsonschema/releases
#   GREENCHECK_REPO  path to this repository (default: two levels above this file)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
py="${PYTHON:-python3}"
export JSONSCHEMA_CLI="${JSONSCHEMA_CLI:-jsonschema}"
export GREENCHECK_REPO="${GREENCHECK_REPO:-$(cd "$here/.." && pwd)}"

if [ "${1:-}" = "--fetch" ]; then
  cd "$here/openapi30-2026-11"
  echo "== scanning the APIs.guru index for documents with usable examples"
  "$py" scan_eligible.py --scan
  echo "== drawing 20 documents with seed 20261103 and capping at 5 examples each"
  "$py" scan_eligible.py --sample
  echo "== mutating and judging (Sourcemeta CLI, then openapi-schema-validator)"
  "$py" study.py
  echo "== re-judging every instance one call at a time"
  "$py" check.py
  echo "== writing out/stats.txt"
  "$py" stats.py
  echo "== static questions the mutation run cannot answer"
  "$py" static_stats.py
fi

cd "$here/openapi30-2026-11"
echo "== merging the nine strata into 499 / 333 / 550"
"$py" map_strata.py
echo
echo "== every field of x16 the article quotes"
"$py" x16_numbers.py
echo
echo "offline numbers re-derived. Full re-run: $0 --fetch"
