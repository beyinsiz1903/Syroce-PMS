"""Host retention safety: pure planner plus an in-memory Docker executor."""
import fcntl
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("image_retention", ROOT / "deploy/image-retention.py")
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)
PREFIX = "ghcr.io/example/syroce"
NOW = datetime(2026, 10, 25, 15, tzinfo=UTC)


def sha(index):
    return f"{index:040x}"


def ref(index, service):
    return f"{PREFIX}-{service}:{sha(index)}"


def fixture():
    images = []
    for index in range(7):
        for service in sorted(policy.SERVICES):
            tag = ref(index, service)
            images.append({"id": "sha256:" + hashlib.sha256(tag.encode()).hexdigest(),
                           "tags": [tag], "created": (NOW - timedelta(days=7 - index)).isoformat()})
    images.append({"id": "nginx-image", "tags": ["nginx:1.25-alpine"], "created": NOW.isoformat()})
    containers = []
    for service in sorted(policy.RUNTIME):
        reference = "nginx:1.25-alpine" if service == "nginx" else ref(6, "worker" if service == "beat" else service)
        image = next(row for row in images if reference in row["tags"])
        containers.append({"id": service, "image": image["id"], "reference": reference,
                           "project": "syroce-pms", "service": service, "running": True, "health": "healthy"})
    return {"images": images, "containers": containers, "volumes": ["untouched-data"]}


def plan(data=None, history=None, candidate=None):
    return policy.build_plan(data or fixture(), PREFIX, history or [], candidate or sha(7), NOW)


def test_bootstrap_keeps_active_plus_two_complete_older_rollback_sets_and_candidate():
    result = plan()
    assert result["current"] == sha(6)
    assert set(result["bootstrap_rollback_candidates"]) == {sha(5), sha(4)}
    assert set(result["protected_revisions"]) == {sha(4), sha(5), sha(6), sha(7)}
    assert {target["reference"] for target in result["targets"]} == {
        ref(index, service) for index in range(4) for service in policy.SERVICES}


def test_successful_history_is_not_displaced_by_newer_failed_complete_pulls():
    result = plan(history=[sha(0), sha(1), sha(2)])
    assert set(result["protected_revisions"]) == {sha(0), sha(1), sha(2), sha(6), sha(7)}
    assert result["bootstrap_rollback_candidates"] == []
    assert {row["reference"] for row in result["targets"]} == {ref(i, s) for i in (3, 4, 5) for s in policy.SERVICES}


def test_stopped_unrelated_container_pins_its_exact_image():
    data = fixture()
    image = data["images"][0]
    data["containers"].append({"id": "stopped", "image": image["id"], "reference": image["tags"][0],
                               "project": "another-app", "service": "unrelated", "running": False, "health": None})
    assert image["tags"][0] not in {row["reference"] for row in plan(data)["targets"]}


def test_unmanaged_alias_and_shared_protected_image_ids_are_preserved():
    data = fixture()
    data["images"][0]["tags"].append("another-project:release")
    data["images"][1]["id"] = next(image["id"] for image in data["images"] if ref(6, "worker") in image["tags"])
    candidates = {row["reference"] for row in plan(data)["targets"]}
    assert ref(0, "backend") not in candidates
    assert ref(0, "frontend") not in candidates


def test_recent_partial_candidate_and_untagged_or_non_sha_images_are_untouched():
    data = fixture()
    data["images"][0]["created"] = (NOW - timedelta(minutes=14)).isoformat()
    data["images"].extend([
        {"id": "candidate-partial", "tags": [ref(7, "backend")], "created": (NOW - timedelta(days=8)).isoformat()},
        {"id": "dangling", "tags": None, "created": "not examined"},
        {"id": "latest", "tags": [PREFIX + "-backend:latest"], "created": "not examined"},
    ])
    targets = plan(data)["targets"]
    assert ref(0, "backend") not in {row["reference"] for row in targets}
    assert not {"candidate-partial", "dangling", "latest"} & {row["id"] for row in targets}


@pytest.mark.parametrize("change", ["unhealthy", "mixed", "retagged", "missing_service", "incomplete_history", "bad_time"])
def test_ambiguous_or_unhealthy_recovery_state_refuses_planning(change):
    data = fixture()
    history = []
    if change == "unhealthy":
        data["containers"][0]["health"] = "starting"
    elif change == "mixed":
        data["containers"][0]["reference"] = ref(5, "backend")
        data["containers"][0]["image"] = next(i["id"] for i in data["images"] if ref(5, "backend") in i["tags"])
    elif change == "retagged":
        data["containers"][0]["image"] = "old-tag-image"
    elif change == "missing_service":
        data["containers"].pop()
    elif change == "incomplete_history":
        history = [sha(0)]
        data["images"].pop(0)
    elif change == "bad_time":
        data["images"][0]["created"] = "unknown"
    with pytest.raises(policy.PolicyError):
        plan(data, history)


