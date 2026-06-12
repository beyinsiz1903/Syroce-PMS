import React, { useEffect, useState } from 'react';
import { ScrollView, View } from 'react-native';
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
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  cancelReservation,
  getReservationDetailsEnhanced,
  getReservationOtaDetails,
  overrideRate,
  ReservationUpdate,
  updateReservation,
} from '../../src/api/reservations';
import { assignRoom } from '../../src/api/bookings';
import { getAvailability, AvailabilityRoom } from '../../src/api/availability';
import { roomPanelView } from '../../src/utils/availabilityFilters';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';

// DD.MM.YYYY → YYYY-MM-DD (same normaliser the list screen uses). Returns
// undefined for blank / unparseable input so the caller can reject it.
function toISODate(input: string): string | undefined {
  const v = (input || '').trim();
  if (!v) return undefined;
  const dm = v.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (dm) {
    const [, d, m, y] = dm;
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  return undefined;
}

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
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md, marginTop: 2 }}>
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

  const offline =
    (enhanced.isError && isOffline(enhanced.error)) || (ota.isError && isOffline(ota.error));

  const totalAmount = p.total_amount ? Number(p.total_amount) : undefined;
  const paidAmount = p.paid_amount ? Number(p.paid_amount) : undefined;
  const balance =
    p.balance && p.balance !== ''
      ? Number(p.balance)
      : totalAmount != null && paidAmount != null
      ? totalAmount - paidAmount
      : undefined;

  const rate = enhanced.data?.rate_breakdown;
  const commission = enhanced.data?.commission;
  const policy = enhanced.data?.cancellation_policy;
  const otaData = ota.data;

  const qc = useQueryClient();

  // Which inline action panel is open ('' = none). Only one at a time keeps the
  // detail screen readable on a phone.
  const [panel, setPanel] = useState<'' | 'dates' | 'room' | 'rate' | 'guests'>('');
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
  const [adults, setAdults] = useState('');
  const [children, setChildren] = useState('');
  const [specialRequests, setSpecialRequests] = useState('');
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

  const isCancelled = (p.status || '').toLowerCase() === 'cancelled';

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ['reservations-search'] });
    qc.invalidateQueries({ queryKey: ['reservation-enhanced', id] });
    qc.invalidateQueries({ queryKey: ['reservation-ota', id] });
  };

  const closePanel = () => {
    setPanel('');
    setActionError(null);
  };

  const openPanel = (next: 'dates' | 'room' | 'rate' | 'guests') => {
    setActionError(null);
    setSuccessMsg(null);
    setCancelConfirming(false);
    setPanel((cur) => (cur === next ? '' : next));
    if (next === 'guests') {
      // Prefill from the OTA-details payload so an edit to one field never
      // clobbers the others (PUT only writes the fields that changed).
      setAdults(otaData?.adults != null ? String(otaData.adults) : '');
      setChildren(otaData?.children != null ? String(otaData.children) : '');
      setSpecialRequests(otaData?.special_requests || '');
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
      return;
    }
    let cancelled = false;
    setRoomsLoading(true);
    getAvailability(ci, co)
      .then((rs) => {
        // Store the raw rooms; roomPanelView() is the single source of truth
        // that filters down to available === true before they're rendered.
        if (!cancelled) setRooms(rs);
      })
      .catch(() => {
        if (!cancelled) setRooms([]);
      })
      .finally(() => {
        if (!cancelled) setRoomsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [panel, roomCheckIn, roomCheckOut]);

  const datesMutation = useMutation({
    mutationFn: () => {
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
      const value = parseFloat((newRate || '').replace(',', '.'));
      if (!Number.isFinite(value) || value < 0) {
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
      const body: ReservationUpdate = {};
      const aRaw = (adults || '').trim();
      const chRaw = (children || '').trim();
      const a = parseInt(aRaw, 10);
      const ch = chRaw === '' ? 0 : parseInt(chRaw, 10);
      if (!Number.isInteger(a) || a < 1 || a > 50) {
        return Promise.reject(new Error(tr.reservations.invalidGuests));
      }
      if (!Number.isInteger(ch) || ch < 0 || ch > 50) {
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
    mutationFn: (room: AvailabilityRoom) => assignRoom(id, room.id),
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
    mutationFn: () => cancelReservation(id),
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

  const onCancelPress = () => {
    haptic.tap();
    setActionError(null);
    setSuccessMsg(null);
    setCancelConfirming((v) => !v);
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
    >
      <OfflineBanner visible={offline} />

      <DetailHeader
        title={p.guest_name || tr.reservations.guest}
        subtitle={p.booking_number ? `#${p.booking_number}` : undefined}
        badges={
          <>
            {p.status ? <Badge label={p.status} tone={isCancelled ? 'danger' : 'info'} /> : null}
            {p.room_number ? (
              <Badge label={`${tr.reservations.room} ${p.room_number}`} tone="default" icon="bed" />
            ) : null}
          </>
        }
      />

      {successMsg ? (
        <Card accent={c.success}>
          <Body style={{ color: c.success }}>{successMsg}</Body>
        </Card>
      ) : null}

      <Card>
        <H2>{tr.reservations.stay}</H2>
        <Body style={{ marginTop: spacing.xs }}>
          {formatDate(p.check_in)} {formatTime(p.check_in)} → {formatDate(p.check_out)}{' '}
          {formatTime(p.check_out)}
        </Body>
        <Muted style={{ marginTop: 2 }}>
          {tr.reservations.room} {p.room_number || '—'} · {p.room_type || ''}
        </Muted>
      </Card>

      {!isCancelled ? (
        <Card>
          <H2>{tr.reservations.manage}</H2>
          {actionError ? (
            <Body style={{ color: c.danger, marginTop: spacing.sm }}>{actionError}</Body>
          ) : null}

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md }}>
            <Button
              title={tr.reservations.editDates}
              variant={panel === 'dates' ? 'primary' : 'secondary'}
              onPress={() => openPanel('dates')}
            />
            <Button
              title={tr.reservations.changeRoom}
              variant={panel === 'room' ? 'primary' : 'secondary'}
              onPress={() => openPanel('room')}
            />
            <Button
              title={tr.reservations.overrideRate}
              variant={panel === 'rate' ? 'primary' : 'secondary'}
              onPress={() => openPanel('rate')}
            />
            <Button
              title={tr.reservations.editGuests}
              variant={panel === 'guests' ? 'primary' : 'secondary'}
              onPress={() => openPanel('guests')}
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
                label={tr.reservations.newRate}
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

      {p.guest_phone || p.guest_email ? (
        <Card>
          <H2>{tr.reservations.contact}</H2>
          <Row label={tr.guests.phone} value={p.guest_phone} />
          <Row label={tr.guests.contact} value={p.guest_email} />
        </Card>
      ) : null}

      {enhanced.isLoading ? (
        <SkeletonCard />
      ) : (
        <Card>
          <H2>{tr.reservations.rateBreakdown}</H2>
          {enhanced.isError && !offline ? (
            <Muted style={{ marginTop: spacing.xs, color: c.danger }}>
              {errorMessage(enhanced.error, tr.reservations.loadError)}
            </Muted>
          ) : null}
          <Row
            label={tr.reservations.baseRate}
            value={rate?.base_rate != null ? formatCurrency(rate.base_rate) : undefined}
          />
          <Row
            label={tr.reservations.total}
            value={
              rate?.total_amount != null
                ? formatCurrency(rate.total_amount)
                : totalAmount != null
                ? formatCurrency(totalAmount)
                : undefined
            }
          />
          {paidAmount != null ? (
            <Row label={tr.reservations.paid} value={formatCurrency(paidAmount)} />
          ) : null}
          {balance != null ? (
            <Row label={tr.reservations.balance} value={formatCurrency(balance)} />
          ) : null}
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
                ? formatCurrency(commission.commission_amount)
                : undefined
            }
          />
          <Row
            label={tr.reservations.netRevenue}
            value={
              commission.net_revenue != null ? formatCurrency(commission.net_revenue) : undefined
            }
          />
        </Card>
      ) : null}

      {ota.isLoading ? (
        <SkeletonCard />
      ) : (
        <Card>
          <H2>{tr.reservations.specialRequests}</H2>
          {ota.isError && !offline ? (
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
            <Row label={tr.reservations.source} value={otaData.source_of_booking} />
          ) : null}
        </Card>
      )}

      {!ota.isLoading ? (
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
                <Body>{formatCurrency(ch.charge_amount)}</Body>
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
