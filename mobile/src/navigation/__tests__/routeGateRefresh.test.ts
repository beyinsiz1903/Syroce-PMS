import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';
import React from 'react';
import { JsxEmit, ModuleKind, transpileModule } from 'typescript';
import * as access from '../routeAccess';
import { ROUTES } from '../routes';
function harness() {
  const state: any = { user: { role: 'front_desk', tenant_id: 'synthetic' }, loading: false };
  let segments = ['(frontdesk)', 'more'];
  const subscription: any = { data: {}, isPending: false, fetchStatus: 'idle', isError: false };
  const module = { exports: {} as any };
  const code = transpileModule(readFileSync(resolve('src/components/MobileRouteGate.tsx'), 'utf8'), {
    compilerOptions: { module: ModuleKind.CommonJS, jsx: JsxEmit.React, esModuleInterop: true },
  }).outputText;
  const ports: Record<string, any> = {
    react: React, 'react-native': { View: 'View', ActivityIndicator: 'ActivityIndicator' },
    'expo-router': { Redirect: 'Redirect', useSegments: () => segments, useRouter: () => ({ replace() {} }) },
    '@tanstack/react-query': { useQuery: () => subscription }, '../state/authStore': { useAuthStore: () => state },
    '../navigation/routeAccess': access, '../navigation/routes': { ROUTES },
    '../api/subscription': { getCurrentSubscription() {} },
    '../utils/departmentScreens': { hubModuleState: () => 'enabled' },
    './ui': { Button: 'Button', Card: 'Card', Muted: 'Muted' },
  };
  new Function('require', 'module', 'exports', code)((name: string) => {
    if (!(name in ports)) throw new Error(`Unexpected dependency ${name}`);
    return ports[name];
  }, module, module.exports);
  const child = React.createElement('PrivateNavigator');
  return { state, subscription, child, setSegments(value: string[]) { segments = value; },
    render: () => module.exports.MobileRouteGate({ children: child }) as React.ReactElement<any> };
}
function nodes(element: any): any[] {
  return React.isValidElement(element)
    ? [element, ...React.Children.toArray((element.props as any).children).flatMap(nodes)] : [];
}
test('session refresh retains navigator position and blocks input until validation finishes', () => {
  const h = harness(); const before = h.render();
  h.state.loading = true; const during = h.render();
  h.state.loading = false; const after = h.render();
  for (const tree of [before, during, after]) {
    assert.equal(tree.type, 'View');
    assert.equal(tree.props.children[0].props.children, h.child);
  }
  assert.equal(during.props.children[0].props.pointerEvents, 'none');
  assert.equal(during.props.children[0].props.accessibilityElementsHidden, true);
  assert.ok(nodes(during).some(n => n.props.testID === 'session-validation-overlay'));
  assert.equal(after.props.children[0].props.pointerEvents, 'auto');
  assert.equal(nodes(after).some(n => n.props.testID === 'session-validation-overlay'), false);
});
test('cold hydration never exposes private children', () => {
  const h = harness(); h.state.user = null; h.state.loading = true;
  assert.equal(nodes(h.render()).includes(h.child), false);
  assert.ok(nodes(h.render()).some(n => n.type === 'ActivityIndicator'));
});
test('logout redirects without private children', () => {
  const h = harness(); h.state.user = null; const tree = h.render();
  assert.equal(tree.type, 'Redirect'); assert.equal(tree.props.href, ROUTES.login);
});
test('revoked role redirects away from the previous private route', () => {
  const h = harness(); h.state.user = { role: 'guest' }; const tree = h.render();
  assert.equal(tree.type, 'Redirect'); assert.equal(tree.props.href, '/(guest)');
});
test('paid module verification still withholds content while fetching', () => {
  const h = harness(); h.state.user = { role: 'super_admin' }; h.setSegments(['(departments)', 'spa']);
  h.subscription.isPending = true; h.subscription.fetchStatus = 'fetching';
  assert.equal(h.render().type, 'ActivityIndicator'); assert.equal(nodes(h.render()).includes(h.child), false);
});
