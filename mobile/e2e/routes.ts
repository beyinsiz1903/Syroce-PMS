// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke matrix (28 screens, render-only).
// ─────────────────────────────────────────────────────────────────────────
// Inventory source of truth: docs/F10_MOBILE_COVERAGE_ROADMAP.md §2.1
// File source of truth:      mobile/app/**/*.tsx (Expo Router file-based)
//
// Notes:
//   - Route groups in parens are stripped on Expo Web URLs. Collisions
//     (e.g. `/checkin` exists in both frontdesk and guest groups) are
//     resolved by the currently active group, which is selected by
//     `AuthGate` based on the logged-in role. So each role visits its
//     own set of paths.
//   - `criticality` mirrors §2.1 (P0/P1/P3). Smoke is render-only, but
//     critical screens have stricter empty-screen tolerance.
// ─────────────────────────────────────────────────────────────────────────

export type Role = 'frontdesk' | 'gm' | 'housekeeping' | 'guest';

export type Screen = {
    key: string;
    role: Role | 'auth';
    label: string;
    // URL path after group prefix is stripped by Expo Router web.
    path: string;
    crit: 'P0' | 'P1' | 'P2' | 'P3';
};

// 1 (auth) + 9 (frontdesk) + 2 (gm) + 3 (housekeeping) + 13 (guest) = 28
// surfaces. The frontdesk group gained the Reservations + Availability
// tabs (Task #255) and the Rooms board (Task #508); each is covered
// render-only here and exercised interactively in smoke.spec.ts. We
// faithfully cover every file under `mobile/app/`.
export const SCREENS: Screen[] = [
    // ── (auth) ────────────────────────────────────────────────────────
    { key: 'auth_login', role: 'auth', label: 'Login', path: '/login', crit: 'P0' },

    // ── (frontdesk) ───────────────────────────────────────────────────
    { key: 'fd_today',    role: 'frontdesk', label: 'Frontdesk · Bugün',   path: '/',         crit: 'P0' },
    { key: 'fd_reservations', role: 'frontdesk', label: 'Frontdesk · Rezervasyonlar', path: '/reservations', crit: 'P1' },
    { key: 'fd_availability', role: 'frontdesk', label: 'Frontdesk · Müsaitlik',      path: '/availability', crit: 'P1' },
    { key: 'fd_rooms',    role: 'frontdesk', label: 'Frontdesk · Odalar',     path: '/rooms',    crit: 'P1' },
    { key: 'fd_checkin',  role: 'frontdesk', label: 'Frontdesk · Check-in',  path: '/checkin',  crit: 'P0' },
    { key: 'fd_checkout', role: 'frontdesk', label: 'Frontdesk · Check-out', path: '/checkout', crit: 'P0' },
    { key: 'fd_guests',   role: 'frontdesk', label: 'Frontdesk · Misafirler',path: '/guests',   crit: 'P1' },
    { key: 'fd_walkin',   role: 'frontdesk', label: 'Frontdesk · Walk-in',   path: '/walkin',   crit: 'P1' },
    { key: 'fd_more',     role: 'frontdesk', label: 'Frontdesk · Daha',      path: '/more',     crit: 'P3' },

    // ── (gm) ──────────────────────────────────────────────────────────
    { key: 'gm_dashboard', role: 'gm', label: 'GM · Dashboard', path: '/',     crit: 'P1' },
    { key: 'gm_more',      role: 'gm', label: 'GM · Daha',      path: '/more', crit: 'P3' },

    // ── (housekeeping) ────────────────────────────────────────────────
    { key: 'hk_tasks',  role: 'housekeeping', label: 'HK · Görevler',  path: '/',       crit: 'P1' },
    { key: 'hk_damage', role: 'housekeeping', label: 'HK · Hasar',     path: '/damage', crit: 'P1' },
    { key: 'hk_more',   role: 'housekeeping', label: 'HK · Daha',      path: '/more',   crit: 'P3' },

    // ── (guest) ───────────────────────────────────────────────────────
    { key: 'g_index',         role: 'guest', label: 'Guest · Rezervasyonlar',  path: '/',              crit: 'P0' },
    { key: 'g_booking',       role: 'guest', label: 'Guest · Rezervasyon',     path: '/booking',       crit: 'P0' },
    { key: 'g_checkin',       role: 'guest', label: 'Guest · Online Check-in', path: '/checkin',       crit: 'P0' },
    { key: 'g_cart',          role: 'guest', label: 'Guest · Sepet',           path: '/cart',          crit: 'P0' },
    { key: 'g_orders',        role: 'guest', label: 'Guest · Siparişler',      path: '/orders',        crit: 'P1' },
    { key: 'g_roomservice',   role: 'guest', label: 'Guest · Oda Servisi',     path: '/roomservice',   crit: 'P1' },
    { key: 'g_digitalKey',    role: 'guest', label: 'Guest · Dijital Anahtar', path: '/digitalKey',    crit: 'P0' },
    { key: 'g_earlylate',     role: 'guest', label: 'Guest · Erken/Geç',       path: '/earlylate',     crit: 'P1' },
    { key: 'g_loyalty',       role: 'guest', label: 'Guest · Sadakat',         path: '/loyalty',       crit: 'P2' },
    { key: 'g_messages',      role: 'guest', label: 'Guest · Mesajlar',        path: '/messages',      crit: 'P0' },
    { key: 'g_messageThread', role: 'guest', label: 'Guest · Mesaj Thread',    path: '/messageThread', crit: 'P0' },
    { key: 'g_qrBadge',       role: 'guest', label: 'Guest · QR Rozet',        path: '/qrBadge',       crit: 'P0' },
    { key: 'g_more',          role: 'guest', label: 'Guest · Daha',            path: '/more',          crit: 'P3' },
];

// Console messages that are expected/benign and should NOT fail smoke.
// Keep tight — expand only with documented reason.
export const CONSOLE_ERROR_ALLOWLIST: string[] = [
    // Expo / Metro dev banners on web bundle
    'Download the React DevTools',
    'expo-secure-store is not supported on web',
    'expo-local-authentication is not supported on web',
    'Camera is not supported on web',
    // React Native Web shims warn about non-native props
    'is not a valid prop on a DOM element',
    'Unknown event handler property',
    // TanStack Query info logs
    '[TanStack Query]',
];
