#!/usr/bin/env bash
# Run the Maestro smoke test suite against a connected simulator/emulator.
#
# Usage:
#   npm run smoke                                          # runs every flow under .maestro/flows
#   npm run smoke -- .maestro/flows/frontdesk_today.yaml   # absolute / repo-relative path
#   npm run smoke -- frontdesk_today.yaml                  # bare name resolved under .maestro/flows
#
# Honoured environment variables:
#   SMOKE_EMAIL / SMOKE_PASSWORD             — frontdesk login (default: demo)
#   SMOKE_GUEST_EMAIL / SMOKE_GUEST_PASSWORD — guest login    (default: demo)
#   MAESTRO_DEVICE                           — explicit device id when multiple
#                                              simulators/emulators are running
#
# Exit codes:
#   0   all flows passed
#   1   one or more flows failed
#   127 maestro CLI not installed
set -euo pipefail

if ! command -v maestro >/dev/null 2>&1; then
  cat >&2 <<'EOF'
[smoke] Maestro CLI not found on PATH.

Install with:
  curl -fsSL "https://get.maestro.mobile.dev" | bash

…or via Homebrew:
  brew tap mobile-dev-inc/tap && brew install maestro

After installing, ensure ~/.maestro/bin is on your PATH and re-run.
EOF
  exit 127
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FLOWS_DIR="$ROOT_DIR/.maestro/flows"

if [ ! -d "$FLOWS_DIR" ]; then
  echo "[smoke] Flows directory not found: $FLOWS_DIR" >&2
  exit 2
fi

# Forward credential env vars to Maestro so the YAML ${VAR} placeholders
# resolve. We only forward when the variable is set in the parent shell;
# otherwise the flow's own default (demo account) wins.
ENV_ARGS=()
for var in SMOKE_EMAIL SMOKE_PASSWORD SMOKE_GUEST_EMAIL SMOKE_GUEST_PASSWORD; do
  if [ -n "${!var:-}" ]; then
    ENV_ARGS+=("-e" "${var}=${!var}")
  fi
done

DEVICE_ARGS=()
if [ -n "${MAESTRO_DEVICE:-}" ]; then
  DEVICE_ARGS+=("--device" "${MAESTRO_DEVICE}")
fi

# When the caller passes a path argument, run only that flow; otherwise
# run the entire flows directory. We normalise the argument so common
# shorthands resolve under .maestro/flows: a bare filename ("login.yaml"),
# the legacy "flows/..." prefix, or an absolute / repo-relative path are
# all accepted. The first argument that fails to resolve is forwarded
# verbatim to Maestro so users can still pass arbitrary CLI options.
TARGET="$FLOWS_DIR"
if [ "$#" -gt 0 ]; then
  candidate="$1"
  if [ -e "$candidate" ]; then
    TARGET="$candidate"
    shift
  elif [ -e "$ROOT_DIR/$candidate" ]; then
    TARGET="$ROOT_DIR/$candidate"
    shift
  elif [ -e "$FLOWS_DIR/$candidate" ]; then
    TARGET="$FLOWS_DIR/$candidate"
    shift
  elif [[ "$candidate" == flows/* ]] && [ -e "$ROOT_DIR/.maestro/$candidate" ]; then
    TARGET="$ROOT_DIR/.maestro/$candidate"
    shift
  fi
fi

echo "[smoke] maestro ${DEVICE_ARGS[*]:-} test ${ENV_ARGS[*]:-} $TARGET"
exec maestro "${DEVICE_ARGS[@]}" test "${ENV_ARGS[@]}" "$TARGET" "$@"
