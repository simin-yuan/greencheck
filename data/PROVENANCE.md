# Provenance and anonymisation

## What is published

| file | contents | transformation |
|---|---|---|
| `ledger_metric_samples.jsonl` | 84 samples recorded by a self-assessment job in production | field names neutralised; **no value, timestamp or count altered** |
| `gate_daily.jsonl` | per-day event counts from a guard log | aggregated; raw lines not published |
| `gate_summary.json` | window totals, firing count, first firing, silent days | aggregated; raw lines not published |

## Transformation rules

### Metric ledger — names only

Two field names referred to the operator and to the agent by name. They are
replaced with neutral identifiers (`user_refs_recent`, `self_refs_recent`) by
`tools/anonymise.py`. The replacement map lives in
`tools/field_renames.local.json`, which is gitignored — the names being
removed are themselves the sensitive part, so the map cannot ship with the
tool.

Every other byte is unchanged: same sample count, same timestamps, same values,
same non-English structure keys.

**Consequence:** any analysis that runs on the private ledger runs on this one
and produces the same numbers. That is the point of restricting the transform
to names.

### Guard log — aggregation, not redaction

The guard log is **not published in any redacted form**. Its lines contain
filesystem paths, host identifiers, session tokens and operator-specific
strings at high frequency, and redacting them line by line is a losing game:
each pass invites the assumption that the pass was complete.

Instead only counts survive: how many events per day, per event type, per tool,
plus window totals. The claims in the case study are all claims about counts,
so aggregation loses nothing the argument needs.

Aggregation is the anonymisation. There is no later step where raw lines get
published.

## The leak gate

`tools/anonymise.py` will not certify a run it cannot first demonstrate is
capable of failing:

- **Generic patterns** ship with the tool (drive paths, POSIX home
  directories, UNC shares, e-mail addresses, credential shapes, PEM blocks,
  bare IPv4). These are the same for every operator, so they can be public.
- **Operator patterns** live in `tools/forbidden.local.txt`, gitignored.
- `--self-test` runs every generic pattern against an input that provably
  contains its trigger and fails the run if any pattern stays silent.

The self-test exists because of the package's own thesis: a gate that has never
been observed to fire is not a gate. A leak check that has never been observed
to catch anything is a comment.

## Reproducing the datasets

The raw inputs are not in this repository. To rebuild the published files from
your own logs:

```bash
python tools/anonymise.py \
  --ledger /path/to/self_assessment.jsonl \
  --gate   /path/to/guard_log.jsonl \
  --out    data/
```

Expected output shape:

```
[ledger] 84 samples -> data/ledger_metric_samples.jsonl
[gate] <N> events -> 16 daily rows
[gate] firings=5 first_fire=2026-09-19T14:52:23.011940+00:00 silent_days_before=13
[self-test] generic patterns=7 fired=7
[self-test] PASS — the leak gate fires on known-positive input

leak check: clean (3 files, 18 patterns)
```

Numbers will differ with your logs. The structure and the two-stage check
should not.
