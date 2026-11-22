# NGINX security update — 22 November 2026

Official advisory: https://nginx.org/en/security_advisories.html
CVE-2026-123007 and CVE-2026-123633 are fixed in OSS 1.30.7 / 1.31.9 and newer. Repository TLS proxy configurations enable HTTP/2. All four old 1.25-alpine image references are replaced with official 1.30.7-alpine, pinned to the Docker Hub multi-platform index digest verified on 22 November 2026.

The deployment pulls the proxy before replacing services, recreates changed-image services through Compose, and checks nginx -v in both frontend and proxy containers. It records actual running image IDs and retains configuration validation, health checks and the existing rollout gates. A reload alone does not replace an old executable.

Validation: 12 deployment/preflight regression tests passed. Docker is unavailable locally, so container build and nginx -t must pass in CI/deployment. SSH to the address in the deployment guide was unreachable; the live binary and image have NOT been verified or patched by this change yet. Merge/deployment and successful live checks remain required.

The separate PHP notice is not evidence that Syroce uses PHP. The scanned application deployment is Python/FastAPI and React, with no PHP/FastCGI configuration found. Other workloads on the host have not been inventoried.

If rollout cannot be completed promptly, an operator can temporarily disable HTTP/2 in the affected live TLS server blocks, validate nginx -t, reload and verify old workers have exited. This fallback has not been applied remotely. Do not roll back to a vulnerable proxy image without disabling HTTP/2 first.
