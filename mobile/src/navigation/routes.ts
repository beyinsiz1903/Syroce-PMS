import type { Href } from 'expo-router';
import type { AppRole } from '../state/authStore';

export const ROUTES = {
  login: '/(auth)/login',
  frontdesk: '/(frontdesk)',
  housekeeping: '/(housekeeping)',
  gm: '/(gm)',
  guest: '/(guest)',
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

export function rootForRole(role: AppRole): Href {
  switch (role) {
    case 'front_desk':
      return ROUTES.frontdesk;
    case 'housekeeping':
      return ROUTES.housekeeping;
    case 'guest_app':
      return ROUTES.guest;
    case 'gm':
      return ROUTES.gm;
    default:
      return ROUTES.gm;
  }
}

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
      return '(gm)';
  }
}

// Expo Router top-level group segments. All-access users (super_admin/admin)
// are permitted to sit inside ANY of these, unlike single-role users who are
// pinned to their own group by AuthGate.
export const GROUP_SEGMENTS = ['(frontdesk)', '(housekeeping)', '(gm)', '(guest)'] as const;

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
