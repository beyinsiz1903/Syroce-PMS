---
name: Expo web export starved by a second metro on the same project
description: Why `npx expo export -p web` crawls/stalls in this repl and the isolated-root workaround
---

Running `npx expo export -p web` while the dev "Mobile Web" workflow (also `expo start --web` on the SAME `mobile/` project root) is up makes the export crawl to a near-stall: the bundler "Starting Metro Bundler / rebuilding" forever, the isolated TMPDIR cache grows only a few MB in 8+ min, dist stays empty. No EXIT line, but cgroup mem is fine = NOT OOM.

**Why:** two metro instances on the same project root contend on the shared file-map / haste map / watcher even with separate `TMPDIR` and `--max-workers`. The dev metro is idle (CI mode, "Waiting on :8080", bundles lazily) yet still holds the file map.

**How to apply:** don't fight it with TMPDIR/worker flags. Build from an isolated copy of the source so the two metros have different project roots:
- `tar --exclude=node_modules --exclude=dist --exclude=.expo -cf -` the `mobile/` source into `/tmp/<copy>` (rsync is NOT installed here),
- symlink node_modules: `ln -s /abs/mobile/node_modules /tmp/<copy>/node_modules`,
- run the export there with its own `TMPDIR`.
This completes EXIT=0. The clean deploy builder has no second metro, so it builds fine too — this contention is a local-dev-only blocker, not a config defect.

Symlink artifact: with node_modules symlinked, exported asset paths embed the absolute real path (`assets/__home/runner/.../node_modules/...`). That weirdness is the symlink's doing only; a real build (node_modules inside the project) emits normal asset paths.

Process-mgmt trap: `pkill/pgrep -f "expo export"` (or any cmd whose own text contains "expo export", incl. an echo label) self-matches the tool shell and SIGTERMs it (exit 143). Kill by numeric PID, or keep the literal string out of your command entirely.

F10A hosting: `mobile/app.json` web.output = "single" (SPA) + `mobile/build-web.sh` (build cmd) + publicDir `mobile/dist`, deployed as a Replit Static Deployment (static serves index.html SPA-fallback so /login resolves). NOTE: this `-1` repl's deploy slot IS the mobile static deploy (operator-confirmed) — the prod PMS+backend is the separate `-syroce` project — so `deployConfig` static here is correct (see `syroce-mobile-vs-backend-deploy.md`). The earlier "never deployConfig in the main repl" assumed this repl held the PMS slot; it does not.

Second silent-death mode (distinct from the dual-metro crawl above): the export can also die OUTRIGHT — process gone, dist empty, log truncated exactly at "Starting Metro Bundler", no EXIT/error — with NO second metro present, when the rest of the dev stack (Backend API + Quick-ID + frontend Vite all running) starves the container during bundling (resource/OOM kill). The dual-metro case CRAWLS forever (mem fine); this case just vanishes mid-bundle. Either way the local export is unreliable in a busy dev container — do NOT trust an empty local `mobile/dist` as a build-script defect; the clean deploy builder (build-only, no dev stack) completes it, and it worked before. The dev "Mobile Web" metro itself bundles fine on-demand (`Web Bundled … 964 modules`); only the full production export is heavy enough to get killed.
