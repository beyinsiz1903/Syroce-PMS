# Nilvera CreateReturn Sandbox Discovery

## Status

CreateReturn remains disabled by default. The Sandbox contract and GET-only
reconciliation verified that the operation creates an e-Invoice draft. The
production incoming-return API and lifecycle worker still require the explicit
`NILVERA_CREATE_RETURN_ENABLED=true` feature gate; merging the implementation
does not enable a provider mutation.

Nilvera's official endpoint page documents:

- `POST /einvoice/Purchase/{UUID}/CreateReturn`
- bearer authentication
- a success response containing `UUID` and optional `InvoiceNumber`
- no request body in the OpenAPI operation and raw HTTP example

Generated examples on the same page show an unrelated notification body. The
Sandbox discovery therefore sends no guessed payload and requires one explicit,
exact-head provider-write approval to establish the real contract.

## Safety Gates

The `run_create_return_discovery` workflow mode is mutually exclusive with all
other Nilvera modes. It requires:

- the `nilvera-sandbox` environment
- distinct sender and receiver Sandbox accounts
- an exact source fixture run ID, source timestamp, and explicit fixture date
- exact reviewed head SHA approval
- explicit test-account attestation and provider-write confirmation
- first workflow attempt only
- `NILVERA_CREATE_RETURN_ENABLED=true` only inside the selected Sandbox test

The test first reconciles the exact source fixture using GET requests. It
requires one receiver-visible, alias-owned, terminal incoming invoice. It then
permits at most one bodyless CreateReturn POST with retries disabled. A timeout,
network error, 5xx, malformed response, missing response UUID, or failed
read-only lookup is not success and never triggers a second write.

## Production Gate

The Sandbox discovery verified:

1. the bodyless request contract,
2. the response shape,
3. created-document lookup and reconciliation,
4. the resulting document is a draft rather than a sale invoice.

The application lifecycle now provides:

- atomic action creation and quantity reservation,
- one non-retrying CreateReturn POST after a durable attempt marker,
- exact generated-UUID verification through `GET /einvoice/Draft/{UUID}/model`,
- no second POST after timeout, 5xx, malformed response, or ambiguous outcome,
- deterministic rejection release and ambiguous-outcome reconciliation states,
- tenant-scoped balances and allocations,
- full-return support only. Partial returns fail closed because the verified
  bodyless provider contract has no line-quantity input.

Production activation remains a separate NO-GO until credentials, tenant
mapping, monitoring, and the feature gate receive an explicit production
cutover approval.

Each mutation experiment requires a separate exact-head approval. CreateReturn,
incoming APPROVE/REJECT, fixture creation, cancellation, deletion, and cleanup
must never share one approval or workflow run.

If the POST succeeds but its immediate GET verification fails locally, the
write workflow must not be rerun. The mutually exclusive
`run_create_return_reconciliation` mode searches a bounded creation-time window,
validates the return type and both counterpart identities with keyed HMAC, and
uses only non-retrying GET requests. Zero matches, multiple matches, malformed
responses, 4xx, 5xx, timeouts, or an unavailable status remain blocked.
