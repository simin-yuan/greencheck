# Two mutation studies behind "What a JSON Schema accepts isn't always what it meant"

Frozen artifacts and the scripts that produced them. Every number in the guest post
comes from a file in this directory.

## Run it

```bash
./studies/reproduce.sh            # offline: re-derive every number from the shipped artifacts
./studies/reproduce.sh --fetch    # full: re-download the OpenAPI sample and re-mutate (network, minutes)
```

Offline mode needs only Python 3 and the JSON files here. `--fetch` additionally needs:

- `greencheck` importable (`pip install -e .` from the repo root)
- the Sourcemeta CLI on `PATH`, or `JSONSCHEMA_CLI=/path/to/jsonschema`
- `openapi-schema-validator` for the cross-check (`pip install openapi-schema-validator`)
- network access to `api.apis.guru`

## `schemastore-2026-10/`

SchemaStore at commit `778278bb`, 38 schema/instance pairs, mutated with greencheck 0.4.0.
Source pinned 2026-10-11, seed `20261011`.

| file | what it holds |
|---|---|
| `out/results.json` | the run: 3,418 mutants, 1,791 judged, 1,402 escapes |
| `out/x3_strata_rebuilt.json` | the nine strata the three-way split is merged from |
| `out/x3_positions.json` | per-mutant position and lint coverage for all 1,382 CI-gate escapes |
| `out/x3_compare3.json` | three-engine comparison, 1,681 of 1,699 agree, 18 date-format divergences |
| `out/x12_annotation_basis.json` | annotation basis before the `$ref` merge (450 / 382 / 550) |
| `out/x16_merged_basis.json` | the merge the article quotes (499 / 333 / 550, 883 need an annotation) |
| `out/x13_owning_node_additional_properties.json` | what the owning node writes about keys it never declares |

**A label to read carefully.** In `x16_merged_basis.json`, the key
`classes.undeclared-key.composition.added-undeclared-key` (248) is a name carried over from an
earlier artifact. It does not mean "a key the mutation added": the mutants behind it are key
deletions and blanked values. Read it as "the mutated instance has, at this position, a key that
the schema declares nowhere along the node's chain". The companion count,
`removed-undeclared-key` (85), is the same situation reached from the removal side. The term is
kept because the file is write-once; the article does not print either number.

Scripts are numbered in the order they were written (`x3_` through `x16_`) and each
reads the frozen artifacts rather than re-running the mutation.

## `openapi30-2026-11/`

APIs.guru OpenAPI 3.0 descriptions, seeds taken from their own `example` values,
judged by `sourcemeta/jsonschema` 17.3.2 through `validate --entrypoint`.

| file | what it holds |
|---|---|
| `out/sample.json` | the draw: frame 1,704, eligible 217, 20 documents, seed `20261103`, index sha256 |
| `out/cases.csv` | one row per seed: baseline verdict, mutant counts, escapes |
| `out/escapes.jsonl` | one row per escaped mutant, with the class it falls into |
| `out/stats.txt` | every headline number the article quotes |
| `out/bases.txt` | `allOf` bases, `additionalProperties`, `properties` without `required` |
| `METHOD_v2.md` | the method, frozen before the run (sha256 in `out/method_v2.sha256`) |
| `REPORT_v2.md` | the full result, including the parts that did not work |
| `LINT_CHECK.md` | what the CLI's `valid_example` rule does, and why it could not be run yet |
| `numbers_check.md` | every number in the article mapped to a field in the files above |

The 20 vendored OpenAPI descriptions are not shipped. They are third-party content,
and `scan_eligible.py --sample` re-downloads the exact same set with the same seed and
checks the index hash.

## What these studies do not show

They measure one thing: how often a mutated document still validates. An acceptance is
not a defect, and it is not evidence about any particular validator. The classes in
`out/escapes.jsonl` say where in the schema the acceptance happened, which is a
description of the schema, not of anyone's intent.
