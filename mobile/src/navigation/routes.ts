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
