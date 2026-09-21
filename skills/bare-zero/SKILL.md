---
name: bare-zero
description: Use when a metric, counter, rate or score reports zero. Zero from "nothing matched" and zero from "nothing was examined" are different facts, and a bare 0 cannot tell them apart.
---

# A bare zero is not a measurement

## The rule

**When a metric reports `0`, it must be possible to tell whether it examined
nothing, or examined something and found nothing.** If those two states produce
the same output, the metric cannot distinguish "no results" from "no search" —
and both read as a clean bill of health.

## The case

An agent's self-reported memory recall rate:

```
samples:                84
reported recall_rate:   0.0  (all 84)
samples with n = 0:     63
```

**63 of the 84 samples examined nothing at all** and reported `0.0`. The metric
was not measuring recall. It was measuring nothing, on three quarters of its
observations, using a number that also had a legitimate meaning of "searched, and
found nothing".

A reader of that dashboard sees "recall is 0" every day. The truth is closer to
"recall was never attempted", and no amount of staring at the number reveals that.

## The fix

Separate the two states in the output, always:

| state | output |
|---|---|
| nothing examined | `NO_DATA` (or `null`, or the field is absent) |
| examined, nothing found | `0` |
| examined, found something | the value |

**Never let an empty input and a negative result share a representation.**

## This applies to the tooling that checks for it

The same class of bug appeared in the audit tool built to find it: an empty
input file returned `PASS`. Nothing matched the query, so nothing was flagged —
which is indistinguishable from "everything is fine".

That is why the tool returns `NO_DATA` rather than `PASS` for empty input. **If
you build a checker, it must not commit the error it exists to catch.**

## Procedure

1. **Find every place a metric can report zero.**
2. **For each, ask: what would happen if the underlying collection were empty?**
   If the answer is "it would report the same zero", the metric is broken.
3. **Add the denominator.** Report `hits / examined`, not `hits`. A rate without
   its base is not a rate.
4. **Make the empty case visible**, ideally as an explicit absent value rather
   than a numeric zero.
5. **Alert on the empty case separately** — "nothing was examined for N periods"
   is its own failure, and often the more serious one.

## Failure modes

- **Averaging over the empty case.** `mean([0, 0, 0])` where all three are
  "not examined" is 0, and looks like a valid average of bad news.
- **Rate without base.** `0/0` collapsed to `0` hides the fact that the
  denominator never existed.
- **Dashboards that render absent as zero.** A missing value drawn as `0` is a
  lie told by the chart library.
- **The counter that resets.** A windowed count returning to zero after rollover
  is not evidence the underlying condition cleared.

## Verify

You can state, for each zero-reporting metric, what it prints when nothing was
examined — and the answer is not `0`.
