import React from 'react';
import { Alert, RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Button, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getGuestLoyalty } from '../../src/api/guestLoyalty';
import { useAuthStore } from '../../src/state/authStore';
import { getApiUrl } from '../../src/api/client';

const TIER_TONE: Record<string, 'default' | 'info' | 'warning' | 'vip' | 'success'> = {
  bronze: 'warning',
  silver: 'info',
  gold: 'warning',
  platinum: 'vip',
};

export default function LoyaltyScreen() {
  const c = useTheme();
  const { user, logout } = useAuthStore();
  const q = useQuery({ queryKey: ['guest-loyalty'], queryFn: getGuestLoyalty });

  const onLogout = () => {
    Alert.alert(tr.more.logout, '', [
      { text: tr.app.cancel, style: 'cancel' },
      { text: tr.more.logout, style: 'destructive', onPress: () => logout() },
    ]);
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
      refreshControl={
        <RefreshControl
          refreshing={q.isFetching && !q.isLoading}
          onRefresh={() => q.refetch()}
          tintColor={c.primary}
        />
      }
    >
      <H1>{tr.guest.loyaltyTitle}</H1>

      {q.isLoading ? (
        <SkeletonCard />
      ) : (
        <Card>
          <Muted>{tr.guest.totalPoints}</Muted>
          <H1 style={{ fontSize: 36 }}>{q.data?.total_points || 0}</H1>
          <View style={{ marginTop: spacing.sm }}>
            <Badge
              label={`${tr.guest.globalTier}: ${q.data?.global_tier || 'bronze'}`}
              tone={TIER_TONE[q.data?.global_tier || 'bronze'] || 'default'}
            />
          </View>
        </Card>
      )}

      {(q.data?.loyalty_programs || []).map((p) => (
        <Card key={p.id}>
          <H2>{p.hotel_name || 'Otel'}</H2>
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              marginTop: spacing.xs,
            }}
          >
            <Muted>Seviye</Muted>
            <Body>{p.tier || '—'}</Body>
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Muted>Puan</Muted>
            <Body>{p.points}</Body>
          </View>
          {p.next_tier ? (
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Muted>{tr.guest.nextTier}</Muted>
              <Body>
                {p.next_tier} ({p.points_to_next_tier} {tr.guest.pointsToNext})
              </Body>
            </View>
          ) : null}
          {p.tier_benefits && p.tier_benefits.length > 0 ? (
            <View style={{ marginTop: spacing.sm }}>
              <Muted>{tr.guest.benefits}</Muted>
              {p.tier_benefits.map((b, i) => (
                <Body key={i}>• {b}</Body>
              ))}
            </View>
          ) : null}
        </Card>
      ))}

      {(q.data?.upcoming_rewards || []).length > 0 ? (
        <Card>
          <H2>{tr.guest.upcomingRewards}</H2>
          {(q.data?.upcoming_rewards || []).map((r, i) => (
            <View
              key={i}
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                marginTop: spacing.xs,
              }}
            >
              <Body>{r.name}</Body>
              <Muted>
                {r.points_remaining > 0
                  ? `${r.points_remaining} ${tr.guest.pointsToNext}`
                  : 'Hak kazandınız'}
              </Muted>
            </View>
          ))}
        </Card>
      ) : null}

      <Card>
        <H2>{tr.more.profile}</H2>
        <Body>{user?.name || user?.email || '—'}</Body>
        <Muted>{user?.email}</Muted>
        <Muted>API: {getApiUrl()}</Muted>
      </Card>

      <Button title={tr.more.logout} variant="danger" onPress={onLogout} fullWidth />
    </ScrollView>
  );
}
