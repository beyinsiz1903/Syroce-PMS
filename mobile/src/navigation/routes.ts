import type { Href } from 'expo-router';
import type { AppRole } from '../state/authStore';

export const ROUTES = {
  login: '/(auth)/login',
  home: '/(home)',
  homeNotifications: '/(home)',
  homeTasks: '/(home)/tasks',
  homeToday: '/(home)/today',
  homeApprovals: '/(home)/approvals',
  homeMessages: '/(home)/messages',
  homeSearch: '/(home)/search',
  homeProfile: '/(home)/profile',
  frontdesk: '/(frontdesk)',
  housekeeping: '/(housekeeping)',
  gm: '/(gm)',
  guest: '/(guest)',
  departments: '/(departments)',
  spa: '/(departments)/spa',
  mice: '/(departments)/mice',
  accounting: '/(departments)/accounting',
  maintenance: '/(departments)/maintenance',
  checkin: '/(frontdesk)/checkin',
  checkout: '/(frontdesk)/checkout',
  walkin: '/(frontdesk)/walkin',
  reservations: '/(frontdesk)/reservations',
  reservationDetail: '/(frontdesk)/reservation',
  availability: '/(frontdesk)/availability',
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

// Task #327 — every staff role now lands in the unified common shell `(home)`
// (Tier-1 backbone). Guests keep their dedicated experience. The role-specific
// Tier-2 groups remain reachable from within the shell, but they are no longer
// the staff landing surface.
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
