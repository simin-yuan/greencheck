# vtex.local:Marketplace-Protocol/1.0 — rejected at the document layer

**Source** https://api.apis.guru/v2/specs/vtex.local/Marketplace-Protocol/1.0/openapi.json
**sha256** 9394968389f980876ea29734592b1bd7edd6ff1b3ad9fa124d6459cc8bd66ac2
**OpenAPI** 3.0.0 · 15 entries under `paths`
**CLI** jsonschema 17.3.2 · `lint` · exit **4**

## The collision

Here both colliding paths have two templated segments, and neither parameter name
matches the other:

```
line 4021   "/{fulfillmentEndpoint}/pvt/orders/{orderId}/cancel"
line 4219   "/{marketplaceServicesEndpoint}/pvt/orders/{marketplaceOrderId}/cancel"
```

Same rule as above: after templating, the two are one path written twice. OpenAPI 3.0.4,
Paths Object, treats `/pets/{petId}` and `/pets/{name}` as "identical and invalid".

## Command

```sh
curl -sS https://api.apis.guru/v2/specs/vtex.local/Marketplace-Protocol/1.0/openapi.json -o vtex.json \
  && jsonschema lint vtex.json --color never; echo "exit=$?"
```

## Output, as captured

```
error: The Paths Object keys must not repeat a templated path
  at line 4219
  at column 5
  at file path D:/temp/onecase/vtex.local_Marketplace-Protocol_1.0.json
  at location "/paths/~1{marketplaceServicesEndpoint}~1pvt~1orders~1{marketplaceOrderId}~1cancel"
  at base uri file:///D:/temp/onecase/vtex.local_Marketplace-Protocol_1.0.json
exit=4
```

## Consequence for the study

Same as the other case: no judged mutant, no statement about accepted examples. This
document also carried one of the four examples that contradict their own schema
(`settings` → `/orderCustomDataAppId` expects a value, the example gives `null`), but
that example could never be tested here, because the document does not load.
