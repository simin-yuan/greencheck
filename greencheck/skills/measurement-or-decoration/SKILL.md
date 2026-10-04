---
name: measurement-or-decoration
description: Use when a system reports a score, confidence, health value or composite metric about itself. Zero variance over the observation window means the number is decoration, not measurement.
---

# Measurement or decoration

## The rule

> **A number is not a measurement until it has been observed to take different
> values on inputs that are known to differ.**

Everything else in this skill set is a special case of this sentence.

## Synthetic example

Suppose a service reports four internal metrics over repeated checks:

| instrument | observed values | likely meaning |
|---|---|---|
| `quality_score` | `1.0` every time | constant; carries no information |
| `match_rate` | `0.0` every time | ambiguous unless the denominator is known |
| `freshness_score` | two values | may be only a liveness flag |
| `overall` | same two values | may duplicate the same underlying boolean |

Correct code can still produce a useless measurement. A value arriving on
schedule and in the right format is not evidence that it measures the property
named on the dashboard.

## Why zero variance is not stability

A metric pinned at `1.0` or `0.0` may look reassuring, but if it never moves
with known changes in the subject, it cannot carry information about that
subject.

**Constant output is not a strong signal. It is the absence of a signal.**

## Procedure

1. Collect repeated observations.
2. Count distinct values.
3. Attribute the variance of composites to their inputs.
4. Construct probe pairs that differ in the claimed dimension.
5. Re-run after changes; instruments can drift.

## Failure modes

- A vanity score that always reports a high value.
- A composite whose variance comes from one boolean.
- A score that moves with time or freshness rather than the claimed subject.
- An instrument that reacts to presence/absence but not content.

## Verify

For each metric, name two inputs that differ in the way the metric claims to
care about and show that the reported value differs between them.
