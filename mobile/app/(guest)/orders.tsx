import React, { useMemo } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getGuestBookings } from '../../src/api/guestBookings';
import { listRoomServiceOrders } from '../../src/api/guestRoomService';
import { formatCurrency, formatTime } from '../../src/utils/format';

const STATUS_TONE: Record<string, 'success' | 'warning' | 'info' | 'default' | 'danger'> = {
  pending: 'warning',
  confirmed: 'info',
  preparing: 'info',
  delivered: 'success',
  cancelled: 'danger',
};

const STATUS_LABEL: Record<string, string> = {
  pending: 'Beklemede',
  confirmed: 'Onaylandı',
  preparing: 'Hazırlanıyor',
  delivered: 'Teslim edildi',
  cancelled: 'İptal',
};

export default function GuestOrdersScreen() {
  const c = useTheme();
  const bookingsQ = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });
  const activeBooking = useMemo(
    () => (bookingsQ.data?.active_bookings || []).find((b) => b.status === 'checked_in'),
    [bookingsQ.data],
  );

  const ordersQ = useQuery({
    queryKey: ['room-service-orders', activeBooking?.id],
    queryFn: () => (activeBooking ? listRoomServiceOrders(activeBooking.id) : Promise.resolve([])),
    enabled: !!activeBooking,
    refetchInterval: 15_000,
  });

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
      refreshControl={
        <RefreshControl
          refreshing={ordersQ.isFetching && !ordersQ.isLoading}
          onRefresh={() => ordersQ.refetch()}
          tintColor={c.primary}
        />
      }
    >
      <H1>{tr.guest.orderHistory}</H1>
      {!activeBooking ? (
        <Card>
          <Muted>{tr.guest.selectActiveBooking}</Muted>
        </Card>
      ) : ordersQ.isLoading ? (
        <SkeletonCard />
      ) : (ordersQ.data || []).length === 0 ? (
        <Card>
          <Muted>{tr.app.empty}</Muted>
        </Card>
      ) : (
        (ordersQ.data || []).map((o) => (
          <Card key={o.id}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Body style={{ fontWeight: '600' }}>
                {o.items?.map((i) => `${i.quantity}× ${i.name}`).join(', ') || '—'}
              </Body>
              <Badge
                label={STATUS_LABEL[o.status || 'pending'] || o.status || '—'}
                tone={STATUS_TONE[o.status || 'pending'] || 'default'}
              />
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: spacing.sm }}>
              <Muted>{formatTime(o.ordered_at)}</Muted>
              <Muted>
                {tr.guest.estimatedDelivery}: {formatTime(o.estimated_delivery)}
              </Muted>
            </View>
            <View style={{ marginTop: spacing.xs, alignItems: 'flex-end' }}>
              <Body style={{ color: c.text, fontWeight: '600' }}>
                {formatCurrency(o.total_amount || 0)}
              </Body>
            </View>
            {o.special_instructions ? <Muted>Not: {o.special_instructions}</Muted> : null}
          </Card>
        ))
      )}
    </ScrollView>
  );
}
