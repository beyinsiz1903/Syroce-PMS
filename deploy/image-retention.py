#!/usr/bin/env python3
"""Fail-closed, local-only SHA image retention for the single Droplet.

Dry-run by default. Never prunes containers, volumes, build cache, dangling
images, unrelated repositories or registry packages. Stdlib only on the host.
"""
import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

KEEP = 3
GIB = 1024**3
LOCK = Path("/var/lock/syroce-pms-deploy.lock")
STATE = Path("/var/lib/syroce-pms/image-retention.json")
SHA = re.compile(r"[0-9a-f]{40}\Z")
PREFIX = re.compile(r"ghcr\.io/[a-z0-9][a-z0-9_-]*/syroce\Z")
SERVICES = {"backend", "frontend", "worker"}
RUNTIME = SERVICES | {"beat", "nginx"}


class PolicyError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PolicyError(message)


def emit(event, **values):
    print(json.dumps({"event": event, **values}, sort_keys=True), flush=True)


def run(args):
    # Never dump inspect environment, a registry config or raw CLI errors.
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    require(result.returncode == 0, "Docker command failed: " + " ".join(args[:3]))
    return result.stdout


def inventory():
    ids = sorted(set(run(["docker", "image", "ls", "-q", "--no-trunc"]).splitlines()))
    require(ids, "No images found")
    fmt = '{"id":{{json .Id}},"tags":{{json .RepoTags}},"created":{{json .Created}}}'
    images = [json.loads(line) for line in run(["docker", "image", "inspect", "--format", fmt, *ids]).splitlines()]
    containers = []
    cids = run(["docker", "container", "ls", "-aq", "--no-trunc"]).splitlines()
    if cids:
        fmt = ('{"id":{{json .Id}},"image":{{json .Image}},"reference":{{json .Config.Image}},'
               '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
               '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
               '"running":{{json .State.Running}},'
               '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}')
        containers = [json.loads(line) for line in run(["docker", "container", "inspect", "--format", fmt, *cids]).splitlines()]
    return {"images": images, "containers": containers, "volumes": sorted(run(["docker", "volume", "ls", "-q"]).splitlines())}


def created_at(image):
    try:
        value = datetime.fromisoformat(image["created"].replace("Z", "+00:00"))
        require(value.tzinfo is not None, "Image creation time has no timezone")
        return value
    except (KeyError, ValueError, TypeError) as error:
        raise PolicyError("Invalid managed image creation time") from error


def build_plan(snapshot, prefix, history, candidate, now):
    require(bool(PREFIX.fullmatch(prefix)), "Invalid managed image prefix")
    require(bool(SHA.fullmatch(candidate)), "Invalid candidate revision")
    require(isinstance(history, list) and len(history) <= KEEP
            and all(isinstance(sha, str) and SHA.fullmatch(sha) for sha in history)
            and len(set(history)) == len(history), "Invalid successful release history")
    pattern = re.compile(re.escape(prefix) + r"-(backend|frontend|worker):([0-9a-f]{40})\Z")
    refs, releases, aliases = {}, {}, set()
    for image in snapshot["images"]:
        tags = image["tags"] or []
        require(isinstance(tags, list) and all(isinstance(tag, str) for tag in tags), "Invalid image tag inventory")
        if any(not pattern.fullmatch(tag) for tag in tags):
            aliases.add(image["id"])
        for tag in tags:
            match = pattern.fullmatch(tag)
            if not match:
                continue
            require(tag not in refs, "Ambiguous managed image tag")
            refs[tag] = image
            service, sha = match.groups()
            releases.setdefault(sha, {})[service] = image
            created_at(image)  # Fail closed for malformed managed metadata.

    managed = [c for c in snapshot["containers"] if c["project"] == "syroce-pms" and c["running"]]
    require({c["service"] for c in managed} == RUNTIME, "Unexpected active Compose topology")
    require(all(c["health"] == "healthy" for c in managed), "Services must be healthy before retention")
    active = set()
    for container in managed:
        if container["service"] == "nginx":
            continue
        match = pattern.fullmatch(container["reference"])
        expected = "worker" if container["service"] == "beat" else container["service"]
        require(match is not None and match[1] == expected, "Unrecognized active release reference")
        require(container["reference"] in refs and refs[container["reference"]]["id"] == container["image"], "Active release was retagged")
        active.add(match[2])
    require(len(active) == 1, "Mixed active revisions; refuse cleanup during recovery")
    current = next(iter(active))
    complete = {sha: max(created_at(image) for image in parts.values())
                for sha, parts in releases.items() if set(parts) == SERVICES}
    require(current in complete and all(sha in complete for sha in history), "Protected rollback set is incomplete")

    # Before three verified post-deploy successes exist, keep older complete
    # local sets as bootstrap rollback candidates. Do not call them certified.
    protected = set(history) | {current}
    bootstrap = []
    for sha in sorted(complete, key=lambda value: (complete[value], value), reverse=True):
        if len(protected) >= KEEP:
            break
        if sha not in protected and complete[sha] <= complete[current]:
            protected.add(sha)
            bootstrap.append(sha)
    protected.add(candidate)  # A retry's candidate can be older than the grace period.
    pinned_ids = {c["image"] for c in snapshot["containers"]} | aliases
    protected_refs = {tag: image["id"] for tag, image in refs.items() if pattern.fullmatch(tag)[2] in protected}
    pinned_ids.update(protected_refs.values())
    cutoff = now - timedelta(minutes=15)
    targets = [{"reference": tag, "id": image["id"]} for tag, image in refs.items()
               if image["id"] not in pinned_ids and created_at(image) <= cutoff]
    targets.sort(key=lambda row: (created_at(refs[row["reference"]]), row["reference"]))
    return {"current": current, "successful_releases": history,
            "bootstrap_rollback_candidates": bootstrap, "protected_revisions": sorted(protected),
            "protected_references": protected_refs, "targets": targets}


