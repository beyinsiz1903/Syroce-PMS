import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, Share, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import {
  Badge,
  Body,
  Button,
  Card,
  Field,
  H1,
  H2,
  Muted,
  Skeleton,
} from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { searchBookingByRoom, checkout, getBooking, Booking } from '../../src/api/bookings';
import { Folio, getFolioForBooking, postPayment } from '../../src/api/folio';
import { formatCurrency } from '../../src/utils/format';
import { errorMessage } from '../../src/utils/errors';

export default function CheckoutScreen() {
  const c = useTheme();
  const params = useLocalSearchParams<{ bookingId?: string }>();
  const [roomNo, setRoomNo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [folio, setFolio] = useState<Folio | null>(null);

  useEffect(() => {
    if (params.bookingId) {
      void loadByBookingId(params.bookingId);
    }
  }, [params.bookingId]);

  const loadByBookingId = async (bid: string) => {
    setBusy(true);
    setError(null);
    try {
      const [f, b] = await Promise.all([getFolioForBooking(bid), getBooking(bid)]);
      setFolio(f);
      setBooking(b || ({ id: bid } as Booking));
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
    } finally {
      setBusy(false);
    }
  };

  const onLookup = async () => {
    if (!roomNo) return;
    setBusy(true);
    setError(null);
    try {
      const list = await searchBookingByRoom(roomNo);
      if (!list.length) {
        setError('Oda için aktif rezervasyon bulunamadı');
        haptic.warning();
        return;
      }
      const b = list[0];
      setBooking(b);
      const f = await getFolioForBooking(b.id);
      setFolio(f);
      haptic.success();
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  const onPay = async () => {
    if (!booking || !folio) return;
    const amount = folio.balance || 0;
    if (amount <= 0) return;
    setBusy(true);
    try {
      await postPayment(booking.id, amount, 'cash');
      const f = await getFolioForBooking(booking.id);
      setFolio(f);
      haptic.success();
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  const onCheckout = async () => {
    if (!booking) return;
    setBusy(true);
    try {
      await checkout(booking.id, false);
      haptic.success();
      Alert.alert(tr.app.success, tr.checkout.success);
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  const onShare = async () => {
    if (!folio) return;
    const lines = [
      `Folio ${folio.folio_number || folio.id}`,
      `Oda: ${booking?.room_number || roomNo}`,
      `Bakiye: ${formatCurrency(folio.balance)}`,
      ...(folio.charges || []).map(
        (ch) =>
          `${ch.description || ch.charge_category || 'Charge'}: ${formatCurrency(
            ch.total ?? ch.amount,
          )}`,
      ),
    ];
    try {
      await Share.share({ message: lines.join('\n') });
    } catch {
      // user cancelled
    }
  };

  return (
    <ScrollView
      contentContainerStyle={{
        padding: spacing.lg,
        gap: spacing.md,
        backgroundColor: c.bg,
        flexGrow: 1,
      }}
    >
      <H1>{tr.checkout.title}</H1>

      <Card>
        <Field
          label={tr.checkout.roomNo}
          value={roomNo}
          onChangeText={setRoomNo}
          keyboardType="number-pad"
          returnKeyType="search"
          onSubmitEditing={onLookup}
        />
        <View style={{ height: spacing.sm }} />
        <Button title="Bul" onPress={onLookup} loading={busy} fullWidth />
      </Card>

      {error ? <Body style={{ color: c.danger }}>{error}</Body> : null}

      {busy && !folio ? (
        <Card>
          <Skeleton height={18} width="60%" />
          <View style={{ height: spacing.sm }} />
          <Skeleton height={14} />
          <View style={{ height: spacing.sm }} />
          <Skeleton height={14} width="50%" />
        </Card>
      ) : null}

      {folio ? (
        <Card>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <H2>{tr.checkout.folio}</H2>
            <Badge
              label={`${tr.checkout.balance}: ${formatCurrency(folio.balance)}`}
              tone={(folio.balance || 0) > 0 ? 'warning' : 'success'}
            />
          </View>
          {(folio.charges || []).slice(0, 8).map((ch) => (
            <View
              key={ch.id}
              style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}
            >
              <Muted>{ch.description || ch.charge_category}</Muted>
              <Body>{formatCurrency(ch.total ?? ch.amount)}</Body>
            </View>
          ))}
          {(folio.charges || []).length === 0 ? <Muted>{tr.app.empty}</Muted> : null}
        </Card>
      ) : null}

      {folio && (folio.balance || 0) > 0 ? (
        <Button title={tr.checkout.pay} onPress={onPay} loading={busy} fullWidth />
      ) : null}

      {folio ? (
        <Button title={tr.checkout.share} variant="secondary" onPress={onShare} fullWidth />
      ) : null}

      {booking ? (
        <Button
          title={`${tr.app.confirm} · ${tr.checkout.title}`}
          onPress={onCheckout}
          loading={busy}
          fullWidth
        />
      ) : null}
    </ScrollView>
  );
}
