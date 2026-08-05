# Nilvera Incoming Invoice Answers

## Scope

Syroce can approve or reject an incoming `TICARIFATURA` through Nilvera. `TEMELFATURA` is rejected by the API before an action is created. The provider contract is the documented `POST /einvoice/Purchase/SendAnswer` endpoint with `UUID`, `AnswerCode`, and an optional `RejectNote` used only for rejections.

Provider reference: <https://developer.nilvera.com/en/api/e-invoice-api/incoming-invoices/respond-to-the-invoice>

## Safety Model

- The API accepts only an invoice whose synchronized provider status is `SUCCEED` and whose answer status is `PENDING`.
- `request_uuid` is a required UUID and forms part of the tenant-scoped idempotency key.
- A partial unique answer guard prevents competing approve/reject actions for the same tenant and invoice.
- The worker persists `provider_attempted_at` before the provider call. After that marker exists, the write is never sent again.
- A timeout, network error, HTTP 409, HTTP 429, or provider 5xx moves the action to `PROVIDER_PENDING`; the worker performs status-only verification.
- `SUCCEEDED` is written only after `GET /einvoice/Purchase/{UUID}/Status` reports the requested terminal answer and the local incoming invoice is updated.
- A conflicting terminal answer, an exhausted verification window, a lost lease, or a local persistence failure is not success. It requires reconciliation.
- Logs contain only fixed messages, exception types, and bounded error codes. Tenant IDs, document UUIDs, invoice numbers, tax identities, notes, amounts, and provider payloads are not logged.

## States

`REQUESTED` and `RETRY_SCHEDULED` may issue the provider write only when `provider_attempted_at` is absent. `PROCESSING` is leased work. `PROVIDER_PENDING` is verification-only. Terminal states are `SUCCEEDED`, `FAILED`, and `RECONCILIATION_REQUIRED`.

## Sandbox Verification

The Sandbox workflow input `run_incoming_answer` defaults to `false`. The write test runs only when it is explicitly set to `true` after approval. It approves only a pending, commercial invoice whose number uses the Sandbox suite's reserved test prefix. Missing candidates, provider errors, timeouts, unsupported responses, pending exhaustion, and conflicting terminal states fail the test.

Production credentials, production tenants, and production deployment are outside this procedure.
