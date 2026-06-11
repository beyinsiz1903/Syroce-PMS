import React from 'react';
import { Pressable, View } from 'react-native';
import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';

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

// Header utility actions (top-right). Notifications + Search live here on every
// role so the bottom bar stays at a thumb-friendly 4 tabs; Messages joins them
// only for approver roles, whose 4th bottom tab is "Onaylarım" instead. Plain
// Pressable + Ionicons keeps it web-safe (no reanimated / no Alert), and the
// 44x44 targets clear the thumb-zone minimum. Navigation is push-only — these
// are cosmetic shortcuts; every screen still enforces its own access server-
// side, so nothing here weakens RBAC.
function HeaderActions({ showMessages }: { showMessages: boolean }) {
  const c = useTheme();
  const router = useRouter();
  const btn = {
    width: 44,
    height: 44,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  };
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', marginRight: 4 }}>
      {showMessages ? (
        <Pressable
          onPress={() => router.push(ROUTES.homeMessages)}
          accessibilityRole="button"
          accessibilityLabel={tr.tabs.messages}
          testID="smoke-header-messages"
          hitSlop={8}
          style={btn}
        >
          <Ionicons name="chatbubble-ellipses-outline" size={22} color={c.text} />
        </Pressable>
      ) : null}
      <Pressable
        onPress={() => router.push(ROUTES.homeNotifications)}
        accessibilityRole="button"
        accessibilityLabel={tr.tabs.notifications}
        testID="smoke-header-notifications"
        hitSlop={8}
        style={btn}
      >
        <Ionicons name="notifications-outline" size={22} color={c.text} />
      </Pressable>
      <Pressable
        onPress={() => router.push(ROUTES.homeSearch)}
        accessibilityRole="button"
        accessibilityLabel={tr.tabs.search}
        testID="smoke-header-search"
        hitSlop={8}
        style={btn}
      >
        <Ionicons name="search-outline" size={22} color={c.text} />
      </Pressable>
    </View>
  );
}

// P5 — role-based bottom tab bar. The single (home) Tabs navigator stays the
// common shell (every staff role lands here), but the bottom bar is now trimmed
// to FOUR role-relevant tabs via `href: null`, so Housekeeping and a Manager
// feel different at a glance:
//   line staff (HK / front desk / other): Bugün · Görevlerim · Mesajlar · Profil
//   approvers (GM / all-access):           Bugün · Görevlerim · Onaylarım · Profil
// Notifications + Search move to the header (always), and Messages moves there
// too for approvers. Every Tabs.Screen entry — and every smoke-tab-* testID —
// is kept; `href: null` only hides the tab, the route + screen stay reachable
// by URL and header shortcut. All gating is cosmetic; the backend enforces
// every action, so RBAC is unchanged.
export default function HomeLayout() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
  const approvalsAccess = useAuthStore((s) => s.approvalsAccess);
  const allAccess = useAuthStore((s) => s.allAccess);
  const showApprovals = approvalsAccess || allAccess;
  // Approvers get "Onaylarım" as their 4th tab, so Messages relocates to the
  // header for them; line staff keep Messages as their 4th tab.
  const showMessagesTab = !showApprovals;

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
        headerRight: () => <HeaderActions showMessages={showApprovals} />,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: tr.tabs.notifications,
          // Notifications moved to the header utility row for all roles.
          href: null,
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
          // Line staff keep Messages in the bar; approvers reach it from the
          // header (their 4th tab is Onaylarım instead).
          href: showMessagesTab ? undefined : null,
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
          // Search moved to the header utility row for all roles.
          href: null,
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
