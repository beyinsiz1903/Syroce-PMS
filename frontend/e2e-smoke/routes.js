// ─────────────────────────────────────────────────────────────────────────
// Route katalogu — UI smoke kapsamı.
// ─────────────────────────────────────────────────────────────────────────
// Her entry: { key, label, path, group, critical }
//   - critical=true: PASS olmazsa suite FAIL (production-blocker page)
//   - critical=false: WARNING (sayfa açılır ama buton tıklamaları opsiyonel)
//
// Kullanıcı talebine göre TARGET pages işaretlendi:
//   System Health / Channel Manager / Conflict Queue / Reservation /
//   Folio / Users-Roles / Settings.
// Diğerleri "menü gezintisi" kapsamında, daha gevşek doğrulama.
// ─────────────────────────────────────────────────────────────────────────

export const ROUTES = [
    // ── CRITICAL: TARGET PAGES ────────────────────────────────────────
    { key: 'dashboard',          label: 'Dashboard',                path: '/app/dashboard',                  group: 'core',    critical: true },
    { key: 'system_health',      label: 'Sistem Sağlığı',           path: '/system-health',                  group: 'admin',   critical: true },
    { key: 'channels_hub',       label: 'Kanallar Hub',             path: '/channels',                       group: 'channels',critical: true },
    { key: 'cm_dashboard',       label: 'CM Dashboard',             path: '/cm-dashboard',                   group: 'channels',critical: true },
    { key: 'unified_rate_mgr',   label: 'Unified Rate Manager',     path: '/unified-rate-manager',           group: 'channels',critical: true },
    { key: 'channel_connect',    label: 'Channel Connections',      path: '/channel-connections',            group: 'channels',critical: true },
    { key: 'channel_ops',        label: 'Channel Operations',       path: '/channel-ops',                    group: 'channels',critical: true },
    { key: 'conflict_queue',     label: 'Conflict Queue',           path: '/channels?tab=conflicts',         group: 'channels',critical: true },
    { key: 'user_roles',         label: 'Kullanıcı / Rol',          path: '/admin/user-roles',               group: 'admin',   critical: true },
    { key: 'reservation_cal',    label: 'Rezervasyon Takvimi',      path: '/app/reservation-calendar',       group: 'reservations', critical: true },
    { key: 'pms',                label: 'PMS',                      path: '/app/pms',                        group: 'reservations', critical: true },
    { key: 'pms_operations',     label: 'PMS Operasyonlar',         path: '/pms-operations',                 group: 'reservations', critical: true },
    { key: 'folio_detail',       label: 'Folio',                    path: '/folio-detail',                   group: 'finance', critical: true },
    { key: 'group_folio',        label: 'Grup Folio',               path: '/group-folio',                    group: 'finance', critical: true },
    { key: 'admin_control',      label: 'Admin Control Panel',      path: '/app/admin-control-panel',        group: 'admin',   critical: true },
    { key: 'settings',           label: 'Ayarlar',                  path: '/app/settings',                   group: 'admin',   critical: true },
    { key: 'security',           label: 'Güvenlik',                 path: '/security',                       group: 'admin',   critical: true },

    // ── SECONDARY: SUPPORTING PAGES ───────────────────────────────────
    { key: 'control_plane',      label: 'Control Plane',            path: '/control-plane',                  group: 'admin',   critical: false },
    { key: 'audit_timeline',     label: 'Denetim Zaman Çizelgesi',  path: '/audit-timeline',                 group: 'admin',   critical: false },
    { key: 'rate_manager',       label: 'Rate Manager',             path: '/rate-manager',                   group: 'channels',critical: false },
    { key: 'hr_hub',             label: 'İK',                       path: '/hr',                             group: 'management', critical: false },
    { key: 'supplies_market',    label: 'Tedarik Pazarı',           path: '/app/supplies-market',            group: 'operations', critical: false },
    { key: 'procurement',        label: 'Satınalma',                path: '/app/procurement',                group: 'operations', critical: false },
];

// Console errors that are expected/benign and should NOT fail the suite.
// Pattern matched against `msg.text()` — case-insensitive substring.
export const CONSOLE_ERROR_ALLOWLIST = [
    'i18next::translator',                  // missing translation keys (warn-level)
    'Download the React DevTools',
    'Sentry Logger',
    'sentry-trace',
    '[HMR]',                                 // dev-server only
    'Failed to load resource: net::ERR_FAILED',  // ignored cancelled fetch on nav
    'favicon.ico',
    'Service Worker',
    'workbox',
    'WebSocket connection',                  // WS reconnect noise
    // App-specific known noise; keep narrow:
    'ResizeObserver loop',                   // benign browser warning
];

// Network responses that are EXPECTED to be non-2xx during smoke (e.g. some
// /api/health/* probes return 503 when subsystems are degraded — that is
// information, not a UI bug).
export const NETWORK_ERROR_ALLOWLIST = [
    /\/api\/health\/(readiness|liveness)/,   // may be 503 on degraded prod
    /\/api\/feature-flags/,                  // may 404 if flag-svc disabled
    /\/api\/integrations\/.*\/status/,       // tenant-config dependent
    /\/_vite\//,                             // dev-only
    /sentry\.io/,                            // beacon failures don't matter
];
