# greencheck

### 28,176 green checks. Zero denials.

That is not a passing gate. That is a gate that ran 28,176 times without ever
firing once — and nobody noticed for thirteen days.

`greencheck` audits the instruments an agent uses to report on itself, and finds
the ones that look like measurements but measure nothing.

---

## The one rule

> **A number is not a measurement until it has been observed to take different
> values on inputs that are known to differ.**

A metric that reads `1.0` forever is not telling you things are perfect. It is
not telling you anything. A dashboard that is green because it has never been
asked a question it could fail is a specific kind of silence — and this tool
exists to make that silence audible.

Point it at a metric you already collect: a self-score, a recall rate, a guard,
a health probe. It tells you whether the number varies with the thing it is
named after, or only with something adjacent — input existence, wall-clock
freshness, a single boolean.

---

## 30 seconds

```console
$ greencheck demo

[ok  ] content_length          (2 samples)
[FAIL] content_presence_score  (2 samples)
       - IDENTITY: 0/1 probe pairs separated within the claimed dimension
         'content'. The instrument responds to something other than what it
         claims to measure.
[FAIL] always_one (control)    (2 samples)
```

The middle line is the point. `content_presence_score` **does** separate one of
the probe pairs — `1.0` for text, `0.0` for empty. A naive check ("did any two
outputs differ?") passes it. But the pair it separates differs in *existence*,
not in *content*, and `content` is what the instrument is named after. A
discriminability test that is not dimension-scoped is itself a decoration.

Audit a real ledger:

```console
$ greencheck audit ledger.jsonl --field identity.identity_score

[FAIL] identity.identity_score  (84 samples)
       - CONSTANT: 84/84 samples report the identical value 1.0.
         Zero variance over the observed window.
       stats: n_samples=84, distinct_values=1
```

Check whether an assertion has ever fired:

```console
$ greencheck gate guard_events.jsonl --fire-event block_issued

[DEAD_GATE] block_issued never fired in 28,176 events spanning 13 days.
            A criterion that has never been observed to trigger is not a
            defence. It is an untested assumption with a dashboard attached.
```

No dependencies. Python 3.9+. Nothing to install beyond the repo.

---

## What it catches

| verdict | signature | how you notice |
|---|---|---|
| `CONSTANT` | Zero variance over the whole window | 84/84 samples report the same value |
| `IDENTITY` | Separates inputs by existence, not by the claimed dimension | Empty vs non-empty moves it; good vs contradictory content does not |
| `BARE_ZERO` | `n = 0` and `n > 0, 0 hits` produce the same output | 63 of 84 "recall" samples examined nothing and reported `0.0` |
| `LIVENESS_BIT` | All variance traces to one boolean | A composite score whose two values are exactly a freshness flag |
| `DEAD_GATE` | A guard exists, logs health, has never fired | 26,668 healthy events, 0 firings, 13 days |
| `NO_DATA` | Nothing matched | Reported instead of `PASS`, on purpose |

**`NO_DATA` is the failure mode of the audit tool itself.** An empty input
returning `PASS` is precisely the class of bug this repository exists to catch,
so the tool refuses to commit it. And `IDENTITY` is not "the values differ
somewhere" — discrimination is scoped to the dimension the instrument *claims*
to measure, which is a strictly harder bar and the one that actually matters.

None of these is hypothetical. Each was found on a real instrument, in
production, in the case study below.

---

## The case study

`data/` holds two anonymised datasets from a continuously-running autonomous
agent over roughly two months. Everything in this repo is reproducible from
them:

```bash
python case_study/run_case_study.py
```

| instrument | n | verdict |
|---|---:|---|
| `self_assessment.identity_score` | 84 | **CONSTANT** |
| `self_assessment.memory_recall.recall_rate` | 84 | **CONSTANT; BARE_ZERO** |
| `self_assessment.reflection_score` | 84 | **LIVENESS_BIT** |
| `self_assessment.overall (composite)` | 84 | **LIVENESS_BIT** |
| `guard denial path — before any positive control` | 28,176 | **DEAD_GATE** |
| `guard denial path — full window` | 33,228 | **PASS** |

Six instruments. Five flagged. Full write-up:
[`case_study/results/CASE_STUDY.md`](case_study/results/CASE_STUDY.md).

The last two rows are **the same guard**. It reads `DEAD_GATE` for the thirteen
days before anyone constructed an input it was *known* to have to block, and
`PASS` afterwards. Nothing about the guard changed at that moment. What changed
is that somebody finally asked it to prove itself.

That is the whole thesis. A control is not validated by its presence in the
code, nor by its green light. It is validated by having been observed to fire.

---

## Install / use

No dependencies. Python 3.9+.

```bash
git clone https://github.com/simin-yuan/greencheck
cd greencheck
python -m unittest discover -s tests      # 13 tests, stdlib only
python -m greencheck.cli demo
```

Audit your own ledger:

```bash
python -m greencheck.cli audit my_ledger.jsonl \
    --field identity.identity_score \
    --count memory_recall.sampled \
    --fresh reflection.fresh
```

Or drive it as a library:

```python
from greencheck import ProbePair, discriminate

discriminate(my_metric, [
    ProbePair("rich vs degenerate", rich_text, "aaaa", dimension="content"),
    ProbePair("present vs absent", "hello", "", dimension="content"),
], subject="my_metric", claimed_dimensions=["content"])
```

---

## Where the evidence comes from

The underlying logs are from production and contain filesystem paths, host
identifiers and operator-specific strings. **They are not published.** What is
published is aggregated:

- `data/ledger_metric_samples.jsonl` — 84 samples, field names neutralised; no
  value, timestamp or count altered
- `data/gate_summary.json`, `data/gate_daily.jsonl` — per-day counts only

`tools/anonymise.py` produces them and **fails the run** if any forbidden pattern
survives. The leak gate has its own positive control (`--self-test`), because a
checker that has never been observed to fire is not a checker — and that rule
applies to this repository before it applies to yours. `tools/leakscan.py`
re-verifies the entire tree independently. Rules and provenance:
[`data/PROVENANCE.md`](data/PROVENANCE.md).

---

## Standing on

This did not start from nothing, and it would be dishonest to imply otherwise:

- **Dimension-scoped discriminability and falsification-first verification** —
  adapted from [obra/superpowers](https://github.com/obra/superpowers) (MIT).
- **`n = 1` case-study discipline** — report a single system honestly instead of
  inflating it into a general claim.

The strongest contribution in the other direction: if you have a metric that
passes `greencheck` and still lies to you, that is a bug here, and the issue is
welcome.

---

## Limits

- **This tests instruments, not systems.** A `PASS` means the instrument
  separates inputs within its claimed dimension. It does not mean the thing
  measured is good, or that the dimension is the right one to measure.
- **`n = 1` system.** One agent, roughly two months. The signatures recur across
  its instruments, but cross-system replication is open. Treat the taxonomy as a
  starting set, not a closed one.
- **The tool only sees what you record.** A metric that is never written down
  cannot be audited. Absence of records is itself a finding — a different one.
- **A positive control is part of the procedure, not an optional extra.** A
  guard's firing count is meaningless until someone has shown it fires when it
  should. See [`docs/METHOD.md`](docs/METHOD.md).
- **The instruments were written by the system being measured.** That is the
  condition under study, not a flaw in the study.
- **The judging standard is not set by the thing being judged.** The verdicts in
  the case study are proposed by this tool's author and should be read as a
  draft. Disagreeing with one of them is the useful move.

## Falsifiers

1. If any instrument in the case study is shown to separate inputs within the
   dimension it claims to measure, the corresponding finding is false.
2. If the guard is shown to have fired before `2026-09-19T14:52:23Z` on an input
   that should have been blocked, the `DEAD_GATE` finding is false.
3. If anonymisation changed any *value* (as opposed to a field name), every
   number in the case study is void. `tools/anonymise.py` is the only transform
   applied; its leak check is mandatory.

## Citation

See [`CITATION.cff`](CITATION.cff).

## License

MIT — see [`LICENSE`](LICENSE).

**Simon**, 2026.
