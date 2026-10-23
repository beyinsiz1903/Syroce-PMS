#!/usr/bin/env bash
# Pull-only preflight: no container replacement, local build or persistent login.
set -euo pipefail

: "${DEPLOY_SHA:?Exact CI revision required}"
: "${DEPLOY_IMAGE_PREFIX:?CI registry prefix required}"
: "${REGISTRY_USER:?Registry user required}"
: "${REGISTRY_TOKEN:?Registry token required}"

[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid deployment revision" >&2; exit 1; }
[[ "$DEPLOY_IMAGE_PREFIX" =~ ^ghcr\.io/[a-z0-9][a-z0-9_-]*/syroce$ ]] || {
  echo "Invalid CI image prefix" >&2
  exit 1
}

# Never overwrite /root/.docker/config.json or retain the short-lived Actions
# token on the server. Remove only this helper's private temporary config.
registry_config="$(mktemp -d /tmp/syroce-registry.XXXXXXXX)"
cleanup() {
  rm -f -- "$registry_config/config.json"
  rmdir -- "$registry_config"
}
trap cleanup EXIT
printf '%s' "$REGISTRY_TOKEN" | docker --config "$registry_config" login ghcr.io \
  --username "$REGISTRY_USER" --password-stdin

# Pull sequentially to avoid competing image extraction on the small host.
# Beat reuses worker, so there are only three distinct images to download.
for service in backend frontend worker; do
  docker --config "$registry_config" compose \
    -f docker-compose.prod.yml -f deploy/docker-compose.registry.yml pull "$service"
done
