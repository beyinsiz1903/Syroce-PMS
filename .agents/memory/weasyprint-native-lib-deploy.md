---
name: WeasyPrint native-lib OSError in Replit VM deploy
description: Why PDF export (weasyprint/cairo) raises "cannot load library libgobject" only in the Reserved-VM deploy, and the LD_LIBRARY_PATH fix.
---

# WeasyPrint "cannot load library 'libgobject-2.0-0'" in Replit VM deploy

**Symptom:** `OSError: cannot load library 'libgobject-2.0-0'` from `from weasyprint import HTML`
in the deployed (Reserved VM) backend, while the SAME code imports fine in the Replit dev shell —
even though replit.nix already declares glib/pango/cairo/gdk-pixbuf/gtk3.

**Why dev works but deploy doesn't:**
- dlopen on NixOS finds nothing in /lib /usr/lib and there is no global ld.so cache for the nix store —
  it relies on `LD_LIBRARY_PATH`.
- In the dev shell `LD_LIBRARY_PATH` is EMPTY too, but it still works because
  `ctypes.util.find_library('gobject-2.0')` falls back to invoking **gcc** with the `-L` paths in
  `NIX_LDFLAGS`. The Reserved VM deploy image has **no C compiler**, so that fallback fails → OSError.
- The running backend process only ever has `NIX_LDFLAGS` set, never `LD_LIBRARY_PATH`.

**Fix (the durable rule):** derive `LD_LIBRARY_PATH` from the `-L` entries inside `NIX_LDFLAGS`
in `backend/start.sh` before `exec uvicorn`. Parse with `sed -n 's/^-L//p' | paste -sd: -` — this is
**hash-independent** (no hard-coded /nix/store paths) so it survives nixpkgs/channel bumps. Append
(don't replace) any existing value. NIX_LDFLAGS already contains glib/pango(+pangocairo)/cairo/
gdk-pixbuf/harfbuzz/fontconfig, i.e. all the weasyprint runtime native deps.

**Verification that's actually meaningful (can't run the VM locally):**
- Render a real PDF under the derived path and assert `%PDF-` magic (not just `import weasyprint`).
- Import ALL heavy C-extension modules (cryptography, pymongo, motor, numpy, pandas, sklearn, xgboost,
  PIL, lxml, redis, jose) under the derived `LD_LIBRARY_PATH` to rule out RPATH/LD ABI-shadowing —
  LD_LIBRARY_PATH does take precedence over DT_RUNPATH, but since the dirs come from the project's own
  NIX_LDFLAGS (same channel) they are ABI-consistent. Confirmed clean.
- Emit a startup log line ("LD_LIBRARY_PATH NIX_LDFLAGS'tan türetildi (N dizin)") + an explicit warning
  when NIX_LDFLAGS is empty, so the operator can confirm from DEPLOY logs whether the derivation fired
  (the one thing unverifiable from dev).

**Companion code-classification rule:** import-time `OSError` from a native renderer is an environment
problem, not a per-request bug — catch `(ImportError, OSError)` on the weasyprint import → **503**
"renderer unavailable" (logger.error, operator-actionable, no Sentry page); keep real `write_pdf()`
failures as **500** via the generic handler (logger.exception). Never add an HTML-as-PDF fallback
(fake-green: 200 + HTML bytes under application/pdf media-type, leaks rendered HTML).

**Operator step:** start.sh changes only take effect after a REDEPLOY. If after redeploy the endpoint
still 503s, NIX_LDFLAGS was absent in the VM → fall back to globbing /nix/store for the sonames.
Note: ~5 other prod weasyprint call sites still catch only ImportError; FIX 1 (LD_LIBRARY_PATH) covers
them all globally, so per-site OSError guards are only needed if NIX_LDFLAGS proves absent in the VM.
