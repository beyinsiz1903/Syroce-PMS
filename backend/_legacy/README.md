# _legacy/

Quarantined legacy Python modules that are **not imported** by any active application code.

These files were originally in `/app/backend/` root and were moved here during the enterprise codebase cleanup (2026-03-22).

## Why not deleted?

Some modules contain domain logic or data models that may be useful as reference during future feature development.

## Can I delete them?

Yes. The application runs without any of these files. They are safe to remove entirely.

## File count

67 modules (endpoints, models, utilities, seed scripts)
