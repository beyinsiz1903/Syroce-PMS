# Syroce brand assets

The user confirmed the existing blue/cyan circular logo with white Syroce mark on 2026-10-28. Marketing drafts must use this asset as their brand reference, not the retired blue/green S with black uppercase wordmark.

- Approved circular source: `frontend/public/syroce-circle.png`.
- Existing responsive family: `syroce-circle-64/128/256/512.webp` in the same directory.
- Existing workspace-header variant: `frontend/public/syroce-logo.svg`. Live PMS DOM uses `/syroce-logo.svg`; this file is preserved.
- Existing notification/service-worker icon: `frontend/public/syroce-icon.svg`, preserved.

Two identical obsolete, unreferenced PNG copies were removed: `frontend/public/syroce-logo.png` and `frontend/src/assets/syroce-logo.png` (old SHA256 `4ee6d8beb11af575fff9990ffec89cf84ced343250505f78ea2e24ff10e92e7e`). They remain recoverable in Git history. No gallery candidate, active logo, favicon or responsive variant was removed. A warm-up-gate test still intentionally probes the legacy URL to test extension handling; it does not require the obsolete file to exist.

The brand-asset regression tests protect active asset availability and prevent either retired PNG from being shipped again. This source cleanup takes effect in production only after normal merge/deploy; it does not alter LinkedIn profiles or publish any marketing material.
