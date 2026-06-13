import React, { useEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Button,
  Card,
  DetailRow,
  EmptyState,
  Field,
  H1,
  Muted,
  SkeletonCard,
  webCenter,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { Guest, checkBlacklist, searchGuests } from '../../src/api/guests';
import { errorMessage, isOffline } from '../../src/utils/errors';

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
  const tooShort = q.trim().length < 2;

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <View style={[{ flex: 1, padding: spacing.lg }, webCenter]}>
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
        <Card accent={blacklisted ? c.danger : selected.vip_status ? c.vip : c.primary}>
          <View
            style={{
              flexDirection: 'row',
              gap: spacing.sm,
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <Body style={{ fontWeight: '700', fontSize: 17, flexShrink: 1 }}>
              {selected.first_name || ''} {selected.last_name || selected.full_name || ''}
            </Body>
            {selected.vip_status ? <Badge label={tr.guests.vip} tone="vip" icon="star" /> : null}
            {blacklisted ? <Badge label={tr.guests.blacklist} tone="danger" icon="ban" /> : null}
          </View>
          <View style={{ height: spacing.sm }} />
          {selected.phone ? <DetailRow label={tr.guests.phone} value={selected.phone} /> : null}
          {selected.email ? <DetailRow label={tr.guests.contact} value={selected.email} /> : null}
          {selected.nationality ? (
            <DetailRow label={tr.guests.nationality} value={selected.nationality} />
          ) : null}
          {selected.notes ? (
            <DetailRow label={tr.guests.preferences} value={selected.notes} />
          ) : null}
        </Card>
      ) : null}

      {selected ? <View style={{ height: spacing.md }} /> : null}

      {tooShort ? (
        <EmptyState icon="search-outline" title={tr.guests.searchHint} />
      ) : guests.isError && !offline ? (
        <Card accent={c.danger}>
          <Muted>{errorMessage(guests.error, tr.guests.loadError)}</Muted>
          <View style={{ height: spacing.sm }} />
          <Button
            title={tr.app.retry}
            icon="refresh"
            variant="outline"
            onPress={() => guests.refetch()}
            fullWidth
          />
        </Card>
      ) : showSkeleton ? (
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
            !guests.isLoading ? (
              <EmptyState icon="person-outline" title={tr.guests.noResults} />
            ) : null
          }
          renderItem={({ item }) => (
            <Pressable onPress={() => setSelected(item)} accessibilityRole="button">
              <Card>
                <View
                  style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Body style={{ fontWeight: '600' }}>
                      {item.first_name || ''} {item.last_name || item.full_name || ''}
                    </Body>
                    <Muted>{item.phone || item.email || item.id_number || ''}</Muted>
                  </View>
                  <View style={{ flexDirection: 'row', gap: spacing.xs }}>
                    {item.vip_status ? <Badge label={tr.guests.vip} tone="vip" icon="star" /> : null}
                    {item.blacklisted ? <Badge label="!" tone="danger" /> : null}
                  </View>
                </View>
              </Card>
            </Pressable>
          )}
        />
      )}
      </View>
    </View>
  );
}
