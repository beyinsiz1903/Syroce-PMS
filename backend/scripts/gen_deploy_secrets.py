#!/usr/bin/env python3
"""
Generate production secrets for the DigitalOcean (or any) deployment.

Run this in a TRUSTED shell (e.g. the Replit Shell). It prints four secret
values to STDOUT and writes NOTHING to disk. Copy each ``KEY=VALUE`` line into
the deployment platform's ENCRYPTED environment variables, then close the
terminal.

NEVER paste these values into a chat, commit them, or share them. Each run
produces brand-new values; re-running ROTATES them (which invalidates existing
JWTs, browser push subscriptions, and re-keys field encryption — only rotate
deliberately).

Generated keys:
  JWT_SECRET             - JWT signing secret (strong random)
  CM_MASTER_KEY_CURRENT  - field-encryption master key (32+ chars)
  VAPID_PUBLIC_KEY       - Web Push P-256 public key (65-byte point, base64url)
  VAPID_PRIVATE_KEY      - Web Push P-256 private scalar (32-byte, base64url)

Usage:
  python backend/scripts/gen_deploy_secrets.py
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys

from cryptography.hazmat.primitives.asymmetric import ec

# Dev hashes that infra/production_config.FORBIDDEN_DEV_HASHES rejects at boot.
_FORBIDDEN_DEV_HASHES = {
    "22a37967b374a741a098889a2e138a1899499d0ae54e05fcd503e7bb6f86196d",
    "868a835b20ce9fa05d2a549e0d3812178d717279e438cde6bd56e6bbd10b2929",
    "0b2b61eaa2e151477eb687402d1c9ef6252c76644419d78964ed3145afcc681c",
    "6c746409f783b492d492026d654d7680a0ea9ca4078fc7aecdcfa1837c3ea4bf",
    "d8653c8676059b84c4299f805848f826b998746cc44a25c838c9daa976aa4815",
}


def _b64url_no_pad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def strong_secret() -> str:
    """A strong random secret that is never one of the forbidden dev hashes."""
    while True:
        value = secrets.token_urlsafe(48)
        if hashlib.sha256(value.encode()).hexdigest() not in _FORBIDDEN_DEV_HASHES:
            return value


def gen_vapid_keypair() -> tuple[str, str]:
    """Generate a P-256 VAPID keypair in the exact encoding the backend uses
    (see domains/guest/messaging/web_push.py): uncompressed 65-byte public
    point (0x04 || X || Y) and the raw 32-byte private scalar, both base64url
    without padding."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    nums = private_key.public_key().public_numbers()
    pub_raw = b"\x04" + nums.x.to_bytes(32, "big") + nums.y.to_bytes(32, "big")
    priv_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    return _b64url_no_pad(pub_raw), _b64url_no_pad(priv_raw)


def main() -> int:
    jwt_secret = strong_secret()
    cm_master_key = strong_secret()
    vapid_public, vapid_private = gen_vapid_keypair()

    # Self-validate the VAPID keys against the project's own boot-time gate so a
    # malformed keypair can never reach the deployment.
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, backend_dir)
    try:
        from infra.production_config import validate_vapid_key_format

        errors = validate_vapid_key_format(public_key=vapid_public, private_key=vapid_private)
        if errors:
            print("ERROR: generated VAPID keys failed self-validation:", file=sys.stderr)
            for err in errors:
                print("  - " + err, file=sys.stderr)
            return 1
    except Exception as exc:  # pragma: no cover - validator import is best-effort
        print(f"WARN: could not self-validate VAPID keys ({exc!r})", file=sys.stderr)

    print("# ---- COPY EACH LINE INTO DO ENCRYPTED ENV VARS — DO NOT SHARE ----")
    print(f"JWT_SECRET={jwt_secret}")
    print(f"CM_MASTER_KEY_CURRENT={cm_master_key}")
    print(f"VAPID_PUBLIC_KEY={vapid_public}")
    print(f"VAPID_PRIVATE_KEY={vapid_private}")
    print("# ---- also set (non-secret): STRICT_JWT_SECRET=1 ----")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
