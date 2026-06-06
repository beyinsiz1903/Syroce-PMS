#!/usr/bin/env bash
# Guard: fail if any tracked lockfile pins package URLs to Replit's internal
# package firewall (package-firewall.replit.local). That host only resolves
# inside the Replit network, so committing such URLs breaks external CI with
# "getaddrinfo EAI_AGAIN package-firewall.replit.local" at the install step.
#
# Recurrence trigger: running `yarn install` / `npm install` inside Replit and
# committing the regenerated lockfile. Fix: rewrite the `resolved` hosts to the
# public registry (yarn.lock -> registry.yarnpkg.com, *-lock.json ->
# registry.npmjs.org), keeping integrity hashes untouched.
set -euo pipefail

BAD_HOST="package-firewall.replit.local"
found=0

# Check every tracked lockfile (yarn.lock + package-lock.json) in the repo.
while IFS= read -r f; do
  if grep -Fq "$BAD_HOST" "$f"; then
    count=$(grep -Fc "$BAD_HOST" "$f")
    echo "ERROR: $f contains $count reference(s) to $BAD_HOST"
    found=1
  fi
done < <(git ls-files '*yarn.lock' '*package-lock.json' '*pnpm-lock.yaml' '*npm-shrinkwrap.json')

if [ "$found" -ne 0 ]; then
  echo ""
  echo "A lockfile was committed with Replit internal package-firewall URLs."
  echo "These only resolve inside Replit and will fail external CI installs."
  echo "Fix (host-only rewrite; integrity hashes are content-based, unaffected):"
  echo "  sed -i 's|http://${BAD_HOST}/npm/|https://registry.yarnpkg.com/|g' <yarn.lock>"
  echo "  sed -i 's|http://${BAD_HOST}/npm/|https://registry.npmjs.org/|g' <package-lock.json>"
  echo "Do NOT re-run install inside Replit to verify — it re-injects the firewall host."
  exit 1
fi

echo "Lockfile host guard OK: no $BAD_HOST references in any tracked lockfile."
