import importlib


def _production_limiter(monkeypatch):
    for key in (
        "CLOUD_DEPLOYMENT",
        "E2E_ALLOW_DESTRUCTIVE_STRESS",
        "TESTING",
        "CI",
        "APP_ENV",
        "CLOUD_INSTANCE_ID",
        "CLOUD_DEV_DOMAIN",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")

    import apm_middleware

    importlib.reload(apm_middleware)
    return apm_middleware.EnhancedRateLimitMiddleware(app=lambda *_args, **_kwargs: None)


def test_public_room_qr_has_bounded_dedicated_bucket(monkeypatch):
    limiter = _production_limiter(monkeypatch)

    assert limiter._get_category("/api/public/room-qr/tenant/room/session", "POST", False) == "room_qr_public"
    assert limiter._get_category("/api/public/room-qr/tenant/room/submit", "POST", False) == "room_qr_public"
    assert limiter._get_category("/api/public/room-qr/tenant/room/catalogue", "GET", False) == "anonymous"
    assert limiter._get_category("/api/public/other", "POST", False) == "anonymous"

    qr_decisions = [limiter._check_limit("ip:test", "room_qr_public")[0] for _ in range(121)]
    assert qr_decisions[:120] == [True] * 120
    assert qr_decisions[120] is False

    anonymous_decisions = [limiter._check_limit("ip:other", "anonymous")[0] for _ in range(61)]
    assert anonymous_decisions[:60] == [True] * 60
    assert anonymous_decisions[60] is False
