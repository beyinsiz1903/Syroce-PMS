# Browser-local border preference

- Default light mode restores soft card/divider outlines and soft neutral outline
  actions. Form input/select outlines and stronger text contrast remain.
- Theme menu > Belirgin sınırlar / Prominent borders opts into stronger outlines
  for this browser only. No tenant/user backend setting or device detection.
- Preference is retained across reloads, synchronized between mounted menus and
  same-origin tabs, and falls back to session memory if storage is blocked.
- In light mode, calendar room rows, day-column separators, room-type groups and
  unassigned-inventory cells use the stronger input outline when enabled.
  Reservation borders, today's marker and block/status colors are not overridden.
- Dark mode ignores this visual override without deleting the saved preference.

## Verification

Local calendar DOM: room borders change from rgb(203, 213, 225) to
rgb(113, 129, 152), retaining 1px width. Preview uses synthetic records.
Unit coverage: default, opt-in/out, multiple menus, remount, cross-tab storage
event, clearing and blocked storage; existing calendar behavior tests retained.
Physical ASUS display verification remains a post-deployment user check.
