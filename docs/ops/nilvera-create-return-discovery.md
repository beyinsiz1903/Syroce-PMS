# Nilvera CreateReturn Sandbox Discovery

## Status

CreateReturn remains disabled by default. The production incoming-return API
continues to fail closed with `PROVIDER_CONTRACT_NOT_VERIFIED`; merging the
discovery infrastructure does not enable a provider mutation.

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

Production CreateReturn remains NO-GO until the Sandbox discovery has verified:

1. the bodyless request contract,
2. the response shape,
3. created-document lookup and reconciliation,
4. duplicate-call behavior through read-only evidence or a separately approved
   isolated experiment,
5. the lifecycle worker and allocation state transitions.

Each mutation experiment requires a separate exact-head approval. CreateReturn,
incoming APPROVE/REJECT, fixture creation, cancellation, deletion, and cleanup
must never share one approval or workflow run.

If the POST succeeds but its immediate GET verification fails locally, the
write workflow must not be rerun. The mutually exclusive
`run_create_return_reconciliation` mode searches a bounded creation-time window,
validates the return type and both counterpart identities with keyed HMAC, and
uses only non-retrying GET requests. Zero matches, multiple matches, malformed
responses, 4xx, 5xx, timeouts, or an unavailable status remain blocked.
