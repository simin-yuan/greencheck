---
name: dead-check
description: Use when writing or reviewing a monitoring rule, an assertion spec, or a log pattern that is supposed to detect a failure. Covers criteria that can never trigger and criteria whose polarity is inverted.
---

# Criteria that cannot fail

## The rule

**A detection rule has three ways to be dead, and all three look identical to a
healthy system: it can never match, it can match with the wrong polarity, or it
can be unreachable from where it is evaluated.**

Absence of alerts is the output of all three.

## Two real cases

### 1. The pattern that matched nothing

A detection criterion used a log pattern to decide whether a job had delivered.
The pattern appeared **zero times** across every log file in the system — the
full history, not a sample.

Nothing marked it broken, because a rule that never matches produces no output,
and no output is indistinguishable from "nothing bad happened". It had been
counted as coverage since the day it was written.

**The check before writing any pattern: confirm it matches at least once on data
where it is *supposed* to match.** A pattern with zero positive hits is not a
rule. It is a string.

### 2. The inverted polarity

A second criterion used a freshness helper: `file_fresh(path, 48h)`.
The helper returns `ok = True` when the file **was written recently**. But the
criterion's own stated failure condition was the opposite — *"if the file has not
been written for 48h, this rule is obsolete and should be deleted"*.

So `ok = True` (file is being written, everything is healthy) was being read as
"satisfied, safe to remove". The rule would have deleted itself precisely when
the system was working, and survived while the system was dead.

**The check: `ok = True` must mean the same thing as the failure text.** Write
them next to each other and read them as one sentence. If the sentence is wrong,
the rule is wrong.

## Procedure

1. **State the failure in one sentence**, in the direction of "this is broken
   when X".
2. **Write the expression that evaluates true when X holds.**
3. **Positive control:** feed it data where X holds; confirm it fires.
4. **Negative control:** feed it data where X does not hold; confirm it is
   silent.
5. **Confirm it is reachable** — that the code path evaluating it actually
   executes in production, not only in a test.

## Failure modes

- **Liveness evidence standing in for detection evidence.** "The rule ran 1,000
  times" says nothing about whether it can match.
- **Counting coverage by rule count.** Ten rules that cannot fire provide less
  coverage than one that can and is monitored.
- **Silent self-deletion.** A rule whose polarity is inverted may retire itself
  or its subject while reporting health.
- **Rules evaluated in a scope that never runs.** A health check inside a job
  only checks when the job runs — so a job that never starts is never checked.
  Put the check outside the thing being checked.

## Verify

For each rule: name the input that makes it fire, and state the last time it
fired. Two rules with zero total firings across the full history are not
coverage — they are two strings that look like coverage.
