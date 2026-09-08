from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from infra import atlas_backup_check
from infra.deployment_orchestrator import DeploymentOrchestrator


def _prod_atlas(monkeypatch, tmp_path):
    atlas_backup_check._LIVE_CACHE.clear()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MONGO_URL", "mongodb+srv://example.mongodb.net/app")
    monkeypatch.setenv("ATLAS_TIER", "M10")
    sidecar = tmp_path / "atlas.json"
    monkeypatch.setenv("ATLAS_BACKUP_SIDECAR", str(sidecar))
    return sidecar


def _set_api_keys(monkeypatch):
    monkeypatch.setenv("ATLAS_API_PUBLIC_KEY", "public")
    monkeypatch.setenv("ATLAS_API_PRIVATE_KEY", "private")
    monkeypatch.setenv("ATLAS_PROJECT_ID", "project")
    monkeypatch.setenv("ATLAS_CLUSTER_NAME", "cluster")


def test_tier_alone_is_not_backup_proof(monkeypatch, tmp_path):
    _prod_atlas(monkeypatch, tmp_path)

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": True})

    assert payload["status"] == "atlas_backup_not_declared"
    assert payload["atlas"]["supports_continuous_backup"] is True
    assert payload["atlas"]["has_continuous_backup"] is False
    assert score == 0.0


def test_declared_backup_without_verification_fails_closed(monkeypatch, tmp_path):
    _prod_atlas(monkeypatch, tmp_path)
    monkeypatch.setenv("ATLAS_CLOUD_BACKUP_ENABLED", "true")
    monkeypatch.setenv("ATLAS_PITR_ENABLED", "true")

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": False})

    assert payload["status"] == "atlas_backup_unverified"
    assert score == 0.0


def test_fresh_verified_continuous_backup_is_ready(monkeypatch, tmp_path):
    sidecar = _prod_atlas(monkeypatch, tmp_path)
    monkeypatch.setenv("ATLAS_CLOUD_BACKUP_ENABLED", "true")
    monkeypatch.setenv("ATLAS_PITR_ENABLED", "true")
    sidecar.write_text(
        json.dumps(
            {
                "verified_at": datetime.now(UTC).isoformat(),
                "snapshot_age_hours": 1.0,
                "fresh": True,
            }
        )
    )

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": False})

    assert payload["status"] == "atlas_managed"
    assert payload["atlas"]["verification_fresh"] is True
    assert score == 1.0


def test_stale_sidecar_cannot_remain_fresh_forever(monkeypatch, tmp_path):
    sidecar = _prod_atlas(monkeypatch, tmp_path)
    monkeypatch.setenv("ATLAS_CLOUD_BACKUP_ENABLED", "true")
    monkeypatch.setenv("ATLAS_PITR_ENABLED", "true")
    sidecar.write_text(
        json.dumps(
            {
                "verified_at": (datetime.now(UTC) - timedelta(hours=30)).isoformat(),
                "snapshot_age_hours": 1.0,
                "fresh": True,
            }
        )
    )

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": False})

    assert payload["status"] == "atlas_backup_unverified"
    assert payload["atlas"]["verification_fresh"] is False
    assert score == 0.0


def test_snapshot_age_advances_after_verification(monkeypatch, tmp_path):
    sidecar = _prod_atlas(monkeypatch, tmp_path)
    monkeypatch.setenv("ATLAS_CLOUD_BACKUP_ENABLED", "true")
    monkeypatch.setenv("ATLAS_PITR_ENABLED", "true")
    sidecar.write_text(
        json.dumps(
            {
                "verified_at": (datetime.now(UTC) - timedelta(hours=10)).isoformat(),
                "snapshot_age_hours": 20.0,
                "fresh": True,
            }
        )
    )

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": False})

    assert payload["status"] == "atlas_backup_unverified"
    assert payload["atlas"]["effective_snapshot_age_hours"] >= 29.9
    assert score == 0.0


