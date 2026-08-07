# HotelRunner ARI Pilot

## Provider contract

HotelRunner supplies an interactive test account for PMS integrations. The
official REST contract documents the test-account credentials and the ARI
endpoints on `https://app.hotelrunner.com`; it does not document a separate
REST sandbox host.

Primary references:

- https://developers.hotelrunner.com/custom-apps/getting-started
- https://developers.hotelrunner.com/custom-apps/rest-api/inventory/update-room

The pilot workflow therefore accepts only the documented host and separately
requires an operator attestation that the configured credentials belong to a
dedicated HotelRunner test account. Production property credentials are not
permitted.

## Manual workflow

Workflow: `HotelRunner ARI Pilot`

GitHub environment: `hotelrunner-pilot`

The environment must have a required reviewer and these secrets:

- `HOTELRUNNER_PILOT_TOKEN`
- `HOTELRUNNER_PILOT_HR_ID`
- `HOTELRUNNER_PILOT_INV_CODE`
- `HOTELRUNNER_PILOT_CHANNEL_CODE`
- `HOTELRUNNER_PILOT_HMAC_KEY`

It also requires these environment variables:

- `HOTELRUNNER_PILOT_ACCOUNT_CONFIRMED=true`
- `HOTELRUNNER_PILOT_TEST_DATE` between 30 and 365 days in the future
- `HOTELRUNNER_PILOT_AVAILABILITY` between 0 and 20
- `HOTELRUNNER_PILOT_RATE` between 1 and 100000
- `HOTELRUNNER_PILOT_STOP_SELL` set to 0 or 1
- `HOTELRUNNER_PILOT_MIN_STAY` between 1 and 30

Do not place credentials, room codes, channel codes, or provider payloads in
workflow inputs. The room and channel must belong to a dedicated test account.

## Gates

Every run requires the exact 40-character approved head SHA. Both normal CI
workflows must have a successful completed run on that exact SHA before the
pilot job can reach provider configuration.

The `operation` input selects exactly one target:

- `discovery`: GET-only credential, room, channel, and capability checks
- `availability`: one date-range availability PUT
- `rate`: one date-range price PUT
- `stop_sell`: one date-range stop-sell PUT
- `restriction`: one date-range minimum-stay PUT

Write modes additionally require `confirm_provider_write=true`. The HTTP guard
allows only the documented discovery and transaction GET endpoints plus at
most one `PUT /api/v2/apps/rooms/~`. POST, PATCH, DELETE, reservation ACK, and a
second PUT fail before provider egress.

## Result rules

The initial `status=ok` response is not success. A write passes only after the
transaction details endpoint reports `succeeded>0`, `failed=0`, and
`in_progress=0` and the durable local reconciliation state is `confirmed`.

HTTP 4xx/5xx, timeout, malformed response, missing transaction identity,
pending, empty, ambiguous, and partial results fail closed. The workflow never
retries the mutation, restores inventory automatically, or sends cleanup,
cancel, reservation ACK, or any other provider write.

Only safe metadata is emitted: booleans, count classes, HTTP status, delivery
state, operation class, provider write count, and a truncated keyed-HMAC
correlation label. Credentials, provider identifiers, room/channel values, and
provider payloads are never logged.
