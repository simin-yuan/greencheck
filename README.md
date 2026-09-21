# metric-discrimination-test

> A dashboard that reads `1.0` every hour is not reporting good news.
> It is not reporting.

**One rule:**

> A number is not a measurement until it has been observed to take different
> values on inputs that are known to differ.

`mdt` is a small, dependency-free checker for that rule. Point it at a metric
you already collect — a self-score, a recall rate, a guard, a health probe —
and it tells you whether the number varies with the thing it is named after,
or only with something adjacent (input existence, wall-clock freshness, a
single boolean).

This repository is the replication package for a paper on **self-reported
metrics in long-running autonomous agents**: instruments an agent writes to
audit itself, and the specific ways those instruments can be correct code,
produce a number on schedule, and measure nothing.

---

## 30-second version

```bash
python -m mdt.cli demo
```

```
[ok  ] content_length          (2 samples)
[FAIL] content_presence_score  (2 samples)
       - IDENTITY: 0/1 probe pairs separated within the claimed dimension
         'content'. The instrument responds to something other than what it
         claims to measure.
[FAIL] always_one (control)    (2 samples)
```

The middle line is the point. `content_presence_score` **does** separate one of
the probe pairs — it returns `1.0` for text and `0.0` for empty. A naive check
("did any two outputs differ?") passes it. But the pair it separates differs in
*existence*, not in *content*, and `content` is what the instrument is named
after. A discriminability test that is not dimension-scoped is itself a
decoration.

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

These are not hypothetical. Each was found on a real instrument, in production,
in the case study below.

---

## The case study

`data/` holds two anonymised datasets from a continuously-running agent over
roughly two months. Everything in this repo is reproducible from them:

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

Full write-up: [`case_study/results/CASE_STUDY.md`](case_study/results/CASE_STUDY.md).

The last two rows are the same guard. It reads `DEAD_GATE` for the 13 days
before anyone constructed an input it was *known* to have to block, and `PASS`
afterwards. Nothing about the guard changed at that moment. What changed is
that somebody finally asked it to prove itself.

---

## Install / use

No dependencies. Python 3.9+.

```bash
git clone <this repo>
cd metric-discrimination-test
python -m unittest discover -s tests      # 13 tests, ~0s
python -m mdt.cli demo
```

Audit your own ledger:

```bash
python -m mdt.cli audit my_ledger.jsonl \
    --field identity.identity_score \
    --count memory_recall.sampled \
    --fresh reflection.fresh
```

```python
from mdt import ProbePair, discriminate, audit_ledger

discriminate(my_metric, [
    ProbePair("rich vs degenerate", rich_text, "aaaa", dimension="content"),
    ProbePair("present vs absent", "hello", "", dimension="content"),
], subject="my_metric", claimed_dimensions=["content"])
```

---

## Method and honest limits

- **This tests instruments, not systems.** A `PASS` means the instrument
  separates inputs within its claimed dimension. It does not mean the thing
  being measured is good, or that the dimension is the right one to measure.
- **`n = 1` system.** The case study is one agent. The five signatures recur
  across instruments, but cross-system replication is an open problem, and the
  paper says so.
- **A positive control is part of the procedure, not an optional extra.** The
  firing count of a guard is meaningless until someone has shown it fires when
  it should. See [`docs/METHOD.md`](docs/METHOD.md).
- **The instruments were written by the system being measured.** That is the
  condition under study, not a flaw in the study.

## Falsifiers

1. If any instrument in the case study is shown to separate inputs within the
   dimension it claims to measure, the corresponding finding is false.
2. If the guard is shown to have fired before `2026-09-19T14:52:23Z` on an
   input that should have been blocked, the `DEAD_GATE` finding is false.
3. If anonymisation changed any *value* (as opposed to a field name), every
   number in the case study is void. `tools/anonymise.py` is the only transform
   applied; its leak check is mandatory and its rules are in
   [`data/PROVENANCE.md`](data/PROVENANCE.md).

## Citation

See [`CITATION.cff`](CITATION.cff).

## License

MIT — see [`LICENSE`](LICENSE).
