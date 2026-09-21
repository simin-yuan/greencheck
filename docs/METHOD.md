# Method

## The rule

> A number is not a measurement until it has been observed to take different
> values on inputs that are known to differ.

This is a falsifiable requirement, and it is deliberately weak. It does not ask
whether a metric is *good*, *calibrated*, or *measuring the right thing*. It
asks only whether the metric is distinguishable from a constant and from the
neighbouring quantities that happen to be correlated with it.

Anything that fails this is not a weak measurement. It is not a measurement.

## Three levels

### 1. Instrument level — `discriminate()`

Feed the callable a set of `ProbePair`s. Each pair holds two inputs known to
differ, tagged with the **dimension** in which they differ.

A pair is *separated* when the two outputs differ by more than `tolerance`.

**Dimension scoping is the load-bearing part.** An instrument that separates
"long text" from "short text" has demonstrated nothing about whether it
measures content. Only separation within the dimension the instrument claims
to measure counts. Concretely: given `claimed_dimensions=["content"]`, an
instrument that returns `1.0` for any non-empty string separates the
existence probe and still fails, because it collapses every pair inside
`content`.

A checker without dimension scoping is itself a decoration.

### 2. Ledger level — `audit_ledger()`

Run over samples already recorded in production. This is the stronger evidence
of the two, because the inputs were not chosen by whoever wanted the metric to
look good.

| verdict | condition |
|---|---|
| `CONSTANT` | exactly one distinct value across the window |
| `BARE_ZERO` | a modal zero value coincides with `count_field == 0`, and the same zero is returned by samples that examined a non-zero number of items |
| `LIVENESS_BIT` | ≥ 2 distinct values, and the proportion of variance in the value explained by a single boolean is ≥ 0.999 |
| `NO_DATA` | nothing matched the requested field |

`NO_DATA` exists because the obvious default — returning `PASS` when there is
nothing to audit — reproduces the exact failure this package is about. An audit
with no data has not succeeded; it has not happened.

### 3. Gate level — `audit_gate()` / `audit_gate_counts()`

A guard, assertion or denial path that logs health N times and fires 0 times
across the whole observed window is reported `DEAD_GATE`.

`audit_gate_counts()` takes integers rather than events, so that a guard log can
be audited without the log being published. The counts support the claim; the
raw lines carry whatever the operator's environment contained.

An empty window is **not** reported as death. Zero firings over zero events is
an absence of evidence, and conflating the two is the error the gate audit
exists to catch.

## Positive controls are part of the procedure

A firing count of zero means one of two things, and the count alone cannot tell
you which:

1. the gate is dead, or
2. nothing has ever tried to make it fire.

So the firing count is only interpretable **after** someone has constructed an
input the gate is known to have to block, and shown that it blocks it.

The case study makes this concrete. The same guard reads `DEAD_GATE` for the
13 days before a positive control was written for it, and `PASS` afterwards.
Nothing about the guard changed at that moment.

This requirement applies to the tool itself: `tools/anonymise.py --self-test`
runs the privacy leak gate against known-positive input and fails the run if
any pattern stays silent.

## What a `PASS` does not mean

- It does not mean the measured quantity is good.
- It does not mean the claimed dimension is the right one to measure. This
  method tests whether an instrument responds to what it is named after, not
  whether the name was well chosen.
- It does not transfer across systems. A `PASS` here is a `PASS` for this
  instrument on this probe set.

## Known limits

- **`n = 1` system.** The case study is one agent over roughly two months. The
  five signatures recur across instruments within it; cross-system replication
  is an open problem.
- **The instruments were authored by the system they measure.** This is the
  condition under study, not a defect in the study. It is also the reason the
  findings were available at all.
- **Threshold choices are explicit and arbitrary.** `≥ 0.999` for liveness-bit
  attribution and `0` for separation are conventions, not derivations. They are
  parameters, not hidden constants.
