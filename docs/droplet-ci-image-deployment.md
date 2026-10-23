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

No new long-lived registry secret is needed. The repository must retain read
access to its CI-published packages. A missing image, denied registry login or
failed Exely preflight stops deployment before the running services are touched.
This does not introduce automatic rollback after a failed service replacement.

Merge and a successful production rollout are still required to establish that
the new version is live. CI success alone is not production acceptance. A green
gate-only run with `Deploy to Server` skipped is not a completed deployment.
