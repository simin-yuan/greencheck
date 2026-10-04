# Example: a gate that lets through a config it should reject

A small, complete, runnable example. One gate, one valid input, twelve mutants,
one escaped.

## Run it

From the repository root:

```console
$ cd examples/mutate-demo
$ greencheck mutate --gate "python gate.py {target}/config.json" --target ./input
```

## The gate

[`gate.py`](gate.py) is the kind of check most projects actually have. It
confirms the file parses, every required key is present, and no value is blank.

Nothing about it is lazy. It reads as thorough, and a reviewer would sign off on
it.

## The input

```json
{
  "service": "billing",
  "region": "eu-west-1",
  "replicas": 3,
  "owner": "team-payments"
}
```

## What happened

```
baseline rc: 0  PASS (baseline is clean, mutating)
mutants    : 12
----------------------------------------------------------------------
      caught  drop-file:config.json
      caught  empty-file:config.json
      caught  drop-line:config.json:1:{
      caught  drop-line:config.json:2:"service": "billing",
      caught  drop-line:config.json:3:"region": "eu-west-1",
      caught  drop-line:config.json:4:"replicas": 3,
      caught  drop-line:config.json:5:"owner": "team-payments",
      caught  drop-line:config.json:6:}
      caught  blank-value:config.json:2:"service":
      caught  blank-value:config.json:3:"region":
   * ESCAPED  blank-value:config.json:4:"replicas":
      caught  blank-value:config.json:5:"owner":
----------------------------------------------------------------------
caught 11 / 12

mutants the gate let through (1):
  *  blank-value:config.json:4:"replicas":

  These are questions, not findings. Some are real gaps. Some are
  mutations that are semantically legal, and a gate that rejected
  them would be wrong. This run cannot tell you which is which -
  that needs someone who knows what the gate is for.
  For each line, ask: if this had happened, why didn't the gate care?
```

This one is a real gap, and the next section shows why. But the tool does not
decide that for you, and it should not pretend to: the same output shape is
produced by a genuine hole and by a mutation that any correct gate would allow.

## What the escaped mutant actually is

The mutant turns

```json
"replicas": 3
```

into

```json
"replicas": 0
```

The gate accepts it. Look at why:

```python
for key in REQUIRED:
    if config[key] in ("", None):     # 0 is neither "" nor None
        return 1
```

The check asks *"is this field filled in?"* It never asks *"is this value
usable?"* Zero replicas is a service that does not run, and the gate that
guards this config says yes to it.

**Note what did not fail here.** The JSON is still valid. The key is still
present. Every structural property the gate tests for still holds — that is
precisely why this class of gap survives review. It is invisible to any check
that only looks at shape.

## The fix

```python
if key == "replicas" and not (1 <= config[key] <= 100):
    print(f"replicas out of range: {config[key]}")
    return 1
```

Then re-run: the mutant is caught, and the number stays caught on every future
run. That is the whole loop — **find an input the gate must reject, confirm it
rejects it, keep the check.**

## Honest limits of this example

Eleven of the twelve mutants were caught, which says the gate is not useless.
One escaped, which says it is not complete. Neither number means "the gate is
correct" — only "under these twelve mutations, this is what it did".

An escaped mutant is not automatically a defect. Some mutations are
semantically legal, and a gate that rejects them would be wrong. The escaped
list is a list of questions, not a list of bugs. But every line deserves an
answer to: **if this had happened, why didn't the gate care?**
