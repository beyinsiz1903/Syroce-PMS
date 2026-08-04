# QR Structured Submission Architecture

## Ledger-Backed Idempotency & Convergence
Guest service submissions via QR codes support multiple distinct service requests bundled into a single physical checkout/basket.
To prevent duplicates across retries, page reloads, and spotty networks, we use a converged ledger approach.

### 1. Ledger-First Replay
Upon receiving a structured payload with an `idempotency_key`, the system first checks the `guest_service_submissions` ledger:
- **Matching Ledger**: If a ledger exists and the payload fingerprint matches exactly, it loads the previously prepared items without re-resolving the catalogue or regenerating references.
- **Fingerprint Mismatch**: If the ledger exists but the fingerprint differs, it indicates a conflicting request under the same key. Returns HTTP 409 Conflict.
- **No Ledger**: It resolves the catalogue at that exact moment in time, prepares the canonical items and snapshots, and atomically inserts the winning ledger into MongoDB using `$setOnInsert`.

### 2. DuplicateKeyError & Winner Reread
If two concurrent identical requests miss the initial `find_one` lookup, both will attempt `find_one_and_update(upsert=True)`. The database `DuplicateKeyError` ensures only one wins.
The loser catches `DuplicateKeyError` and performs a bounded scoped reread to adopt the winner's ledger.
- If the reread yields a matching fingerprint, the loser proceeds with the winner's items.
- If the reread yields a conflicting fingerprint (impossible in identical races but caught defensively), returns 409.
- If the winner is not visible after 5 bounded retries, it returns a sanitized HTTP 503.

### 3. Partial Retry & Convergence Check
After adopting the prepared items (either as creator or replay adopter):
The system attempts an idempotent insertion of each `qr_request` item.
- `submission_group_id` + `service_code` unique constraints protect against duplicate items.
- If a `request_reference` collision occurs independently, a new public reference is generated, updated atomically inside the full-scoped ledger item, and retried.
- **Convergence Miss**: If the number of successfully persisted items does not match the ledger's prepared items count (e.g. database interruption), the ledger remains in `pending` status. The system does *not* set it to `failed`. `failed` is reserved for explicit business rejection.
- A future replay with the same idempotency key will skip the already-inserted items and only insert the missing ones, eventually reaching full convergence (status `completed`).

### 4. Visibility & Notification
- **Partial Visibility**: Items are visible in operations (PMS) the moment they land in `qr_requests`. They do not wait for the entire ledger to converge.
- **Notification**: Notifications are sent on a best-effort basis for the newly inserted items only.
- **Attempt Count**: Every attempt (including retries) safely increments the `attempt_count` of the ledger via scoped `$inc` updates.
