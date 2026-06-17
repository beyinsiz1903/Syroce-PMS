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

# Resolve a python interpreter for the full-read verifier (shared with
# backend/start.sh). The size-only verify() above CANNOT detect a file whose
# inode reports the right st_size but whose data blocks are unreadable/short or
# all-NUL (the deploy-VM sparse/holes materialization that white-screens while
# the build "looks healthy"). The verifier actually reads every served file.
if [ -n "${PYTHON_BIN:-}" ] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYBIN="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYBIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYBIN="python"
else
  PYBIN=""
fi

# Full-read integrity gate. Prefers the python verifier (whole-tree, reports
# offenders); falls back to a dependency-free shell full read (cat|wc -c forces
# a real read — `wc -c <file` would fstat and miss the corruption) of the
# index.html /js refs + every build/js/*.js. Never silently skips (no fake-green).
fullread_verify() {
  if [ -n "$PYBIN" ] && [ -f verify_build_readable.py ]; then
    "$PYBIN" verify_build_readable.py build
    return $?
  fi
  echo "[build-frontend] full-read verifier unavailable (python/script missing) — shell fallback"
  [ -f build/index.html ] || return 1
  local refs r bad=0 f exp act nonnul
  # cat|wc -c forces a real read (short => truncation); tr -d '\0'|wc -c counts
  # non-NUL bytes (js is text, so count<size => partially-sparse hole even when
  # the total length still matches st_size).
  _frv_check() {
    exp=$(stat -c%s "$1" 2>/dev/null || echo -1)
    act=$(cat "$1" 2>/dev/null | wc -c | tr -d ' ')
    nonnul=$(tr -d '\000' < "$1" 2>/dev/null | wc -c | tr -d ' ')
    if [ "$exp" -le 0 ] || [ "$act" != "$exp" ] || [ "$nonnul" != "$exp" ]; then
      echo "[build-frontend] full-read FAIL $1 (read=$act nonNUL=$nonnul size=$exp)"
      bad=1
    fi
  }
  refs=$(grep -oE '/js/[A-Za-z0-9._-]+\.js' build/index.html 2>/dev/null | sort -u)
  [ -n "$refs" ] || return 1
  while IFS= read -r r; do
    [ -n "$r" ] || continue
    _frv_check "build$r"
  done <<EOF2
$refs
EOF2
  for f in build/js/*.js; do
    [ -e "$f" ] || continue
    _frv_check "$f"
  done
  return $bad
}

# Free regenerable caches BEFORE the write-heavy bundler phase so it has real
# disk headroom on the VM. Metadata-correct-but-unreadable (sparse / all-NUL)
# js chunks are the signature of a write phase that ran out of disk. The backend
# venv is already extracted; download caches are regenerable and safe to drop.
free_disk() {
  echo "[build-frontend] disk before cleanup:"; df -h . 2>/dev/null || true
  uv cache clean >/dev/null 2>&1 || true
  [ -n "$PYBIN" ] && "$PYBIN" -m pip cache purge >/dev/null 2>&1 || true
  rm -rf "${HOME:-/home/runner}/.cache/uv" "${HOME:-/home/runner}/.cache/pip" 2>/dev/null || true
  npm cache clean --force >/dev/null 2>&1 || true
  rm -rf "${HOME:-/home/runner}/.npm/_cacache" 2>/dev/null || true
  yarn cache clean >/dev/null 2>&1 || true
  echo "[build-frontend] disk after cleanup:"; df -h . 2>/dev/null || true
}

WANT=$(src_hash)

REUSE_OK=0
if verify; then
  if fullread_verify; then
    REUSE_OK=1
  else
    echo "[build-frontend] build is size-intact but FULL-READ FAILED (unreadable/sparse data blocks) — discarding and rebuilding"
  fi
else
  echo "[build-frontend] no intact build (js=$(js_total), empty=$(js_empty)) — building"
fi

if [ "$REUSE_OK" = "1" ]; then
  if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$WANT" ]; then
    echo "[build-frontend] fresh intact build present (source-hash match, js=$(js_total), full-read OK) — skipping rebuild"
    exit 0
  fi
  if [ "${SYROCE_REUSE_FRONTEND_BUILD:-0}" = "1" ]; then
    echo "[build-frontend] intact+readable build + SYROCE_REUSE_FRONTEND_BUILD=1 — blessing as current (js=$(js_total)) and skipping rebuild"
    echo "$WANT" > "$MARKER"
    exit 0
  fi
  echo "[build-frontend] intact+readable build present but source-hash absent/mismatch — rebuilding for freshness"
fi

echo "[build-frontend] installing deps"
yarn install --ignore-engines --frozen-lockfile || { echo "[build-frontend] FATAL: yarn install failed"; exit 1; }
free_disk

for attempt in 1 2 3; do
  echo "[build-frontend] build attempt ${attempt}"
  rm -rf build
  yarn build || echo "[build-frontend] yarn build exited nonzero on attempt ${attempt}"
  # Both gates must pass: verify() (size/refs) AND fullread_verify() (every
  # served byte actually readable). sync() flushes the freshly written data
  # blocks to disk before we stamp the build as good.
  if verify && fullread_verify; then
    sync || true
    echo "$WANT" > "$MARKER"
    echo "[build-frontend] OK on attempt ${attempt} (js=$(js_total), empty=0, full-read verified, source-hash stamped)"
    exit 0
  fi
  echo "[build-frontend] WARN attempt ${attempt} produced broken build (size-verify and/or full-read failed)"
  free_disk
done

echo "[build-frontend] FATAL: js chunks still empty/unreadable after retries — failing deploy (refusing to ship white screen)"
exit 1
