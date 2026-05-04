import React, { useEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Card,
  Field,
  H1,
  H2,
  Muted,
  SkeletonCard,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { Guest, checkBlacklist, searchGuests } from '../../src/api/guests';
import { isOffline } from '../../src/utils/errors';

export default function GuestsScreen() {
  const c = useTheme();
  const [q, setQ] = useState('');
  const [selected, setSelected] = useState<Guest | null>(null);
  const [blacklisted, setBlacklisted] = useState<boolean | null>(null);

  const guests = useQuery({
    queryKey: ['guests-search', q.trim()],
    queryFn: () => searchGuests(q.trim()),
    enabled: q.trim().length >= 2,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!selected) {
      setBlacklisted(null);
      return;
    }
    let cancelled = false;
    setBlacklisted(null);
    checkBlacklist(selected.id).then((res) => {
      if (!cancelled) setBlacklisted(res.blacklisted);
    });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const refreshing = guests.isFetching && !guests.isLoading;
  const offline = guests.isError && isOffline(guests.error);
  const showSkeleton = guests.isLoading && q.trim().length >= 2;
  const data = guests.data || [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }}>
      <H1>{tr.guests.title}</H1>
      <View style={{ height: spacing.sm }} />
      <Field
        placeholder={tr.guests.search}
        value={q}
        onChangeText={setQ}
        autoCapitalize="none"
      />
      <View style={{ height: spacing.md }} />

      <OfflineBanner visible={offline} />

      {selected ? (
        <Card>
          <View
            style={{
              flexDirection: 'row',
              gap: spacing.sm,
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <H2>
              {selected.first_name || ''} {selected.last_name || selected.full_name || ''}
            </H2>
            {selected.vip_status ? <Badge label={tr.guests.vip} tone="vip" /> : null}
            {blacklisted ? <Badge label={tr.guests.blacklist} tone="danger" /> : null}
          </View>
          {selected.phone ? <Muted>Tel: {selected.phone}</Muted> : null}
          {selected.email ? <Muted>{selected.email}</Muted> : null}
          {selected.nationality ? <Muted>Uyruk: {selected.nationality}</Muted> : null}
          {selected.notes ? (
            <View style={{ marginTop: spacing.sm }}>
              <Muted>{tr.guests.preferences}</Muted>
              <Body>{selected.notes}</Body>
            </View>
          ) : null}
        </Card>
      ) : null}

      {showSkeleton ? (
        <SkeletonCard />
      ) : (
        <FlatList
          data={data}
          keyExtractor={(g) => g.id}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => guests.refetch()}
              tintColor={c.primary}
            />
          }
          ListEmptyComponent={
            q.trim().length >= 2 && !guests.isLoading ? (
              <Card>
                <Muted>{tr.guests.noResults}</Muted>
              </Card>
            ) : null
          }
          renderItem={({ item }) => (
            <Pressable onPress={() => setSelected(item)}>
              <Card>
                <View
                  style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Body>
                      {item.first_name || ''} {item.last_name || item.full_name || ''}
                    </Body>
                    <Muted>{item.phone || item.email || item.id_number || ''}</Muted>
                  </View>
                  <View style={{ flexDirection: 'row', gap: spacing.xs }}>
                    {item.vip_status ? <Badge label="VIP" tone="vip" /> : null}
                    {item.blacklisted ? <Badge label="!" tone="danger" /> : null}
                  </View>
                </View>
              </Card>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}
