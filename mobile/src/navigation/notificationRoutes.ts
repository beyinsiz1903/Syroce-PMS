import type { ServerAccessContext } from '../state/roleAccess';
import { mobileHome, mobileTargetAllowed } from './routeAccess';
import { ROUTES } from './routes';

export type NotificationUser = ServerAccessContext & { id?: string; user_id?: string; tenant_id?: string; hotel_id?: string };
export type PushPayload = { type?: unknown; booking_id?: unknown; thread_id?: unknown; tenant_id?: unknown; user_id?: unknown };
export type NotificationTarget = string | { pathname: string; params: Record<string, string> };

export function notificationTarget(payload: PushPayload, user: NotificationUser | null, coldStart = false): NotificationTarget | null {
  if (!user) return null;
  const tenant = user.tenant_id || user.hotel_id;
  const recipient = user.id || user.user_id;
  if ((payload.tenant_id && payload.tenant_id !== tenant) || (payload.user_id && payload.user_id !== recipient)) return null;
  // A previously tapped OS notification can survive logout and account change.
  // Old unscoped notifications cannot reopen a resource on a cold login.
  if (coldStart && (!payload.tenant_id || !payload.user_id)) return null;
  const home = mobileHome(user);
  const allowed = (target: NotificationTarget) => mobileTargetAllowed(user, typeof target === 'string' ? target : target.pathname) ? target : home;
  const id = (value: unknown) => typeof value === 'string' && value.trim() ? value : undefined;
  switch (payload.type) {
    case 'no_show_risk':
      return id(payload.booking_id) ? allowed({ pathname: ROUTES.checkin, params: { bookingId: id(payload.booking_id)! } }) : home;
    case 'damage_report': return allowed(ROUTES.housekeeping);
    case 'guest_message': {
      if (user.role === 'guest' || user.role === 'guest_app') {
        const bookingId = id(payload.booking_id) || id(payload.thread_id);
        return bookingId ? allowed({ pathname: ROUTES.guestMessageThread, params: { bookingId } }) : allowed(ROUTES.guestMessages);
      }
      return allowed(ROUTES.homeMessages);
    }
    case 'housekeeping_task':
    case 'maintenance_task': return allowed(ROUTES.homeTasks);
    case 'qr_charge_approval':
    case 'qr_charge_rejected': return user.role === 'guest' || user.role === 'guest_app' ? allowed(ROUTES.guestQrBadge) : home;
    case 'vip_arrival':
    case 'eod_ready': return home;
    default: return null;
  }
}
