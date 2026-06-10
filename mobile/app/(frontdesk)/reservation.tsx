import React, { useState } from 'react';
import { Alert, ScrollView, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Button,
  Card,
  Divider,
  Field,
  H1,
  H2,
  Muted,
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
  updateReservation,
} from '../../src/api/reservations';
import { assignRoom } from '../../src/api/bookings';
import { listRooms, Room } from '../../src/api/rooms';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';

const AVAILABLE_ROOM_STATUSES = ['available', 'inspected'];

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
  const [panel, setPanel] = useState<'' | 'dates' | 'room' | 'rate'>('');
  const [actionError, setActionError] = useState<string | null>(null);

  const [checkIn, setCheckIn] = useState(toDisplayDate(p.check_in));
  const [checkOut, setCheckOut] = useState(toDisplayDate(p.check_out));
  const [newRate, setNewRate] = useState(p.total_amount || '');
  const [reason, setReason] = useState('');
  const [rooms, setRooms] = useState<Room[]>([]);

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

  const openPanel = (next: 'dates' | 'room' | 'rate') => {
    setActionError(null);
    setPanel((cur) => (cur === next ? '' : next));
    if (next === 'room' && rooms.length === 0) {
      listRooms()
        .then((rs) =>
          setRooms(
            rs.filter((r) => AVAILABLE_ROOM_STATUSES.includes((r.status || '').toLowerCase())),
          ),
        )
        .catch(() => setRooms([]));
    }
  };

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
      Alert.alert(tr.app.success, tr.reservations.saved);
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
      Alert.alert(tr.app.success, tr.reservations.saved);
    },
    onError: (e: unknown) => {
      haptic.error();
      setActionError(errorMessage(e, tr.reservations.actionError));
    },
  });

  const roomMutation = useMutation({
    mutationFn: (room: Room) => assignRoom(id, room.id),
    onSuccess: () => {
      haptic.success();
      refreshAll();
      closePanel();
      Alert.alert(tr.app.success, tr.reservations.roomChanged);
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
      Alert.alert(tr.app.success, tr.reservations.saved);
    },
    onError: (e: unknown) => {
      haptic.error();
      Alert.alert(tr.app.error, errorMessage(e, tr.reservations.actionError));
    },
  });

  const confirmCancel = () => {
    Alert.alert(tr.reservations.cancelConfirmTitle, tr.reservations.cancelConfirmBody, [
      { text: tr.reservations.cancel, style: 'cancel' },
      {
        text: tr.reservations.cancelConfirmYes,
        style: 'destructive',
        onPress: () => cancelMutation.mutate(),
      },
    ]);
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
    >
      <OfflineBanner visible={offline} />

      <View>
        <H1>{p.guest_name || tr.reservations.guest}</H1>
        {p.booking_number ? <Muted>#{p.booking_number}</Muted> : null}
      </View>

      <Card>
        <H2>{tr.reservations.stay}</H2>
        <Body style={{ marginTop: spacing.xs }}>
          {formatDate(p.check_in)} {formatTime(p.check_in)} → {formatDate(p.check_out)}{' '}
          {formatTime(p.check_out)}
        </Body>
        <Muted style={{ marginTop: 2 }}>
          {tr.reservations.room} {p.room_number || '—'} · {p.room_type || ''}
        </Muted>
        {p.status ? (
          <View style={{ flexDirection: 'row', marginTop: spacing.sm }}>
            <Badge label={p.status} tone="info" />
          </View>
        ) : null}
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

          {panel === 'room' ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              <Muted>{tr.reservations.selectRoom}</Muted>
              {rooms.length === 0 ? (
                <Body style={{ color: c.textMuted }}>{tr.reservations.noAvailableRooms}</Body>
              ) : (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
                  {rooms.map((room) => (
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
            <Button
              title={tr.reservations.cancelReservation}
              variant="danger"
              onPress={confirmCancel}
              loading={cancelMutation.isPending}
              fullWidth
            />
          </View>
        </Card>
      ) : null}

      {p.guest_phone || p.guest_email ? (
        <Card>
          <H2>{tr.reservations.contact}</H2>
          <Row label="Tel" value={p.guest_phone} />
          <Row label="E-posta" value={p.guest_email} />
        </Card>
      ) : null}

      {enhanced.isLoading ? (
        <SkeletonCard />
      ) : (
        <Card>
          <H2>{tr.reservations.rateBreakdown}</H2>
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
          <Body style={{ marginTop: spacing.xs }}>
            {otaData?.special_requests || tr.reservations.none}
          </Body>
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
