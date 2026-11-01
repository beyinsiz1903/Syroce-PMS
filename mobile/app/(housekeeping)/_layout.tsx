import React from 'react';
import { MobileRouteGate } from '../../src/components/MobileRouteGate';
import type { ColorValue } from 'react-native';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { OperationalHeader } from '../../src/components/OperationalHeader';
import { useAuthStore } from '../../src/state/authStore';
import { mobileOperationAllowed } from '../../src/state/roleAccess';

type IoniconName = keyof typeof Ionicons.glyphMap;

function tabIcon(active: IoniconName, inactive: IoniconName) {
  return ({ color, focused, size }: { color: ColorValue; focused: boolean; size: number }) => (
    <Ionicons name={focused ? active : inactive} size={size ?? 24} color={color} />
  );
}

export default function HousekeepingLayout() {
  return <MobileRouteGate><HousekeepingLayoutContent /></MobileRouteGate>;
}

function HousekeepingLayoutContent() {
  const c = useTheme();
  const user = useAuthStore((s) => s.user);
  const insets = useSafeAreaInsets();
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
        options={{ title: tr.tabs.rooms, tabBarIcon: tabIcon('bed', 'bed-outline') }}
      />
      <Tabs.Screen
        name="damage"
        options={{ href: mobileOperationAllowed(user, 'update_room_status') ? undefined : null, title: tr.tabs.damage, tabBarIcon: tabIcon('construct', 'construct-outline') }}
      />
      <Tabs.Screen
        name="more"
        options={{
          title: tr.tabs.settings,
          tabBarLabel: tr.tabs.more,
          tabBarIcon: tabIcon('ellipsis-horizontal-circle', 'ellipsis-horizontal-circle-outline'),
        }}
      />
    </Tabs>
  );
}
