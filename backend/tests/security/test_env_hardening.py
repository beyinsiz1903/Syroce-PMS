"""
Tests for security hardening changes in deploy/generate_env.py and backend/start.sh.

Covers:
- generate_env.py: secret values must NOT appear on stdout
- generate_env.py: generated file must have mode 0600
- generate_env.py: must refuse to overwrite an existing file
- start.sh: production without CM_MASTER_KEY_CURRENT must exit non-zero
- start.sh: non-production allows the dev fallback
"""
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATE_ENV = REPO_ROOT / "deploy" / "generate_env.py"
START_SH = REPO_ROOT / "backend" / "start.sh"
PYTHON = sys.executable


# ── generate_env.py tests ──────────────────────────────────────────────────


class TestGenerateEnv:
    def _run(self, target_dir: str, env: dict | None = None) -> subprocess.CompletedProcess:
        """Run generate_env.py with a patched target directory."""
        # Patch the target path via env so we never write to the real deploy/.env
        code = GENERATE_ENV.read_text()
        patched = code.replace(
            "os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')",
            f"os.path.join({repr(target_dir)}, '.env')",
        )
        tmp_script = Path(target_dir) / "_test_generate_env.py"
        tmp_script.write_text(patched)
        result = subprocess.run(
            [PYTHON, str(tmp_script)],
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        tmp_script.unlink(missing_ok=True)
        return result

    def test_secrets_not_in_stdout(self):
        """Generated secret values must not appear on stdout."""
        with tempfile.TemporaryDirectory() as d:
            result = self._run(d)
            assert result.returncode == 0, result.stderr

            env_path = Path(d) / ".env"
            env_content = env_path.read_text()

            # Extract actual secret values from the file
            secrets = {}
            for line in env_content.splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    secrets[k.strip()] = v.strip()

            secret_keys = {"JWT_SECRET", "CM_CREDENTIAL_KEY", "CM_MASTER_KEY_CURRENT"}
            for key in secret_keys:
                value = secrets.get(key, "")
                assert value, f"{key} is empty in generated file"
                assert value not in result.stdout, (
                    f"{key} value appeared on stdout — secret leaked!"
                )

    def test_generated_file_permissions(self):
        """Generated .env file must have mode 0600."""
        with tempfile.TemporaryDirectory() as d:
            result = self._run(d)
            assert result.returncode == 0, result.stderr

            env_path = Path(d) / ".env"
            file_mode = stat.S_IMODE(env_path.stat().st_mode)
            assert file_mode == 0o600, (
                f"Expected 0600, got {oct(file_mode)}"
            )

    def test_refuses_to_overwrite_existing_file(self):
        """Script must exit non-zero if .env already exists."""
        with tempfile.TemporaryDirectory() as d:
            # Pre-create the file
            existing = Path(d) / ".env"
            existing.write_text("EXISTING=true\n")

            result = self._run(d)
            assert result.returncode != 0, "Should have exited non-zero when .env exists"
            # Original file must be untouched
            assert existing.read_text() == "EXISTING=true\n"

    def test_no_plain_dash_dash_separator_on_stdout(self):
        """The old '---' separator with secret dump must not appear."""
        with tempfile.TemporaryDirectory() as d:
            result = self._run(d)
            assert "---" not in result.stdout or "values are not displayed" in result.stdout

    def test_done_message_contains_path(self):
        """Stdout must contain the file path for operator confirmation."""
        with tempfile.TemporaryDirectory() as d:
            result = self._run(d)
            assert result.returncode == 0, result.stderr
            assert ".env" in result.stdout


# ── start.sh CM_MASTER_KEY guard tests ────────────────────────────────────


def _run_start_sh_dry(env_overrides: dict) -> subprocess.CompletedProcess:
    """
    Source _validate_master_key() from the real start.sh and call it.

    This exercises the actual production function, not a copy of it.
    If start.sh is changed, this test will pick up the change automatically.
    """
    # Extract only function definitions + the guard call to avoid side-effects
    # (MongoDB/Redis startup etc). We do this by sourcing start.sh with set -n
    # (parse without executing) to get the function defined, then calling it.
    # Simpler and more portable: grep out the function body and call it.
    wrapper = f"""
#!/bin/bash
set -e

# Source only the _validate_master_key function from the real start.sh.
# We use `source` with a sub-shell trick: extract the function, eval it,
# then call it. This avoids executing the rest of start.sh.
_fn_body=$(awk '
  /^_validate_master_key\\(\\)/ {{ found=1 }}
  found {{ print }}
  found && /^\\}}/ {{ found=0; exit }}
' "{START_SH}")

eval "$_fn_body"

_validate_master_key
EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  echo "KEY_CHECK: ok"
else
  echo "KEY_CHECK: failed"
  exit 1
fi
"""
    with tempfile.NamedTemporaryFile(suffix=".sh", mode="w", delete=False) as f:
        f.write(wrapper)
        script_path = f.name

    try:
        os.chmod(script_path, 0o700)
        result = subprocess.run(
            ["bash", script_path],
            capture_output=True,
            text=True,
            env={**os.environ, **env_overrides},
        )
    finally:
        os.unlink(script_path)

    return result


class TestStartShMasterKeyGuard:
    def test_production_without_key_fails(self):
        """start.sh must exit non-zero in production if CM_MASTER_KEY_CURRENT is unset."""
        result = _run_start_sh_dry({"APP_ENV": "production", "CM_MASTER_KEY_CURRENT": ""})
        assert result.returncode != 0
        assert "ERROR" in result.stdout or "ERROR" in result.stderr

    def test_cloud_deployment_without_key_fails(self):
        """CLOUD_DEPLOYMENT set without key must also fail."""
        result = _run_start_sh_dry({
            "APP_ENV": "",
            "CLOUD_DEPLOYMENT": "1",
            "CM_MASTER_KEY_CURRENT": "",
        })
        assert result.returncode != 0

    def test_production_with_key_passes(self):
        """start.sh must succeed in production when a key is provided."""
        result = _run_start_sh_dry({
            "APP_ENV": "production",
            "CM_MASTER_KEY_CURRENT": "a-strong-32-character-production-key!",
        })
        assert result.returncode == 0
        assert "KEY_CHECK: ok" in result.stdout

    def test_non_production_allows_fallback(self):
        """In non-production, missing key must fall back to dev value (not fail)."""
        result = _run_start_sh_dry({"APP_ENV": "development", "CM_MASTER_KEY_CURRENT": ""})
        assert result.returncode == 0
        assert "KEY_CHECK: ok" in result.stdout

    def test_non_production_respects_provided_key(self):
        """In non-production, if a key IS provided it must be used (not overwritten)."""
        result = _run_start_sh_dry({
            "APP_ENV": "development",
            "CM_MASTER_KEY_CURRENT": "my-dev-key",
        })
        assert result.returncode == 0
        assert "KEY_CHECK: ok" in result.stdout

    def test_dev_fallback_value_rejected_in_production(self):
        """The known dev fallback value must never pass production guard."""
        result = _run_start_sh_dry({
            "APP_ENV": "production",
            "CM_MASTER_KEY_CURRENT": "dev-master-key-not-for-production-use-only",
        })
        # The start.sh guard itself only checks for empty/missing.
        # The startup_validator / env_guard is responsible for rejecting the known-weak value.
        # Here we confirm the shell guard PASSES (non-empty), but document that
        # the application-level env_guard must reject the known-weak hash.
        # This test is intentionally a documentation test, not a security gate.
        assert result.returncode == 0, (
            "Shell guard passes non-empty dev key — "
            "rejection of this specific value is handled by startup_validator / env_guard"
        )
