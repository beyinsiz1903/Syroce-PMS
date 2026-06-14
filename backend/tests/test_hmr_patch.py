"""
Regression test: Verifies that the Vite HMR client patch is correctly applied.

This test ensures that after any `yarn install`, the postinstall script
has removed all `location.reload()` calls from Vite's HMR client, preventing
automatic page refreshes in proxied environments.

Run: pytest backend/tests/test_hmr_patch.py -v
"""

import os
import re
import subprocess

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend')
VITE_CLIENT = os.path.join(
    FRONTEND_DIR, 'node_modules', 'vite', 'dist', 'client', 'client.mjs'
)
PATCH_SCRIPT = os.path.join(FRONTEND_DIR, 'scripts', 'patch-vite-client.js')


class TestHmrPatchRegression:
    """Regression tests for the HMR auto-reload suppression."""

    def test_patch_script_exists(self):
        """Postinstall patch script must exist."""
        assert os.path.isfile(PATCH_SCRIPT), (
            f"Patch script missing at {PATCH_SCRIPT}. "
            "This is required to prevent page auto-refresh in proxied environments."
        )

    def test_vite_client_is_patched(self):
        """Vite client must have the Syroce patch marker."""
        assert os.path.isfile(VITE_CLIENT), f"Vite client not found at {VITE_CLIENT}"
        with open(VITE_CLIENT, 'r') as f:
            content = f.read()
        assert '__SYROCE_HMR_PATCHED__' in content, (
            "Vite client is NOT patched. Run `yarn install` or "
            "`node scripts/patch-vite-client.js` to apply the patch."
        )

    def test_no_location_reload_in_vite_client(self):
        """Vite client must NOT contain any location.reload() calls."""
        assert os.path.isfile(VITE_CLIENT), f"Vite client not found at {VITE_CLIENT}"
        with open(VITE_CLIENT, 'r') as f:
            content = f.read()
        matches = re.findall(r'location\.reload\(\)', content)
        assert len(matches) == 0, (
            f"Found {len(matches)} unpatched location.reload() calls in Vite client. "
            "Run `node scripts/patch-vite-client.js` to fix."
        )

    def test_suppression_logs_present(self):
        """Patched Vite client should have suppression console.debug calls."""
        assert os.path.isfile(VITE_CLIENT), f"Vite client not found at {VITE_CLIENT}"
        with open(VITE_CLIENT, 'r') as f:
            content = f.read()
        count = content.count('auto-reload suppressed by Syroce patch')
        assert count >= 3, (
            f"Expected at least 3 suppression markers, found {count}. "
            "The patch may be incomplete."
        )

    def test_postinstall_in_package_json(self):
        """package.json must have the postinstall script configured."""
        import json
        pkg_path = os.path.join(FRONTEND_DIR, 'package.json')
        with open(pkg_path, 'r') as f:
            pkg = json.load(f)
        scripts = pkg.get('scripts', {})
        assert 'postinstall' in scripts, (
            "postinstall script missing from package.json. "
            "Add: \"postinstall\": \"node scripts/patch-vite-client.js\""
        )
        assert 'patch-vite-client' in scripts['postinstall'], (
            "postinstall script does not reference patch-vite-client.js"
        )

    def test_vite_config_has_reload_guard(self):
        """vite.config.js must contain the HMR reload guard plugin."""
        config_path = os.path.join(FRONTEND_DIR, 'vite.config.js')
        with open(config_path, 'r') as f:
            content = f.read()
        assert 'hmrReloadGuard' in content or 'hmr-reload-guard' in content, (
            "vite.config.js is missing the hmrReloadGuard plugin"
        )
        assert 'transformIndexHtml' in content, (
            "vite.config.js plugin must include transformIndexHtml for runtime guard"
        )

    def test_reload_guard_is_dev_only(self):
        """Layer 3 runtime reload override must be injected ONLY in dev.

        The guard overrides Location.prototype.reload to no-op without recent user
        interaction. In a production build there is no Vite HMR client (the thing it
        defends against), so injecting it into prod only silently blocks the
        stale-chunk self-heal reload -> blank white screen on returning tabs after a
        deploy. It must therefore be gated on `ctx.server`, which Vite sets only
        during `vite serve` (dev), never during `vite build`.
        """
        config_path = os.path.join(FRONTEND_DIR, 'vite.config.js')
        with open(config_path, 'r') as f:
            content = f.read()
        assert 'transformIndexHtml(html, ctx)' in content, (
            "transformIndexHtml must accept ctx so it can distinguish dev from prod."
        )
        assert 'ctx.server' in content, (
            "Layer 3 reload guard must be gated on ctx.server (dev-only). Injecting it "
            "into production builds breaks the stale-chunk self-heal and causes a blank "
            "white screen on already-open tabs after a deploy."
        )

    def test_patch_is_idempotent(self):
        """Running the patch script twice should not double-patch."""
        result = subprocess.run(
            ['node', PATCH_SCRIPT],
            capture_output=True, text=True, cwd=FRONTEND_DIR
        )
        assert result.returncode == 0, f"Patch script failed: {result.stderr}"
        assert 'Already patched' in result.stdout, (
            "Second run should detect existing patch and skip"
        )
        # Verify still only 3 suppression markers
        with open(VITE_CLIENT, 'r') as f:
            content = f.read()
        count = content.count('auto-reload suppressed by Syroce patch')
        assert count == 3, f"Expected exactly 3 suppression markers after idempotent run, found {count}"

    def test_hmr_timeout_configured(self):
        """Vite HMR timeout should be configured for frequent pings."""
        config_path = os.path.join(FRONTEND_DIR, 'vite.config.js')
        with open(config_path, 'r') as f:
            content = f.read()
        assert 'timeout:' in content or 'timeout :' in content, (
            "vite.config.js should configure HMR timeout for proxy keepalive"
        )
