import os


def enforce_production_safety_gate() -> None:
    """
    Enforces strict security checks on environment variables when the app is
    running in production or staging. Prevents the application from starting
    with dangerous or insecure configurations by raising a RuntimeError.
    """
    env = os.environ.get("ENV", "").lower()

    # 1. We only apply these strict guards if we are in production or staging
    is_production = env == "production"
    is_staging = env == "staging"

    if not (is_production or is_staging):
        return

    # 2. Check for TESTING flag
    if is_production and os.environ.get("TESTING") == "1":
        raise RuntimeError("Cannot run production with TESTING=1")

    # 3. Check for COOKIE_SECURE flag
    cookie_secure_raw = os.environ.get("COOKIE_SECURE", "true").lower()
    if cookie_secure_raw in ("false", "0", ""):
        raise RuntimeError(f"Cannot run {env} with COOKIE_SECURE disabled")

    # 4. Check for ALLOWED_ORIGINS explicitly containing dangerous values or being unset
    if is_production:
        allowed_origins = os.environ.get("ALLOWED_ORIGINS")
        if allowed_origins is None:
            raise RuntimeError("Cannot run production without ALLOWED_ORIGINS explicitly set")

        origins = [o.strip().lower() for o in allowed_origins.split(",") if o.strip()]

        for origin in origins:
            if origin == "*" or "localhost" in origin or "127.0.0.1" in origin or "0.0.0.0" in origin:
                raise RuntimeError(f"Cannot run production with dangerous ALLOWED_ORIGINS: {origin}")

    # 5. Check for DEBUG flag
    if is_production:
        debug_raw = os.environ.get("DEBUG", "false").lower()
        if debug_raw in ("true", "1"):
            raise RuntimeError("Cannot run production with DEBUG=True")

    # 6. Check for DEMO_PASSWORD
    if is_production and os.environ.get("DEMO_PASSWORD"):
        raise RuntimeError("Cannot run production with DEMO_PASSWORD set (seed operations forbidden)")

    # 7. Check critical secrets
    if is_production:
        critical_secrets = [
            "JWT_SECRET",
            "CM_MASTER_KEY_CURRENT",
        ]

        # Sadece varsayılan COOKIE_SECRET varsa kontrol et, bazı frameworkler SESSION_SECRET kullanıyor olabilir
        if os.environ.get("COOKIE_SECRET") is not None:
            critical_secrets.append("COOKIE_SECRET")

        dummy_values = {"", "changeme", "dev", "test", "secret", "default"}

        for secret_name in critical_secrets:
            secret_val = os.environ.get(secret_name, "").strip().lower()
            if secret_val in dummy_values:
                raise RuntimeError(f"Cannot run production with missing, empty, or default {secret_name}")
