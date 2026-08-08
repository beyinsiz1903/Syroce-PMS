# Exely PMSConnect Pilot

## Provider contract

The pilot follows the supplied Exely PMSConnect 1.17 specification. Reservation
reads use only `OTA_ReadRQ` with `SelectionType="Undelivered"`. ARI and
reservation acknowledgement operations use their official SOAP actions and
require explicit provider success; HTTP success alone is insufficient.

The only permitted endpoint is the official Exely test PMSConnect endpoint.
Production credentials, properties, endpoints, and deployments are prohibited.
Credentials previously shared through screenshots or messages must be treated
as exposed and rotated before pilot configuration.

## Protected environment

Workflow: `Exely PMSConnect Pilot`

GitHub environment: `exely-pilot`

The environment must have at least one required reviewer. It requires these
secrets, with values belonging only to a dedicated Exely test property:

- `EXELY_PILOT_USERNAME`
- `EXELY_PILOT_PASSWORD`
- `EXELY_PILOT_HOTEL_CODE`
- `EXELY_PILOT_HMAC_KEY`
- `EXELY_PILOT_ACK_RESERVATION_ID`
- `EXELY_PILOT_ACK_CONFIRMATION_ID`
- `EXELY_PILOT_ACK_CREATE_DATETIME`
- `EXELY_PILOT_ACK_LAST_MODIFY_DATETIME`

ARI mutation runs additionally require these mapping secrets. They are optional
for read-only discovery, which reports only safe capability booleans and count
classes without exposing discovered provider identifiers:

- `EXELY_PILOT_ROOM_TYPE_CODE`
- `EXELY_PILOT_RATE_PLAN_CODE`

It also requires these environment variables:

- `EXELY_PILOT_ACCOUNT_CONFIRMED=true`
- `EXELY_PILOT_CREDENTIAL_SCOPE=test`
- `EXELY_PILOT_TEST_DATE` between 30 and 365 days in the future
- `EXELY_PILOT_AVAILABILITY` between 0 and 20
- `EXELY_PILOT_RATE` between 1 and 100000
- `EXELY_PILOT_CURRENCY` as a three-letter uppercase currency code
- `EXELY_PILOT_STOP_SELL` set to `true` or `false`
- `EXELY_PILOT_MIN_LOS` between 1 and 30
- `EXELY_PILOT_MIN_LOS_ARRIVAL` between 1 and 30
- `EXELY_PILOT_ACK_DURABLE_PMS_ATTESTED=true` only for a separately approved ACK

Do not place credentials, property identifiers, room/rate codes, reservation
identifiers, guest data, or provider payloads in workflow inputs.

## Gates

Every run requires a separately approved exact 40-character head SHA. Normal
backend quality jobs and the frontend workflow must have successful completed
runs on that exact SHA. Production and staging deployment jobs are deliberately
excluded from the pilot gate, so a test-account pilot can never require or
approve a deployment. The workflow is manual only and selects exactly one
operation:

- `discovery`: one read-only availability/discovery request
- `reservation_read`: one official undelivered reservation read
- `availability`: one availability mutation
- `rate`: one rate mutation
- `stop_sell`: one stop-sell mutation
- `min_los`: one minimum-length-of-stay mutation
- `min_los_arrival`: one arrival-based minimum-length-of-stay mutation
- `reservation_ack`: one acknowledgement after read-only exact-version matching

Read-only modes require `confirm_provider_write=false`. Every mutation requires
`confirm_provider_write=true`; each mutation needs its own user approval and
workflow run. The transport guard permits only the expected SOAP actions and
blocks a second mutation before provider egress.

## Result rules

ARI passes only on explicit `SUCCESS` or `WARNING_SUCCESS`, a durable local
delivery state of `confirmed` or `warning_success`, and exactly one provider
write. PMSConnect has no ARI read-back, so ambiguous, malformed, timeout,
rate-limited, rejected, pending, or provider-error outcomes remain blocked and
are never retried automatically.

Reservation ACK additionally requires a read-only exact reservation/version
match and the dedicated durable-PMS attestation. It never runs in the same
workflow execution as an ARI mutation.

Only safe metadata is emitted: booleans, count classes, operation class,
delivery/result class, exception class, provider write count, and a truncated
keyed-HMAC correlation label. Credentials, provider identifiers, guest data,
financial data, and request/response payloads are never logged.

## Provider dependencies

Before any pilot run, Exely must confirm the dedicated test property, supported
PMSConnect mode, room and rate mappings, supported restriction capabilities,
request limits, certification steps, any IP allowlist, access to provider-side
diagnostics, and extranet access. Values are configured only in the protected
environment and are not copied into source control or reports.
