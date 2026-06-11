import React from 'react';
import { ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import type { Href } from 'expo-router';
import { Button, Card, Divider, H1, H2, Muted } from '../../src/components/ui';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';

type ModuleEntry = { key: string; label: string; route: Href; visible: boolean };

export default function ProfileScreen() {
  const c = useTheme();
  const router = useRouter();
  const {
    user,
    role,
    allAccess,
    spaAccess,
    miceAccess,
    maintenanceAccess,
    financeReports,
    logout,
  } = useAuthStore();

  // Tier-2 module visibility skeleton: each role-specific area is surfaced only
  // when the signed-in user is entitled to it. AuthGate admits these targets
  // (native group / departments / all-access) and the backend enforces every
  // action inside — this list never grants access, it only reveals entry points.
  const modules: ModuleEntry[] = [
    {
      key: 'frontdesk',
      label: tr.hub.moduleFrontdesk,
      route: ROUTES.frontdesk,
      visible: allAccess || role === 'front_desk',
    },
    {
      key: 'housekeeping',
      label: tr.hub.moduleHousekeeping,
      route: ROUTES.housekeeping,
      visible: allAccess || role === 'housekeeping',
    },
    {
      key: 'manager',
      label: tr.hub.moduleManager,
      route: ROUTES.gm,
      visible: allAccess || role === 'gm',
    },
    { key: 'spa', label: tr.hub.moduleSpa, route: ROUTES.spa, visible: allAccess || spaAccess },
    { key: 'mice', label: tr.hub.moduleMice, route: ROUTES.mice, visible: allAccess || miceAccess },
    {
      key: 'cashier',
      label: tr.hub.moduleCashier,
      route: ROUTES.cashier,
      visible: allAccess || financeReports,
    },
    {
      key: 'accounting',
      label: tr.hub.moduleAccounting,
      route: ROUTES.accounting,
      visible: allAccess || financeReports,
    },
    {
      key: 'maintenance',
      label: tr.hub.moduleMaintenance,
      route: ROUTES.maintenance,
      visible: allAccess || maintenanceAccess,
    },
  ];
  const visibleModules = modules.filter((m) => m.visible);

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}>
        <H1>{tr.hub.profileTitle}</H1>

        <Card>
          <H2>{user?.name || user?.username || user?.email || '—'}</H2>
          {user?.email ? <Muted style={{ marginTop: spacing.xs }}>{user.email}</Muted> : null}
          {user?.role ? <Muted style={{ marginTop: spacing.xs }}>{user.role}</Muted> : null}
        </Card>

        <RoleSwitcher />

        <H2 style={{ marginTop: spacing.sm }}>{tr.hub.modules}</H2>
        <Card testID="smoke-profile-modules">
          {visibleModules.length === 0 ? (
            <Muted testID="smoke-no-modules">{tr.hub.noModules}</Muted>
          ) : (
            visibleModules.map((m, i) => (
              <View key={m.key}>
                {i > 0 ? <Divider /> : null}
                <Button
                  testID={`smoke-module-${m.key}`}
                  title={m.label}
                  variant="secondary"
                  onPress={() => router.push(m.route)}
                  fullWidth
                />
              </View>
            ))
          )}
        </Card>

        <Button
          title={tr.auth.logout}
          variant="danger"
          onPress={() => logout()}
          fullWidth
          style={{ marginTop: spacing.md }}
        />
      </ScrollView>
    </View>
  );
}
