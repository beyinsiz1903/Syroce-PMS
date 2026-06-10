import React from 'react';
import { ScrollView, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, Divider, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  getReservationDetailsEnhanced,
  getReservationOtaDetails,
} from '../../src/api/reservations';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';

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
