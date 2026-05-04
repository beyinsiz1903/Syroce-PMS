import React, { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Body, Button, Card, Field, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useCartStore } from '../../src/state/cartStore';
import { getGuestBookings } from '../../src/api/guestBookings';
import { createRoomServiceOrder } from '../../src/api/guestRoomService';
import { formatCurrency } from '../../src/utils/format';
import { errorMessage } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';
import { ROUTES } from '../../src/navigation/routes';

export default function CartScreen() {
  const c = useTheme();
  const router = useRouter();
  const { lines, setQty, remove, total, clear } = useCartStore();
  const bookingsQ = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeBooking = useMemo(
    () => (bookingsQ.data?.active_bookings || []).find((b) => b.status === 'checked_in'),
    [bookingsQ.data],
  );

  const onPlace = async () => {
    if (!activeBooking) {
      setError(tr.guest.selectActiveBooking);
      return;
    }
    if (lines.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await createRoomServiceOrder(
        activeBooking.id,
        lines.map((l) => ({ id: l.itemId, name: l.name, price: l.price, quantity: l.quantity })),
        notes || undefined,
      );
      haptic.success();
      clear();
      Alert.alert(tr.app.success, tr.guest.orderPlaced, [
        {
          text: tr.app.close,
          onPress: () => router.replace(ROUTES.guestOrders),
        },
      ]);
    } catch (e) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
    >
      <H1>{tr.guest.cart}</H1>
      {lines.length === 0 ? (
        <Card>
          <Muted>{tr.guest.cartEmpty}</Muted>
        </Card>
      ) : (
        lines.map((l) => (
          <Card key={l.itemId}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
              <View style={{ flex: 1 }}>
                <Body style={{ fontWeight: '600' }}>{l.name}</Body>
                <Muted>{formatCurrency(l.price)}</Muted>
              </View>
              <View
                style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}
              >
                <Pressable
                  onPress={() => setQty(l.itemId, l.quantity - 1)}
                  accessibilityRole="button"
                  accessibilityLabel="Azalt"
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 18,
                    borderWidth: 1,
                    borderColor: c.border,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Body>−</Body>
                </Pressable>
                <Body style={{ minWidth: 24, textAlign: 'center' }}>{l.quantity}</Body>
                <Pressable
                  onPress={() => setQty(l.itemId, l.quantity + 1)}
                  accessibilityRole="button"
                  accessibilityLabel="Arttır"
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 18,
                    borderWidth: 1,
                    borderColor: c.border,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Body>+</Body>
                </Pressable>
              </View>
            </View>
            <View style={{ marginTop: spacing.sm, alignItems: 'flex-end' }}>
              <Pressable onPress={() => remove(l.itemId)} accessibilityRole="button">
                <Muted style={{ color: c.danger }}>Kaldır</Muted>
              </Pressable>
            </View>
          </Card>
        ))
      )}

      {lines.length > 0 ? (
        <Card>
          <H2>{tr.guest.orderInstructions}</H2>
          <Field
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={3}
            placeholder="Örn: alerji, soğuk içecek tercihi..."
          />
        </Card>
      ) : null}

      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <H2>{tr.guest.orderTotal}</H2>
          <H2>{formatCurrency(total())}</H2>
        </View>
      </Card>

      {error ? <Body style={{ color: c.danger }}>{error}</Body> : null}

      <Button
        title={tr.guest.placeOrder}
        onPress={onPlace}
        loading={busy}
        disabled={lines.length === 0 || !activeBooking}
        fullWidth
      />
    </ScrollView>
  );
}
