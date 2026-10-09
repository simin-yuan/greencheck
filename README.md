# greencheck

[![tests](https://github.com/simin-yuan/greencheck/actions/workflows/tests.yml/badge.svg)](https://github.com/simin-yuan/greencheck/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/greencheck.svg)](https://pypi.org/project/greencheck/)
[![licence: MIT](https://img.shields.io/badge/licence-MIT-yellow.svg)](LICENSE)
[![dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#)

### Your validator passes inputs it should reject. This finds them.

```console
$ pip install greencheck
```

Zero runtime dependencies. Python 3.9+.

## What it does

`greencheck` tests whether a validator, metric, guard, or quality gate can actually distinguish the cases it claims to distinguish.

The core rule is simple:

> **A check is not evidence until it has been observed to react differently to inputs that are known to differ in the dimension it claims to measure.**

It supports two broad uses:

- **Mutation testing for gates and validators** — deliberately damage an artefact, then re-run the gate and report mutations that escape.
- **Discriminability checks for metrics** — detect constant outputs, bare-zero ambiguity, single-bit liveness proxies, and checks that react to the wrong dimension.

## 30-second mutation demo

From a checkout of this repository:

```console
$ python -m greencheck.cli mutate --gate "python examples/mutate-demo/gate.py {target}/config.json" --target examples/mutate-demo/input
```

The bundled example intentionally contains a weak gate. It catches most mutations but lets one bad configuration through, showing the difference between “the check ran” and “the check can reject the right thing.”

## Metric demo

```console
$ python -m greencheck.cli demo
```

The demo uses synthetic inputs only. It shows three patterns:

- a metric that genuinely separates the claimed dimension;
- a metric that reacts only to presence/absence rather than content;
- a constant control that carries no information.

For your own JSONL ledger, point `audit` at the field you want to test:

```bash
python -m greencheck.cli audit my_ledger.jsonl --field metrics.score
```

Optional count and freshness fields can be supplied when the meaning of zero or a liveness proxy needs to be tested.

## Gate audit

If you already have aggregate gate counts, the library API can distinguish a gate that has been observed to fire from one that merely exists in code.

The important distinction is not “green versus red.” It is:

> **Has the rejection path ever been exercised by a known-positive control?**

## What it can flag

| verdict | meaning |
|---|---|
| `CONSTANT` | The reported value never varies over the observed window |
| `IDENTITY` | The instrument reacts to a different dimension from the one it claims to measure |
| `BARE_ZERO` | “nothing examined” and “examined, zero hits” collapse to the same value |
| `LIVENESS_BIT` | Nearly all variance is explained by a single freshness/health boolean |
| `DEAD_GATE` | A rejection path exists but has never been observed to fire |
| `NO_DATA` | There is not enough evidence to issue a pass/fail conclusion |

These are diagnostic signatures, not automatic defect verdicts. A human still decides whether a surviving mutation or flagged metric matters.

## Skills

The package also ships small agent-readable review skills:

```console
$ python -m greencheck.cli skills
```

Read one in full:

```console
$ python -m greencheck.cli skills positive-control
```

Included skills cover:

- measurement vs. decoration;
- positive controls;
- dead checks;
- dimension-scoped discriminability;
- ambiguous zero values.

## Third-party example

`case_study/third_party/` contains a self-contained example using public third-party artefacts. It is retained to show how the mutation/triage loop works without publishing private datasets or internal system material.

## Install / verify

```console
$ python -m unittest discover -s tests
```

The library can also be driven directly:

```python
from greencheck import ProbePair, discriminate

discriminate(
    my_metric,
    [
        ProbePair("rich vs degenerate", rich_text, "aaaa", dimension="content"),
        ProbePair("present vs absent", "hello", "", dimension="presence"),
    ],
    subject="my_metric",
    claimed_dimensions=["content"],
)
```

## Public-scope boundary

This repository intentionally contains only the generic tool, synthetic examples, and public third-party demonstration material.

It does **not** publish private datasets, internal measurements, operator-specific identifiers, unpublished research, or product engineering.

## Standing on

Dimension-scoped discriminability and falsification-first verification were adapted in part from [obra/superpowers](https://github.com/obra/superpowers) (MIT).

## Limits

- A surviving mutation is a question, not automatically a bug.
- Passing the audit does not prove the measured system is good; it only says the instrument can distinguish the tested cases.
- The tool only sees what you record.
- Positive controls are part of the validation procedure, not an optional extra.

## License

MIT — see [LICENSE](LICENSE).

**Simin Yuan**, 2026.
