import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';

type IoniconName = keyof typeof Ionicons.glyphMap;

// Build a focused/unfocused Ionicon pair into a Tabs `tabBarIcon` render-prop.
// Icons make the bottom-tab backbone scannable at a glance (icon + label),
// matching the (home) shell. Titles/names/testIDs are untouched so the smoke
// matrix keeps resolving every tab.
function tabIcon(active: IoniconName, inactive: IoniconName) {
  return ({ color, focused, size }: { color: string; focused: boolean; size: number }) => (
    <Ionicons name={focused ? active : inactive} size={size ?? 24} color={color} />
  );
}

export default function FrontDeskLayout() {
  const c = useTheme();
  const insets = useSafeAreaInsets();
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
        headerTintColor: c.text,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: tr.tabs.today, tabBarIcon: tabIcon('today', 'today-outline') }}
      />
      <Tabs.Screen
        name="reservations"
        options={{
          title: tr.reservations.title,
          tabBarIcon: tabIcon('calendar', 'calendar-outline'),
        }}
      />
      <Tabs.Screen
        name="availability"
        options={{ title: tr.availability.title, tabBarIcon: tabIcon('grid', 'grid-outline') }}
      />
      <Tabs.Screen
        name="guests"
        options={{ title: tr.tabs.guests, tabBarIcon: tabIcon('people', 'people-outline') }}
      />
      <Tabs.Screen
        name="more"
        options={{
          title: tr.tabs.more,
          tabBarIcon: tabIcon('ellipsis-horizontal-circle', 'ellipsis-horizontal-circle-outline'),
        }}
      />
      <Tabs.Screen name="checkin" options={{ href: null, title: tr.checkin.title }} />
      <Tabs.Screen name="checkout" options={{ href: null, title: tr.checkout.title }} />
      <Tabs.Screen name="walkin" options={{ href: null, title: tr.walkin.title }} />
      <Tabs.Screen name="reservation" options={{ href: null, title: tr.reservations.detailTitle }} />
    </Tabs>
  );
}
