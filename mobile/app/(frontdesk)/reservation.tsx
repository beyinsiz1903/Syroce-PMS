import React, { useEffect, useRef, useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionButton,
  Badge,
  Body,
  Button,
  Card,
  DetailHeader,
  Divider,
  Field,
  H2,
  Muted,
  SegmentedActions,
  SkeletonCard,
  webCenter,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { invalidateRoomOccupancy } from '../../src/cache/roomOccupancy';
import { useAuthStore } from '../../src/state/authStore';
import { mobileOperationAllowed } from '../../src/state/roleAccess';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  cancelReservation,
  getReservationDetailsEnhanced,
  getReservationOtaDetails,
  getReservationFullDetail,
  overrideRate,
  ReservationUpdate,
  updateReservation,
} from '../../src/api/reservations';
import { assignRoom } from '../../src/api/bookings';
import { getAvailability, AvailabilityRoom } from '../../src/api/availability';
import { roomPanelView } from '../../src/utils/availabilityFilters';
import { formatDate } from '../../src/utils/format';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';
import { postBookingPayment } from '../../src/api/folio';
import { reservationDateInput as toISODate, reservationGuestCount, reservationRateInput } from '../../src/utils/reservationEntry';
import {
  SIMPLE_PAYMENT_METHODS,
  parsePaymentAmount,
  paymentAmountError,
  paymentAttemptForInput,
  type PaymentAttempt,
  type SimplePaymentMethod,
} from '../../src/utils/paymentEntry';
import {
  reservationMoneySummary,
  reservationStatusLabel,
  reservationStatusTone,
  reservationAmountLabel,
  reservationCurrency,
  reservationSourceLabel,
  paymentMethodLabel as movementMethodLabel,
  paymentStatusLabel,
  hasSeparatePayer,
} from '../../src/utils/reservationPresentation';

