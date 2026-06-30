#!/usr/bin/env bash
# Build the Expo Web (SPA) bundle for the F10A mobile render-only smoke deployment.
#
# Intended use: a SEPARATE DigitalOcean Static Deployment (its own repl) that serves
# the bundle. Do NOT deploy this from the main app repl - that repl's single
# deployment slot is the production PMS (autoscale) and must not be replaced.
#
# Static deployment config for the separate repl:
#   build command : bash mobile/build-web.sh
#   publicDir     : mobile/dist
#
# The exported bundle is a SPA (app.json -> web.output = "single"). DigitalOcean
# static deployments do NOT rewrite unknown routes to index.html - they serve
# a 404.html (if present) for any path that isn't a real file. Without it a
# hard navigation to a client route (e.g. /login, /checkin) returns an empty
# 404 and the SPA never boots. We therefore copy index.html -> 404.html so
# every deep route falls back to the SPA shell and the client router resolves.
set -euo pipefail
cd "$(dirname "$0")"

# Backend the bundled app talks to (the app appends /api itself).
# This MUST be the web+backend host (pms.syroce.com),
# NOT the -syroce static host that serves THIS bundle: -syroce has no
# backend, so pointing the app there makes every API/QuickID call resolve
# to the static SPA shell (404 text/html) and the app cannot log in.
# Override these via the deployment's environment if the URLs change.
: "${EXPO_PUBLIC_API_URL:=https://pms.syroce.com}"
: "${EXPO_PUBLIC_QUICKID_URL:=https://pms.syroce.com}"
export EXPO_PUBLIC_API_URL EXPO_PUBLIC_QUICKID_URL
export CI=1

npm install --no-audit --no-fund
npx expo export -p web --output-dir dist
# SPA fallback for the DigitalOcean static host (see header note).
cp dist/index.html dist/404.html
echo "Web bundle exported to mobile/dist (with 404.html SPA fallback)"
