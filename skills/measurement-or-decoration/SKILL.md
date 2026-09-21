---
name: measurement-or-decoration
description: Use when a system reports a score, confidence, health value or composite metric about itself. Zero variance over the observation window means the number is decoration, not measurement.
---

# Measurement or decoration

## The rule

> **A number is not a measurement until it has been observed to take different
> values on inputs that are known to differ.**

Everything else in this skill set is a special case of this sentence.

## What it catches

An agent's self-assessment job wrote four instruments into a ledger, hourly.
After 84 samples:

| instrument | observed values | what it was measuring |
|---|---|---|
| `identity_score` | `1.0` × 84 | nothing |
| `memory_recall.recall_rate` | `0.0` × 84 | nothing (63 of 84 examined no input) |
| `reflection_score` | `1.0` × 38, `0.5` × 46 | one boolean |
| `overall` (composite) | two values | the same boolean as above |

**Four instruments. Zero measurements.** Two of them reported the identical
value on every single observation. One of them reported a composite whose
**entire variance** traced to a single boolean that was almost always `true` —
a sixteenth of a bit of real information wearing the costume of a score.

Every one of these was correct code. Each produced its number on schedule, in
the right format, in the right place. Nothing logged an error, because nothing
was wrong — except that the numbers carried no information at all, and were read
as though they did.

## Why zero variance is not stability

A metric pinned at `1.0` is read as "perfect, consistently". A metric pinned at
`0.0` is read as "clean, consistently". Both readings are wrong in the same way:
the number is not varying with anything, so it cannot be reporting on anything.

**Constant output is not a strong signal. It is the absence of a signal.**

## Procedure

1. **Collect at least a few dozen observations** of the metric as it is actually
   produced.
2. **Count distinct values.** One distinct value over the whole window is a
   decoration. Stop here and fix it.
3. **Attribute the variance.** For a composite, decompose it: what fraction of
   the observed variance comes from each input? If one boolean carries all of it,
   you have a boolean, not a score.
4. **Run a discriminability probe.** Construct inputs that are *known to differ*
   along the claimed dimension and confirm the metric moves.
5. **Re-check after changes.** Instruments rot; a metric that separated inputs
   last quarter may be constant this quarter.

## Failure modes

- **The vanity self-score.** An agent asked to rate its own output rates it
  highly, forever. It is not lying; the instrument simply has nothing to measure
  against.
- **The composite that is one flag.** Weights and averaging hide the fact that
  only one input ever varies.
- **Variance from time, not from the subject.** Freshness, sample count and
  wall-clock all move scores while the claimed subject sits still.
- **The instrument written by the thing being measured.** Self-assessment
  systems drift toward metrics that are easy to satisfy. This is the condition
  to watch for, not a moral failing of any particular agent.

## Verify

For each reported metric, you can name two inputs that differ *in the way the
metric claims to care about*, and show that the reported value differs between
them. Anything less is a number being printed, not a measurement being taken.
