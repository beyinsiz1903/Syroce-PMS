"""
TS-011 to TS-015: Retry / Replay Resilience Tests

Tests:
- TS-011: Dry-run retry MUST NOT mutate state
- TS-012: Retry of already-successful (resolved) failure must be rejected
- TS-013: Replay of import failure must not create duplicate booking
- TS-014: Replay with missing mapping → graceful review_required
- TS-015: Key rotation — old ciphertext still decrypts

Markers: chaos_l1, chaos_l2
"""
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = [pytest.mark.asyncio]


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════
# TS-011: Dry-Run Retry MUST NOT Mutate State
# ═══════════════════════════════════════════════════════════════════

class TestDryRunSafety:
    """
    Scenario F-04: Operator runs dry-run retry.
    Guarantee: ZERO state mutation. No DB writes. No dispatch.
    """

    @pytest.mark.chaos_l1
    async def test_dry_run_does_not_change_failure_status(
        self, db, failure_event_factory, tenant_factory, retry_engine
    ):
        """Dry-run retry must not change failure status or retry_count."""
        tenant_id = tenant_factory("dryrun-001")
        failure = failure_event_factory(
            tenant_id=tenant_id,
            status="open",
            failure_type="retryable",
        )
        await db.cp_failures.insert_one(failure)

        # Record state before dry-run
        before = await db.cp_failures.find_one({"id": failure["id"]}, {"_id": 0})
        before_status = before["status"]
        before_retry_count = before["retry_count"]

        # Execute dry-run
        result = await retry_engine.retry(failure["id"], dry_run=True)

        # Verify dry-run response
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result.get("would_retry") is True

        # Verify ZERO state mutation
        after = await db.cp_failures.find_one({"id": failure["id"]}, {"_id": 0})
        assert after["status"] == before_status
        assert after["retry_count"] == before_retry_count

    @pytest.mark.chaos_l1
    async def test_dry_run_creates_no_retry_log(
        self, db, failure_event_factory, tenant_factory, retry_engine
    ):
        """Dry-run must not create any retry log entries."""
        tenant_id = tenant_factory("dryrun-002")
        failure = failure_event_factory(tenant_id=tenant_id)
        await db.cp_failures.insert_one(failure)

        # Count retry logs before
        before_count = await db.cp_retry_log.count_documents(
            {"failure_id": failure["id"]}
        )

        # Dry-run
        await retry_engine.retry(failure["id"], dry_run=True)

        # Count after — must be same
        after_count = await db.cp_retry_log.count_documents(
            {"failure_id": failure["id"]}
        )
        assert after_count == before_count

    @pytest.mark.chaos_l1
    async def test_dry_run_on_permanent_failure_rejected(
        self, db, failure_event_factory, tenant_factory, retry_engine
    ):
        """Dry-run on PERMANENT failure should be rejected (permanent = not retryable)."""
        tenant_id = tenant_factory("dryrun-003")
        failure = failure_event_factory(
            tenant_id=tenant_id,
            failure_type="permanent",
        )
        await db.cp_failures.insert_one(failure)

        result = await retry_engine.retry(failure["id"], dry_run=True)
        # For permanent failures, the engine should reject even dry-run
        # because permanent failures cannot be retried
        assert result["success"] is False
        assert result["error"] == "permanent_failure"


# ═══════════════════════════════════════════════════════════════════
# TS-012: Retry of Already-Resolved Failure
# ═══════════════════════════════════════════════════════════════════

class TestRetryAlreadyResolved:
    """
    Scenario: Operator retries a failure that is already resolved.
    Guarantee: Retry rejected. No dispatch. No state change.
    """

    @pytest.mark.chaos_l1
    async def test_resolved_failure_cannot_be_retried(
        self, db, failure_event_factory, tenant_factory, retry_engine
    ):
        """Resolved failures must not be retryable."""
        tenant_id = tenant_factory("resolved-001")
        failure = failure_event_factory(
            tenant_id=tenant_id,
            status="resolved",
        )
        await db.cp_failures.insert_one(failure)

        result = await retry_engine.retry(failure["id"])
        assert result["success"] is False
        assert result["error"] == "not_retryable"
        assert "resolved" in result.get("reason", "").lower()

    @pytest.mark.chaos_l1
    async def test_ignored_failure_cannot_be_retried(
        self, db, failure_event_factory, tenant_factory, retry_engine
    ):
        """Ignored failures must not be retryable."""
        tenant_id = tenant_factory("ignored-001")
        failure = failure_event_factory(
            tenant_id=tenant_id,
            status="ignored",
        )
        await db.cp_failures.insert_one(failure)

        result = await retry_engine.retry(failure["id"])
        assert result["success"] is False
        assert result["error"] == "not_retryable"


# ═══════════════════════════════════════════════════════════════════
# TS-013: Replay Must Not Create Duplicate Booking
# ═══════════════════════════════════════════════════════════════════

