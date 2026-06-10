import React from 'react';
import { Tabs } from 'expo-router';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';

export default function GMLayout() {
  const c = useTheme();
  // Cosmetic mirror of the backend `view_finance_reports` permission. When the
  // role lacks it we hide the Reports tab (`href: null`); the backend still
  // enforces the permission on every report endpoint, so this never weakens RBAC.
  const financeReports = useAuthStore((s) => s.financeReports);

  return (
    <Tabs
      screenOptions={{
        tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.border },
        tabBarActiveTintColor: c.primary,
        tabBarInactiveTintColor: c.textMuted,
        headerStyle: { backgroundColor: c.surface },
        headerTitleStyle: { color: c.text },
      }}
    >
      <Tabs.Screen name="index" options={{ title: tr.tabs.overview }} />
      <Tabs.Screen
        name="reports"
        options={{ title: tr.manager.reportsTab, href: financeReports ? undefined : null }}
      />
      <Tabs.Screen name="more" options={{ title: tr.tabs.more }} />
    </Tabs>
  );
}
