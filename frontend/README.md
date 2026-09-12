# Syroce PMS — Frontend

React 19 single-page application powering the Syroce Hotel PMS Control Plane and operational UI.

## Tech Stack

| Layer | Library | Purpose |
|-------|---------|---------|
| UI Framework | React 19 | Component rendering |
| Routing | react-router-dom 7 | Client-side navigation |
| Styling | Tailwind CSS + shadcn/ui | Design system |
| State / Data | @tanstack/react-query 5 | Server-state management |
| Forms | react-hook-form + zod | Validation |
| i18n | react-i18next | Multi-language (8 languages) |
| Charts | recharts + chart.js | Analytics & dashboards |

## Directory Structure

```
src/
  components/       # Shared components
    ui/             # shadcn/ui primitives
    calendar/       # Calendar-specific components
  pages/            # Route-level page components
    calendar/       # Calendar sub-pages
  hooks/            # Custom React hooks
  lib/              # Utility functions
  i18n/             # Internationalization config & translations
```

## Development

```bash
# Install dependencies (always use yarn)
yarn install

# Start dev server (hot-reload on port 3000)
yarn start
```

**Environment:** All API calls route through `VITE_BACKEND_URL` defined in `.env`.

## Marketing landing and measurement

The hotel-focused Google Ads destination is `/otel-programi`. Both it and the
main landing use the shared demo form (`POST /api/leads/contact`). Submitted
leads include the landing path and available `utm_source`, `utm_medium`, and
`utm_campaign` values in lead metadata. A five-minute backend deduplication
prevents duplicate lead creation.
Leads are stored in the super-admin **Pazarlama Talepleri** inbox at
`/app/admin/leads`; this flow does not currently send an email or SMS alert.
After deploying both backend and frontend, verify one anonymous submission on
the live site and confirm that the same lead appears in that inbox.

Optional Google measurement is disabled unless deployment supplies real IDs:

```text
VITE_GOOGLE_TAG_ID=G-XXXXXXXXXX
VITE_GOOGLE_ADS_ID=AW-XXXXXXXXX
VITE_GOOGLE_ADS_DEMO_CONVERSION_LABEL=XXXXXXXXXXXX
```

The visitor must accept optional analytics before the Google tag loads. A
`generate_lead` event and Google Ads conversion event fire only after a new,
successful demo submission, not on a failed or deduplicated request. Configure
and verify the conversion action in Google Ads before running campaigns. Do
not put placeholders in production environment variables.

The existing privacy-policy page should receive legal review before launch;
there is no approved Terms of Service document in this repository, so the
former footer link that incorrectly led to the privacy policy was removed.

## Build

```bash
yarn build    # Production bundle → build/
```