// ISO string → DD.MM.YYYY for prefilling the edit fields.
function toDisplayDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${d.getFullYear()}`;
}

function Row({ label, value }: { label: string; value?: string | number | null }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md, paddingVertical: spacing.xs }}>
      <Muted style={{ flexShrink: 1 }}>{label}</Muted>
      <Body style={{ textAlign: 'right', flexShrink: 1 }}>{value}</Body>
    </View>
  );
}

export default function ReservationDetailScreen() {
  const c = useTheme();
  const p = useLocalSearchParams<{
    id: string;
    guest_name?: string;
    room_number?: string;
    room_type?: string;
    check_in?: string;
    check_out?: string;
    status?: string;
    total_amount?: string;
    paid_amount?: string;
    balance?: string;
    guest_phone?: string;
    guest_email?: string;
    booking_number?: string;
    panel?: string;
  }>();

  const id = String(p.id || '');

  const enhanced = useQuery({
    queryKey: ['reservation-enhanced', id],
    queryFn: () => getReservationDetailsEnhanced(id),
    enabled: !!id,
  });
  const ota = useQuery({
    queryKey: ['reservation-ota', id],
    queryFn: () => getReservationOtaDetails(id),
    enabled: !!id,
  });
  const detail = useQuery({
    queryKey: ['reservation-full', id],
    queryFn: () => getReservationFullDetail(id),
    enabled: !!id,
  });

  const offline =
    detail.fetchStatus === 'paused' ||
    (enhanced.isError && isOffline(enhanced.error)) ||
    (ota.isError && isOffline(ota.error)) ||
    (detail.isError && isOffline(detail.error));

  const booking = detail.data?.booking;
  const guest = detail.data?.guest;
  const guestName = guest?.name || [guest?.first_name, guest?.last_name].filter(Boolean).join(' ') || booking?.guest_name || p.guest_name;
  const roomNumber = detail.data?.room?.room_number || booking?.room_number || p.room_number;
  const roomType = detail.data?.room?.room_type || booking?.room_type || p.room_type;
  const stayCheckIn = booking?.check_in || p.check_in;
  const stayCheckOut = booking?.check_out || p.check_out;
  const currency = reservationCurrency(booking?.currency);
  const amountLabel = (value: unknown) => reservationAmountLabel(value, currency);

  const rate = enhanced.data?.rate_breakdown;
  const commission = enhanced.data?.commission;
  const policy = enhanced.data?.cancellation_policy;
  const otaData = ota.data;
  const currentStatus = booking?.status || enhanced.data?.status || p.status;
  const source = booking?.ota_channel || booking?.source_channel || booking?.channel || booking?.booking_source || booking?.source || otaData?.ota_channel || otaData?.source_of_booking;
  const separatePayer = hasSeparatePayer({ ...booking, payment_model: booking?.payment_model || otaData?.payment_model || undefined, folios: detail.data?.folios });
  const readOnly = detail.data?.read_only === true;
  const pricingIssue = detail.data?.summary?.pricing_reconciliation_required === true;
  const user = useAuthStore((s) => s.user);
  const canOperate = !!booking && detail.isSuccess && !detail.isFetching && !readOnly && !offline;
  const canManage = canOperate && mobileOperationAllowed(user, 'edit_booking');
  const canOverrideRate = canManage && mobileOperationAllowed(user, 'override_rate');
  const money = reservationMoneySummary({
    summaryTotal: detail.data?.summary?.gross_total,
    summaryBalance: detail.data?.summary?.reservation_total_due,
    bookingTotal: booking?.total_amount ?? p.total_amount,
    bookingCollected: booking?.collected_amount,
    bookingBalance: booking?.balance,
    rateTotal: rate?.total_amount,
    charges: detail.data?.charges,
    payments: detail.data?.payments,
    currency,
  });
  const canTakePayment = canOperate && !['cancelled', 'canceled'].includes((currentStatus || '').toLowerCase()) && mobileOperationAllowed(user, 'post_payment') && !separatePayer && !pricingIssue && !!currency && money.balance !== undefined && money.balance > 0;

  const qc = useQueryClient();

  // Which inline action panel is open ('' = none). Only one at a time keeps the
  // detail screen readable on a phone.
  const [panel, setPanel] = useState<'' | 'dates' | 'room' | 'rate' | 'guests' | 'payment'>(p.panel === 'payment' ? 'payment' : '');
  const [actionError, setActionError] = useState<string | null>(null);
  // Inline success banner (NOT Alert.alert — a no-op on Expo Web). Cleared when
  // a new panel opens or another action starts.
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  // Inline two-step cancel confirm (Alert-based confirm is broken on web).
  const [cancelConfirming, setCancelConfirming] = useState(false);

  const [checkIn, setCheckIn] = useState(toDisplayDate(p.check_in));
  const [checkOut, setCheckOut] = useState(toDisplayDate(p.check_out));
  const [newRate, setNewRate] = useState(p.total_amount || '');
  const [reason, setReason] = useState('');
  const [rooms, setRooms] = useState<AvailabilityRoom[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [roomsError, setRoomsError] = useState<string | null>(null);
  const [roomsRetry, setRoomsRetry] = useState(0);
  const [adults, setAdults] = useState('');
  const [children, setChildren] = useState('');
  const [specialRequests, setSpecialRequests] = useState('');
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<SimplePaymentMethod>('card');
  const paymentAttempt = useRef<PaymentAttempt | null>(null);
  const paymentIssue = paymentAmountError(parsePaymentAmount(paymentAmount), money.balance);
  // Room-change availability window. Defaults to the reservation's own dates
  // but the operator can edit it to check a different window without first
  // saving a date change.
  const [roomCheckIn, setRoomCheckIn] = useState(toDisplayDate(p.check_in));
  const [roomCheckOut, setRoomCheckOut] = useState(toDisplayDate(p.check_out));
  const roomDatesValid = (() => {
    const ci = toISODate(roomCheckIn);
    const co = toISODate(roomCheckOut);
    return !!ci && !!co && co > ci;
  })();

  // Single source of truth for what the room panel renders: only available
  // rooms are ever offered (no double-booking), plus the loading / empty states.
  const roomView = roomPanelView(rooms, roomsLoading);

  const isCancelled = ['cancelled', 'canceled'].includes((currentStatus || '').toLowerCase());

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['reservations-search'] });
    qc.invalidateQueries({ queryKey: ['reservation-enhanced', id] });
    qc.invalidateQueries({ queryKey: ['reservation-ota', id] });
    qc.invalidateQueries({ queryKey: ['reservation-folio', id] });
    qc.invalidateQueries({ queryKey: ['reservation-full', id] });
    void invalidateRoomOccupancy(qc);
    qc.invalidateQueries({ queryKey: ['calendar', 'reservations'] });
  };

  const closePanel = () => {
    setPanel('');
    setActionError(null);
  };

  const openPanel = (next: 'dates' | 'room' | 'rate' | 'guests' | 'payment') => {
    if (next === 'rate' && !canOverrideRate) return;
    if (next === 'payment' ? !canTakePayment : !canManage) return;
    setActionError(null);
    setSuccessMsg(null);
    setCancelConfirming(false);
    setPanel((cur) => (cur === next ? '' : next));
    if (next === 'guests') {
      // Prefill from the OTA-details payload so an edit to one field never
      // clobbers the others (PUT only writes the fields that changed).
      const currentAdults = booking?.adults ?? otaData?.adults;
      const currentChildren = booking?.children ?? otaData?.children;
      setAdults(currentAdults != null ? String(currentAdults) : '');
      setChildren(currentChildren != null ? String(currentChildren) : '');
      setSpecialRequests(booking?.special_requests ?? otaData?.special_requests ?? '');
    }
    if (next === 'dates') {
      setCheckIn(toDisplayDate(stayCheckIn));
      setCheckOut(toDisplayDate(stayCheckOut));
    }
    if (next === 'room') {
      setRoomCheckIn(toDisplayDate(stayCheckIn));
      setRoomCheckOut(toDisplayDate(stayCheckOut));
    }
    if (next === 'rate') setNewRate(booking?.total_amount != null ? String(booking.total_amount) : '');
    if (next === 'payment') {
      const current = canTakePayment ? money.balance ?? 0 : 0;
      setPaymentAmount(current > 0 ? String(Math.round(current * 100) / 100) : '');
    }
  };

  // Re-query availability whenever the room panel is open and the selected
  // window changes. Invalid / inverted dates clear the list instead of firing
  // a request. A cancel flag avoids a stale response overwriting a newer one.
  useEffect(() => {
    if (panel !== 'room') return;
    const ci = toISODate(roomCheckIn);
    const co = toISODate(roomCheckOut);
    if (!ci || !co || co <= ci) {
      setRooms([]);
      setRoomsLoading(false);
      setRoomsError(null);
      return;
    }
    let cancelled = false;
    setRoomsLoading(true);
    setRoomsError(null);
    getAvailability(ci, co)
      .then((rs) => {
        // Store the raw rooms; roomPanelView() is the single source of truth
        // that filters down to available === true before they're rendered.
        if (!cancelled) setRooms(rs);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setRooms([]);
          setRoomsError(errorMessage(error, tr.reservations.roomsLoadError));
        }
      })
      .finally(() => {
        if (!cancelled) setRoomsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [panel, roomCheckIn, roomCheckOut, roomsRetry]);

  const datesMutation = useMutation({
    mutationFn: () => {
      if (!canManage) throw new Error('Rezervasyonu düzenleme yetkiniz yok.');
      const ci = toISODate(checkIn);
      const co = toISODate(checkOut);
      if (!ci || !co || co <= ci) {
        return Promise.reject(new Error(tr.reservations.invalidDates));
      }
      return updateReservation(id, { check_in: ci, check_out: co });
    },
    onSuccess: () => {
      haptic.success();
      refreshAll();
      closePanel();
      setSuccessMsg(tr.reservations.saved);
    },
    onError: (e: unknown) => {
      haptic.error();
      setActionError(errorMessage(e, tr.reservations.actionError));
    },
  });

  const rateMutation = useMutation({
    mutationFn: () => {
      if (!canOverrideRate) throw new Error('Fiyat değiştirme yetkiniz yok.');
      const value = reservationRateInput(newRate);
      if (value === null) {
        return Promise.reject(new Error(tr.reservations.invalidRate));
      }
      if ((reason || '').trim().length < 3) {
        return Promise.reject(new Error(tr.reservations.reasonRequired));
      }
      return overrideRate(id, value, reason.trim());
    },
    onSuccess: () => {
      haptic.success();
      refreshAll();
      closePanel();
      setSuccessMsg(tr.reservations.saved);
    },
    onError: (e: unknown) => {
      haptic.error();
      setActionError(errorMessage(e, tr.reservations.actionError));
    },
  });

  const guestsMutation = useMutation({
    mutationFn: () => {
      if (!canManage) throw new Error('Rezervasyonu düzenleme yetkiniz yok.');
      const body: ReservationUpdate = {};
      const aRaw = (adults || '').trim();
      const chRaw = (children || '').trim();
      const a = reservationGuestCount(aRaw, 1);
      const ch = reservationGuestCount(chRaw || '0', 0);
      if (a === null) {
        return Promise.reject(new Error(tr.reservations.invalidGuests));
      }
      if (ch === null) {
        return Promise.reject(new Error(tr.reservations.invalidGuests));
      }
      body.adults = a;
      body.children = ch;
      body.guests_count = a + ch;
      body.special_requests = (specialRequests || '').trim();
      return updateReservation(id, body);
    },
    onSuccess: () => {
      haptic.success();
      refreshAll();
      closePanel();
      setSuccessMsg(tr.reservations.saved);
    },
    onError: (e: unknown) => {
      haptic.error();
      setActionError(errorMessage(e, tr.reservations.actionError));
    },
  });

  const roomMutation = useMutation({
    mutationFn: (room: AvailabilityRoom) => {
      if (!canManage) throw new Error('Rezervasyonu düzenleme yetkiniz yok.');
      return assignRoom(id, room.id);
    },
    onSuccess: () => {
      haptic.success();
      refreshAll();
      closePanel();
      setSuccessMsg(tr.reservations.roomChanged);
    },
    onError: (e: unknown) => {
      haptic.error();
      setActionError(errorMessage(e, tr.reservations.actionError));
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => {
      if (!canManage) throw new Error('Rezervasyonu düzenleme yetkiniz yok.');
      return cancelReservation(id);
    },
    onSuccess: () => {
      haptic.success();
      refreshAll();
      setCancelConfirming(false);
      setActionError(null);
      setSuccessMsg(tr.reservations.saved);
    },
    onError: (e: unknown) => {
      haptic.error();
      setCancelConfirming(false);
      setActionError(errorMessage(e, tr.reservations.actionError));
    },
  });

  const paymentMutation = useMutation({
    mutationFn: async () => {
      if (!canTakePayment || !currency) throw new Error(tr.reservations.paymentUnavailable);
      // Confirm the amount and payer against a fresh server read before a
      // financial write, including when this screen has been open a while.
      const latest = await getReservationFullDetail(id);
      if (latest) qc.setQueryData(['reservation-full', id], latest);
      const latestCurrency = reservationCurrency(latest?.booking.currency);
      const currentBalance = latest?.summary?.reservation_total_due;
      if (!latest || ['cancelled', 'canceled'].includes(latest.booking.status || '') || latest.read_only || latest.summary?.pricing_reconciliation_required || latestCurrency !== currency || hasSeparatePayer({ ...latest.booking, folios: latest.folios }) || typeof currentBalance !== 'number' || !Number.isFinite(currentBalance)) {
        throw new Error(tr.reservations.paymentUnavailable);
      }
      const amount = parsePaymentAmount(paymentAmount);
      const amountIssue = paymentAmountError(amount, currentBalance);
      if (amountIssue === 'invalid') throw new Error(tr.reservations.paymentInvalid);
      if (amountIssue === 'overpayment') throw new Error(tr.reservations.paymentOver);
      if (amountIssue === 'no_balance') throw new Error(tr.reservations.paymentNoBalance);
      if (amountIssue) throw new Error(tr.reservations.paymentUnavailable);
      const safeAmount = amount as number;
      paymentAttempt.current = paymentAttemptForInput(paymentAttempt.current,
        { bookingId: id, currency, amount: safeAmount, method: paymentMethod, balance: currentBalance },
        () => `mobile-payment-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
      );
      return postBookingPayment(
        id,
        { amount: safeAmount, method: paymentMethod, payment_type: paymentAttempt.current.paymentType, currency },
        paymentAttempt.current.key,
      );
    },
    onSuccess: async () => {
      haptic.success();
      paymentAttempt.current = null;
      await detail.refetch();
      void qc.invalidateQueries();
      refreshAll();
      closePanel();
      setSuccessMsg(tr.reservations.paymentSaved);
    },
    onError: (e: unknown) => {
      haptic.error();
      setActionError(errorMessage(e, tr.reservations.actionError));
      void detail.refetch();
    },
  });

  const paymentMethodLabel = (method: SimplePaymentMethod): string => {
    switch (method) {
      case 'cash':
        return tr.reservations.paymentCash;
      case 'card':
        return tr.reservations.paymentCard;
      case 'bank_transfer':
        return tr.reservations.paymentTransfer;
      case 'online':
        return tr.reservations.paymentOnline;
    }
  };

  const onCancelPress = () => {
    haptic.tap();
    setActionError(null);
    setSuccessMsg(null);
    setCancelConfirming((v) => !v);
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }, webCenter]}
      refreshControl={<RefreshControl refreshing={detail.isRefetching} onRefresh={() => { void detail.refetch(); void enhanced.refetch(); void ota.refetch(); }} tintColor={c.primary} />}
      keyboardShouldPersistTaps="handled"
    >
      <OfflineBanner visible={offline} />

      <DetailHeader
        title={guestName || tr.reservations.guest}
        subtitle={booking?.booking_number || p.booking_number ? `#${booking?.booking_number || p.booking_number}` : tr.reservations.detailTitle}
        badges={
          <>
            {currentStatus ? (
              <Badge
                label={reservationStatusLabel(currentStatus)}
                tone={reservationStatusTone(currentStatus)}
              />
            ) : null}
            {roomNumber ? (
              <Badge label={`${tr.reservations.room} ${roomNumber}`} tone="default" icon="bed" />
            ) : null}
            {source ? <Badge label={reservationSourceLabel(source)} tone="info" icon="globe-outline" /> : null}
          </>
        }
      />

      {successMsg ? (
        <Card accent={c.success}>
          <Body style={{ color: c.success }}>{successMsg}</Body>
        </Card>
      ) : null}

      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
          <Ionicons name="bed-outline" size={22} color={c.primary} />
          <H2>{tr.reservations.stay}</H2>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.lg, marginTop: spacing.lg }}>
          <View style={{ flex: 1, minWidth: 120 }}>
            <Muted>{tr.reservations.arrival}</Muted>
            <Body style={{ fontWeight: '700', marginTop: spacing.xs }}>{formatDate(stayCheckIn)}</Body>
          </View>
          <View style={{ flex: 1, minWidth: 120 }}>
            <Muted>{tr.reservations.departure}</Muted>
            <Body style={{ fontWeight: '700', marginTop: spacing.xs }}>{formatDate(stayCheckOut)}</Body>
          </View>
        </View>
        <Divider />
        <Row label={tr.reservations.room} value={[roomNumber, roomType].filter(Boolean).join(' · ') || '—'} />
        <Row label={tr.reservations.source} value={reservationSourceLabel(source)} />
        {otaData?.adults != null ? <Row label={tr.reservations.guestCount} value={`${otaData.adults} ${tr.reservations.adults}${otaData.children ? ` · ${otaData.children} ${tr.reservations.children}` : ''}`} /> : null}
      </Card>

      <Card accent={money.balance !== undefined && money.balance > 0 ? c.warning : c.primary}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
          <Ionicons name="wallet-outline" size={22} color={c.primary} />
          <H2>{tr.reservations.accountSummary}</H2>
        </View>
        {detail.isLoading ? <SkeletonCard /> : detail.isError || !detail.data ? (
          <View testID="reservation-account-error" style={{ gap: spacing.sm, marginTop: spacing.md }}>
            <Body style={{ color: c.danger }}>{errorMessage(detail.error, tr.reservations.detailError)}</Body>
            <Button title={tr.reservations.retry} variant="secondary" onPress={() => { void detail.refetch(); }} fullWidth />
          </View>
        ) : (
          <View style={{ marginTop: spacing.md, gap: spacing.md }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md }}>
              <View style={{ flex: 1, minWidth: 120 }}>
                <Muted>{tr.reservations.reservationTotal}</Muted>
                <Body testID="reservation-account-total" style={{ fontSize: 19, fontWeight: '700', marginTop: spacing.xs }}>{amountLabel(money.total)}</Body>
              </View>
              <View style={{ flex: 1, minWidth: 120 }}>
                <Muted>{tr.reservations.collectedTotal}</Muted>
                <Body testID="reservation-account-collected" style={{ fontSize: 19, fontWeight: '700', marginTop: spacing.xs }}>{amountLabel(money.paid)}</Body>
              </View>
            </View>
            <View style={{ backgroundColor: c.surfaceAlt, borderRadius: radius.md, padding: spacing.lg, gap: spacing.xs }}>
              <Muted>{tr.reservations.reservationBalance}</Muted>
              <Body testID="reservation-account-balance" style={{ fontSize: 28, lineHeight: 36, fontWeight: '800', color: money.balance !== undefined && money.balance > 0 ? c.warning : c.text }}>{amountLabel(money.balance)}</Body>
            </View>
            <Muted>{separatePayer ? tr.reservations.payerBreakdownUnavailable : tr.reservations.accountSummaryHint}</Muted>
            {!currency ? <Muted style={{ color: c.warning }}>{tr.reservations.currencyUnavailable}</Muted> : null}
            {pricingIssue ? <Muted style={{ color: c.danger }}>{tr.reservations.pricingReviewRequired}</Muted> : null}
            {readOnly ? <Muted>{tr.reservations.readOnly}</Muted> : null}
          </View>
        )}
      </Card>

      {!isCancelled && (canManage || canTakePayment) ? (
        <Card>
          <H2>{tr.reservations.manage}</H2>
          <View style={{ marginTop: spacing.md }}>
            <Button title={tr.reservations.takePayment} disabled={!canTakePayment} icon="card-outline" variant={panel === 'payment' ? 'primary' : 'success'} onPress={() => openPanel('payment')} fullWidth />
          </View>
          {actionError ? (
            <Body style={{ color: c.danger, marginTop: spacing.sm }}>{actionError}</Body>
          ) : null}

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md }}>
            <Button
              title={tr.reservations.editDates}
              icon="calendar-outline"
              style={{ flexGrow: 1, flexBasis: '45%' }}
              variant={panel === 'dates' ? 'primary' : 'secondary'}
              onPress={() => openPanel('dates')}
              disabled={!canManage}
            />
            <Button
              title={tr.reservations.changeRoom}
              icon="bed-outline"
              style={{ flexGrow: 1, flexBasis: '45%' }}
              variant={panel === 'room' ? 'primary' : 'secondary'}
              onPress={() => openPanel('room')}
              disabled={!canManage}
            />
            <Button
              title={tr.reservations.overrideRate}
              icon="pricetag-outline"
              style={{ flexGrow: 1, flexBasis: '45%' }}
              variant={panel === 'rate' ? 'primary' : 'secondary'}
              onPress={() => openPanel('rate')}
              disabled={!canOverrideRate}
            />
            <Button
              title={tr.reservations.editGuests}
              icon="people-outline"
              style={{ flexGrow: 1, flexBasis: '45%' }}
              variant={panel === 'guests' ? 'primary' : 'secondary'}
              onPress={() => openPanel('guests')}
              disabled={!canManage}
            />
          </View>

          {panel === 'dates' ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              <Field
                label={tr.reservations.checkInLabel}
                value={checkIn}
                onChangeText={setCheckIn}
                keyboardType="numbers-and-punctuation"
              />
              <Field
                label={tr.reservations.checkOutLabel}
                value={checkOut}
                onChangeText={setCheckOut}
                keyboardType="numbers-and-punctuation"
              />
              <Button
                title={tr.reservations.save}
                onPress={() => datesMutation.mutate()}
                loading={datesMutation.isPending}
                fullWidth
              />
            </View>
          ) : null}

          {panel === 'rate' ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              <Field
                label={`${tr.reservations.newRate}${currency ? ` (${currency})` : ''}`}
                value={newRate}
                onChangeText={setNewRate}
                keyboardType="decimal-pad"
              />
              <Field
                label={tr.reservations.overrideReason}
                value={reason}
                onChangeText={setReason}
              />
              <Button
                title={tr.reservations.save}
                onPress={() => rateMutation.mutate()}
                loading={rateMutation.isPending}
                fullWidth
              />
            </View>
          ) : null}

          {panel === 'guests' ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              <Field
                label={tr.reservations.adultsLabel}
                value={adults}
                onChangeText={setAdults}
                keyboardType="number-pad"
              />
              <Field
                label={tr.reservations.childrenLabel}
                value={children}
                onChangeText={setChildren}
                keyboardType="number-pad"
              />
              <Field
                label={tr.reservations.specialRequestsLabel}
                value={specialRequests}
                onChangeText={setSpecialRequests}
                multiline
              />
              <Button
                title={tr.reservations.save}
                onPress={() => guestsMutation.mutate()}
                loading={guestsMutation.isPending}
                fullWidth
              />
            </View>
          ) : null}

          {panel === 'room' ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              <Field
                label={tr.reservations.checkInLabel}
                value={roomCheckIn}
                onChangeText={setRoomCheckIn}
                keyboardType="numbers-and-punctuation"
              />
              <Field
                label={tr.reservations.checkOutLabel}
                value={roomCheckOut}
                onChangeText={setRoomCheckOut}
                keyboardType="numbers-and-punctuation"
              />
              <Muted>{tr.reservations.selectRoom}</Muted>
              {!roomDatesValid ? (
                <Body style={{ color: c.textMuted }}>{tr.reservations.invalidDates}</Body>
              ) : roomsError ? (
                <View style={{ gap: spacing.sm }}>
                  <Body style={{ color: c.danger }}>{roomsError}</Body>
                  <Button title={tr.reservations.retry} variant="secondary" onPress={() => setRoomsRetry((value) => value + 1)} fullWidth />
                </View>
              ) : roomView.kind === 'loading' ? (
                <Body style={{ color: c.textMuted }}>{tr.reservations.loadingRooms}</Body>
              ) : roomView.kind === 'empty' ? (
                <Body style={{ color: c.textMuted }}>{tr.reservations.noAvailableRooms}</Body>
              ) : (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
                  {roomView.rooms.map((room) => (
                    <Button
                      key={room.id}
                      title={`${room.room_number}${room.room_type ? ` · ${room.room_type}` : ''}`}
                      variant="secondary"
                      onPress={() => roomMutation.mutate(room)}
                      disabled={roomMutation.isPending}
                    />
                  ))}
                </View>
              )}
            </View>
          ) : null}

          {panel === 'payment' ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              {!canTakePayment ? (
                <Body style={{ color: c.textMuted }}>
                  {separatePayer ? tr.reservations.payerBreakdownUnavailable : !currency ? tr.reservations.currencyUnavailable : pricingIssue ? tr.reservations.pricingReviewRequired : money.balance === undefined ? tr.reservations.paymentBalanceUnknown : tr.reservations.paymentNoBalance}
                </Body>
              ) : (
                <>
                  <H2>{tr.reservations.guestCollection}</H2>
                  <Muted>{tr.reservations.guestCollectionHint}</Muted>
                  <Row
                    label={tr.reservations.paymentBalance}
                    value={amountLabel(money.balance)}
                  />
                  <Field
                    label={`${tr.reservations.paymentAmount} (${currency})`}
                    value={paymentAmount}
                    onChangeText={setPaymentAmount}
                    keyboardType="decimal-pad"
                  />
                  {paymentAmount && paymentIssue ? <Muted accessibilityLiveRegion="polite" style={{ color: c.danger }}>{paymentIssue === 'overpayment' ? tr.reservations.paymentOver : tr.reservations.paymentInvalid}</Muted> : null}
                  <Muted>{tr.reservations.paymentMethod}</Muted>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
                    {SIMPLE_PAYMENT_METHODS.map((method) => (
                      <Button
                        key={method}
                        title={paymentMethodLabel(method)}
                        variant={paymentMethod === method ? 'primary' : 'secondary'}
                        onPress={() => setPaymentMethod(method)}
                        disabled={paymentMutation.isPending}
                      />
                    ))}
                  </View>
                  <Button
                    testID="reservation-payment-submit"
                    title={tr.reservations.takePayment}
                    icon="checkmark-circle-outline"
                    variant="success"
                    onPress={() => paymentMutation.mutate()}
                    loading={paymentMutation.isPending}
                    disabled={paymentIssue !== null}
                    fullWidth
                  />
                </>
              )}
            </View>
          ) : null}

          <View style={{ marginTop: spacing.md }}>
            {cancelConfirming ? (
              <View style={{ gap: spacing.sm }}>
                <Muted>{tr.reservations.cancelConfirmBody}</Muted>
                <SegmentedActions>
                  <ActionButton
                    label={tr.reservations.cancel}
                    icon="arrow-undo"
                    onPress={() => setCancelConfirming(false)}
                    bg={c.surfaceAlt}
                    fg={c.text}
                    disabled={cancelMutation.isPending}
                  />
                  <ActionButton
                    label={tr.reservations.cancelConfirmYes}
                    icon="trash-outline"
                    onPress={() => cancelMutation.mutate()}
                    bg={c.danger}
                    fg="#ffffff"
                    loading={cancelMutation.isPending}
                  />
                </SegmentedActions>
              </View>
            ) : (
              <Button
                title={tr.reservations.cancelReservation}
                variant="danger"
                icon="close-circle-outline"
                onPress={onCancelPress}
                fullWidth
              />
            )}
          </View>
        </Card>
      ) : null}

      {guest?.phone || guest?.email || booking?.guest_phone || booking?.guest_email || p.guest_phone || p.guest_email ? (
        <Card>
          <H2>{tr.reservations.contact}</H2>
          <Row label={tr.guests.phone} value={guest?.phone || booking?.guest_phone || p.guest_phone} />
          <Row label={tr.guests.contact} value={guest?.email || booking?.guest_email || p.guest_email} />
        </Card>
      ) : null}

      <Card>
        <H2>{tr.reservations.paymentHistory}</H2>
        <Muted style={{ marginTop: spacing.xs }}>{tr.reservations.paymentHistoryHint}</Muted>
        {detail.isLoading ? <SkeletonCard /> : detail.isError || !Array.isArray(detail.data?.payments) ? (
          <Muted style={{ marginTop: spacing.md }}>{tr.reservations.paymentHistoryUnavailable}</Muted>
        ) : detail.data.payments.length === 0 ? (
          <Muted style={{ marginTop: spacing.md }}>{tr.reservations.noPayments}</Muted>
        ) : [...detail.data.payments].sort((a, b) => (b.processed_at || '').localeCompare(a.processed_at || '')).map((payment, index) => {
          const payer = detail.data?.folios?.find((item) => item.id === payment.folio_id);
          const payerLabel = payer?.payor_type || payer?.folio_type;
          return (
            <View key={payment.id || index} style={{ paddingTop: spacing.md, marginTop: spacing.md, borderTopWidth: 1, borderTopColor: c.border, gap: spacing.xs }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Body style={{ fontWeight: '700' }}>{movementMethodLabel(payment.method)}</Body>
                  <Muted>{payment.processed_at ? formatDate(payment.processed_at) : tr.reservations.dateUnavailable} · {paymentStatusLabel(payment)}</Muted>
                </View>
                <Body style={{ fontWeight: '700', flexShrink: 1 }}>{reservationAmountLabel(payment.amount, payment.currency || currency)}</Body>
              </View>
              {payerLabel ? <Muted>{tr.reservations.account}: {payerLabel === 'guest' ? tr.reservations.guestAccount : payerLabel === 'agency' ? tr.reservations.agencyAccount : payerLabel === 'company' ? tr.reservations.companyAccount : payerLabel}</Muted> : <Muted>{tr.reservations.accountUnspecified}</Muted>}
              {payment.reference ? <Muted>{tr.reservations.reference}: {payment.reference}</Muted> : null}
            </View>
          );
        })}
      </Card>

      {enhanced.isLoading ? (
        <SkeletonCard />
      ) : (
        <Card>
          <H2>{tr.reservations.rateBreakdown}</H2>
          {enhanced.isError ? (
            <Muted style={{ marginTop: spacing.xs, color: c.danger }}>
              {errorMessage(enhanced.error, tr.reservations.loadError)}
            </Muted>
          ) : null}
          <Row
            label={tr.reservations.baseRate}
            value={rate?.base_rate != null ? amountLabel(rate.base_rate) : undefined}
          />
          <Row label={tr.reservations.rateType} value={rate?.rate_type} />
          <Row label={tr.reservations.marketSegment} value={rate?.market_segment} />
          {policy?.type ? (
            <>
              <Divider />
              <Row label={tr.reservations.cancellationPolicy} value={String(policy.type)} />
            </>
          ) : null}
        </Card>
      )}

      {commission ? (
        <Card>
          <H2>{tr.reservations.commission}</H2>
          <Row label={tr.reservations.source} value={commission.ota_channel} />
          <Row
            label={tr.reservations.commissionPct}
            value={commission.commission_pct != null ? `%${commission.commission_pct}` : undefined}
          />
          <Row
            label={tr.reservations.commissionAmount}
            value={
              commission.commission_amount != null
                ? amountLabel(commission.commission_amount)
                : undefined
            }
          />
          <Row
            label={tr.reservations.netRevenue}
            value={
              commission.net_revenue != null ? amountLabel(commission.net_revenue) : undefined
            }
          />
        </Card>
      ) : null}

      {booking?.agency_name || detail.data?.company ? (
        <Card>
          <H2>{tr.reservations.payerInformation}</H2>
          <Row label={tr.reservations.agencyAccount} value={booking?.agency_name} />
          <Row label={tr.reservations.companyAccount} value={detail.data?.company?.name || detail.data?.company?.company_name} />
          <Row label={tr.reservations.paymentModel} value={booking?.payment_model || otaData?.payment_model} />
          <Muted style={{ marginTop: spacing.sm }}>{tr.reservations.payerBreakdownUnavailable}</Muted>
        </Card>
      ) : null}

      {ota.isLoading ? (
        <SkeletonCard />
      ) : (
        <Card>
          <H2>{tr.reservations.specialRequests}</H2>
          {ota.isError ? (
            <Muted style={{ marginTop: spacing.xs, color: c.danger }}>
              {errorMessage(ota.error, tr.reservations.loadError)}
            </Muted>
          ) : (
            <Body style={{ marginTop: spacing.xs }}>
              {otaData?.special_requests || tr.reservations.none}
            </Body>
          )}
          {otaData?.remarks ? (
            <>
              <Muted style={{ marginTop: spacing.sm }}>{tr.reservations.remarks}</Muted>
              <Body>{otaData.remarks}</Body>
            </>
          ) : null}
          {otaData?.source_of_booking ? (
            <Row label={tr.reservations.source} value={reservationSourceLabel(otaData.source_of_booking)} />
          ) : null}
        </Card>
      )}

      {ota.isSuccess && otaData ? (
        <Card>
          <H2>{tr.reservations.extraCharges}</H2>
          {otaData?.extra_charges && otaData.extra_charges.length > 0 ? (
            otaData.extra_charges.map((ch, i) => (
              <View
                key={ch.id || `${ch.charge_name}-${i}`}
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  gap: spacing.md,
                  marginTop: spacing.sm,
                }}
              >
                <View style={{ flexShrink: 1 }}>
                  <Body>{ch.charge_name || '—'}</Body>
                  {ch.notes ? <Muted>{ch.notes}</Muted> : null}
                </View>
                <Body>{amountLabel(ch.charge_amount)}</Body>
              </View>
            ))
          ) : (
            <Muted style={{ marginTop: spacing.xs }}>{tr.reservations.noExtraCharges}</Muted>
          )}
        </Card>
      ) : null}

      {otaData?.multi_room_info ? (
        <Card>
          <H2>{tr.reservations.multiRoom}</H2>
          <Row label="" value={otaData.multi_room_info.group_name} />
          {(otaData.multi_room_info.related_bookings || []).map((rb, i) => (
            <Row
              key={rb.booking_id || i}
              label={`${tr.reservations.room} ${rb.room_number || '—'}`}
              value={rb.guest_name}
            />
          ))}
        </Card>
      ) : null}
    </ScrollView>
  );
}