def test_live_admin_api_verification_closes_readiness(monkeypatch, tmp_path):
    _prod_atlas(monkeypatch, tmp_path)
    _set_api_keys(monkeypatch)
    monkeypatch.setenv("ATLAS_CLOUD_BACKUP_ENABLED", "true")
    monkeypatch.setenv("ATLAS_PITR_ENABLED", "true")
    monkeypatch.setattr(
        "scripts.verify_atlas_backup._fetch_latest_snapshot",
        lambda: {
            "snapshot_id": "snapshot-1",
            "created_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            "cloud_backup_enabled": True,
            "pitr_enabled": True,
        },
    )

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": False})

    assert payload["status"] == "atlas_managed"
    assert payload["atlas"]["verification_source"] == "atlas_admin_api"
    assert payload["atlas"]["verification_error"] is None
    assert score == 1.0


def test_admin_api_disabled_backup_overrides_optimistic_env(monkeypatch, tmp_path):
    _prod_atlas(monkeypatch, tmp_path)
    _set_api_keys(monkeypatch)
    monkeypatch.setenv("ATLAS_CLOUD_BACKUP_ENABLED", "true")
    monkeypatch.setenv("ATLAS_PITR_ENABLED", "true")
    monkeypatch.setattr(
        "scripts.verify_atlas_backup._fetch_latest_snapshot",
        lambda: {
            "snapshot_id": "snapshot-1",
            "created_at": datetime.now(UTC).isoformat(),
            "cloud_backup_enabled": False,
            "pitr_enabled": False,
        },
    )

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": False})

    assert payload["status"] == "atlas_backup_not_declared"
    assert payload["atlas"]["cloud_backup_enabled"] is False
    assert payload["atlas"]["pitr_enabled"] is False
    assert score == 0.0


def test_live_verification_failure_is_sanitized(monkeypatch, tmp_path):
    _prod_atlas(monkeypatch, tmp_path)
    _set_api_keys(monkeypatch)
    monkeypatch.setenv("ATLAS_CLOUD_BACKUP_ENABLED", "true")
    monkeypatch.setenv("ATLAS_PITR_ENABLED", "true")

    def fail():
        raise RuntimeError("secret-bearing URL must not leak")

    monkeypatch.setattr("scripts.verify_atlas_backup._fetch_latest_snapshot", fail)

    payload, score = atlas_backup_check.resolve_backup_check({"enabled": False})

    assert payload["status"] == "atlas_backup_unverified"
    assert payload["atlas"]["verification_error"] == "RuntimeError"
    assert "secret-bearing" not in str(payload)
    assert score == 0.0


def test_non_atlas_enabled_flag_without_real_backup_fails_closed(monkeypatch):
    atlas_backup_check._LIVE_CACHE.clear()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MONGO_URL", "mongodb://mongo:27017/app")

    payload, score = atlas_backup_check.resolve_backup_check(
        {"enabled": True, "backup_path": "/tmp/backups", "last_successful": None}
    )

    assert payload["status"] == "enabled_unverified"
    assert payload["durable_destination"] is False
    assert score == 0.0


def test_non_atlas_recent_durable_backup_is_ready(monkeypatch, tmp_path):
    atlas_backup_check._LIVE_CACHE.clear()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MONGO_URL", "mongodb://mongo:27017/app")

    payload, score = atlas_backup_check.resolve_backup_check(
        {
            "enabled": True,
            "backup_path": str(tmp_path),
            "last_successful": {
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
            },
        }
    )

    assert payload["status"] == "enabled_verified"
    assert payload["durable_destination"] is True
    assert score == 1.0


def test_deployment_risk_uses_resolved_backup_evidence(monkeypatch):
    monkeypatch.setattr(
        atlas_backup_check,
        "resolve_backup_check",
        lambda _status: ({"status": "atlas_managed"}, 1.0),
    )

    result = DeploymentOrchestrator().assess_risk()

    assert all(risk["factor"] != "no_backup" for risk in result["risks"])
