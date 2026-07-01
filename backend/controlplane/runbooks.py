"""
Runbook System — Structured Operational Runbooks
==================================================
Runbooks are structured data, not documentation.
They provide operators with concrete steps to resolve known issues.

Each runbook includes:
- Description of the problem
- Possible root causes
- Step-by-step resolution instructions
- Retry guidance
- Severity and category
"""

from typing import Any


class Runbook:
    """Single operational runbook."""

    def __init__(
        self,
        *,
        id: str,
        title: str,
        description: str,
        category: str,
        severity: str,
        possible_causes: list[str],
        resolution_steps: list[str],
        retry_instructions: str,
        related_operations: list[str],
        prevention: str = "",
    ):
        self.id = id
        self.title = title
        self.description = description
        self.category = category
        self.severity = severity
        self.possible_causes = possible_causes
        self.resolution_steps = resolution_steps
        self.retry_instructions = retry_instructions
        self.related_operations = related_operations
        self.prevention = prevention

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
            "possible_causes": self.possible_causes,
            "resolution_steps": self.resolution_steps,
            "retry_instructions": self.retry_instructions,
            "related_operations": self.related_operations,
            "prevention": self.prevention,
        }


# ── Runbook Registry ──────────────────────────────────────────────

RUNBOOKS: list[Runbook] = [
    Runbook(
        id="reservation_import_failed",
        title="Reservation Import Failed",
        description="An OTA reservation could not be automatically imported into the PMS.",
        category="import",
        severity="high",
        possible_causes=[
            "Room type mapping missing or incorrect",
            "Rate plan not found in PMS",
            "Availability conflict (overbooking prevention)",
            "Provider API returned invalid data",
            "Network timeout during import attempt",
        ],
        resolution_steps=[
            "1. Check the failure details in /api/ops/failures for the specific error",
            "2. If mapping error: verify room type mappings in Channel Manager settings",
            "3. If availability conflict: check PMS calendar for the dates in question",
            "4. If network error: retry via /api/ops/failures/{id}/retry",
            "5. If data error: review the raw imported reservation in /api/imports/events",
        ],
        retry_instructions="Use POST /api/ops/failures/{id}/retry with dry_run=true first to validate. If dry run passes, retry without dry_run.",
        related_operations=["reservation_import", "reservation_pull"],
        prevention="Ensure all room type and rate plan mappings are configured before activating a provider connection.",
    ),
    Runbook(
        id="reservation_duplicate_detected",
        title="Duplicate Reservation Detected",
        description="A reservation was identified as a duplicate during import.",
        category="import",
        severity="warning",
        possible_causes=[
            "OTA sent the same reservation notification twice",
            "Webhook retry delivered a previously processed reservation",
            "Import retry worker processed an already-imported record",
        ],
        resolution_steps=[
            "1. This is usually safe — the system correctly prevented a duplicate",
            "2. Verify the original reservation exists in PMS with correct details",
            "3. Check if the duplicate detection was by external_reservation_id or booking source",
            "4. If the reservation is genuinely missing, mark the duplicate as 'pending' for re-import",
        ],
        retry_instructions="Duplicates should NOT be retried. Mark as resolved if the original reservation is correct.",
        related_operations=["reservation_import"],
        prevention="Idempotency keys and booking source checks prevent duplicates automatically.",
    ),
    Runbook(
        id="reservation_mapping_missing",
        title="Reservation Room/Rate Mapping Missing",
        description="A reservation references a room type or rate plan that is not mapped in the channel manager.",
        category="import",
        severity="high",
        possible_causes=[
            "New room type added in OTA but not mapped in PMS",
            "Rate plan ID changed on the OTA side",
            "Mapping was deleted or corrupted",
        ],
        resolution_steps=[
            "1. Identify the unmapped room_type_id or rate_plan_id from the failure context",
            "2. Go to Channel Manager > Mappings and add the missing mapping",
            "3. Retry the failed import via /api/ops/failures/{id}/retry",
        ],
        retry_instructions="After adding the mapping, use POST /api/ops/failures/{id}/retry. The import will use the new mapping.",
        related_operations=["reservation_import", "mapping_resolve"],
        prevention="Set up all room type and rate plan mappings before activating the provider. Use the mapping validation endpoint to verify completeness.",
    ),
    Runbook(
        id="outbox_stuck",
        title="Outbox Events Stuck",
        description="One or more outbox events have been pending for longer than the expected processing time.",
        category="outbox",
        severity="high",
        possible_causes=[
            "Outbox worker is not running or has crashed",
            "Worker lock is held by a dead process",
            "Provider endpoint is unreachable",
            "Database write conflicts during claim",
        ],
        resolution_steps=[
            "1. Check outbox worker status via /api/ops/outbox",
            "2. If worker is stopped: check application logs for crash reason",
            "3. If events are stuck in 'processing': the worker may have died mid-processing",
            "4. Manually requeue stuck events via /api/outbox/{event_id}/requeue",
            "5. If persistent: check provider endpoint health",
        ],
        retry_instructions="Use POST /api/outbox/{event_id}/requeue for individual events, or POST /api/outbox/replay for batch replay.",
        related_operations=["outbox_dispatch"],
        prevention="Monitor the stuck_outbox_count metric. Set up alerts for when it exceeds threshold.",
    ),
    Runbook(
        id="outbox_replay_failed",
        title="Outbox Replay Failed",
        description="An attempt to replay a failed outbox event did not succeed.",
        category="outbox",
        severity="high",
        possible_causes=[
            "The original failure cause has not been resolved",
            "Provider credentials have expired",
            "Provider API is returning errors",
            "Event payload has become stale (e.g., booking was cancelled since)",
        ],
        resolution_steps=[
            "1. Check the original failure reason in the event's last_error field",
            "2. Verify provider credentials are valid",
            "3. Check provider API status page",
            "4. If the event is stale, consider marking it as resolved/ignored",
        ],
        retry_instructions="Fix the root cause first, then retry. Do not blindly retry provider errors.",
        related_operations=["outbox_dispatch", "ari_push"],
        prevention="Monitor provider credential expiry. Set up health checks for provider endpoints.",
    ),
    Runbook(
        id="ari_push_failed",
        title="ARI Push Failed",
        description="An availability/rate/inventory push to an OTA provider failed.",
        category="ari",
        severity="high",
        possible_causes=[
            "Provider API rejected the request (validation error)",
            "Provider rate limiting",
            "Network timeout",
            "Invalid room type mapping",
            "Provider credential expired",
        ],
        resolution_steps=[
            "1. Check the failure error_code and error_message",
            "2. If rate limited: wait and let the retry mechanism handle it",
            "3. If validation error: check the ARI payload for invalid data",
            "4. If auth error: rotate provider credentials",
            "5. Retry via the control plane retry API",
        ],
        retry_instructions="Use dry_run mode first. ARI retries are safe — they push the current state, not a delta.",
        related_operations=["ari_push", "outbox_dispatch"],
        prevention="Validate ARI payloads before pushing. Monitor provider rate limits.",
    ),
    Runbook(
        id="ari_parity_mismatch",
        title="ARI Parity Mismatch",
        description="Local PMS state does not match what the OTA reports for availability, rates, or restrictions.",
        category="ari",
        severity="critical",
        possible_causes=[
            "ARI push failed silently (no error but data not applied)",
            "OTA applied partial update",
            "Race condition between two concurrent updates",
            "Manual changes made directly on the OTA extranet",
        ],
        resolution_steps=[
            "1. Run reconciliation via /api/channel-manager/reconciliation",
            "2. Compare local ARI state with OTA-reported state",
            "3. If mismatch confirmed: force a full ARI push for affected dates",
            "4. Check if manual changes were made on the OTA side",
            "5. Log the incident for post-mortem analysis",
        ],
        retry_instructions="Do NOT retry individual events. Trigger a full reconciliation and then a full ARI push if needed.",
        related_operations=["ari_push", "reconciliation"],
        prevention="Schedule regular reconciliation jobs. Avoid manual changes on OTA extranets.",
    ),
    Runbook(
        id="provider_auth_failed",
        title="Provider Authentication Failed",
        description="Authentication to an OTA provider API failed.",
        category="provider",
        severity="critical",
        possible_causes=[
            "API key or credentials have expired",
            "Credentials were rotated on the provider side but not updated in PMS",
            "Provider is experiencing authentication service issues",
            "Incorrect credential format after migration",
        ],
        resolution_steps=[
            "1. Check the provider's API status page",
            "2. Verify credentials in the credential vault are current",
            "3. If expired: obtain new credentials from the provider",
            "4. Update credentials via the secure credential management API",
            "5. Test connection after update",
        ],
        retry_instructions="Do NOT retry until credentials are verified. Retry will fail with the same auth error.",
        related_operations=["provider_auth", "provider_sync"],
        prevention="Set up credential expiry monitoring. Rotate credentials proactively.",
    ),
    Runbook(
        id="provider_rate_limited",
        title="Provider Rate Limited",
        description="The OTA provider is rate-limiting our API requests.",
        category="provider",
        severity="warning",
        possible_causes=[
            "Too many API calls in a short period",
            "Bulk ARI push exceeding provider limits",
            "Multiple tenants hitting the same provider simultaneously",
        ],
        resolution_steps=[
            "1. Check the 429 response headers for retry-after information",
            "2. The system will automatically retry with exponential backoff",
            "3. If persistent: reduce the batch size for ARI pushes",
            "4. Contact the provider to request higher rate limits",
        ],
        retry_instructions="Let the automatic retry handle this. Manual retry will make it worse.",
        related_operations=["ari_push", "reservation_pull", "provider_sync"],
        prevention="Implement rate-aware batching. Spread requests across time windows.",
    ),
    Runbook(
        id="secret_access_denied",
        title="Secret Access Denied",
        description="A service attempted to access a secret it is not authorized to read.",
        category="security",
        severity="critical",
        possible_causes=[
            "Service is trying to access another tenant's secrets (tenant isolation violation)",
            "Access policy does not include this service",
            "Incorrect tenant context in the request",
        ],
        resolution_steps=[
            "1. Check the secret access audit log for the denied request",
            "2. Verify the calling service's tenant context is correct",
            "3. If legitimate: update the access policy to include the service",
            "4. If suspicious: investigate as a potential security incident",
        ],
        retry_instructions="Do NOT retry until the access policy issue is resolved.",
        related_operations=["secret_access"],
        prevention="Enforce strict tenant isolation in all secret access paths. Regular access policy review.",
    ),
    Runbook(
        id="secret_missing_or_unreadable",
        title="Secret Missing or Unreadable",
        description="A required secret could not be found or decrypted.",
        category="security",
        severity="critical",
        possible_causes=[
            "Secret was never created for this tenant/provider",
            "Secret was deleted",
            "Encryption key was rotated without re-encrypting the secret",
            "Secret data is corrupted",
        ],
        resolution_steps=[
            "1. Check if the secret exists in the credential vault",
            "2. If missing: create the secret via the credential management API",
            "3. If unreadable: check if crypto keys were rotated recently",
            "4. If key rotation issue: re-encrypt using the migration script",
            "5. Check the crypto service health via startup validation",
        ],
        retry_instructions="Fix the secret issue first. Retry the dependent operation after the secret is available.",
        related_operations=["secret_access", "crypto_decrypt"],
        prevention="Validate all secrets during startup. Monitor secret access failures.",
    ),
    Runbook(
        id="crypto_decryption_failed",
        title="Crypto Decryption Failed",
        description="A credential could not be decrypted.",
        category="security",
        severity="critical",
        possible_causes=[
            "Encryption key was rotated without migrating existing data",
            "Data was encrypted with a key that is no longer available",
            "Ciphertext was tampered with (AAD mismatch)",
            "Envelope format is corrupted or unknown",
        ],
        resolution_steps=[
            "1. Check if CM_MASTER_KEY_PREVIOUS is set for the old key",
            "2. Run the crypto migration script to re-encrypt with current key",
            "3. If AAD mismatch: the data context (tenant/provider/property) may have changed",
            "4. Check the crypto service health endpoint",
            "5. If all else fails: the credential must be re-entered manually",
        ],
        retry_instructions="Decryption failures require key/data fixes. Retry only after resolving the crypto issue.",
        related_operations=["crypto_decrypt", "secret_access"],
        prevention="Always run the migration script after key rotation. Monitor for decryption failures.",
    ),
    Runbook(
        id="night_audit_blocked",
        title="Night Audit Blocked",
        description="The nightly audit process could not complete.",
        category="operations",
        severity="critical",
        possible_causes=[
            "Unresolved check-out transactions",
            "Open folios with pending charges",
            "Database lock conflict",
            "Previous night audit still running",
        ],
        resolution_steps=[
            "1. Check for pending check-outs in the PMS",
            "2. Review open folios for unposted charges",
            "3. If locked: check for stale locks in the database",
            "4. If previous audit running: wait for completion or cancel it",
            "5. Resolve all blockers and re-run the night audit",
        ],
        retry_instructions="Resolve all blockers first. Night audit can be safely re-run once blockers are cleared.",
        related_operations=["night_audit"],
        prevention="Ensure all check-outs are processed before the audit window. Set up pre-audit validation.",
    ),
    Runbook(
        id="inventory_drift_detected",
        title="Inventory Drift Detected",
        description="The channel manager's pushed availability does not match the authoritative room_type_inventory view. Provider state has diverged from PMS truth.",
        category="sync",
        severity="critical",
        possible_causes=[
            "ARI push failed silently — provider did not apply the update",
            "Provider applied a partial update (some room types updated, others not)",
            "Manual changes made directly on the OTA extranet overrode PMS values",
            "Race condition between concurrent ARI pushes",
            "Reconciliation view is stale (>15 min) and real availability changed since",
            "Room night locks (hold, OOO, OOS) changed but ARI push was not triggered",
        ],
        resolution_steps=[
            "1. Check drift details via /api/ops/dashboard/drift-alerts for affected providers and dates",
            "2. Check view freshness via /api/ops/dashboard/inventory-alignment — if stale, trigger reconciliation",
            "3. Compare authoritative_sellable vs pushed_available per room-type-night in the provider breakdown",
            "4. If provider received wrong data: trigger a full ARI re-push for affected dates",
            "5. If provider made extranet changes: document the incident and re-push correct values",
            "6. If reconciliation is stale: wait for auto-reconciliation (5 min cycle) or trigger manually",
            "7. Verify drift is resolved by re-running /api/ops/dashboard/drift-alerts/evaluate",
        ],
        retry_instructions="Do NOT retry individual sync events. Trigger a full ARI re-push for the affected date range. Verify with a fresh alignment check after push completes.",
        related_operations=["ari_push", "reconciliation", "inventory_sync"],
        prevention="Schedule regular reconciliation jobs (every 5 min). Monitor drift alerts. Avoid manual changes on OTA extranets. Ensure ARI push confirms receipt.",
    ),
    Runbook(
        id="sync_job_stalled",
        title="Sync Job Stalled",
        description="A synchronization job has been running longer than expected without completing.",
        category="sync",
        severity="high",
        possible_causes=[
            "Provider API is slow or unresponsive",
            "Large data volume causing timeout",
            "Worker process died while processing",
            "Database connection pool exhausted",
        ],
        resolution_steps=[
            "1. Check the sync job status in /api/ops/sync",
            "2. If running too long: check provider API response times",
            "3. If worker is dead: restart the sync worker",
            "4. Mark the stalled job as failed and create a new one",
            "5. Check database connection pool health",
        ],
        retry_instructions="Mark the stalled job as failed first, then trigger a new sync. Do not retry the stalled job directly.",
        related_operations=["sync_job", "provider_sync"],
        prevention="Set appropriate timeouts. Monitor job duration metrics.",
    ),
]

# Index for fast lookup
_RUNBOOK_INDEX: dict[str, Runbook] = {rb.id: rb for rb in RUNBOOKS}


def get_runbook(runbook_id: str) -> Runbook | None:
    """Get a single runbook by ID."""
    return _RUNBOOK_INDEX.get(runbook_id)


def list_runbooks(*, category: str | None = None) -> list[dict[str, Any]]:
    """List all runbooks, optionally filtered by category."""
    result = RUNBOOKS
    if category:
        result = [rb for rb in result if rb.category == category]
    return [rb.to_dict() for rb in result]
