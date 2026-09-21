---
name: positive-control
description: Use when writing a guard, assertion, test, alert, or validation rule that is supposed to fail on bad input. A check that has never been observed to fire is not a check.
---

# Positive controls

## The rule

**For every check that claims it will reject bad input: construct one input it is
*known* to have to reject, run it, and confirm it rejects.**

Until that has happened, the check's existence is not evidence of anything.

## Why this is not pedantry

A guard sat in a production system for thirteen days. It ran on every event,
wrote a health record each time, and never denied anything:

```
events:  28,176
denials: 0
days:    13
```

Nothing in the logs looked wrong — because **a guard that never fires and a
guard that has nothing to fire on produce identical output**. The dashboard was
green the whole time. The question "does this thing work?" had no evidence
behind it in either direction, and nobody noticed, because "green" felt like an
answer.

The moment somebody built an input it was *known* to have to block, the guard
did fire. The record changed from `DEAD_GATE` to `PASS`. Nothing about the guard
changed at that moment. What changed is that it was finally asked to prove
itself.

## Procedure

1. **Enumerate the rejection paths.** Every branch that can say "no".
2. **For each one, write the input that must trigger it.** If you cannot write
   one, *that is the finding* — the branch is unreachable, not safe.
3. **Run it.** Observe the rejection. Not the code path — the observable output.
4. **Record the first time it fired.** A timestamp. This is the only artefact
   that distinguishes a working control from a decorative one.
5. **Re-run after every change** to either the guard or the thing it guards.

## Failure modes

- **Existence mistaken for efficacy.** The rule is present in the code, so it is
  assumed to work. Code that has never executed is a comment.
- **Health metrics that only measure liveness.** "The guard ran" is not "the
  guard works". Log denials, not just invocations.
- **The unreachable branch.** A condition that cannot be true — wrong type,
  wrong sign, string compared against a number — never fires, and reads as calm.
- **Tests that assert the absence of failure.** `assert not raised(...)` passes
  when the code under test never ran at all.

## Verify

You are done when, for each check, you can state:

> "It fired at `<timestamp>` on input X, which must be rejected."

A check with no such sentence has not been validated. It has only been written.
