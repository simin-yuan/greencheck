---
name: dimension-scope
description: Use when testing whether an instrument, metric or classifier actually measures what its name claims. Discrimination must be scoped to the claimed dimension, not to "any two inputs differ".
---

# Scope discrimination to the claimed dimension

## The rule

**An instrument's discriminating power must be tested along the dimension it
claims to measure — not along any dimension you happen to have probes for.**

Two outputs differing is not evidence. Two outputs differing *because the
claimed property differed* is evidence. These are not the same test, and the
weaker one passes things the stronger one catches.

## The case

An instrument named `content_presence_score` was tested against two probe
pairs:

| probe pair | differs in | outputs | separated? |
|---|---|---|---|
| rich text vs. `"aaaa"` | content | `1.0` vs `1.0` | no |
| `"hello"` vs `""` | *existence* | `1.0` vs `0.0` | yes |

A naive check — "did any pair separate?" — passes it. But the pair it separates
differs in **existence**, while the instrument is named after **content**. The
instrument responds to *whether there is input at all*, which is a strictly
weaker and different property than *what the input says*.

That is a decoration, not a measurement, and it took a dimension-scoped test to
see it. The naive test would have signed off.

## Procedure

1. **Write down the claimed dimension in one phrase.** "Content." "Freshness."
   "Whether the source is reachable." If you cannot, the instrument has no
   claim, and therefore nothing to test.
2. **Build probe pairs that differ *only* along that dimension**, with
   everything else held constant.
3. **Run each pair.** Record the outputs.
4. **Require separation on the claimed dimension.** At least one pair that
   differs in the claimed dimension must produce different outputs.
5. **Treat separation on an adjacent dimension as a failure**, not a pass. The
   instrument is measuring the adjacent thing.

## Failure modes

- **The existence trap.** Empty vs. non-empty separates almost anything. It is
  the single most common way a useless instrument earns a green light.
- **The length trap.** Longer input produces longer output, and the score moves.
  That measures input size, not quality.
- **The freshness trap.** A score that tracks "was this written recently?" will
  separate any old/new pair while claiming to measure correctness.
- **Testing with whatever data is on hand.** Convenient probes cluster along the
  dimensions that are easy to vary, which are rarely the claimed one.

## Verify

For each instrument, you should be able to name the probe pair that separated
**on its claimed dimension**. If the only pair that separated differs in
something else, the instrument has not been shown to measure its subject.
