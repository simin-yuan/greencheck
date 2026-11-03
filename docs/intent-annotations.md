# Two intent annotations for JSON Schema

**Status:** draft for community discussion. Nothing here is a specification, and no
implementation is required to support it.
**Author:** Simin Yuan
**Date:** First drafted 2026-10-14; this version 2026-11-03
**Measured against:** the two mutation studies in [`studies/`](../studies/), artifact
names given per number.

## The gap

A JSON Schema states what a document may contain. When an author writes a schema that
is deliberately permissive at some position (an open object, a value that may be
anything), the schema usually says nothing about it, and silence is indistinguishable
from an author who forgot.

That ambiguity is harmless while the schema only filters documents. It costs more once
the same schema is handed to a generator as an instruction: a model reading "produce
output valid against this" sees no difference between a constraint the author chose to
omit and one the author never considered.

The mutation studies behind this note measure the size of that gap. In the SchemaStore
sample, 883 of 1,382 escaped mutants sit where the schema never settles whether the
openness was intended; in the OpenAPI sample, none of the 11 base schemas reached
through `allOf` says anything about keys it does not declare, while nine of them
declare `required`.

## What the annotations say

Two keywords, written at the node whose openness is intended, in the same style as
`x-lint-exclude` (sourcemeta/jsonschema#626): the author states something in place, and
tools read it.

### `x-open-object`

Placed on an object schema whose extra keys are welcome.

```json
{
  "type": "object",
  "properties": {
    "id":   { "type": "string" },
    "name": { "type": "string" }
  },
  "required": ["id"],
  "x-open-object": true
}
```

This says: an instance may carry keys beyond `id` and `name`, and that is intended.
It is the statement an author currently makes by leaving `additionalProperties`
unwritten, with the difference that it can now be read as a decision.

### `x-open-value`

Placed on a schema whose value may be anything.

```json
{
  "type": "object",
  "additionalProperties": { "x-open-value": true }
}
```

This says: entries under this node may hold arbitrary values. It is the statement an
author currently makes with `{}` or by omitting a subschema entirely.

## What changes, and what does not

Nothing about validation. Both keywords are annotations: a validator that ignores
unknown keywords produces the same verdicts with or without them. A schema can adopt
them one node at a time, and removing them restores exactly the previous behaviour.

They are also not a substitute for what the schema already has. `required` is the
existing instrument for "this declared key may be omitted"; a mapping node or a
`patternProperties` node already says its entries come and go. Annotating those would
restate the schema. The annotations are aimed at the positions where the schema says
nothing at all.

## How much would be covered

From the SchemaStore study (`studies/schemastore-2026-10/out/x16_merged_basis.json`,
`studies/openapi30-2026-11/map_strata.py`):

| class | escapes | annotation |
|---|---|---|
| the schema already states the absence | 499 | none needed |
| undeclared key, no keyword anywhere the node reaches | 333 | `x-open-object` |
| value level, no constraint reached | 550 | `x-open-value` |

`x-open-object` reaches 308 of the 333 and `x-open-value` reaches 510 of the 550: 818
of the 883 that need an annotation. With the 499 the schema already states, that is
1,317 of 1,382 escapes. The remaining 65 admit no annotation of this shape: 31 sit at
a declared keyword outside the annotation's scope, 25 are reached through an array
index, and 9 are non-asserting metadata. The coverage figure is therefore an upper
bound.

**Writing at the definition rather than at every use is what makes the cost small.**
Reaching half of a schema's own annotation-needing escapes takes a median of 2 write
sites (minimum 1, Q3 4.25, maximum 13), and all 36 schemas that have such escapes reach
that half mark within 13 sites. Cutting at the 20 largest write sites accounts for 401
escapes; the same cut on instance paths instead of definitions accounts for 60.

## Open questions

1. **Naming.** `x-open-object` / `x-open-value` follow the existing `x-lint-exclude`
   style. A vocabulary keyword would need a home in a published vocabulary; an `x-`
   prefix keeps this out of scope for validators.
2. **Placement.** The cost figures above assume an annotation written once at a
   definition applies wherever that definition is used through `$ref`. Whether tools
   should honour it that way, or expect it at each use, is open.
3. **Interaction with `additionalProperties`.** A node writing
   `additionalProperties: false` and `x-open-object: true` contradicts itself. The
   annotation is intended for nodes that write neither `true` nor a schema. An explicit
   `additionalProperties: true` may already say the same thing; whether `x-open-object`
   is then redundant there is open (see sourcemeta/jsonschema#632).
4. **Interaction with `unevaluatedProperties`.** A node that looks open in one schema
   may be closed by a schema that composes it. Any tool honouring these keywords should
   resolve composition before concluding.

## Where this came from

The measurement, the classes, and the two-annotation proposal come out of the mutation
studies in this repository. Numbers are checked against the frozen artifacts by
`studies/reproduce.sh`, and the mapping from every figure to its artifact is in
`studies/openapi30-2026-11/numbers_check.md`.
