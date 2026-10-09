# Dark theme readability — 2026-10-09

## Diagnosis

Read-only inspection of the live channel hub, application center and reservation
calendar exposed inherited near-black control text in dark mode. The unlayered
body rule in App.css overrode the themed base rule from index.css. Computed body
ink was rgb(26, 32, 44), including outline controls without their own text color.
The calendar also used inline light reservation surfaces regardless of theme.

## Changes

- Scope a body ink/canvas/color-scheme override to html.dark.
- Use less saturated dark neutral surfaces, softer foreground ink, and a filled
  primary color with readable white text. Keep text-primary links brighter.
- Mute legacy red/orange/amber/yellow/green/emerald/blue status backgrounds while
  retaining status hues, labels and lifecycle border colors.
- Give calendar cards theme variables with the exact original light fallbacks.
- Reduce bright primary actions in the calendar and room booking/payment forms.
- Expose the existing theme selector inside the narrow-screen navigation menu.
- Include App.css in the local preview so visual QA exercises the real cascade.

## Verification and limits

The local, synthetic-data preview was used to inspect the shared header,
outline actions, room screen and reservation form, plus the light-mode header.
Computed dark body colors became rgb(233, 236, 241) on rgb(18, 22, 33).
Automated contracts cover 4.5:1 contrast for shared foreground/muted/primary/link
tokens and all three calendar card text/muted pairs. Calendar interaction tests
continue to cover existing booking behavior.

This is not a full accessibility certification or an assertion that every
tenant/module/state was visually exercised. No production records were changed.
After deployment, smoke-check channels, calendar, room filters and dialogs in
both themes on the real tenant. Custom inline colors in other modules may still
need targeted follow-up.
