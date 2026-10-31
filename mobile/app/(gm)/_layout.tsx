import React from 'react';
import { MobileRouteGate } from '../../src/components/MobileRouteGate';
import type { ColorValue } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { OperationalHeader } from '../../src/components/OperationalHeader';
import { HeaderBackButton } from '../../src/components/HeaderBackButton';
import { ROUTES } from '../../src/navigation/routes';

type IoniconName = keyof typeof Ionicons.glyphMap;

function tabIcon(active: IoniconName, inactive: IoniconName) {
  return ({ color, focused, size }: { color: ColorValue; focused: boolean; size: number }) => (
    <Ionicons name={focused ? active : inactive} size={size ?? 24} color={color} />
  );
}

export default function GMLayout() {
  return <MobileRouteGate><GMLayoutContent /></MobileRouteGate>;
}

function GMLayoutContent() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  // Cosmetic mirror of the backend `view_finance_reports` permission. When the
  // role lacks it we hide the Reports tab (`href: null`); the backend still
  // enforces the permission on every report endpoint, so this never weakens RBAC.
  const financeReports = useAuthStore((s) => s.financeReports);
  const managerAccess = useAuthStore((s) => s.managerAccess);

  return (
    <Tabs
      screenOptions={{
        tabBarStyle: {
          backgroundColor: c.surface,
          borderTopColor: c.border,
          height: 60 + insets.bottom,
          paddingBottom: insets.bottom + 6,
          paddingTop: 6,
        },
        tabBarActiveTintColor: c.primary,
        tabBarInactiveTintColor: c.textMuted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        headerStyle: { backgroundColor: c.surface },
        headerTitleStyle: { color: c.text },
        headerTitle: ({ children }) => <OperationalHeader title={children} />,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ href: managerAccess ? undefined : null, title: tr.tabs.overview, tabBarIcon: tabIcon('speedometer', 'speedometer-outline') }}
      />
      <Tabs.Screen
        name="reports"
        options={{
          title: tr.manager.reportsTab,
          headerLeft: () => <HeaderBackButton fallback={ROUTES.homeProfile} />,
          href: financeReports ? undefined : null,
          tabBarIcon: tabIcon('bar-chart', 'bar-chart-outline'),
        }}
      />
      <Tabs.Screen name="report-detail" options={{ href: null, title: 'Rapor detayı', headerLeft: () => <HeaderBackButton fallback={ROUTES.homeProfile} /> }} />
      <Tabs.Screen
        name="more"
        options={{
          title: tr.tabs.settings,
          href: managerAccess ? undefined : null,
          tabBarLabel: tr.tabs.more,
          tabBarIcon: tabIcon('ellipsis-horizontal-circle', 'ellipsis-horizontal-circle-outline'),
        }}
      />
    </Tabs>
  );
}
