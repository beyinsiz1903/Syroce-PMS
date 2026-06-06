---
name: Replit package-firewall URLs leak into committed lockfiles, break external CI
description: Committed yarn.lock/package-lock.json may point resolved URLs at package-firewall.replit.local, which only resolves inside Replit, failing GitHub Actions install.
---

# package-firewall.replit.local URLs in lockfiles break external CI

**Symptom (CI / GitHub Actions):** `yarn install` (or `npm ci`) fails at the
fetch step with:
`error Error: getaddrinfo EAI_AGAIN package-firewall.replit.local`
`error http://package-firewall.replit.local/npm/<pkg>/-/<pkg>.tgz: ...`

**Root cause:** installs run *inside* Replit route through the internal
package-firewall proxy, and yarn/npm bake that proxy host into every
`resolved` URL of the lockfile. When that lockfile is committed and CI runs
*outside* Replit, the host `package-firewall.replit.local` does not resolve
(it only exists inside the Replit network) and install dies.

**Fix — host-only rewrite to the public registry:**
- `yarn.lock`: replace `http://package-firewall.replit.local/npm/` →
  `https://registry.yarnpkg.com/`
- `package-lock.json`: replace `http://package-firewall.replit.local/npm/` →
  `https://registry.npmjs.org/`
- The firewall path is `/npm/<pkg>/-/<file>.tgz`; the public registries use
  `/<pkg>/-/<file>.tgz` (scoped `@scope/name/-/...` identical), so dropping
  the `/npm` segment in the same replacement is correct.
- `integrity` hashes are content-based, NOT URL-based — a host swap does not
  change them, so resolution stays pinned to the exact same tarballs. This is
  not fake-green.
- After: `grep -c package-firewall.replit.local <file>` must be 0; validate
  package-lock.json with `node -e "JSON.parse(fs.readFileSync(...))"`.

**Check ALL lockfiles, not just the one named in the error** — a monorepo
typically has several (per workspace/app), each feeding a different CI job;
grep every tracked lockfile, not only the failing one.

**Do NOT run `yarn install`/`npm install` inside Replit to "verify" the fix**
— install here goes back through the firewall proxy and rewrites the URLs
straight back to `package-firewall.replit.local`, silently undoing the fix.
The fix is for external CI; trust the grep + JSON-validate, don't re-install.

**Recurs** whenever someone runs a fresh install inside Replit and commits
the regenerated lockfile. If it keeps coming back, that is the trigger.