@pytest.mark.parametrize("prefix,candidate,history", [
    ("other-registry/syroce", sha(7), []),
    (PREFIX + ";docker system prune", sha(7), []),
    (PREFIX, "latest", []), (PREFIX, "A" * 40, []),
    (PREFIX, sha(7), [sha(0), sha(0)]), (PREFIX, sha(7), [None]),
    (PREFIX, sha(7), [sha(i) for i in range(4)]),
])
def test_invalid_scope_or_state_cannot_broaden_deletion(prefix, candidate, history):
    with pytest.raises(policy.PolicyError):
        policy.build_plan(fixture(), prefix, history, candidate, NOW)


@pytest.fixture
def executor(monkeypatch, tmp_path):
    data = fixture()
    commands = []
    monkeypatch.setattr(policy, "inventory", lambda: deepcopy(data))
    monkeypatch.setattr(policy, "free_space", lambda: 25 * policy.GIB)
    def fake_run(args):
        commands.append(args)
        assert args[:4] == ["docker", "image", "rm", "--no-prune"]
        assert len(args) == 5 and "--force" not in args
        for image in list(data["images"]):
            if args[4] in (image["tags"] or []):
                image["tags"].remove(args[4])
                if not image["tags"]:
                    data["images"].remove(image)
                return ""
        raise AssertionError("Unknown deletion target")
    monkeypatch.setattr(policy, "run", fake_run)
    return data, commands, tmp_path / "state.json"


def test_dry_run_does_not_write_state_or_issue_mutating_commands(executor):
    _, commands, state = executor
    policy.retain(PREFIX, sha(7), "pre", False, state, NOW)
    assert not commands and not state.exists()


def test_apply_only_removes_exact_planned_tags_and_preserves_protected_inventory(executor):
    data, commands, state = executor
    before = deepcopy(data)
    expected = plan(before)["targets"]
    policy.retain(PREFIX, sha(7), "pre", True, state, NOW)
    assert commands == [["docker", "image", "rm", "--no-prune", t["reference"]] for t in expected]
    assert before["containers"] == data["containers"] and before["volumes"] == data["volumes"]
    assert not state.exists()  # A preflight is not a successful deployment.


def test_low_space_fails_preflight_even_when_no_additional_safe_targets(executor, monkeypatch):
    _, _, state = executor
    monkeypatch.setattr(policy, "free_space", lambda: 14 * policy.GIB)
    with pytest.raises(policy.PolicyError, match="need 20 GiB"):
        policy.retain(PREFIX, sha(7), "pre", True, state, NOW)


@pytest.mark.parametrize("race", ["new_container", "retag_candidate", "retag_protected"])
def test_each_deletion_rechecks_container_references_and_exact_image_identity(executor, monkeypatch, race):
    data, commands, state = executor
    original = deepcopy(data)
    first = plan(original)["targets"][0]
    calls = 0
    def changing_inventory():
        nonlocal calls
        calls += 1
        if calls == 2:
            if race == "new_container":
                data["containers"].append({"id": "new-stopped", "image": first["id"], "reference": first["reference"],
                                           "project": "other", "service": "other", "running": False, "health": None})
            elif race == "retag_candidate":
                next(i for i in data["images"] if first["reference"] in i["tags"])["id"] = "replacement-image"
            else:
                next(i for i in data["images"] if ref(5, "backend") in i["tags"])["id"] = "replacement-protected"
        return deepcopy(data)
    monkeypatch.setattr(policy, "inventory", changing_inventory)
    if race == "retag_candidate":
        # A changed candidate is safely skipped; unrelated safe targets may
        # still be collected. Protected-set/container changes abort instead.
        policy.retain(PREFIX, sha(7), "pre", True, state, NOW)
    else:
        with pytest.raises(policy.PolicyError):
            policy.retain(PREFIX, sha(7), "pre", True, state, NOW)
    assert ["docker", "image", "rm", "--no-prune", first["reference"]] not in commands


def test_docker_failure_stops_without_force_or_broad_prune(executor, monkeypatch):
    _, commands, state = executor
    def fail(args):
        commands.append(args)
        raise policy.PolicyError("Docker command failed")
    monkeypatch.setattr(policy, "run", fail)
    with pytest.raises(policy.PolicyError):
        policy.retain(PREFIX, sha(7), "pre", True, state, NOW)
    assert len(commands) == 1 and "--force" not in commands[0] and "prune" not in commands[0]


def test_only_publicly_healthy_running_revision_enters_success_history(executor, monkeypatch):
    _, commands, state = executor
    policy.save_history(state, PREFIX, [sha(1), sha(2), sha(3)])
    monkeypatch.setattr(policy, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps({"status": "healthy", "commit": sha(6)}).encode()))
    policy.retain(PREFIX, sha(6), "post", True, state, NOW)
    assert policy.load_history(state, PREFIX) == [sha(2), sha(3), sha(6)]
    assert commands
    assert state.stat().st_mode & 0o777 == 0o600


def test_repeated_success_does_not_duplicate_history_or_delete_more_images(executor, monkeypatch):
    _, commands, state = executor
    policy.save_history(state, PREFIX, [sha(1), sha(2), sha(3)])
    monkeypatch.setattr(policy, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps({"status": "healthy", "commit": sha(6)}).encode()))
    policy.retain(PREFIX, sha(6), "post", True, state, NOW)
    first_commands, first_state = deepcopy(commands), state.read_text()
    policy.retain(PREFIX, sha(6), "post", True, state, NOW)
    assert commands == first_commands and state.read_text() == first_state


