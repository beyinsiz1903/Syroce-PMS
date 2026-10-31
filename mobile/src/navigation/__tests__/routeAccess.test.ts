import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';
import { mobileHome, mobileRouteAllowed, mobileTargetAllowed, paidDepartmentForSegments } from '../routeAccess';
import { deriveMobileAccess, type ServerAccessContext } from '../../state/roleAccess';
import { visibleHubTiles } from '../../utils/departmentScreens';

const hk: ServerAccessContext = { role: 'housekeeping', module_scopes: ['housekeeping', 'tasks'],
  effective_permissions: ['view_hk_board'], page_access: { housekeeping: true, frontdesk: false, maintenance: false } };
const finance: ServerAccessContext = { role: 'finance', module_scopes: ['finance', 'reports'],
  effective_permissions: ['view_reports', 'view_financial_reports'], page_access: { finance: true, reports: true, frontdesk: false } };
const restricted: ServerAccessContext = { role: 'admin', module_scopes: ['procurement'],
  effective_permissions: ['view_procurement'], page_access: { procurement: true } };
const delegated: ServerAccessContext = { role: 'staff', module_scopes: ['hr'],
  effective_permissions: ['view_hr'], page_access: { hr: true } };

test('staff landing follows actual workspace; no HK or procurement login is forced into frontdesk', () => {
  assert.equal(mobileHome(hk), '/(housekeeping)');
  assert.equal(mobileHome(finance), '/(home)');
  assert.equal(mobileHome(restricted), '/(home)');
  assert.equal(mobileHome({ role: 'guest' }), '/(guest)');
  assert.equal(mobileHome({ role: 'front_desk' }), '/(frontdesk)');
});

test('every restricted landing is allowed itself; redirects cannot bounce between denied homes', () => {
  const maps: Record<string, boolean>[] = [{}, { frontdesk: false }, { housekeeping: true }, { reports: true }, { finance: true }];
  for (const role of ['admin', 'super_admin', 'supervisor', 'front_desk', 'housekeeping', 'finance', 'staff', 'procurement', 'guest', 'unrecognized']) {
    for (const page_access of maps) {
      const user = { role, page_access };
      assert.equal(mobileTargetAllowed(user, mobileHome(user)), true, `${role}/${JSON.stringify(page_access)}`);
    }
  }
});

test('only the exact subscription-bound routes request a paid-module check', () => {
  assert.equal(paidDepartmentForSegments(['(departments)', 'spa']), 'spa');
  assert.equal(paidDepartmentForSegments(['(departments)', 'mice', 'synthetic-event']), 'mice');
  assert.equal(paidDepartmentForSegments(['(departments)', 'accounting']), undefined);
  assert.equal(paidDepartmentForSegments(['(guest)', 'spa']), undefined);
  const gate = readFileSync(resolve('src/components/MobileRouteGate.tsx'), 'utf8');
  assert.match(gate, /hubModuleState\(paidTile, subscription.data\)/);
  assert.ok(gate.indexOf("state !== 'enabled'") < gate.indexOf('return <>{children}</>'));
});

test('department menu and cold/deep links use identical server context', () => {
  for (const user of [hk, finance, restricted, delegated, { role: 'super_admin' }]) {
    const tiles = visibleHubTiles(user.role, { user });
    for (const screen of ['spa', 'mice', 'cashier', 'accounting', 'maintenance', 'procurement', 'hr', 'revenue', 'pos'] as const) {
      assert.equal(mobileRouteAllowed(user, ['(departments)', screen]), tiles.includes(screen), `${user.role}/${screen}`);
    }
  }
  assert.equal(mobileRouteAllowed(hk, ['(frontdesk)', 'reservation']), false);
  assert.equal(mobileRouteAllowed(hk, ['(gm)', 'report-detail']), false);
  assert.equal(mobileRouteAllowed(finance, ['(gm)', 'report-detail']), true);
  assert.equal(mobileRouteAllowed(restricted, ['(departments)', 'accounting']), false);
  assert.equal(mobileRouteAllowed(delegated, ['(departments)', 'hr']), true);
  assert.equal(deriveMobileAccess(restricted).allAccess, false);
});

test('bookings visibility is not permission to check in or create a reservation', () => {
  const user = { role: 'staff', page_access: { bookings: true }, effective_permissions: ['view_bookings'] };
  assert.equal(mobileRouteAllowed(user, ['(frontdesk)', 'reservations']), true);
  for (const screen of ['checkin', 'checkout', 'walkin', 'new-reservation']) {
    assert.equal(mobileRouteAllowed(user, ['(frontdesk)', screen]), false);
  }
  assert.equal(mobileRouteAllowed({ ...user, effective_permissions: ['view_bookings', 'checkin'] }, ['(frontdesk)', 'checkin']), true);
});

test('guests cannot enter staff pages and staff JWTs cannot impersonate the guest app', () => {
  assert.equal(mobileRouteAllowed({ role: 'guest' }, ['(home)']), false);
  assert.equal(mobileRouteAllowed({ role: 'guest' }, ['(guest)', 'booking']), true);
  assert.equal(mobileRouteAllowed({ role: 'super_admin' }, ['(guest)']), false);
  assert.equal(mobileRouteAllowed(finance, ['(departments)', 'typo']), false);
});

test('password, 2FA and hydration share a derivation; all six layouts gate children before mount', () => {
  const auth = readFileSync(resolve('src/state/authStore.ts'), 'utf8');
  assert.match(auth, /hydrate\(\)[\s\S]*?\.\.\.deriveMobileAccess\(user\)/);
  for (const method of ['login', 'verifyTwoFactor']) {
    assert.match(auth, new RegExp(`async ${method}\\([\\s\\S]*?\\.\\.\\.deriveMobileAccess\\(res.user\\)`));
  }
  for (const group of ['home', 'gm', 'frontdesk', 'housekeeping', 'guest', 'departments']) {
    const layout = readFileSync(resolve(`app/(${group})/_layout.tsx`), 'utf8');
    assert.match(layout, /return <MobileRouteGate><\w+Content \/><\/MobileRouteGate>/);
  }
});

test('GM and Revenue screens use web report contracts, not collected-payment or mixed-currency legacy scalars', () => {
  const gm = readFileSync(resolve('app/(gm)/index.tsx'), 'utf8');
  assert.match(gm, /getDailyFlash\(financial.data\?\.business_date\)/);
  assert.match(gm, /value=\{roomKpis.adr\}/);
  assert.doesNotMatch(gm, /formatCurrency\(today\?\.(revenue|adr|revpar)/);
  const revenue = readFileSync(resolve('app/(departments)/revenue.tsx'), 'utf8');
  assert.match(revenue, /queryFn: getRevenuePeriod/);
  assert.doesNotMatch(revenue, /getRevenueDashboard|formatCurrency\(/);
});
