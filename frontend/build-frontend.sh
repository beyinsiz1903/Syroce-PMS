#!/usr/bin/env bash
# Deploy-time frontend build with integrity + freshness verification.
#
# Why this exists: the VM deploy intermittently produced 0-byte JS chunks
# (the js/ + assets/ dirs were present, but the .js files were empty on disk)
# -> Caddy served empty JS -> permanent WHITE SCREEN, while the deploy still
# looked "healthy". The bundler had generated full content (the index.html
# content-hash matched the full chunk), so the failure was in the write phase
# on the deploy VM, not in the bundle itself.
#
# Strategy (cause-agnostic, no fake-green):
#   1) Reuse an already-shipped build ONLY when it is both intact AND proven
#      fresh (its recorded source-hash matches the current source tree). This
#      avoids the fragile VM rebuild without ever shipping stale frontend code.
#      Operators who built locally just before publishing get the reliable
#      workspace build served verbatim; the VM never rebuilds.
#   2) Otherwise install deps and build, with a single clean retry to ride
#      out a transient write/codegen hiccup, then stamp the source-hash.
#   3) ALWAYS verify integrity: >=1 js chunk, ZERO empty js, and every
#      /js chunk referenced by index.html exists and is non-empty. If still
#      broken, FAIL the deploy loudly (exit 1) so the platform keeps the
#      previous good build instead of promoting a white screen.
#
# Escape hatch: SYROCE_REUSE_FRONTEND_BUILD=1 blesses an intact (but unstamped)
# build as current and reuses it — only use when you KNOW the shipped build
# matches the shipped source.
set -uo pipefail
cd "$(dirname "$0")"

MARKER="build/.source-hash"

js_total() { find build/js -name '*.js' 2>/dev/null | wc -l | tr -d ' '; }
js_empty() { find build/js -name '*.js' -size 0 2>/dev/null | wc -l | tr -d ' '; }

# Deterministic hash of everything that influences the built SPA. Identical in
# the workspace and on the VM because both see the same committed source.
src_hash() {
  {
    find src public -type f -print0 2>/dev/null
    for f in package.json yarn.lock vite.config.js index.html tailwind.config.js postcss.config.js components.json; do
      [ -f "$f" ] && printf '%s\0' "$f"
    done
  } | LC_ALL=C sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | awk '{print $1}'
}

verify() {
  [ -f build/index.html ] || return 1
  [ -d build/assets ] || return 1
  local t e
  t=$(js_total)
  e=$(js_empty)
  [ "$t" -gt 0 ] || return 1
  [ "$e" -eq 0 ] || return 1
  # Every /js chunk referenced by index.html must exist and be non-empty: a
  # missing entry chunk (0-byte check alone would miss it) is still a white
  # screen via 404.
  local refs r
  refs=$(grep -oE '/js/[A-Za-z0-9._-]+\.js' build/index.html 2>/dev/null | sort -u)
  [ -n "$refs" ] || return 1
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    [ -s "build$r" ] || return 1
  done <<EOF
$refs
EOF
  return 0
}

WANT=$(src_hash)

if verify; then
  if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$WANT" ]; then
    echo "[build-frontend] fresh intact build present (source-hash match, js=$(js_total)) — skipping rebuild"
    exit 0
  fi
  if [ "${SYROCE_REUSE_FRONTEND_BUILD:-0}" = "1" ]; then
    echo "[build-frontend] intact build + SYROCE_REUSE_FRONTEND_BUILD=1 — blessing as current (js=$(js_total)) and skipping rebuild"
    echo "$WANT" > "$MARKER"
    exit 0
  fi
  echo "[build-frontend] intact build present but source-hash absent/mismatch — rebuilding for freshness"
else
  echo "[build-frontend] no intact build (js=$(js_total), empty=$(js_empty)) — building"
fi

echo "[build-frontend] installing deps"
yarn install --ignore-engines --frozen-lockfile || { echo "[build-frontend] FATAL: yarn install failed"; exit 1; }
# Free the global yarn cache so the build's write phase is not starved for
# disk on the VM (node_modules is already extracted; the cache is regenerable).
yarn cache clean || true

for attempt in 1 2; do
  echo "[build-frontend] build attempt ${attempt}"
  rm -rf build
  yarn build || echo "[build-frontend] yarn build exited nonzero on attempt ${attempt}"
  if verify; then
    echo "$WANT" > "$MARKER"
    echo "[build-frontend] OK on attempt ${attempt} (js=$(js_total), empty=0, source-hash stamped)"
    exit 0
  fi
  echo "[build-frontend] WARN attempt ${attempt} produced broken build (js=$(js_total), empty=$(js_empty))"
done

echo "[build-frontend] FATAL: js chunks still empty/missing after retries — failing deploy (refusing to ship white screen)"
exit 1