def test_protected_references_are_rechecked_after_the_final_deletion(executor, monkeypatch):
    data, commands, state = executor
    last_count = len(plan(deepcopy(data))["targets"])
    original_run = policy.run
    def retag_after_last(args):
        result = original_run(args)
        if len(commands) == last_count:
            next(image for image in data["images"] if ref(5, "backend") in image["tags"])["id"] = "externally-retagged"
        return result
    monkeypatch.setattr(policy, "run", retag_after_last)
    with pytest.raises(policy.PolicyError, match="Protected image changed after cleanup"):
        policy.retain(PREFIX, sha(7), "pre", True, state, NOW)


@pytest.mark.parametrize("health", [{"status": "healthy", "commit": sha(5)}, {"status": "degraded", "commit": sha(6)}])
def test_public_health_mismatch_cannot_record_success_or_prune(executor, monkeypatch, health):
    _, commands, state = executor
    monkeypatch.setattr(policy, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps(health).encode()))
    with pytest.raises(policy.PolicyError):
        policy.retain(PREFIX, sha(6), "post", True, state, NOW)
    assert not commands and not state.exists()


def test_non_running_post_candidate_does_not_record_success(executor):
    _, commands, state = executor
    with pytest.raises(policy.PolicyError):
        policy.retain(PREFIX, sha(7), "post", True, state, NOW)
    assert not commands and not state.exists()


@pytest.mark.parametrize("content", ["not json", "{}", '{"version":2}', '{"version":1,"image_prefix":"other"}'])
def test_corrupt_or_mismatched_state_refuses_cleanup(executor, content):
    _, commands, state = executor
    state.write_text(content)
    with pytest.raises(policy.PolicyError):
        policy.retain(PREFIX, sha(7), "pre", True, state, NOW)
    assert not commands


def test_symlink_state_cannot_be_read_or_replaced(tmp_path):
    path = tmp_path / "state"
    target = tmp_path / "other"
    path.symlink_to(target)
    with pytest.raises(policy.PolicyError):
        policy.load_history(path, PREFIX)
    with pytest.raises(policy.PolicyError):
        policy.save_history(path, PREFIX, [])
    assert path.is_symlink() and not target.exists()


def test_standalone_and_inherited_locks_are_nonblocking_and_parent_remains_locked(tmp_path, monkeypatch):
    lock = tmp_path / "deploy.lock"
    monkeypatch.setattr(policy, "LOCK", lock)
    with lock.open("a") as parent:
        fcntl.flock(parent.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with policy.deployment_lock(parent.fileno()):
            pass
        with pytest.raises(BlockingIOError), policy.deployment_lock():
            pass
    with policy.deployment_lock():
        pass
    with (tmp_path / "wrong.lock").open("a") as wrong:
        with pytest.raises(policy.PolicyError), policy.deployment_lock(wrong.fileno()):
            pass


def test_cli_is_dry_run_by_default(monkeypatch):
    calls = []
    @contextmanager
    def no_lock(*args):
        yield
    monkeypatch.setattr(policy, "deployment_lock", no_lock)
    monkeypatch.setattr(policy, "retain", lambda *args: calls.append(args))
    monkeypatch.setattr(sys, "argv", ["retention", "--image-prefix", PREFIX, "--candidate", sha(7)])
    policy.main()
    assert calls[0][3] is False and calls[0][2] == "pre"


def test_workflow_retention_runs_under_existing_lock_before_pull_and_after_health():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
    pre = workflow.index('--candidate "$DEPLOY_SHA" --phase pre --apply --lock-fd 9')
    post = workflow.index('--candidate "$DEPLOY_SHA" --phase post --apply --lock-fd 9')
    pull = workflow.index("bash deploy/pull-ci-images.sh")
    up = workflow.index("up -d --no-build --pull never")
    assert workflow.index("flock -n 9") < pre < pull < up < workflow.index("/usr/local/sbin/syroce-healthwatch", up) < post


def test_no_broad_destructive_command_or_cache_cleanup_fallback_is_introduced():
    source = (ROOT / "deploy/image-retention.py").read_text()
    assert '["docker", "image", "rm", "--no-prune", target["reference"]]' in source
    assert '"--force"' not in source and '"prune"' not in source
    assert "buildx" not in source


def test_healthwatch_surfaces_disk_capacity_without_cleanup():
    source = (ROOT / "deploy/syroce-healthwatch.sh").read_text()
    assert "HEALTHWATCH_MIN_FREE_GIB:-10" in source
    assert "docker info --format '{{.DockerRootDir}}'" in source
    assert "disk-free:" in source and "df -PB1" in source
    assert "prune" not in source and "image rm" not in source


def test_command_errors_do_not_expose_raw_docker_output(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "secret", "secret"))
    with pytest.raises(policy.PolicyError, match="Docker command failed") as caught:
        policy.run(["docker", "image", "inspect", "exact"])
    assert "secret" not in str(caught.value)
