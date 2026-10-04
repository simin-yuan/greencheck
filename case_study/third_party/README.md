# The loop, run against a validator we did not write

Every other example in this repository audits instruments we built. That raises
an obvious question: does the loop do anything on artifacts nobody here wrote?

This directory answers it with third-party inputs on both sides.

| role | artifact | pinned at |
|---|---|---|
| instance | `package.json` of `expressjs/express` | `9a34acf03cb818ff3f8bc40e44176e277a25cbb9` |
| validator | SchemaStore's `package.json` schema, run through `jsonschema` | `95515978468ac0373ed052151745715c05c32fd5` |
| consumer | `npm`, run locally | node v24.18.0 / npm 11.16.0 |

Both files are downloaded at run time rather than vendored, so the run points
at the exact revision it was made against. Run date: 2026-09-22.

## Reproduce

```console
$ pip install jsonschema
$ python case_study/third_party/run.py
...
verdict: the gate let through 132/168 mutants.
```

Raw console output: [`results/mutate-output.txt`](results/mutate-output.txt) ·
machine-readable: [`results/mutate-report.json`](results/mutate-report.json)

Both files are redacted before they are written: absolute paths become
`<path>`, and e-mail addresses that the borrowed file itself carries become
`<redacted-email>`. Those addresses arrive inside mutant names — a mutation
that deletes a `contributors` line quotes the line it deleted. The run itself
is unchanged; only the paper it is printed on. The two third-party files land
in the system temp directory, never in this repository.

Then take the escapes to the consumer:

```console
$ python case_study/third_party/triage.py
blank-value on the root version
    schema (jsonschema + SchemaStore): rc=0 accepts it
    npm pack --dry-run               : rc=1 refuses it -> npm error Invalid package, must have name and version
...
schema accepted 3/3 of these mutants; npm accepted 1/3.
```

Recorded: [`results/triage-output.txt`](results/triage-output.txt)

## What came back

```
baseline rc: 0  PASS (baseline is clean, mutating)
mutants    : 168
caught     : 36
escaped    : 132
```

The 36 rejections have a clear shape: the mutants that broke JSON syntax
(deleting or emptying the whole file, deleting a `{`, `}`, `],` or `},` line) or
broke a type (a container blanked into a string, or `"name": ""`). Everything
else — 132 mutants — the schema said yes to, in recognizable classes:

- **58 `blank-value`** — 44 dependency and devDependency version strings, 8
  metadata strings (`description`, `version`, `author`, `license`,
  `repository`, `homepage`, `type`, `url`), 5 `scripts` entries, 1
  `engines.node`.
- **74 `drop-line`** — one line deleted at a time: metadata fields, entries of
  `keywords`, `contributors` and `files`, single dependency declarations,
  `scripts` entries.

**That is a coverage map, not a bug report against SchemaStore.** The schema's
job is to describe the shape a `package.json` may take inside an editor;
constraining *presence* is not what it is for. What this run measures is the
boundary — every field that can be emptied or removed without the validator
objecting — and the boundary is real, checkable, and nobody's opinion.

## The work the count does not do

The tool prints its own limit, and it is the honest part of the output:

> These are questions, not findings. Some are real gaps. Some are mutations
> that are semantically legal, and a gate that rejected them would be wrong.

So we asked the consumer. Five questions, five answers — the last three are
run by [`triage.py`](triage.py), the first two by the commands shown:

**1. The empty object validates**, which is why so many single-line deletions
escape:

```console
$ echo "{}" > empty.json
$ python case_study/third_party/gate.py empty.json
valid
```

**2. `"name": ""` is rejected, but no `name` at all is accepted.** Blanking the
field was caught by the schema; deleting the line was not. Value-constrained,
presence-unconstrained — a distinction no count can show you, and it is in the
report file.

**3. `"version": ""` — a real gap.** The schema accepts it. `npm` does not:

```console
$ npm pack --dry-run
npm error Invalid package, must have name and version
```

**4. `name` deleted — a real gap.** Same command, same verdict.

**5. `license` deleted — legal.** The schema accepts it, and so does `npm`:

```console
$ npm pack --dry-run   # exit code 0
npm notice Tarball Contents   (output trimmed)
npm notice 2.8kB package.json
```

Of the three escapes we took to `npm`: two real, one legal. That ratio is why
the count alone means nothing. 132 escapes is a reading list, and the reading
is done by whoever knows what the gate is for.

## What this does not show

It does not show that the loop finds bugs in other people's software. It shows
that it runs, unchanged, against artifacts none of us wrote, and that its
output is a question list that costs a consumer — not a tool — to settle. A
validator that says yes to 132 mutations is not broken; it is a validator with
a boundary that had not been measured before.
