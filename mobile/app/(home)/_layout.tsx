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

// Header utility actions (top-right). Arama lives here for every role so it is
// always one tap away; "Onaylarım" joins it only for approver roles so they can
// reach pending approvals from any (home) tab. Bildirimler + Mesajlar are now
// first-class BOTTOM tabs (Task #507), so they no longer appear here. Plain
// Pressable + Ionicons keeps it web-safe (no reanimated / no Alert), and the
// 44x44 targets clear the thumb-zone minimum. Navigation is push-only — these
// are cosmetic shortcuts; every screen still enforces its own access server-
// side, so nothing here weakens RBAC.
function HeaderActions({ showApprovals }: { showApprovals: boolean }) {
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
      {showApprovals ? (
        <Pressable
          onPress={() => router.push(ROUTES.homeApprovals)}
          accessibilityRole="button"
          accessibilityLabel={tr.tabs.approvals}
          testID="smoke-header-approvals"
          hitSlop={8}
          style={btn}
        >
          <Ionicons name="checkmark-done-circle-outline" size={22} color={c.text} />
        </Pressable>
      ) : null}
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

// Task #507 — the (home) bottom tab bar is the unified operations backbone for
// EVERY staff role: Ana Sayfa (HUB) · Görevler · Bildirimler · Mesajlar · Profil.
// Staff land on the HUB ("Ana Sayfa"), an operations center with the live
// "Bugün" KPI card, a smart notification feed, and permission-filtered
// department shortcuts. The bar is identical for all roles (no approver / line-
// staff branching); "Onaylarım", "Bugün" (digest) and "Arama" stay reachable
// but are hidden from the bar via `href: null` (route + screen remain mounted by
// URL / header shortcut / HUB). Approvers additionally get an "Onaylarım"
// header shortcut. All gating is cosmetic; the backend enforces every action,
// so RBAC is unchanged.
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
        headerRight: () => <HeaderActions showApprovals={showApprovals} />,
      }}
    >
      {/* 5 visible tabs — identical for every staff role. */}
      <Tabs.Screen
        name="index"
        options={{
          title: tr.tabs.home,
          tabBarTestID: 'smoke-tab-home',
          tabBarIcon: tabIcon('home', 'home-outline'),
        }}
      />
      <Tabs.Screen
        name="tasks"
        options={{
          title: tr.tabs.tasks,
          tabBarTestID: 'smoke-tab-tasks',
          tabBarIcon: tabIcon('checkbox', 'checkbox-outline'),
        }}
      />
      <Tabs.Screen
        name="notifications"
        options={{
          title: tr.tabs.notifications,
          tabBarTestID: 'smoke-tab-notifications',
          tabBarIcon: tabIcon('notifications', 'notifications-outline'),
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
        name="profile"
        options={{
          title: tr.tabs.profile,
          tabBarTestID: 'smoke-tab-profile',
          tabBarIcon: tabIcon('person-circle', 'person-circle-outline'),
        }}
      />

      {/* Hidden from the bar (href: null) but still reachable by URL / shortcut.
          Every smoke-tab-* testID is kept so the smoke matrix keeps resolving. */}
      <Tabs.Screen
        name="today"
        options={{
          title: tr.tabs.today,
          href: null,
          tabBarTestID: 'smoke-tab-today',
          tabBarIcon: tabIcon('today', 'today-outline'),
        }}
      />
      <Tabs.Screen
        name="approvals"
        options={{
          title: tr.tabs.approvals,
          href: null,
          tabBarTestID: 'smoke-tab-approvals',
          tabBarIcon: tabIcon('checkmark-done-circle', 'checkmark-done-circle-outline'),
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: tr.tabs.search,
          href: null,
          tabBarTestID: 'smoke-tab-search',
          tabBarIcon: tabIcon('search', 'search-outline'),
        }}
      />
    </Tabs>
  );
}
