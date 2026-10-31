import { deriveMobileAccess, hasServerAccess, mobileOperationAllowed, type ServerAccessContext } from '../state/roleAccess';
import { ROUTES } from './routes';

export function mobileTargetAllowed(user: ServerAccessContext | null, target: unknown): boolean {
  if (!user || typeof target !== 'string') return false;
  return mobileRouteAllowed(user, target.split('/').filter(Boolean));
}

export function paidDepartmentForSegments(segments: readonly string[]): 'spa' | 'mice' | 'pos' | 'revenue' | undefined {
  const [group, screen] = segments;
  return group === '(departments)' && ['spa', 'mice', 'pos', 'revenue'].includes(screen)
    ? screen as 'spa' | 'mice' | 'pos' | 'revenue' : undefined;
}

export function mobileHome(user: ServerAccessContext) {
  const a = deriveMobileAccess(user);
  if (a.role === 'guest_app') return ROUTES.guest;
  if (a.role === 'housekeeping' && a.housekeepingAccess) return ROUTES.housekeeping;
  if (a.managerAccess) return ROUTES.gm;
  if (a.frontdeskAccess) return ROUTES.frontdesk;
  return ROUTES.home;
}

/** Screens are gated before mounting: hidden tabs alone do not stop deep links
 * or their queries. This never replaces backend resource/operation RBAC. */
export function mobileRouteAllowed(user: ServerAccessContext, segments: readonly string[]): boolean {
  const a = deriveMobileAccess(user);
  const [group, screen = 'index'] = segments;
  if (a.role === 'guest_app') return group === '(guest)';
  if (group === '(guest)') return false; // Staff JWT is not a guest session.
  if (group === '(home)') return screen !== 'approvals' || a.approvalsAccess;
  if (group === '(housekeeping)') return a.housekeepingAccess && (screen !== 'damage' || mobileOperationAllowed(user, 'update_room_status'));
  if (group === '(gm)') return ['reports', 'report-detail'].includes(screen) ? a.financeReports : a.managerAccess;
  if (group === '(departments)') {
    if (screen === 'index') return a.deptAccess;
    if (screen === 'folio') return a.cashierAccess;
    const flags: Record<string, boolean> = {
      spa: a.spaAccess, mice: a.miceAccess, cashier: a.cashierAccess,
      accounting: a.accountingAccess, maintenance: a.maintenanceAccess,
      procurement: a.procurementAccess, hr: a.hrAccess, revenue: a.revenueAccess, pos: a.posAccess,
    };
    return flags[screen] === true;
  }
  if (group !== '(frontdesk)') return false;
  const pages: Record<string, string> = {
    index: 'frontdesk', more: 'frontdesk', rooms: 'rooms', calendar: 'calendar',
    reservations: 'bookings', reservation: 'bookings', availability: 'bookings',
    checkin: 'bookings', checkout: 'bookings', walkin: 'bookings', 'new-reservation': 'bookings',
    guests: 'guests', reports: 'frontdesk', notifications: 'frontdesk',
    messages: 'frontdesk', tasks: 'frontdesk', fault: 'frontdesk',
  };
  const page = pages[screen];
  if (!page) return false;
  const operations: Record<string, string> = { checkin: 'checkin', checkout: 'checkout', walkin: 'create_booking', 'new-reservation': 'create_booking' };
  return hasServerAccess(user, page, operations[screen]) ?? a.frontdeskAccess;
}
