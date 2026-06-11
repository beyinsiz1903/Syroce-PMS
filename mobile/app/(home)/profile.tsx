import React from 'react';
import { ScrollView, View, Text } from 'react-native';
import { useRouter } from 'expo-router';
import type { Href } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Badge, Button, Card, H1, H2, ListRow, Muted } from '../../src/components/ui';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';

type ModuleEntry = {
  key: string;
  label: string;
  route: Href;
  visible: boolean;
  icon: keyof typeof Ionicons.glyphMap;
};

function initialsFor(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '—';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

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
      icon: 'desktop-outline',
    },
    {
      key: 'housekeeping',
      label: tr.hub.moduleHousekeeping,
      route: ROUTES.housekeeping,
      visible: allAccess || role === 'housekeeping',
      icon: 'brush-outline',
    },
    {
      key: 'manager',
      label: tr.hub.moduleManager,
      route: ROUTES.gm,
      visible: allAccess || role === 'gm',
      icon: 'briefcase-outline',
    },
    {
      key: 'spa',
      label: tr.hub.moduleSpa,
      route: ROUTES.spa,
      visible: allAccess || spaAccess,
      icon: 'flower-outline',
    },
    {
      key: 'mice',
      label: tr.hub.moduleMice,
      route: ROUTES.mice,
      visible: allAccess || miceAccess,
      icon: 'easel-outline',
    },
    {
      key: 'cashier',
      label: tr.hub.moduleCashier,
      route: ROUTES.cashier,
      visible: allAccess || financeReports,
      icon: 'cash-outline',
    },
    {
      key: 'accounting',
      label: tr.hub.moduleAccounting,
      route: ROUTES.accounting,
      visible: allAccess || financeReports,
      icon: 'calculator-outline',
    },
    {
      key: 'maintenance',
      label: tr.hub.moduleMaintenance,
      route: ROUTES.maintenance,
      visible: allAccess || maintenanceAccess,
      icon: 'construct-outline',
    },
  ];
  const visibleModules = modules.filter((m) => m.visible);
  const displayName = user?.name || user?.username || user?.email || '—';

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}>
        <H1>{tr.hub.profileTitle}</H1>

        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
            <View
              style={{
                width: 56,
                height: 56,
                borderRadius: radius.pill,
                backgroundColor: c.primarySoft,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ color: c.primary, fontSize: 20, fontWeight: '800' }}>
                {initialsFor(displayName)}
              </Text>
            </View>
            <View style={{ flex: 1 }}>
              <H2 numberOfLines={1}>{displayName}</H2>
              {user?.email ? (
                <Muted style={{ marginTop: 2 }} numberOfLines={1}>
                  {user.email}
                </Muted>
              ) : null}
              {user?.role ? (
                <View style={{ marginTop: spacing.xs }}>
                  <Badge label={user.role} tone="primary" />
                </View>
              ) : null}
            </View>
          </View>
        </Card>

        <RoleSwitcher />

        <H2 style={{ marginTop: spacing.sm }}>{tr.hub.modules}</H2>
        <Card testID="smoke-profile-modules" padded={false} style={{ overflow: 'hidden' }}>
          {visibleModules.length === 0 ? (
            <View style={{ padding: spacing.lg }}>
              <Muted testID="smoke-no-modules">{tr.hub.noModules}</Muted>
            </View>
          ) : (
            visibleModules.map((m, i) => (
              <ListRow
                key={m.key}
                testID={`smoke-module-${m.key}`}
                icon={m.icon}
                label={m.label}
                onPress={() => router.push(m.route)}
                last={i === visibleModules.length - 1}
              />
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
