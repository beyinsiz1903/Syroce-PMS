import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';

type IoniconName = keyof typeof Ionicons.glyphMap;

// Build a focused/unfocused Ionicon pair into a Tabs `tabBarIcon` render-prop.
// Icons make the bottom-tab backbone scannable at a glance (icon + label),
// which is the Tier-1 ergonomic goal — the label/name/testID stay untouched so
// the smoke matrix keeps resolving every tab.
function tabIcon(active: IoniconName, inactive: IoniconName) {
  return ({ color, focused, size }: { color: string; focused: boolean; size: number }) => (
    <Ionicons name={focused ? active : inactive} size={size ?? 24} color={color} />
  );
}

// Task #327 — Tier-1 common shell. Every staff role sees the SAME bottom-tab
// backbone (Slack/WhatsApp style). The only permission-gated tab is
// "Onaylarım": hidden (`href: null`) when the user holds neither finance nor
// HR approval visibility. The backend still enforces every approval action, so
// this is a cosmetic affordance only.
export default function HomeLayout() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const approvalsAccess = useAuthStore((s) => s.approvalsAccess);
  const allAccess = useAuthStore((s) => s.allAccess);
  const showApprovals = approvalsAccess || allAccess;

  return (
    <Tabs
      screenOptions={{
        tabBarStyle: {
          backgroundColor: c.surface,
          borderTopColor: c.border,
          // Thumb-zone ergonomics: a taller bar with safe-area padding so the
          // targets clear the home indicator on native and read comfortably on
          // web (insets.bottom is 0 there, so the bar settles at 60px).
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
        options={{
          title: tr.tabs.notifications,
          tabBarTestID: 'smoke-tab-notifications',
          tabBarIcon: tabIcon('notifications', 'notifications-outline'),
        }}
      />
      <Tabs.Screen
        name="today"
        options={{
          title: tr.tabs.today,
          tabBarTestID: 'smoke-tab-today',
          tabBarIcon: tabIcon('today', 'today-outline'),
        }}
      />
      <Tabs.Screen
        name="tasks"
        options={{
          title: tr.tabs.myTasks,
          tabBarTestID: 'smoke-tab-tasks',
          tabBarIcon: tabIcon('checkbox', 'checkbox-outline'),
        }}
      />
      <Tabs.Screen
        name="messages"
        options={{
          title: tr.tabs.messages,
          tabBarTestID: 'smoke-tab-messages',
          tabBarIcon: tabIcon('chatbubble-ellipses', 'chatbubble-ellipses-outline'),
        }}
      />
      <Tabs.Screen
        name="approvals"
        options={{
          title: tr.tabs.approvals,
          href: showApprovals ? undefined : null,
          tabBarTestID: 'smoke-tab-approvals',
          tabBarIcon: tabIcon('checkmark-done-circle', 'checkmark-done-circle-outline'),
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: tr.tabs.search,
          tabBarTestID: 'smoke-tab-search',
          tabBarIcon: tabIcon('search', 'search-outline'),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: tr.tabs.profile,
          tabBarTestID: 'smoke-tab-profile',
          tabBarIcon: tabIcon('person-circle', 'person-circle-outline'),
        }}
      />
    </Tabs>
  );
}
