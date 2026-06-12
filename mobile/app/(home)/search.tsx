import React, { useMemo, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Card,
  EmptyState,
  Field,
  H1,
  Muted,
  SectionTitle,
  SkeletonCard,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { isOffline } from '../../src/utils/errors';
import { GuestHit, ReservationHit, RoomHit, unifiedSearch } from '../../src/api/hub';
import { useDebouncedValue } from '../../src/utils/useDebouncedValue';

// Unified cross-entity search (Task #333). One query fans out to guests,
// reservations and rooms via /api/mobile/hub/search. Guest PII is searched
// through the encrypted-PII blind index server-side; the list only shows the
// guest display name + VIP flag.

function statusTone(status: string): 'success' | 'warning' | 'danger' | 'default' {
  const s = (status || '').toLowerCase();
  if (s.includes('cancel') || s.includes('no_show') || s.includes('iptal')) return 'danger';
  if (s.includes('pending') || s.includes('hold') || s.includes('bekle')) return 'warning';
  if (s.includes('confirm') || s.includes('checked_in') || s.includes('clean')) return 'success';
  return 'default';
}

function GuestCard({ g }: { g: GuestHit }) {
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: '600' }} numberOfLines={1}>
          {g.name}
        </Body>
        {g.vip_status ? <Badge label={tr.hub.vip} tone="vip" /> : null}
      </View>
    </Card>
  );
}

function ReservationCard({ r }: { r: ReservationHit }) {
  const dates = [r.check_in?.slice(0, 10), r.check_out?.slice(0, 10)].filter(Boolean).join(' → ');
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: '600' }} numberOfLines={1}>
          {r.guest_name || r.booking_number}
        </Body>
        {r.status ? <Badge label={r.status} tone={statusTone(r.status)} /> : null}
      </View>
      <Muted style={{ marginTop: spacing.xs }} numberOfLines={1}>
        {r.booking_number}
        {r.room_number ? ` · ${tr.hub.room} ${r.room_number}` : ''}
        {dates ? ` · ${dates}` : ''}
      </Muted>
    </Card>
  );
}

function RoomCard({ r }: { r: RoomHit }) {
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: '600' }}>
          {tr.hub.room} {r.room_number}
        </Body>
        {r.status ? <Badge label={r.status} tone={statusTone(r.status)} /> : null}
      </View>
      {r.room_type ? <Muted style={{ marginTop: spacing.xs }}>{r.room_type}</Muted> : null}
    </Card>
  );
}

export default function SearchScreen() {
  const c = useTheme();
  const [term, setTerm] = useState('');
  const debounced = useDebouncedValue(term.trim(), 350);
  const enabled = debounced.length >= 2;

  const search = useQuery({
    queryKey: ['hub-search', debounced],
    queryFn: () => unifiedSearch(debounced),
    enabled,
    placeholderData: keepPreviousData,
  });

  const offline = search.isError && isOffline(search.error);
  const data = search.data;
  const hasResults = useMemo(
    () => !!data && (data.guests.length || data.reservations.length || data.rooms.length) > 0,
    [data],
  );

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-search">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        keyboardShouldPersistTaps="handled"
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.searchTitle}</H1>
        <Field
          placeholder={tr.hub.searchPlaceholder}
          value={term}
          onChangeText={setTerm}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="search"
        />

        {!enabled ? (
          <EmptyState
            icon="search-outline"
            title={tr.hub.searchHintTitle}
            message={tr.hub.searchHint}
          />
        ) : search.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : search.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : !hasResults ? (
          <EmptyState
            icon="file-tray-outline"
            title={tr.hub.searchEmpty}
            message={tr.hub.searchEmptyHint}
          />
        ) : (
          <>
            {data!.guests.length > 0 ? (
              <View>
                <SectionTitle
                  title={`${tr.hub.searchGuests} (${data!.guests.length})`}
                />
                {data!.guests.map((g) => (
                  <GuestCard key={g.id} g={g} />
                ))}
              </View>
            ) : null}

            {data!.reservations.length > 0 ? (
              <View>
                <SectionTitle
                  title={`${tr.hub.searchReservations} (${data!.reservations.length})`}
                />
                {data!.reservations.map((r) => (
                  <ReservationCard key={r.id} r={r} />
                ))}
              </View>
            ) : null}

            {data!.rooms.length > 0 ? (
              <View>
                <SectionTitle title={`${tr.hub.searchRooms} (${data!.rooms.length})`} />
                {data!.rooms.map((r) => (
                  <RoomCard key={r.id} r={r} />
                ))}
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}
