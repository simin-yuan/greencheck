# lgtm.com/v1.0 — rejected at the document layer

**Source** https://api.apis.guru/v2/specs/lgtm.com/v1.0/openapi.json
**sha256** 69a1c8a4de6c09fa1fa8ec54b55b0b43904c29b0d51d2f44a4246a2474af9ad0
**OpenAPI** 3.0.0 · 23 entries under `paths`
**CLI** jsonschema 17.3.2 · `lint` · exit **4**

## The collision

Two paths that differ only in the parameter name:

```
line   91   "/analyses/{analysis-id}"
line  218   "/analyses/{project-id}"
```

The document contains a second collision of the same kind. The CLI reports the first
one it meets and stops, so this pair does not appear in the output:

```
line  349   "/codereviews/{project-id}"
line  471   "/codereviews/{review-id}"
```

Both facts are in the document at the pinned hash; the second is simply below the point
where the run ends.

OpenAPI 3.0.4, Paths Object: `/pets/{petId}` and `/pets/{name}` "are considered
identical and invalid". The two pairs above are the same shape.

## Command

```sh
curl -sS https://api.apis.guru/v2/specs/lgtm.com/v1.0/openapi.json -o lgtm.json \
  && jsonschema lint lgtm.json --color never; echo "exit=$?"
```

## Output, as captured

```
error: The Paths Object keys must not repeat a templated path
  at line 218
  at column 5
  at file path D:/temp/onecase/lgtm.com_v1.0.json
  at location "/paths/~1analyses~1{project-id}"
  at base uri file:///D:/temp/onecase/lgtm.com_v1.0.json
exit=4
```

The `file path` and `base uri` lines carry whichever directory the file was downloaded
into; the line number, column, location, message and exit code do not change.

## Consequence for the study

This document contributes **no** judged mutant. `validate --entrypoint` cannot read it,
so every seed taken from it lands in the `ENGINE-ERROR` bucket. Nothing here says
anything about whether the CLI would have accepted a malformed example.
