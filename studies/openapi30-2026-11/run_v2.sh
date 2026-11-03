#!/usr/bin/env bash
# One command reproduces the whole v2 study. Run from this directory.
#   ./run_v2.sh            full chain on the frozen sample
#   ./run_v2.sh --rescan   re-read all 1704 documents to rebuild out/eligible.json (3 min)
#   ./run_v2.sh --from-scan  rescan, then re-sample with the same seed
set -euo pipefail
PY="python"

case "${1:-}" in
  --rescan)    "$PY" scan_eligible.py --scan; exit 0 ;;
  --from-scan) "$PY" scan_eligible.py --scan; "$PY" scan_eligible.py --sample ;;
  *)           "$PY" scan_eligible.py --sample ;;
esac

"$PY" study.py       | tee out/run.log      # mutation + Sourcemeta CLI + cross-check
"$PY" check.py       | tee out/check.log    # every instance re-judged one call at a time
"$PY" stats.py       | tee out/stats.txt    # every number the report quotes
"$PY" static_stats.py | tee out/bases.txt   # allOf bases, additionalProperties, required
"$PY" audit_v1_required.py | tee out/audit_v1.txt   # the v1 headline claim, re-checked
