# Method

## The rule

> A number is not a measurement until it has been observed to take different
> values on inputs that are known to differ.

This is a deliberately weak but falsifiable requirement. It does not ask
whether a metric is useful, calibrated, or desirable. It asks whether the
instrument responds to the dimension it claims to measure.

## Three levels

### 1. Instrument level — `discriminate()`

Feed a callable a set of `ProbePair` objects. Each pair contains two inputs
known to differ, tagged with the dimension in which they differ.

A pair is separated when the outputs differ by more than the configured
tolerance.

Dimension scoping is essential. An instrument that separates “present” from
“absent” has not demonstrated that it measures content quality. Only
separation within the claimed dimension counts.

### 2. Ledger level — `audit_ledger()`

Run over any recorded samples you are allowed to inspect.

| verdict | condition |
|---|---|
| `CONSTANT` | exactly one distinct value across the observed window |
| `BARE_ZERO` | the same numeric zero represents both “nothing examined” and “examined, no hits” |
| `LIVENESS_BIT` | most or all variance is explained by one boolean freshness/health field |
| `NO_DATA` | nothing matched the requested field |

`NO_DATA` is intentionally not `PASS`. An audit with no evidence has not
succeeded; it has not happened.

### 3. Gate level — `audit_gate()` / `audit_gate_counts()`

A guard, assertion, or denial path that logs activity but has never been
observed to reject a known-bad input should not be treated as validated.

`audit_gate_counts()` accepts aggregate counts so users can test this property
without publishing raw logs.

## Positive controls

A zero firing count is ambiguous: either the gate is broken, or nothing has
ever tried to make it fire. Resolve the ambiguity by constructing a known-bad
input and observing the rejection path directly.

A small synthetic example is enough:

- 100 ordinary events;
- 0 observed rejections;
- introduce one known-bad control;
- confirm the rejection path fires.

The point is not the number of events. The point is that the negative path has
been observed to work.

## What a PASS does not mean

- It does not mean the measured quantity is good.
- It does not mean the claimed dimension is the right one to measure.
- It does not transfer across systems or datasets automatically.
- It does not replace domain judgment.

## Known limits

- Probe quality matters: weak probe pairs can produce weak conclusions.
- Threshold choices are conventions and should be explicit.
- The tool only evaluates data supplied to it.
- Passing one set of probes does not prove universal validity.
