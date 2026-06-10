import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, View } from 'react-native';
import { useRouter } from 'expo-router';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, Field, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { FilterChips } from '../../src/components/FilterChips';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { Reservation, searchReservations } from '../../src/api/reservations';
import { formatCurrency, formatDate } from '../../src/utils/format';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { ROUTES } from '../../src/navigation/routes';

const STATUS_OPTIONS = [
  { value: '', label: tr.reservations.statusAll },
  { value: 'confirmed', label: tr.reservations.statusConfirmed },
  { value: 'guaranteed', label: tr.reservations.statusGuaranteed },
  { value: 'checked_in', label: tr.reservations.statusCheckedIn },
  { value: 'checked_out', label: tr.reservations.statusCheckedOut },
  { value: 'cancelled', label: tr.reservations.statusCancelled },
  { value: 'no_show', label: tr.reservations.statusNoShow },
];

function statusTone(status?: string): 'success' | 'warning' | 'info' | 'default' | 'danger' {
  switch ((status || '').toLowerCase()) {
    case 'checked_in':
      return 'success';
    case 'confirmed':
    case 'guaranteed':
      return 'info';
    case 'checked_out':
      return 'default';
    case 'cancelled':
    case 'no_show':
      return 'danger';
    default:
      return 'warning';
  }
}

function statusLabel(status?: string): string {
  const opt = STATUS_OPTIONS.find((o) => o.value === (status || '').toLowerCase());
  return opt && opt.value ? opt.label : status || '—';
}

function nightsBetween(checkIn?: string, checkOut?: string): number | null {
  if (!checkIn || !checkOut) return null;
  const a = new Date(checkIn).getTime();
  const b = new Date(checkOut).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) return null;
  return Math.round((b - a) / 86_400_000);
}

// Lightweight DD.MM.YYYY → YYYY-MM-DD normaliser so the backend gets ISO dates
// while staff type the familiar Turkish format. Empty / partial input is
// passed through unchanged (the API simply ignores blank filters).
function toISODate(input: string): string | undefined {
  const v = input.trim();
  if (!v) return undefined;
  const dm = v.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (dm) {
    const [, d, m, y] = dm;
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  return undefined;
}

function ReservationRow({ r, onPress }: { r: Reservation; onPress: () => void }) {
  const c = useTheme();
  const nights = nightsBetween(r.check_in, r.check_out);
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${r.guest_name || ''} ${r.room_number || ''}`}
      testID="smoke-reservation-row"
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
    >
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', gap: spacing.sm, alignItems: 'center' }}>
              <Body style={{ fontWeight: '600', flexShrink: 1 }}>{r.guest_name || '—'}</Body>
              {r.vip_status ? <Badge label="VIP" tone="vip" /> : null}
            </View>
            <Muted>
              {tr.reservations.room} {r.room_number || '—'} · {r.room_type || ''}
            </Muted>
            <Body style={{ color: c.text, marginTop: 2 }}>
              {formatDate(r.check_in)} → {formatDate(r.check_out)}
              {nights ? ` · ${nights} ${tr.reservations.nights}` : ''}
            </Body>
            {r.booking_number ? <Muted>#{r.booking_number}</Muted> : null}
          </View>
          <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
            <Badge label={statusLabel(r.status)} tone={statusTone(r.status)} />
            {typeof r.total_amount === 'number' ? (
              <Body style={{ color: c.textMuted, fontSize: 13 }}>
                {formatCurrency(r.total_amount)}
              </Body>
            ) : null}
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

export default function ReservationsScreen() {
  const c = useTheme();
  const router = useRouter();

  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [checkInFrom, setCheckInFrom] = useState('');
  const [checkOutTo, setCheckOutTo] = useState('');

  const params = useMemo(
    () => ({
      query: query.trim() || undefined,
      status: status || undefined,
      check_in: toISODate(checkInFrom),
      check_out: toISODate(checkOutTo),
    }),
    [query, status, checkInFrom, checkOutTo],
  );

  const q = useQuery({
    queryKey: ['reservations-search', params],
    queryFn: () => searchReservations(params),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });

  const data = q.data || [];
  const refreshing = q.isFetching && !q.isLoading;
  const offline = q.isError && isOffline(q.error);
  const hasFilters = !!(query || status || checkInFrom || checkOutTo);

  const clearFilters = () => {
    setQuery('');
    setStatus('');
    setCheckInFrom('');
    setCheckOutTo('');
  };

  const openDetail = (r: Reservation) => {
    router.push({
      pathname: ROUTES.reservationDetail,
      params: {
        id: r.id,
        guest_name: r.guest_name || '',
        room_number: r.room_number || '',
        room_type: r.room_type || '',
        check_in: r.check_in || '',
        check_out: r.check_out || '',
        status: r.status || '',
        total_amount: r.total_amount != null ? String(r.total_amount) : '',
        paid_amount: r.paid_amount != null ? String(r.paid_amount) : '',
        balance: r.balance != null ? String(r.balance) : '',
        guest_phone: r.guest_phone || '',
        guest_email: r.guest_email || '',
        booking_number: r.booking_number || '',
      },
    });
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }}>
      <H1>{tr.reservations.title}</H1>
      <View style={{ height: spacing.sm }} />
      <Field
        placeholder={tr.reservations.search}
        value={query}
        onChangeText={setQuery}
        autoCapitalize="none"
        testID="smoke-reservations-search"
      />
      <View style={{ height: spacing.sm }} />
      <FilterChips options={STATUS_OPTIONS} value={status} onChange={setStatus} />
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
        <View style={{ flex: 1 }}>
          <Field
            placeholder={tr.reservations.checkInFrom}
            value={checkInFrom}
            onChangeText={setCheckInFrom}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
          />
        </View>
        <View style={{ flex: 1 }}>
          <Field
            placeholder={tr.reservations.checkOutTo}
            value={checkOutTo}
            onChangeText={setCheckOutTo}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
          />
        </View>
      </View>
      {hasFilters ? (
        <Pressable onPress={clearFilters} style={{ paddingVertical: spacing.sm }}>
          <Muted style={{ color: c.primary }}>{tr.reservations.clearFilters}</Muted>
        </Pressable>
      ) : (
        <View style={{ height: spacing.sm }} />
      )}

      <OfflineBanner visible={offline} />

      {q.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : q.isError && !offline ? (
        <Card>
          <Muted>{errorMessage(q.error, tr.reservations.loadError)}</Muted>
        </Card>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(r) => r.id}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
          contentContainerStyle={{ paddingBottom: spacing.xxl }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => q.refetch()}
              tintColor={c.primary}
            />
          }
          ListEmptyComponent={
            <Card>
              <Muted>{tr.reservations.noResults}</Muted>
            </Card>
          }
          renderItem={({ item }) => (
            <ReservationRow r={item} onPress={() => openDetail(item)} />
          )}
        />
      )}
    </View>
  );
}
