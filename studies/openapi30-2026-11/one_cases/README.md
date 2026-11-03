# The two documents the CLI refuses to load

Both are published OpenAPI 3.0 descriptions from the APIs.guru directory.
`jsonschema` 17.3.2 exits **4** on them before any instance is examined.

| document | entries under `paths` | reported at | exit |
|---|---|---|---|
| `lgtm.com/v1.0` | 23 | line 218 | 4 |
| `vtex.local:Marketplace-Protocol/1.0` | 15 | line 4219 | 4 |

```
error: The Paths Object keys must not repeat a templated path
```

The rule is the one OpenAPI 3.0.4 §Paths Object states directly: `/pets/{petId}` and
`/pets/{name}` "are considered identical and invalid". Both documents contain such a
pair, so both are invalid documents rather than schemas with a hard case inside them.

## Reproduce

Needs `jsonschema` 17.3.2 (https://github.com/sourcemeta/jsonschema/releases).
Substitute the path to the binary for `jsonschema` if it is not on `PATH`.

```sh
curl -sS https://api.apis.guru/v2/specs/lgtm.com/v1.0/openapi.json -o lgtm.json \
  && jsonschema lint lgtm.json --color never; echo "exit=$?"
```

```sh
curl -sS https://api.apis.guru/v2/specs/vtex.local/Marketplace-Protocol/1.0/openapi.json -o vtex.json \
  && jsonschema lint vtex.json --color never; echo "exit=$?"
```

Expected on both: the message above with the line number from the table, and `exit=4`.

## Pinned inputs

```
lgtm.com/v1.0
  sha256 69a1c8a4de6c09fa1fa8ec54b55b0b43904c29b0d51d2f44a4246a2474af9ad0
vtex.local:Marketplace-Protocol/1.0
  sha256 9394968389f980876ea29734592b1bd7edd6ff1b3ad9fa124d6459cc8bd66ac2
```

The documents themselves are not copied here. Fetching them from the URLs above and
checking the hash is what makes the run reproducible.

## Why these two

In the OpenAPI study under `studies/openapi30-2026-11/`, ten of the 85 seeds carry no
verdict. All ten belong to these two documents, five seeds each: the tool never reaches
an instance, because the document fails to load first.

That distinction matters for reading the numbers. A document that does not load is not
evidence that a malformed example was accepted; it is a case the study could not test.
Neither document is a bug report against the CLI — both are invalid by the
specification, and a tool that only checks schema objects cannot see the problem at all.
