from __future__ import annotations

from datetime import UTC, datetime

from scripts import verify_atlas_backup


def test_missing_keys_are_allowed_in_development(monkeypatch):
    for key in (
        "ATLAS_API_PUBLIC_KEY",
        "ATLAS_API_PRIVATE_KEY",
        "ATLAS_PROJECT_ID",
        "ATLAS_CLUSTER_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")

    assert verify_atlas_backup.main(["--quiet"]) == 0


def test_missing_keys_fail_in_production(monkeypatch):
    for key in (
        "ATLAS_API_PUBLIC_KEY",
        "ATLAS_API_PRIVATE_KEY",
        "ATLAS_PROJECT_ID",
        "ATLAS_CLUSTER_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert verify_atlas_backup.main(["--quiet"]) == 2


def test_require_keys_fails_closed_in_any_environment(monkeypatch):
    for key in (
        "ATLAS_API_PUBLIC_KEY",
        "ATLAS_API_PRIVATE_KEY",
        "ATLAS_PROJECT_ID",
        "ATLAS_CLUSTER_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")

    assert verify_atlas_backup.main(["--quiet", "--require-keys"]) == 2


def test_fetch_verifies_cluster_flags_and_snapshot(monkeypatch):
    import requests

    monkeypatch.setenv("ATLAS_API_PUBLIC_KEY", "public")
    monkeypatch.setenv("ATLAS_API_PRIVATE_KEY", "private")
    monkeypatch.setenv("ATLAS_PROJECT_ID", "project")
    monkeypatch.setenv("ATLAS_CLUSTER_NAME", "cluster")
    calls = []

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/cluster"):
            return Response({"backupEnabled": True, "pitEnabled": True})
        return Response(
            {
                "results": [
                    {
                        "id": "snapshot-1",
                        "createdAt": "2026-09-09T00:00:00Z",
                        "storageSizeBytes": 1048576,
                    }
                ]
            }
        )

    monkeypatch.setattr(requests, "get", get)

    result = verify_atlas_backup._fetch_latest_snapshot()

    assert result["cloud_backup_enabled"] is True
    assert result["pitr_enabled"] is True
    assert result["snapshot_id"] == "snapshot-1"
    assert len(calls) == 2
    assert all("application/vnd.atlas" in call[1]["headers"]["Accept"] for call in calls)


def test_disabled_backup_or_pitr_fails_even_with_fresh_snapshot(monkeypatch, tmp_path):
    for key in (
        "ATLAS_API_PUBLIC_KEY",
        "ATLAS_API_PRIVATE_KEY",
        "ATLAS_PROJECT_ID",
        "ATLAS_CLUSTER_NAME",
    ):
        monkeypatch.setenv(key, "configured")
    monkeypatch.setattr(
        verify_atlas_backup,
        "_fetch_latest_snapshot",
        lambda: {
            "snapshot_id": "snapshot-1",
            "created_at": datetime.now(UTC).isoformat(),
            "type": "scheduled",
            "cloud_backup_enabled": True,
            "pitr_enabled": False,
        },
    )
    sidecar = tmp_path / "verification.json"

    result = verify_atlas_backup.main(["--quiet", "--sidecar", str(sidecar)])

    assert result == 1
    assert '"fresh": false' in sidecar.read_text()
