import React, { useMemo } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Button, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getRoomServiceMenu, MenuItem } from '../../src/api/guestRoomService';
import { getGuestBookings } from '../../src/api/guestBookings';
import { useCartStore } from '../../src/state/cartStore';
import { formatCurrency } from '../../src/utils/format';
import { ROUTES } from '../../src/navigation/routes';
import { haptic } from '../../src/hooks/useHaptic';

export default function RoomServiceScreen() {
  const c = useTheme();
  const router = useRouter();
  const menuQ = useQuery({ queryKey: ['room-service-menu'], queryFn: getRoomServiceMenu });
  const bookingsQ = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });
  const { add, count, total } = useCartStore();

  const activeCheckedIn = useMemo(
    () => (bookingsQ.data?.active_bookings || []).find((b) => b.status === 'checked_in'),
    [bookingsQ.data],
  );

  const onAdd = (item: MenuItem) => {
    add(item);
    haptic.tap();
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 140 }}
      >
        <H1>{tr.guest.roomServiceTitle}</H1>

        {!activeCheckedIn ? (
          <Card>
            <Muted>{tr.guest.selectActiveBooking}</Muted>
          </Card>
        ) : null}

        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <Button
            title={tr.guest.orderHistory}
            variant="ghost"
            onPress={() => router.push(ROUTES.guestOrders)}
          />
        </View>

        {menuQ.isLoading ? (
          <SkeletonCard />
        ) : (menuQ.data?.categories || []).length === 0 ? (
          <Card>
            <Muted>{tr.app.empty}</Muted>
          </Card>
        ) : (
          (menuQ.data?.categories || []).map((cat) => (
            <View key={cat.name} style={{ gap: spacing.sm }}>
              <H2>{cat.name}</H2>
              {cat.items.map((it) => (
                <Pressable
                  key={it.id}
                  onPress={() => onAdd(it)}
                  accessibilityRole="button"
                  accessibilityLabel={`${it.name}, ${formatCurrency(it.price)}`}
                  style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
                >
                  <Card>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <View style={{ flex: 1 }}>
                        <Body style={{ fontWeight: '600' }}>{it.name}</Body>
                        {it.description ? <Muted>{it.description}</Muted> : null}
                      </View>
                      <View style={{ alignItems: 'flex-end' }}>
                        <Body style={{ color: c.text, fontWeight: '600' }}>
                          {formatCurrency(it.price)}
                        </Body>
                        <Badge label={tr.guest.addToCart} tone="primary" />
                      </View>
                    </View>
                  </Card>
                </Pressable>
              ))}
            </View>
          ))
        )}
      </ScrollView>

      {count() > 0 ? (
        <View
          style={{
            position: 'absolute',
            left: spacing.lg,
            right: spacing.lg,
            bottom: spacing.lg,
          }}
        >
          <Button
            title={`${tr.guest.cart} (${count()}) · ${formatCurrency(total())}`}
            onPress={() => router.push(ROUTES.guestCart)}
            fullWidth
          />
        </View>
      ) : null}
    </View>
  );
}
