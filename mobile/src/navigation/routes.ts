import type { Href } from 'expo-router';
import type { AppRole } from '../state/authStore';

// ── Navigation conventions (Task #454) ──────────────────────────────────────
// Every route in the app is declared here in `ROUTES` and consumed via
// `router.push(ROUTES.x)` / `<Redirect href={ROUTES.x} />`. NEVER hard-code a
// path string at a call site — add it here so deep links and refactors stay in
// one place. `satisfies Record<string, Href>` makes a typo a compile error.
//
// GROUP / TIER MODEL
//   Tier-1 backbone:  `(home)` — the unified staff shell. Tabs only (no nested
//                     stack). Staff land on the "Bugün" tab (see rootForRole).
//   Tier-2 groups:    `(frontdesk)` `(housekeeping)` `(gm)` `(guest)` — each is
//                     a role's native area, reachable INTO from the shell.
//   Shared area:      `(departments)` — cross-role; admitted by entitlement,
//                     not by role home (see GROUP_SEGMENTS comment below).
//   Group folders use parentheses so the segment is hidden from the URL; the
//   group's own `index.tsx` is what `/(group)` resolves to.
//
// HEADERS
//   - Tab screens (group `_layout.tsx` with <Tabs>): the bottom tab bar is the
//     navigation; per-tab titles come from the Tabs.Screen `title` option, and
//     role-gated tabs are hidden with `href: null` (NOT unmounted) so the bar
//     highlight stays correct and the screen is still reachable by URL.
//   - Stack screens (list -> detail): set `headerTitle` on the detail screen so
//     the platform back button + title come for free. The on-screen
//     `<DetailHeader>` (components/ui.tsx) is the in-body masthead, separate
//     from the navigator header — do not duplicate the title in both when a
//     native header is shown.
//
// BACK
//   - Prefer the navigator's implicit back (stack header / hardware) for
//     list -> detail. Use `router.back()` only for explicit in-body controls.
//   - To LEAVE a flow to a fixed home (e.g. a guard rejecting access), use
//     `<Redirect href={ROUTES.departments} />` rather than `router.back()`,
//     which could pop to an unexpected screen.
//
// DEEP LINKS
//   - A linkable detail screen takes its id from the route param
//     (`useLocalSearchParams`) and must render its own loading / empty / error
//     states, because a cold deep link has no warm list cache to fall back on.
//     The `<DepartmentListState>` / list->detail->action example pattern shows
//     this (see components/ExampleDepartmentScreen.tsx).
//   - Detail routes are declared WITHOUT the id segment here (e.g.
//     `reservationDetail: '/(frontdesk)/reservation'`); append the id at the
//     call site: `router.push(\`\${ROUTES.reservationDetail}/\${id}\`)`.
export const ROUTES = {
  login: '/(auth)/login',
  home: '/(home)',
  homeNotifications: '/(home)/notifications',
  homeTasks: '/(home)/tasks',
  homeToday: '/(home)/today',
  homeApprovals: '/(home)/approvals',
  homeMessages: '/(home)/messages',
  homeSearch: '/(home)/search',
  homeProfile: '/(home)/profile',
  frontdesk: '/(frontdesk)',
  housekeeping: '/(housekeeping)',
  hkDamage: '/(housekeeping)/damage',
  gm: '/(gm)',
  guest: '/(guest)',
  departments: '/(departments)',
  spa: '/(departments)/spa',
  mice: '/(departments)/mice',
  cashier: '/(departments)/cashier',
  folioDetail: '/(departments)/folio',
  accounting: '/(departments)/accounting',
  maintenance: '/(departments)/maintenance',
  procurement: '/(departments)/procurement',
  hr: '/(departments)/hr',
  revenue: '/(departments)/revenue',
  pos: '/(departments)/pos',
  checkin: '/(frontdesk)/checkin',
  checkout: '/(frontdesk)/checkout',
  walkin: '/(frontdesk)/walkin',
  reservations: '/(frontdesk)/reservations',
  reservationDetail: '/(frontdesk)/reservation',
  availability: '/(frontdesk)/availability',
  frontdeskRooms: '/(frontdesk)/rooms',
  frontdeskGuests: '/(frontdesk)/guests',
  reservationCalendar: '/(frontdesk)/calendar',
  guestBookings: '/(guest)',
  guestOnlineCheckin: '/(guest)/checkin',
  guestRoomService: '/(guest)/roomservice',
  guestCart: '/(guest)/cart',
  guestOrders: '/(guest)/orders',
  guestMessages: '/(guest)/messages',
  guestMessageThread: '/(guest)/messageThread',
  guestLoyalty: '/(guest)/loyalty',
  guestBookingDetail: '/(guest)/booking',
  guestEarlyLate: '/(guest)/earlylate',
  guestDigitalKey: '/(guest)/digitalKey',
  guestQrBadge: '/(guest)/qrBadge',
} as const satisfies Record<string, Href>;

// Every staff role lands in the unified common shell `(home)` (Tier-1
// backbone). Guests keep their dedicated experience. The role-specific Tier-2
// groups remain reachable from within the shell, but they are no longer the
// staff landing surface.
//
// Task #507 — staff land on the HUB "Ana Sayfa" (the (home) group index), an
// operations center with the live "Bugün" KPI card, a smart notification feed,
// and permission-filtered department shortcuts. It is the first visible bottom
// tab, so the bar highlight stays correct. Guests keep their dedicated area.
export function rootForRole(role: AppRole): Href {
  switch (role) {
    case 'guest_app':
      return ROUTES.guest;
    default:
      return ROUTES.home;
  }
}

// The role's native Tier-2 group — the role-specific area a single-role staff
// member may browse INTO from the common shell. Returns `(home)` for roles
// without a dedicated Tier-2 group, so AuthGate keeps them in the shell.
export function groupForRole(role: AppRole): string {
  switch (role) {
    case 'front_desk':
      return '(frontdesk)';
    case 'housekeeping':
      return '(housekeeping)';
    case 'guest_app':
      return '(guest)';
    case 'gm':
      return '(gm)';
    default:
      return '(home)';
  }
}

// Top-level group segment for the unified common shell (Tier-1 backbone).
export const HOME_SEGMENT = '(home)' as const;

// Expo Router top-level group segments. All-access users (super_admin/admin)
// are permitted to sit inside ANY of these, unlike single-role users who are
// pinned to their own group by AuthGate. `(departments)` is a shared cross-role
// area: AuthGate additionally admits single-role users who hold department
// entitlement (see `deptAccess`), so it is intentionally NOT a role home.
export const GROUP_SEGMENTS = [
  '(home)',
  '(frontdesk)',
  '(housekeeping)',
  '(gm)',
  '(guest)',
  '(departments)',
] as const;

// Top-level group segment for the shared departments area.
export const DEPARTMENTS_SEGMENT = '(departments)' as const;

// Roles selectable from the in-app role switcher. Ordered with the manager
// landing first so the switcher reads top-down from the all-access home.
export type SwitchableRole = 'gm' | 'front_desk' | 'housekeeping' | 'guest_app';

export const ALL_ROLE_GROUPS: {
  key: SwitchableRole;
  route: Href;
  group: (typeof GROUP_SEGMENTS)[number];
}[] = [
  { key: 'gm', route: ROUTES.gm, group: '(gm)' },
  { key: 'front_desk', route: ROUTES.frontdesk, group: '(frontdesk)' },
  { key: 'housekeeping', route: ROUTES.housekeeping, group: '(housekeeping)' },
  { key: 'guest_app', route: ROUTES.guest, group: '(guest)' },
];
