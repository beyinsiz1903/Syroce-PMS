import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  H1,
  H2,
  Muted,
  SkeletonCard,
  webCenter,
} from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getRoomServiceMenu, MenuItem } from '../../src/api/guestRoomService';
import { getGuestBookings } from '../../src/api/guestBookings';
import { useCartStore } from '../../src/state/cartStore';
import { formatCurrency } from '../../src/utils/format';
import { ROUTES } from '../../src/navigation/routes';
import { haptic } from '../../src/hooks/useHaptic';
import { errorMessage } from '../../src/utils/errors';

export default function RoomServiceScreen() {
  const c = useTheme();
  const router = useRouter();
  const bookingsQ = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });
  const { add, count, total, lines, locked, bookingId, bindBooking } = useCartStore();
  const [cartError, setCartError] = useState<string | null>(null);

  const activeCheckedIn = useMemo(
    () => {
      const stays = (bookingsQ.data?.active_bookings || []).filter(b => b.status === 'checked_in');
      return stays.find(b => b.id === bookingId) || (stays.length === 1 ? stays[0] : undefined);
    },
    [bookingsQ.data, bookingId],
  );
  const menuQ = useQuery({ queryKey: ['room-service-menu', activeCheckedIn?.id], queryFn: () => getRoomServiceMenu(activeCheckedIn?.id), enabled: Boolean(activeCheckedIn) });

  const onAdd = (item: MenuItem) => {
    try {
      if (!activeCheckedIn) throw new Error(tr.guest.selectActiveBooking);
      bindBooking(activeCheckedIn.id); add(item); setCartError(null); haptic.tap();
    } catch (e) { setCartError(errorMessage(e, tr.errors.generic)); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, paddingBottom: 140 }, webCenter]}
      >
        <H1>{tr.guest.roomServiceTitle}</H1>
        <Muted>{tr.guest.roomServiceIntro}</Muted>
        {(bookingsQ.data?.active_bookings || []).filter(b => b.status === 'checked_in').map(stay => <Button key={stay.id} title={`Konaklama: ${stay.room?.room_number || stay.confirmation_number || 'Oda bilgisi yok'}`} disabled={locked} variant={activeCheckedIn?.id === stay.id ? 'primary' : 'outline'} onPress={() => { try { bindBooking(stay.id); } catch (e) { setCartError(errorMessage(e, tr.errors.generic)); } }} />)}
        {cartError ? <Body style={{ color: c.danger }}>{cartError}</Body> : null}
        {locked ? <Muted>Siparişin sonucu kontrol ediliyor; sepet değiştirilemez. Sipariş geçmişinden doğrulayın.</Muted> : null}

        {!activeCheckedIn ? (
          <Card accent={c.warning}>
            <Body style={{ fontWeight: '600' }}>{tr.guest.selectActiveBookingTitle}</Body>
            <Muted style={{ marginTop: spacing.xs }}>{tr.guest.selectActiveBooking}</Muted>
          </Card>
        ) : null}

        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <Button
            title={tr.guest.orderHistory}
            variant="ghost"
            icon="receipt-outline"
            onPress={() => router.push(ROUTES.guestOrders)}
          />
        </View>

        {menuQ.isLoading ? (
          <SkeletonCard />
        ) : menuQ.isError ? (
          <Card accent={c.danger}>
            <Body style={{ fontWeight: '600' }}>
              {errorMessage(menuQ.error, tr.guest.menuLoadError)}
            </Body>
            <View style={{ height: spacing.sm }} />
            <Button
              title={tr.app.retry}
              icon="refresh"
              variant="outline"
              onPress={() => menuQ.refetch()}
            />
          </Card>
        ) : (menuQ.data?.categories || []).length === 0 ? (
          <Card padded={false}>
            <EmptyState
              icon="restaurant-outline"
              title={tr.guest.menuEmptyTitle}
              message={tr.guest.menuEmptyMessage}
            />
          </Card>
        ) : (
          (menuQ.data?.categories || []).map((cat) => (
            <View key={cat.name} style={{ gap: spacing.sm }}>
              <H2>{cat.name}</H2>
              {cat.items.map((it) => (
                <Pressable
                  key={it.id}
                  disabled={locked || !it.currency}
                  onPress={() => onAdd(it)}
                  accessibilityRole="button"
                  accessibilityLabel={`${it.name}, ${it.currency ? formatCurrency(it.price, it.currency) : 'Para birimi bilinmiyor'}`}
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
                          {it.currency ? formatCurrency(it.price, it.currency) : 'Para birimi bilinmiyor'}
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
            left: 0,
            right: 0,
            bottom: spacing.lg,
            paddingHorizontal: spacing.lg,
            alignItems: 'center',
          }}
        >
          <View style={[{ width: '100%' }, webCenter]}>
            <Button
              title={`${tr.guest.cart} (${count()}) · ${formatCurrency(total(), lines[0]?.currency)}`}
              onPress={() => router.push(ROUTES.guestCart)}
              fullWidth
            />
          </View>
        </View>
      ) : null}
    </View>
  );
}
