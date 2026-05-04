import React from 'react';
import { Tabs } from 'expo-router';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';

export default function GuestLayout() {
  const c = useTheme();
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
      <Tabs.Screen name="index" options={{ title: tr.tabs.home }} />
      <Tabs.Screen name="more" options={{ title: tr.tabs.more }} />
    </Tabs>
  );
}