def load_history(path, prefix):
    if not path.exists():
        require(not path.is_symlink(), "State file is a dangling symlink")
        return []
    require(not path.is_symlink(), "State file must not be a symlink")
    try:
        state = json.loads(path.read_text())
        require(state["version"] == 1 and state["image_prefix"] == prefix, "State version/prefix mismatch")
        require(isinstance(state["successful_releases"], list), "Invalid release history")
        return state["successful_releases"]
    except (ValueError, KeyError, TypeError) as error:
        raise PolicyError("Unreadable retention state; refusing cleanup") from error


def save_history(path, prefix, history):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not path.is_symlink(), "State file must not be a symlink")
    descriptor, temporary = tempfile.mkstemp(prefix=".image-retention-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"version": 1, "image_prefix": prefix, "successful_releases": history}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)  # Only this function's exact private temporary file.


@contextmanager
def deployment_lock(inherited_fd=None):
    if inherited_fd is not None:
        require(os.fstat(inherited_fd).st_ino == LOCK.stat().st_ino
                and os.fstat(inherited_fd).st_dev == LOCK.stat().st_dev, "Wrong inherited lock")
        fcntl.flock(inherited_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield  # The parent keeps its lock; never unlock its shared descriptor.
    else:
        with LOCK.open("a") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield


def free_space():
    docker_root = Path(run(["docker", "info", "--format", "{{.DockerRootDir}}"]).strip())
    require(docker_root.is_absolute() and docker_root.is_dir(), "Invalid Docker storage path")
    paths = {Path("/"), docker_root}
    if Path("/var/lib/containerd").is_dir():
        paths.add(Path("/var/lib/containerd"))
    return min(shutil.disk_usage(path).free for path in paths)


def container_identity(snapshot):
    return sorted((c["id"], c["image"], c["reference"]) for c in snapshot["containers"])


def retain(prefix, candidate, phase, apply, state_file, now):
    before = inventory()
    history = load_history(state_file, prefix)
    plan = build_plan(before, prefix, history, candidate, now)
    if phase == "post":
        require(plan["current"] == candidate, "Candidate is not the running revision")
        # Only record a successful release after the public route agrees too.
        with urlopen("https://pms.syroce.com/api/health", timeout=15) as response:
            health = json.load(response)
        require(health.get("status") == "healthy" and health.get("commit") == candidate, "Public revision/health mismatch")
        history = ([sha for sha in history if sha != candidate] + [candidate])[-KEEP:]
        plan = build_plan(before, prefix, history, candidate, now)
    emit("retention_plan", apply=apply, phase=phase, free_bytes=free_space(), **plan)
    if not apply:
        return
    if phase == "post":
        save_history(state_file, prefix, history)
    for target in plan["targets"]:
        fresh = inventory()
        fresh_plan = build_plan(fresh, prefix, history, candidate, datetime.now(UTC))
        require(all(fresh_plan["protected_references"].get(ref) == image for ref, image in plan["protected_references"].items()), "Protected image set changed")
        require(load_history(state_file, prefix) == history, "Release state changed during cleanup")
        if target not in fresh_plan["targets"]:
            emit("retention_skip", **target)
            continue
        # Exact managed tag; NO --force, NO parent pruning, NO system prune.
        run(["docker", "image", "rm", "--no-prune", target["reference"]])
        emit("retention_removed", **target)
    after = inventory()
    final_plan = build_plan(after, prefix, history, candidate, datetime.now(UTC))
    require(all(final_plan["protected_references"].get(ref) == image for ref, image in plan["protected_references"].items()), "Protected image changed after cleanup")
    require(container_identity(before) == container_identity(after), "Container inventory changed")
    require(before["volumes"] == after["volumes"], "Volume inventory changed")
    deleted = {i["id"] for i in before["images"]} - {i["id"] for i in after["images"]}
    require(deleted <= {t["id"] for t in plan["targets"]}, "Unplanned image removed")
    remaining = free_space()
    emit("retention_complete", phase=phase, free_bytes=remaining, protected_resources_unchanged=True)
    if phase == "pre":
        require(remaining >= 20 * GIB, "Insufficient Docker/containerd space after safe retention; need 20 GiB before pull; current services unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-prefix", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--phase", choices=("pre", "post"), default="pre")
    parser.add_argument("--apply", action="store_true", help="Default is read-only plan")
    parser.add_argument("--lock-fd", type=int)
    args = parser.parse_args()
    with deployment_lock(args.lock_fd):
        retain(args.image_prefix, args.candidate, args.phase, args.apply, STATE, datetime.now(UTC))


if __name__ == "__main__":
    try:
        main()
    except (PolicyError, OSError, ValueError, subprocess.SubprocessError) as error:
        emit("retention_failed", reason=str(error) if isinstance(error, PolicyError) else type(error).__name__)
        raise SystemExit(1) from None
