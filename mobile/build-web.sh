#!/usr/bin/env bash
# Build the Expo Web (SPA) bundle for the F10A mobile render-only smoke deployment.
#
# Intended use: a SEPARATE Replit Static Deployment (its own repl) that serves
# the bundle. Do NOT deploy this from the main app repl - that repl's single
# deployment slot is the production PMS (autoscale) and must not be replaced.
#
# Static deployment config for the separate repl:
#   build command : bash mobile/build-web.sh
#   publicDir     : mobile/dist
#
# The exported bundle is a SPA (app.json -> web.output = "single"); Replit
# static deployments serve index.html as the SPA fallback, so client routes
# like /login resolve correctly.
set -euo pipefail
cd "$(dirname "$0")"

# Backend the bundled app talks to (the app appends /api itself).
# Override these via the deployment's environment if the URLs change.
: "${EXPO_PUBLIC_API_URL:=https://emergent-yeni-uygulama-1.replit.app}"
: "${EXPO_PUBLIC_QUICKID_URL:=https://emergent-yeni-uygulama-1.replit.app}"
export EXPO_PUBLIC_API_URL EXPO_PUBLIC_QUICKID_URL
export CI=1

npm install --no-audit --no-fund
npx expo export -p web --output-dir dist
echo "Web bundle exported to mobile/dist"
