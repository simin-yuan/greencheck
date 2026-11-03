# OpenAPI 3.0 example-as-seed mutation study — METHOD v2 (frozen before the v2 run)

2026-11-03. Supersedes METHOD.md (v1) only in the sampling frame and the per-spec cap.
Everything about mutation, judging, classification and checking is v1's, unchanged —
so v2 does not re-open the method, it re-opens who gets measured.

## Why v1 is labelled a trial run

v1 sampled 20 documents from the whole APIs.guru OpenAPI 3.0 frame with no knowledge of
where examples live. Five of the 20 contributed any case; 15 contributed none. Of the 427
escapes, 306 came from one AWS document. A reader can see that without opening the data:
the pooled rate described one file. The rule that produced it is kept in the lab notebook
as v1, the numbers are kept, and this file states the change rather than quietly replacing it.

## Change 1 — sampling frame

- Candidate set = APIs.guru `list.json` entries whose `openapiVer` starts with `3.0` and
  whose `swaggerUrl` ends with `.json` (v1's frame: 1704 documents).
- **Eligibility** = a candidate whose own spec contains at least one component schema at
  `/components/schemas/<Name>` carrying a top-level `example` that serialises to <= 8192
  bytes as pretty JSON. Eligibility is decided by reading the spec, once, before any
  sampling; the result is frozen to `out/eligible.json` with per-spec counts.
- **Sample** = `random.Random(20261103).sample(sorted(eligible), 20)`.
- Documents are downloaded once and stored under `specs/` with sha256; the run never
  re-fetches and never re-samples.

## Change 2 — per-spec cap

- Cases per spec = schemas with a qualifying top-level `example`, **capped at 5**.
- When a spec has more than 5, `random.Random(20261103).sample(sorted(names), 5)`.
- Purpose: stop one document (or one generator's house style) from carrying the pooled rate.
  It does not change the unit of analysis, which stays "one schema + its own example".

## Unchanged from v1

- Judge: `sourcemeta/jsonschema` v17.3.2 `validate <doc> <instances.jsonl> --entrypoint /components/schemas/<Name> --continue`.
  Exit 0 = pass, 2 = fail, anything else = ENGINE-ERROR and never a verdict.
- Negative control before the run: a synthetic document with one required property, judged
  through the same JSONL path, must return ACCEPT then REJECT for a good and a bad instance.
- Baseline must ACCEPT, or the case is reported as `example_rejected_by_own_schema` and is
  not mutated.
- Mutants: `greencheck.mutate.build_mutants` over the pretty-printed example; unparseable
  and no-op mutants sit outside the denominator; parse_broken is reported split into
  file-level (`drop-file`/`empty-file`) and syntax broken by `drop-line`.
- Classes: `undeclared-key` / `declared-optional-removed` / `value-level` / `ANOMALY` /
  `unresolved`, resolved against the whole document with `properties`, `patternProperties`,
  `items` (both forms), `additionalProperties`, `$ref` keeping siblings, folding
  `allOf`/`anyOf`/`oneOf`.
- Cross-check: every judged mutant also judged by `openapi_schema_validator.OAS30Validator`
  with `#/components/schemas/*` rewritten to `#/definitions/*`; non-local refs counted as
  unresolved, never silently dropped.
- Verification: `check.py` re-judges **every** instance with one CLI call per instance and
  re-counts every mutant; `stats.py` prints every number that appears in the report.

## Added — static statistics (no new mutation operators)

On the v2 case set, at the entry schema's own object node after `$ref`/`allOf` expansion:

1. how many entry schemas inherit a base through `allOf` (a base = a component schema
   referenced by another component schema's `allOf` arm);
2. among those bases, how many write `additionalProperties: true`, how many write a schema,
   how many write nothing, how many write `false`;
3. how many entry schemas declare `required` at their own object node, how many declare it
   only deeper in the tree, how many nowhere.

These answer the "deliberately open base class" question without inventing an operator that
adds keys, which v1's operator set cannot do.

## Denominators

- `escape_rate_pooled` = escaped / judged, panelled beside the per-case median and the
  per-spec table. A pooled rate is never reported alone.
- `declared-optional-removed` is an escape class, not a defect: with `required` absent the
  document is silent by construction. The report says which of the two happened.

## Reproducibility

`./run_v2.sh` = eligibility scan -> sample -> study -> check -> stats. One command, from
this directory. The v1 artifacts stay where they are and are not overwritten.
