# Nilvera Incoming Invoice Answers

## Scope

Syroce can approve or reject an incoming `TICARIFATURA` through Nilvera. `TEMELFATURA` is rejected by the API before an action is created. The provider contract is the documented `POST /einvoice/Purchase/SendAnswer` endpoint with `UUID`, `AnswerCode`, and an optional `RejectNote` used only for rejections.

Provider reference: <https://developer.nilvera.com/en/api/e-invoice-api/incoming-invoices/respond-to-the-invoice>

## Safety Model

- `NILVERA_INCOMING_ANSWER_ENABLED` is a dedicated fail-closed feature gate. It defaults to disabled and must be explicitly enabled independently from the global Nilvera switch.
- While the gate is disabled, the API cannot create an answer action and the worker cannot start a new provider write. An action that already has `provider_attempted_at` may continue GET-only verification so an ambiguous prior write is not abandoned or repeated.
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

The Sandbox workflow input `run_incoming_answer` defaults to `false` and is the only workflow input that enables `NILVERA_INCOMING_ANSWER_ENABLED`. The write test runs only when it is explicitly set to `true` after approval. In that mode the workflow selects only the incoming-answer test, so the suite's outgoing submission test cannot issue another provider write. It approves only one provider-ready, pending commercial invoice whose number uses the Sandbox suite's reserved test prefix. The test creates an isolated local lifecycle action, persists the provider-attempt marker before the write, and asserts exactly one provider write. Success requires the final provider answer, lifecycle action, and local invoice answer to be `APPROVED`/`SUCCEEDED`; these non-sensitive values and the write count are stored in the JUnit artifact. Missing candidates, provider errors, timeouts, unsupported responses, pending exhaustion, and conflicting terminal states fail the test.

The controlled Sandbox fixture was delivered and verified through GET-only reconciliation. Before Syroce could submit `SendAnswer`, the provider moved the document to `APPROVED`; provider history classified the actor as `SYSTEM`. The Sandbox `SendAnswer` mutation is therefore **NOT VERIFIED due to provider-side preemption**, and no Syroce incoming-answer provider write occurred. This is a documented pilot limitation, not evidence of a successful provider mutation. Production approve/reject remains disabled by the dedicated feature gate.

Production credentials, production tenants, and production deployment are outside this procedure.
