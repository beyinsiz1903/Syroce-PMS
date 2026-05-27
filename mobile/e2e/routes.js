// F10A Mobile smoke matrix — single source of truth for routes.
// Mirrors docs/F10_MOBILE_COVERAGE_ROADMAP.md §2.1 (24 screens).
//
// Doctrine:
// - `critical: true` → suite fails if route is unreachable / errors on load.
// - `critical: false` → P3 informational (warn, don't fail) until F10B
//   adds per-route assertion budgets.
// - `requiresAuth: true` → smoke first checks redirect to /login when
//   unauthenticated. Once auth seed is added (Task #93 follow-up), the
//   suite logs in once via the (auth)/login flow and re-walks these.
// - `group` matches the Expo Router segment for grouping in reports.

export const MOBILE_ROUTES = [
    // (auth) — public entry
    { path: '/login', group: 'auth', criticality: 'P0', requiresAuth: false, critical: true },

    // (frontdesk) — staff app
    { path: '/(frontdesk)', group: 'frontdesk', criticality: 'P0', requiresAuth: true, critical: true },
    { path: '/(frontdesk)/checkin', group: 'frontdesk', criticality: 'P0', requiresAuth: true, critical: true },
    { path: '/(frontdesk)/checkout', group: 'frontdesk', criticality: 'P0', requiresAuth: true, critical: true },
    { path: '/(frontdesk)/guests', group: 'frontdesk', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(frontdesk)/walkin', group: 'frontdesk', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(frontdesk)/more', group: 'frontdesk', criticality: 'P3', requiresAuth: true, critical: false },

    // (gm) — manager dashboard
    { path: '/(gm)', group: 'gm', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(gm)/more', group: 'gm', criticality: 'P3', requiresAuth: true, critical: false },

    // (housekeeping)
    { path: '/(housekeeping)', group: 'housekeeping', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(housekeeping)/damage', group: 'housekeeping', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(housekeeping)/more', group: 'housekeeping', criticality: 'P3', requiresAuth: true, critical: false },

    // (guest) — KVKK/PII heavy
    { path: '/(guest)', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/booking', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/checkin', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/cart', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/orders', group: 'guest', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(guest)/roomservice', group: 'guest', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(guest)/digitalKey', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/earlylate', group: 'guest', criticality: 'P1', requiresAuth: true, critical: false },
    { path: '/(guest)/loyalty', group: 'guest', criticality: 'P2', requiresAuth: true, critical: false },
    { path: '/(guest)/messages', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/messageThread', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/qrBadge', group: 'guest', criticality: 'P0', requiresAuth: true, critical: false },
    { path: '/(guest)/more', group: 'guest', criticality: 'P3', requiresAuth: true, critical: false },
];

// PII / token leak patterns scanned on every rendered route body.
// Matches the frontend/e2e-smoke/fixtures.js conventions so a
// finding from web smoke and mobile smoke can be correlated.
export const PII_LEAK_PATTERNS = [
    // JWT (header.payload.signature, all base64url)
    { name: 'jwt', re: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/ },
    // Bearer token literally exposed
    { name: 'bearer', re: /\bBearer\s+[A-Za-z0-9._-]{20,}\b/i },
    // Long credit-card-shaped number (Luhn unchecked — pattern only)
    { name: 'card_pan', re: /\b(?:\d[ -]?){13,19}\b/ },
    // E-mail address list (3+ comma-separated e-mails in one node →
    // exfil-prone list rendered to DOM)
    { name: 'email_list', re: /([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,},\s*){2,}[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i },
];

export const VIEWPORTS = [
    { name: 'mobile', width: 390, height: 844 },
    { name: 'tablet', width: 820, height: 1180 },
];
