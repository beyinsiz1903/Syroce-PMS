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

**Environment:** All API calls route through `REACT_APP_BACKEND_URL` defined in `.env`.

## Build

```bash
yarn build    # Production bundle → build/
```
