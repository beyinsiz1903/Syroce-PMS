# Droplet: deploy the images built by CI

The 4 GiB production host must not run Vite or install the ML dependency tree
during deployment. The failed 2026-10-23 rollout reached Vite's `rendering chunks`
phase and then exceeded the SSH command's 30-minute limit. The same revision's
backend, frontend and worker images had already built successfully in CI.

`Deploy to Droplet` now waits for both successful main-branch push workflows for
the exact current main SHA, as before. It then:

1. Pulls the three SHA-tagged images published by `ci-cd.yml` from GHCR. Beat
   reuses the worker image. No `latest` tag or local build fallback is used.
2. Uses a read-only, short-lived Actions registry token through password stdin
   and a private temporary Docker configuration. The config is removed on both
   success and failure; the host's existing Docker login is not changed.
3. Runs the production Exely configuration check using the candidate backend
   image and the host's existing configuration, before replacing any service.
4. Applies `docker-compose.prod.yml` with `deploy/docker-compose.registry.yml`,
   explicitly disabling build and pull at rollout time. Existing resource
   limits, volumes, scheduler command, healthchecks and replica counts remain.
5. Waits for service health, validates/reloads Nginx and runs healthwatch. Failed
   startup still fails deployment and prints bounded service diagnostics.
6. Records the exact, publicly healthy revision in a durable local rollback
   history and applies bounded image retention. The same policy runs before
   image pulls, with a20GiB free-space gate before services can be replaced.

No new long-lived registry secret is needed. The repository must retain read
access to its CI-published packages. A missing image, denied registry login or
failed Exely preflight stops deployment before the running services are touched.
This does not introduce automatic rollback after a failed service replacement.

Merge and a successful production rollout are still required to establish that
the new version is live. CI success alone is not production acceptance. A green
gate-only run with `Deploy to Server` skipped is not a completed deployment.

## Local image retention and disk headroom

`deploy/image-retention.py` is stdlib-only and **dry-run by default**. The
production workflow passes `--apply` under its existing deployment lock. It
is not a general-purpose Docker cleanup tool and has no force/prune fallback.

- Only exact 40-character lowercase SHA tags in the three repositories
  `ghcr.io/<owner>/syroce-backend`, `-frontend` and `-worker` are eligible.
  Images with unrelated tag aliases are entirely protected. Nginx, old local
  `syroce-pms-*:latest`, dangling images and unrelated repositories are untouched.
- Every image referenced by **any** running or stopped container is protected,
  including other projects. Mixed/unhealthy active Syroce revisions, retagged
  active images and incomplete protected rollback sets stop cleanup.
- The last **three successful releases** are kept in
  `/var/lib/syroce-pms/image-retention.json` (root-owned 0600). A success is
  recorded only after Compose health and the public HTTPS health response
  agree with the exact candidate SHA. Repeating the same success is idempotent.
- On initial adoption, until three success records exist, older complete local
  backend/frontend/worker sets fill the remaining rollback slots. These are
  explicitly reported as bootstrap candidates, not newly certified releases.
  The active revision and candidate are always protected independently.
- Images less than 15 minutes old have a grace period. A partial failed pull does
  not displace successful history; a retry's candidate is protected even after
  the grace period. Extra complete sets that were never successfully deployed
  do not become permanent rollback history merely because they were pulled.
- Cleanup freezes an exact tag/ID plan, rechecks each deletion against fresh
  container/protected-tag state, then uses only
  `docker image rm --no-prune <exact-tag>`, **without force**. Container, volume
  and protected-image invariants are checked again afterward. No source file,
  database, backup, container, volume or build cache is removed.
- Before a pull, at least 20 GiB must be free on root/Docker/containerd storage
  filesystems after safe retention. If not, the deploy fails before image pull
  and service replacement; it does not expand cleanup into protected objects.
  Physical reclaimed bytes may be less than summed image sizes because layers
  can be shared. Success is based on measured free space, not an estimate.
- The existing five-minute healthwatch reports failure below 10 GiB by default
  (`HEALTHWATCH_MIN_FREE_GIB`, validated 1–1024). It monitors but never deletes.
  This feeds the existing systemd journal/status; no new email/SMS delivery or
  external alert receiver is configured by this change.

Read-only operator preview, using the current or proposed exact revision:

```sh
sudo python3 deploy/image-retention.py \
  --image-prefix ghcr.io/beyinsiz1903/syroce \
  --candidate <40-character-revision> --phase pre
```

The workflow passes `--lock-fd 9` because its parent already owns the deployment
lock. Standalone invocations acquire the same lock non-blockingly. Do not run
this through an independent cleanup scheduler that bypasses that lock. A
corrupt/mismatched/symlinked state file is a hard failure, not permission to
discard rollback history. Diagnose and restore a verified history instead.

No database migration or new secret is required. Merge and an actual production
deploy activate the hooks; a successful dry-run does not mean they are installed.
The preflight can free old *eligible* local SHA images on its first deployment,
but does not resize the disk or guarantee space against unrelated backup/log
growth. GHCR packages remain available; this policy only touches the host cache.

Docker documents [tag-specific removal and `--no-prune`](https://docs.docker.com/reference/cli/docker/image/rm/).
We deliberately do not use the broader [build-cache prune](https://docs.docker.com/reference/cli/docker/buildx/prune/)
or system/volume prune commands in this permanent image-retention policy.
