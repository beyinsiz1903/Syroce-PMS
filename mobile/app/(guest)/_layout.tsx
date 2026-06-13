import React from 'react';
import { Tabs } from 'expo-router';
import { useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { HeaderBackButton } from '../../src/components/HeaderBackButton';
import { ROUTES } from '../../src/navigation/routes';

// `href:null` ekranlar Tabs altinda router.push ile acilir; Tabs header'i geri
// oku cizmez, bu yuzden detay sayfalari icin headerLeft'e ozel geri butonu
// takiyoruz (gecmis yoksa guest ana ekranina doner).
const backOptions = { headerLeft: () => <HeaderBackButton fallback={ROUTES.guest} /> };

export default function GuestLayout() {
  const c = useTheme();
  return (
    <Tabs
      screenOptions={{
        tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.border },
        tabBarActiveTintColor: c.primary,
        tabBarInactiveTintColor: c.textMuted,
        tabBarLabelStyle: { fontSize: 11 },
        headerStyle: { backgroundColor: c.surface },
        headerTitleStyle: { color: c.text },
        headerTintColor: c.text,
      }}
    >
      <Tabs.Screen name="index" options={{ title: tr.tabs.bookings }} />
      <Tabs.Screen name="checkin" options={{ title: tr.tabs.onlineCheckin }} />
      <Tabs.Screen name="roomservice" options={{ title: tr.tabs.roomService }} />
      <Tabs.Screen name="messages" options={{ title: tr.tabs.messages }} />
      <Tabs.Screen name="loyalty" options={{ title: tr.tabs.loyalty }} />
      <Tabs.Screen name="qrBadge" options={{ title: tr.tabs.qrBadge }} />
      <Tabs.Screen name="more" options={{ href: null, title: tr.more.profile, ...backOptions }} />
      <Tabs.Screen
        name="booking"
        options={{ href: null, title: tr.guest.bookingDetail, ...backOptions }}
      />
      <Tabs.Screen name="cart" options={{ href: null, title: tr.guest.cart, ...backOptions }} />
      <Tabs.Screen
        name="orders"
        options={{ href: null, title: tr.guest.orderHistory, ...backOptions }}
      />
      <Tabs.Screen
        name="earlylate"
        options={{ href: null, title: tr.guest.earlyLateTitle, ...backOptions }}
      />
      <Tabs.Screen
        name="messageThread"
        options={{ href: null, title: tr.guest.messagesTitle, ...backOptions }}
      />
      <Tabs.Screen
        name="digitalKey"
        options={{ href: null, title: tr.guest.digitalKeyTitle, ...backOptions }}
      />
    </Tabs>
  );
}
