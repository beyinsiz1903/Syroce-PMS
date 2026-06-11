import React from 'react';
import { Tabs } from 'expo-router';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';

// Task #327 — Tier-1 common shell. Every staff role sees the SAME bottom-tab
// backbone (Slack/WhatsApp style). The only permission-gated tab is
// "Onaylarım": hidden (`href: null`) when the user holds neither finance nor
// HR approval visibility. The backend still enforces every approval action, so
// this is a cosmetic affordance only.
export default function HomeLayout() {
  const c = useTheme();
  const approvalsAccess = useAuthStore((s) => s.approvalsAccess);
  const allAccess = useAuthStore((s) => s.allAccess);
  const showApprovals = approvalsAccess || allAccess;

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
      <Tabs.Screen
        name="index"
        options={{ title: tr.tabs.notifications, tabBarTestID: 'smoke-tab-notifications' }}
      />
      <Tabs.Screen
        name="today"
        options={{ title: tr.tabs.today, tabBarTestID: 'smoke-tab-today' }}
      />
      <Tabs.Screen
        name="tasks"
        options={{ title: tr.tabs.myTasks, tabBarTestID: 'smoke-tab-tasks' }}
      />
      <Tabs.Screen
        name="messages"
        options={{ title: tr.tabs.messages, tabBarTestID: 'smoke-tab-messages' }}
      />
      <Tabs.Screen
        name="approvals"
        options={{
          title: tr.tabs.approvals,
          href: showApprovals ? undefined : null,
          tabBarTestID: 'smoke-tab-approvals',
        }}
      />
      <Tabs.Screen
        name="search"
        options={{ title: tr.tabs.search, tabBarTestID: 'smoke-tab-search' }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: tr.tabs.profile, tabBarTestID: 'smoke-tab-profile' }}
      />
    </Tabs>
  );
}
