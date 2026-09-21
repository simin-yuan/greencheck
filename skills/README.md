# Skills

Agent-readable instructions for the failure modes `greencheck` detects.

The CLI audits a ledger **after** the fact. These are for **before** — they are
written to be read by an agent while it is writing an instrument, a guard or a
monitor, so the broken thing doesn't get built in the first place.

| skill | use when |
|---|---|
| [`measurement-or-decoration`](measurement-or-decoration/SKILL.md) | Your system reports a score, confidence or health value about itself. The root rule; the others are special cases. |
| [`positive-control`](positive-control/SKILL.md) | Writing a guard, assertion, alert or validation rule that is supposed to reject bad input. |
| [`dead-check`](dead-check/SKILL.md) | Writing or reviewing a monitoring rule or log pattern that should detect a failure. Covers criteria that can never fire and criteria with inverted polarity. |
| [`dimension-scope`](dimension-scope/SKILL.md) | Testing whether an instrument measures what its name claims. Discrimination must be scoped to the claimed dimension. |
| [`bare-zero`](bare-zero/SKILL.md) | A metric reports `0`. "Nothing matched" and "nothing was examined" are different facts. |

## Installing

These are plain `SKILL.md` files with YAML frontmatter — the format used by
Claude Code, Codex, OpenClaw and most agent harnesses. Copy the directory you
want into wherever your harness looks for skills, or point your agent at the
path and let it read the file directly.

## Where the examples come from

Every case in these files is real. They were found by auditing one agent that
ran continuously for roughly two months — the same audit in
[`case_study/`](../case_study/), reproducible from the data in [`data/`](../data/).

The names and identifiers have been removed. The numbers have not been changed.
