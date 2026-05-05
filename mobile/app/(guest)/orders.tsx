import React, { useEffect, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getGuestBookings } from '../../src/api/guestBookings';
import {
  listRoomServiceOrders,
  subscribeRoomServiceOrders,
  type RoomServiceOrder,
} from '../../src/api/guestRoomService';
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
  const queryClient = useQueryClient();
  const bookingsQ = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });
  const activeBooking = useMemo(
    () => (bookingsQ.data?.active_bookings || []).find((b) => b.status === 'checked_in'),
    [bookingsQ.data],
  );

  const [streamConnected, setStreamConnected] = useState(false);
  const ordersQueryKey = ['room-service-orders', activeBooking?.id] as const;

  const ordersQ = useQuery({
    queryKey: ordersQueryKey,
    queryFn: () => (activeBooking ? listRoomServiceOrders(activeBooking.id) : Promise.resolve([])),
    enabled: !!activeBooking,
    refetchInterval: streamConnected ? false : 15_000,
  });

  useEffect(() => {
    if (!activeBooking) return;
    let cancelled = false;
    let teardown: (() => void) | undefined;

    (async () => {
      const t = await subscribeRoomServiceOrders(activeBooking.id, {
        onOpen: () => {
          if (cancelled) return;
          setStreamConnected(true);
          queryClient.invalidateQueries({ queryKey: ordersQueryKey });
        },
        onEvent: (ev) => {
          if (cancelled) return;
          queryClient.setQueryData<RoomServiceOrder[] | undefined>(
            ordersQueryKey,
            (prev) => mergeOrderEvent(prev, ev.order),
          );
        },
        onClose: () => {
          if (cancelled) return;
          setStreamConnected(false);
        },
        onError: () => {
          if (cancelled) return;
          setStreamConnected(false);
        },
      });
      // If cleanup ran while we were awaiting subscribe, the cleanup
      // closure had no teardown to call — close the just-opened socket
      // here to avoid a leaked connection.
      if (cancelled) {
        t();
      } else {
        teardown = t;
      }
    })();

    return () => {
      cancelled = true;
      teardown?.();
      setStreamConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeBooking?.id]);

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

function mergeOrderEvent(
  prev: RoomServiceOrder[] | undefined,
  incoming: RoomServiceOrder,
): RoomServiceOrder[] {
  const list = Array.isArray(prev) ? prev.slice() : [];
  const idx = list.findIndex((o) => o.id === incoming.id);
  if (idx >= 0) {
    list[idx] = { ...list[idx], ...incoming };
  } else {
    list.unshift(incoming);
  }
  list.sort((a, b) => {
    const ta = a.ordered_at ? Date.parse(a.ordered_at) : 0;
    const tb = b.ordered_at ? Date.parse(b.ordered_at) : 0;
    return tb - ta;
  });
  return list;
}
