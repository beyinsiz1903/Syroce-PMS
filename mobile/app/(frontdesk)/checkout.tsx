import React, { useEffect, useState } from 'react';
import { ScrollView, Share, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import {
  ActionButton,
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  Field,
  H1,
  H2,
  Muted,
  SegmentedActions,
  Skeleton,
  webCenter,
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
  const router = useRouter();
  const params = useLocalSearchParams<{ bookingId?: string }>();
  const [roomNo, setRoomNo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [folio, setFolio] = useState<Folio | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState(false);

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
        setError(tr.checkout.notFound);
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

  // Inline two-step confirm (NOT Alert.alert — a no-op on Expo Web). Tapping
  // "Çıkış yap" reveals an inline confirm row; tapping "Evet, çıkış yap" fires.
  const onCheckoutPress = () => {
    if (!booking) return;
    haptic.tap();
    setError(null);
    setConfirming((v) => !v);
  };

  const onCheckoutConfirm = async () => {
    if (!booking) return;
    setBusy(true);
    try {
      await checkout(booking.id, false);
      haptic.success();
      setConfirming(false);
      setDone(true);
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
      `${tr.checkout.folio} ${folio.folio_number || folio.id}`,
      `${tr.checkout.room}: ${booking?.room_number || roomNo}`,
      `${tr.checkout.balance}: ${formatCurrency(folio.balance)}`,
      ...(folio.charges || []).map(
        (ch) =>
          `${ch.description || ch.charge_category || tr.checkout.charge}: ${formatCurrency(
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

  const resetForNext = () => {
    setDone(false);
    setBooking(null);
    setFolio(null);
    setRoomNo('');
    setError(null);
  };

  if (done) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <View style={[{ flex: 1, padding: spacing.lg, justifyContent: 'center' }, webCenter]}>
          <EmptyState
            icon="checkmark-circle"
            title={tr.checkout.success}
            message={tr.checkout.successHint}
            action={
              <View style={{ gap: spacing.sm, alignItems: 'stretch' }}>
                <Button title={tr.checkout.newCheckout} icon="refresh" variant="secondary" onPress={resetForNext} />
                <Button title={tr.checkout.done} icon="arrow-back" onPress={() => router.back()} />
              </View>
            }
          />
        </View>
      </View>
    );
  }

  const balanceDue = (folio?.balance || 0) > 0;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[
        {
          padding: spacing.lg,
          gap: spacing.md,
          flexGrow: 1,
        },
        webCenter,
      ]}
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
        <Button title={tr.checkout.lookup} icon="search" onPress={onLookup} loading={busy} fullWidth />
      </Card>

      {error ? (
        <Card accent={c.danger}>
          <Body style={{ color: c.danger }}>{error}</Body>
        </Card>
      ) : null}

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
        <Card accent={balanceDue ? c.warning : c.success}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <H2>{tr.checkout.folio}</H2>
            <Badge
              label={`${tr.checkout.balance}: ${formatCurrency(folio.balance)}`}
              tone={balanceDue ? 'warning' : 'success'}
            />
          </View>
          <Muted style={{ marginTop: spacing.xs }}>{tr.checkout.folioNote}</Muted>
          <View style={{ height: spacing.sm }} />
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

      {folio && balanceDue ? (
        <Button title={tr.checkout.pay} icon="cash-outline" variant="secondary" onPress={onPay} loading={busy} fullWidth />
      ) : null}

      {folio ? (
        <Button title={tr.checkout.share} icon="share-outline" variant="outline" onPress={onShare} fullWidth />
      ) : null}

      {booking ? (
        confirming ? (
          <View style={{ gap: spacing.sm }}>
            <Muted>{tr.checkout.confirmTitle}</Muted>
            <SegmentedActions>
              <ActionButton
                label={tr.app.cancel}
                icon="arrow-undo"
                onPress={() => setConfirming(false)}
                bg={c.surfaceAlt}
                fg={c.text}
                disabled={busy}
              />
              <ActionButton
                label={tr.checkout.confirmYes}
                icon="exit-outline"
                onPress={onCheckoutConfirm}
                bg={c.success}
                fg="#ffffff"
                loading={busy}
              />
            </SegmentedActions>
          </View>
        ) : (
          <Button
            title={`${tr.app.confirm} · ${tr.checkout.title}`}
            icon="exit-outline"
            variant="success"
            onPress={onCheckoutPress}
            loading={busy}
            fullWidth
          />
        )
      ) : null}
    </ScrollView>
  );
}
