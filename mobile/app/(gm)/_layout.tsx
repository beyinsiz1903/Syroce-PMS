import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';

type IoniconName = keyof typeof Ionicons.glyphMap;

function tabIcon(active: IoniconName, inactive: IoniconName) {
  return ({ color, focused, size }: { color: string; focused: boolean; size: number }) => (
    <Ionicons name={focused ? active : inactive} size={size ?? 24} color={color} />
  );
}

export default function GMLayout() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  // Cosmetic mirror of the backend `view_finance_reports` permission. When the
  // role lacks it we hide the Reports tab (`href: null`); the backend still
  // enforces the permission on every report endpoint, so this never weakens RBAC.
  const financeReports = useAuthStore((s) => s.financeReports);

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
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: tr.tabs.overview, tabBarIcon: tabIcon('speedometer', 'speedometer-outline') }}
      />
      <Tabs.Screen
        name="reports"
        options={{
          title: tr.manager.reportsTab,
          href: financeReports ? undefined : null,
          tabBarIcon: tabIcon('bar-chart', 'bar-chart-outline'),
        }}
      />
      <Tabs.Screen
        name="more"
        options={{
          title: tr.tabs.more,
          tabBarIcon: tabIcon('ellipsis-horizontal-circle', 'ellipsis-horizontal-circle-outline'),
        }}
      />
    </Tabs>
  );
}
