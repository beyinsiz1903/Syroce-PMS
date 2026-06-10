import React from 'react';
import { Tabs } from 'expo-router';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';

export default function FrontDeskLayout() {
  const c = useTheme();
  return (
    <Tabs
      screenOptions={{
        tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.border },
        tabBarActiveTintColor: c.primary,
        tabBarInactiveTintColor: c.textMuted,
        headerStyle: { backgroundColor: c.surface },
        headerTitleStyle: { color: c.text },
        headerTintColor: c.text,
      }}
    >
      <Tabs.Screen name="index" options={{ title: tr.tabs.today }} />
      <Tabs.Screen name="reservations" options={{ title: tr.reservations.title }} />
      <Tabs.Screen name="availability" options={{ title: tr.availability.title }} />
      <Tabs.Screen name="guests" options={{ title: tr.tabs.guests }} />
      <Tabs.Screen name="more" options={{ title: tr.tabs.more }} />
      <Tabs.Screen name="checkin" options={{ href: null, title: tr.checkin.title }} />
      <Tabs.Screen name="checkout" options={{ href: null, title: tr.checkout.title }} />
      <Tabs.Screen name="walkin" options={{ href: null, title: tr.walkin.title }} />
      <Tabs.Screen name="reservation" options={{ href: null, title: tr.reservations.detailTitle }} />
    </Tabs>
  );
}
