"""Exercise the CI install shell without sudo, network, or package mutations."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _install_step():
    workflow = yaml.safe_load((ROOT / ".github/workflows/frontend-quality.yml").read_text())
    return next(step for step in workflow["jobs"]["e2e-smoke"]["steps"] if step.get("name") == "Install Playwright browsers")


@pytest.mark.parametrize("deps_exit,browser_exit", [(0, 0), (42, 0), (0, 43)])
def test_browser_install_scopes_verified_sources_and_propagates_failure(tmp_path, deps_exit, browser_exit):
    step = _install_step()
    assert step["timeout-minutes"] == 8
    assert not step.get("continue-on-error")
    subprocess.run(["bash", "-n"], input=step["run"], text=True, check=True)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "frontend").mkdir()
    # Run sudo's command as this unprivileged test process. APT_CONFIG still has
    # to be supplied after sudo for the fake node process to see it.
    (bin_dir / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
    (bin_dir / "node").write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, re, sys\n"
        "config_path = pathlib.Path(os.environ['APT_CONFIG'])\n"
        "config = config_path.read_text()\n"
        'sources_path = re.search(r\'Dir::Etc::sourcelist \\"([^\\"]+)\\";\', config)[1]\n'
        'parts_path = re.search(r\'Dir::Etc::sourceparts \\"([^\\"]+)\\";\', config)[1]\n'
        "pathlib.Path(os.environ['INSTALL_EVIDENCE']).write_text(json.dumps({\n"
        "  'args': sys.argv[1:], 'config': config, 'config_path': str(config_path),\n"
        "  'sources': pathlib.Path(sources_path).read_text(),\n"
        "  'parts': list(map(str, pathlib.Path(parts_path).iterdir()))}))\n"
        "sys.exit(int(os.environ['DEPS_EXIT']))\n"
    )
    (bin_dir / "yarn").write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$BROWSER_EVIDENCE"\nexit "$BROWSER_EXIT"\n')
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)
    evidence = tmp_path / "install.json"
    browser_evidence = tmp_path / "browser.txt"
    result = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            **step["env"],
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "INSTALL_EVIDENCE": str(evidence),
            "BROWSER_EVIDENCE": str(browser_evidence),
            "DEPS_EXIT": str(deps_exit),
            "BROWSER_EXIT": str(browser_exit),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == (deps_exit or browser_exit), result.stderr
    observed = json.loads(evidence.read_text())
    assert observed["args"] == ["frontend/node_modules/playwright/cli.js", "install-deps", "chromium"]
    assert observed["parts"] == []
    assert 'Acquire::Retries "2";' in observed["config"]
    assert 'Acquire::https::Timeout "20";' in observed["config"]
    assert 'APT::Update::Error-Mode "any";' in observed["config"]
    assert "azure.archive" not in observed["sources"]
    assert "mirror+file" not in observed["sources"]
    for source in observed["sources"].splitlines():
        assert "signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg" in source
        assert "https://archive.ubuntu.com/ubuntu" in source or "https://security.ubuntu.com/ubuntu" in source
        assert "trusted=yes" not in source
    assert not Path(observed["config_path"]).exists(), "Temporary configuration must be cleaned up"
    if deps_exit:
        assert not browser_evidence.exists(), "A failed dependency install must stop the step"
    else:
        assert browser_evidence.read_text().splitlines() == ["playwright", "install", "chromium"]


def test_smoke_tests_remain_a_hard_gate_after_install():
    workflow = yaml.safe_load((ROOT / ".github/workflows/frontend-quality.yml").read_text())
    smoke = next(step for step in workflow["jobs"]["e2e-smoke"]["steps"] if step.get("name") == "Run e2e smoke")
    assert smoke["run"] == "cd frontend && yarn e2e"
    assert not smoke.get("continue-on-error")
