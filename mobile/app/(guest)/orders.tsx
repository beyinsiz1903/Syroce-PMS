import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Card, EmptyState, H1, Muted, SkeletonCard } from '../../src/components/ui';
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

// Sessiz, üstel artan yeniden bağlanma gecikmeleri (ms). Tavan 60s.
const RECONNECT_DELAYS_MS = [2_000, 5_000, 15_000, 30_000, 60_000];

export default function GuestOrdersScreen() {
  const c = useTheme();
  const queryClient = useQueryClient();
  const bookingsQ = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });
  const activeBooking = useMemo(
    () => (bookingsQ.data?.active_bookings || []).find((b) => b.status === 'checked_in'),
    [bookingsQ.data],
  );

  const [streamConnected, setStreamConnected] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ordersQueryKey = ['room-service-orders', activeBooking?.id] as const;

  const ordersQ = useQuery({
    queryKey: ordersQueryKey,
    queryFn: () => (activeBooking ? listRoomServiceOrders(activeBooking.id) : Promise.resolve([])),
    enabled: !!activeBooking,
    refetchInterval: streamConnected ? false : 15_000,
  });

  const clearPendingReconnect = () => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  const scheduleReconnect = () => {
    if (reconnectTimerRef.current) return;
    const idx = Math.min(reconnectAttemptRef.current, RECONNECT_DELAYS_MS.length - 1);
    const delay = RECONNECT_DELAYS_MS[idx];
    reconnectAttemptRef.current += 1;
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      setRetryNonce((n) => n + 1);
    }, delay);
  };

  // Aktif rezervasyon değişince/sökülünce bekleyen denemeleri ve sayacı sıfırla.
  useEffect(() => {
    reconnectAttemptRef.current = 0;
    clearPendingReconnect();
    return () => {
      clearPendingReconnect();
    };
  }, [activeBooking?.id]);

  useEffect(() => {
    if (!activeBooking) return;
    let cancelled = false;
    let teardown: (() => void) | undefined;

    (async () => {
      const t = await subscribeRoomServiceOrders(activeBooking.id, {
        onOpen: () => {
          if (cancelled) return;
          reconnectAttemptRef.current = 0;
          clearPendingReconnect();
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
          scheduleReconnect();
        },
        onError: () => {
          if (cancelled) return;
          setStreamConnected(false);
          scheduleReconnect();
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
  }, [activeBooking?.id, retryNonce]);

  const handleRetryStream = () => {
    if (streamConnected) return;
    reconnectAttemptRef.current = 0;
    clearPendingReconnect();
    setRetryNonce((n) => n + 1);
    if (activeBooking) {
      ordersQ.refetch();
    }
  };

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
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <H1>{tr.guest.orderHistory}</H1>
        {activeBooking ? (
          streamConnected ? (
            <Badge label={tr.guest.liveBadge} tone="success" />
          ) : (
            <Pressable
              onPress={handleRetryStream}
              accessibilityRole="button"
              accessibilityLabel="Çevrimdışı, yeniden bağlanmak için dokun"
              hitSlop={8}
            >
              <Badge label={tr.guest.offlineRetry} tone="warning" />
            </Pressable>
          )
        ) : null}
      </View>
      {!activeBooking ? (
        <Card padded={false}>
          <EmptyState
            icon="bed-outline"
            title={tr.guest.selectActiveBookingTitle}
            message={tr.guest.selectActiveBooking}
          />
        </Card>
      ) : ordersQ.isLoading ? (
        <SkeletonCard />
      ) : (ordersQ.data || []).length === 0 ? (
        <Card padded={false}>
          <EmptyState
            icon="receipt-outline"
            title={tr.guest.ordersEmptyTitle}
            message={tr.guest.ordersEmptyMessage}
          />
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