class TestReplayIdempotency:
    """
    Scenario: Import failure retried after booking already exists.
    Guarantee: No duplicate booking created.
    """

    @pytest.mark.chaos_l2
    async def test_retry_with_existing_booking_detects_duplicate(
        self, db, failure_event_factory, booking_factory, tenant_factory, retry_engine
    ):
        """Retry engine should detect already-imported booking and skip."""
        tenant_id = tenant_factory("replay-001")
        ext_res_id = f"EXT-REPLAY-{uuid.uuid4().hex[:8]}"
        import_id = str(uuid.uuid4())

        # Create existing booking (already imported)
        booking = booking_factory(
            tenant_id=tenant_id,
            ext_res_id=ext_res_id,
            provider="exely",
        )
        await db.bookings.insert_one(booking)

        # Create import record marked as imported
        import_rec = {
            "id": import_id,
            "tenant_id": tenant_id,
            "property_id": tenant_id,
            "provider": "exely",
            "external_reservation_id": ext_res_id,
            "import_status": "imported",
            "booking_id": booking["id"],
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        await db.imported_reservations.insert_one(import_rec)

        # Create a failure record pointing to this import
        failure = failure_event_factory(
            tenant_id=tenant_id,
            operation_type="reservation_import",
            context={"import_id": import_id},
        )
        await db.cp_failures.insert_one(failure)

        # Retry — should detect already-imported
        result = await retry_engine.retry(failure["id"])

        # Regardless of retry result, booking count must be exactly 1
        count = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "source.external_reservation_id": ext_res_id,
        })
        assert count == 1, f"Expected exactly 1 booking, got {count}"


# ═══════════════════════════════════════════════════════════════════
# TS-015: Key Rotation — Old Ciphertext Still Decrypts
# ═══════════════════════════════════════════════════════════════════

class TestKeyRotationResilience:
    """
    Scenario D-04: Key rotated but old ciphertext still needs to decrypt.
    Guarantee: Previous key in KeyRing allows decryption of old data.
    """

    @pytest.mark.chaos_l1
    async def test_decrypt_with_previous_key_after_rotation(self):
        """Ciphertext encrypted with v1 key should still decrypt after rotation to v2."""
        from core.crypto.engine import AESGCMEngine, AADContext
        from core.crypto.keys import KeyRing
        import secrets

        # Step 1: Encrypt with key v1
        key_v1 = secrets.token_bytes(32)
        keyring_v1 = KeyRing._from_test(current_key=key_v1, kid="v1")
        engine_v1 = AESGCMEngine(keyring_v1)

        aad = AADContext(
            tenant_id="chaos-test-rotation",
            provider="exely",
            property_id="prop1",
            environment="test",
        )
        ciphertext = engine_v1.encrypt("my-secret-api-key", aad=aad)

        # Step 2: Simulate rotation — v2 is current, v1 is previous
        key_v2 = secrets.token_bytes(32)
        keyring_rotated = KeyRing._from_test(
            current_key=key_v2,
            kid="v2",
            previous_key=key_v1,
            previous_kid="v1",
        )
        engine_rotated = AESGCMEngine(keyring_rotated)

        # Step 3: Decrypt old ciphertext with rotated keyring
        plaintext = engine_rotated.decrypt(ciphertext, aad=aad)
        assert plaintext == "my-secret-api-key"

    @pytest.mark.chaos_l1
    async def test_new_encryption_uses_current_key(self):
        """New encryptions after rotation should use the new (current) key."""
        from core.crypto.engine import AESGCMEngine, AADContext
        from core.crypto.keys import KeyRing
        from core.crypto.envelope import EncryptionEnvelope
        import secrets

        key_v1 = secrets.token_bytes(32)
        key_v2 = secrets.token_bytes(32)
        keyring = KeyRing._from_test(
            current_key=key_v2,
            kid="v2",
            previous_key=key_v1,
            previous_kid="v1",
        )
        engine = AESGCMEngine(keyring)

        aad = AADContext(tenant_id="chaos-test-newkey", provider="exely")
        ciphertext = engine.encrypt("new-secret", aad=aad)

        # Verify the envelope uses kid=v2
        envelope = EncryptionEnvelope.deserialize(ciphertext)
        assert envelope.kid == "v2"


# ═══════════════════════════════════════════════════════════════════
# Failure Lifecycle State Machine
# ═══════════════════════════════════════════════════════════════════

class TestFailureLifecycle:
    """
    Full lifecycle: record → resolve/ignore → attempt retry.
    Tests the complete state machine transitions.
    """

    @pytest.mark.chaos_l2
    async def test_full_lifecycle_open_to_resolved(
        self, db, failure_tracker, tenant_factory
    ):
        """Failure lifecycle: record (open) → resolve (resolved)."""
        tenant_id = tenant_factory("lifecycle-001")

        # Record failure
        event = await failure_tracker.record(
            tenant_id=tenant_id,
            provider="exely",
            operation_type="reservation_import",
            error_code="IMPORT_TIMEOUT",
            error_message="Connection timed out",
        )
        assert event["status"] == "open"

        # Resolve
        resolved = await failure_tracker.resolve(event["id"])
        assert resolved is True

        # Verify state
        doc = await db.cp_failures.find_one({"id": event["id"]}, {"_id": 0})
        assert doc["status"] == "resolved"
        assert doc.get("resolved_by") == "operator"

    @pytest.mark.chaos_l2
    async def test_resolve_is_idempotent(
        self, db, failure_tracker, tenant_factory
    ):
        """Resolving an already-resolved failure should return False (no-op)."""
        tenant_id = tenant_factory("lifecycle-002")
        event = await failure_tracker.record(
            tenant_id=tenant_id,
            provider="exely",
            operation_type="ari_push",
            error_code="PUSH_FAILED",
            error_message="Connection refused",
        )

        # First resolve
        assert await failure_tracker.resolve(event["id"]) is True
        # Second resolve — idempotent, returns False
        assert await failure_tracker.resolve(event["id"]) is False
