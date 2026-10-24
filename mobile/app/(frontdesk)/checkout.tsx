import React, { useCallback, useRef, useState } from 'react';
import { ScrollView, Share, View } from 'react-native';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import {
  ActionButton,
  Badge,
  Body,
  Button,
  Card,
  DetailHeader,
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
import { searchBookingByRoom, checkout } from '../../src/api/bookings';
import { getReservationFullDetail, ReservationFullDetail } from '../../src/api/reservations';
import { formatDate } from '../../src/utils/format';
import { errorMessage } from '../../src/utils/errors';
import { ROUTES } from '../../src/navigation/routes';
import { reservationAmountLabel, reservationCurrency, reservationMoneySummary, reservationStatusLabel, reservationStatusTone } from '../../src/utils/reservationPresentation';

export default function CheckoutScreen() {
  const c = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ bookingId?: string }>();
  const [roomNo, setRoomNo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReservationFullDetail | null>(null);
  const booking = detail?.booking;
  const currency = reservationCurrency(booking?.currency);
  const money = reservationMoneySummary({ summaryTotal: detail?.summary?.gross_total, summaryBalance: detail?.summary?.reservation_total_due, bookingTotal: booking?.total_amount, bookingCollected: booking?.collected_amount, bookingBalance: booking?.balance, payments: detail?.payments, currency });
  const amountLabel = (value: unknown) => reservationAmountLabel(value, currency);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState(false);
  const requestVersion = useRef(0);
  const selectedBookingId = useRef<string | undefined>(params.bookingId);

  useFocusEffect(useCallback(() => {
    const id = params.bookingId || selectedBookingId.current;
    if (id) void loadByBookingId(id);
    return () => { requestVersion.current += 1; };
  }, [params.bookingId]));

  const loadByBookingId = async (bid: string) => {
    const version = ++requestVersion.current;
    setBusy(true);
    setError(null);
    setDetail(null);
    setConfirming(false);
    selectedBookingId.current = bid;
    try {
      const result = await getReservationFullDetail(bid);
      if (version !== requestVersion.current) return;
      if (!result) throw new Error(tr.checkout.notFound);
      setDetail(result);
      selectedBookingId.current = bid;
    } catch (e: unknown) {
      if (version === requestVersion.current) setError(errorMessage(e, tr.reservations.detailError));
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  };

  const onLookup = async () => {
    if (!roomNo.trim() || busy) return;
    const version = ++requestVersion.current;
    setBusy(true);
    setError(null);
    setDetail(null);
    selectedBookingId.current = undefined;
    setConfirming(false);
    try {
      const list = await searchBookingByRoom(roomNo);
      if (version !== requestVersion.current) return;
      if (!list.length) {
        setError(tr.checkout.notFound);
        haptic.warning();
        return;
      }
      if (list.length > 1) throw new Error(tr.reservations.roomAmbiguous);
      const b = list[0];
      selectedBookingId.current = b.id;
      const result = await getReservationFullDetail(b.id);
      if (version !== requestVersion.current) return;
      if (!result) throw new Error(tr.checkout.notFound);
      setDetail(result);
      selectedBookingId.current = b.id;
      haptic.success();
    } catch (e: unknown) {
      if (version === requestVersion.current) setError(errorMessage(e, tr.reservations.detailError));
      haptic.error();
    } finally {
      if (version === requestVersion.current) setBusy(false);
    }
  };

  const onPay = () => {
    if (!booking) return;
    router.push({ pathname: ROUTES.reservationDetail, params: { id: booking.id, panel: 'payment' } });
  };

  // Inline two-step confirm (NOT Alert.alert — a no-op on Expo Web). Tapping
  // "Çıkış yap" reveals an inline confirm row; tapping "Evet, çıkış yap" fires.
  const onCheckoutPress = () => {
    if (!booking || !detail || detail.read_only || money.balance === undefined || busy) return;
    haptic.tap();
    setError(null);
    setConfirming((v) => !v);
  };

  const onCheckoutConfirm = async () => {
    if (!booking || !detail || detail.read_only || money.balance === undefined || busy) return;
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
    if (!detail) return;
    const lines = [
      `${tr.reservations.accountSummary} ${booking?.booking_number || ''}`,
      `${tr.checkout.room}: ${booking?.room_number || roomNo}`,
      `${tr.reservations.reservationTotal}: ${amountLabel(money.total)}`,
      `${tr.reservations.collectedTotal}: ${amountLabel(money.paid)}`,
      `${tr.checkout.balance}: ${amountLabel(money.balance)}`,
      ...(detail.charges || []).filter((charge) => !charge.voided).map(
        (ch) =>
          `${ch.description || ch.charge_category || tr.checkout.charge}: ${reservationAmountLabel(
            ch.total ?? ch.amount,
            ch.currency || currency,
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
    requestVersion.current += 1;
    setDetail(null);
    selectedBookingId.current = undefined;
    setConfirming(false);
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

  const balanceDue = money.balance !== undefined && money.balance > 0;

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
        <Card accent={c.danger} testID="checkout-error">
          <Body style={{ color: c.danger }}>{error}</Body>
          <Button title={tr.app.retry} testID="checkout-retry" variant="secondary" disabled={busy} onPress={() => {
            // Retry only the read. Never automatically replay check-out or a
            // payment mutation whose outcome might be unknown after a timeout.
            if (selectedBookingId.current) void loadByBookingId(selectedBookingId.current);
            else void onLookup();
          }} fullWidth />
        </Card>
      ) : null}

      {busy && !detail ? (
        <Card>
          <Skeleton height={18} width="60%" />
          <View style={{ height: spacing.sm }} />
          <Skeleton height={14} />
          <View style={{ height: spacing.sm }} />
          <Skeleton height={14} width="50%" />
        </Card>
      ) : null}

      {detail ? (
        <Card accent={balanceDue ? c.warning : c.primary}>
          <DetailHeader title={detail.guest?.name || booking?.guest_name || tr.reservations.guest} subtitle={`${tr.checkout.room} ${detail.room?.room_number || booking?.room_number || '—'}`} badges={<Badge label={reservationStatusLabel(booking?.status)} tone={reservationStatusTone(booking?.status)} />} />
          <Muted style={{ marginTop: spacing.xs }}>{formatDate(booking?.check_in)} → {formatDate(booking?.check_out)}</Muted>
          <H2 style={{ marginTop: spacing.lg }}>{tr.reservations.accountSummary}</H2>
          <Muted style={{ marginTop: spacing.md }}>{tr.reservations.reservationTotal}</Muted>
          <Body testID="checkout-account-total" style={{ fontWeight: '700' }}>{amountLabel(money.total)}</Body>
          <Muted style={{ marginTop: spacing.md }}>{tr.reservations.collectedTotal}</Muted>
          <Body testID="checkout-account-collected" style={{ fontWeight: '700' }}>{amountLabel(money.paid)}</Body>
          <Muted style={{ marginTop: spacing.md }}>{tr.reservations.reservationBalance}</Muted>
          <Body testID="checkout-account-balance" style={{ fontSize: 28, lineHeight: 36, fontWeight: '800', color: balanceDue ? c.warning : c.text }}>{amountLabel(money.balance)}</Body>
          {detail.read_only ? <Muted style={{ marginTop: spacing.sm }}>{tr.reservations.readOnly}</Muted> : null}
          <View style={{ height: spacing.sm }} />
          {(detail.charges || []).filter((ch) => !ch.voided).slice(0, 8).map((ch) => (
            <View
              key={ch.id}
              style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md, paddingVertical: 4 }}
            >
              <Muted style={{ flex: 1 }}>{ch.description || ch.charge_category}</Muted>
              <Body>{reservationAmountLabel(ch.total ?? ch.amount, ch.currency || currency)}</Body>
            </View>
          ))}
          {Array.isArray(detail.charges) && detail.charges.length === 0 ? <Muted>{tr.reservations.noPostedCharges}</Muted> : null}
        </Card>
      ) : null}

      {detail && balanceDue && !detail.read_only ? (
        <Button title={tr.checkout.pay} icon="cash-outline" variant="secondary" onPress={onPay} loading={busy} fullWidth />
      ) : null}

      {detail ? (
        <Button title={tr.reservations.shareAccountSummary} icon="share-outline" variant="outline" onPress={onShare} fullWidth />
      ) : null}

      {booking && !detail?.read_only ? (
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
                disabled={money.balance === undefined}
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
            disabled={money.balance === undefined}
            fullWidth
          />
        )
      ) : null}
    </ScrollView>
  );
}
