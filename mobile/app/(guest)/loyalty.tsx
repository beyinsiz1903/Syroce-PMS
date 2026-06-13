import React, { useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import {
  ActionButton,
  Badge,
  Body,
  Card,
  DetailRow,
  EmptyState,
  FadeInView,
  H1,
  H2,
  Muted,
  SectionTitle,
  SegmentedActions,
  SkeletonCard,
  webCenter,
} from '../../src/components/ui';
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
  const [confirmingLogout, setConfirmingLogout] = useState(false);

  const programs = q.data?.loyalty_programs || [];
  const rewards = q.data?.upcoming_rewards || [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }, webCenter]}
      refreshControl={
        <RefreshControl
          refreshing={q.isFetching && !q.isLoading}
          onRefresh={() => q.refetch()}
          tintColor={c.primary}
        />
      }
    >
      <FadeInView>
        <H1>{tr.guest.loyaltyTitle}</H1>
        <Muted style={{ marginTop: spacing.xs }}>{tr.guest.loyaltyIntro}</Muted>
      </FadeInView>

      {q.isLoading ? (
        <SkeletonCard />
      ) : (
        <Card accent={c.primary}>
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

      {!q.isLoading && programs.length === 0 ? (
        <Card padded={false}>
          <EmptyState
            icon="ribbon-outline"
            title={tr.guest.loyaltyEmptyTitle}
            message={tr.guest.loyaltyEmptyMessage}
          />
        </Card>
      ) : (
        programs.map((p) => (
          <Card key={p.id}>
            <H2>{p.hotel_name || 'Otel'}</H2>
            <DetailRow label="Seviye" value={p.tier || '—'} />
            <DetailRow label="Puan" value={String(p.points)} />
            {p.next_tier ? (
              <DetailRow
                label={tr.guest.nextTier}
                value={`${p.next_tier} (${p.points_to_next_tier} ${tr.guest.pointsToNext})`}
              />
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
        ))
      )}

      {rewards.length > 0 ? (
        <Card>
          <H2>{tr.guest.upcomingRewards}</H2>
          {rewards.map((r, i) => (
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

      <SectionTitle title={tr.guest.profileTitle} />
      <Card>
        <DetailRow label="Ad" value={user?.name || user?.email || '—'} />
        <DetailRow label="E-posta" value={user?.email || '—'} />
        <DetailRow label="API" value={getApiUrl()} />
      </Card>

      {confirmingLogout ? (
        <SegmentedActions>
          <ActionButton
            label={tr.app.cancel}
            icon="close"
            bg={c.surfaceAlt}
            fg={c.text}
            onPress={() => setConfirmingLogout(false)}
          />
          <ActionButton
            label={tr.more.logout}
            icon="log-out-outline"
            bg={c.danger}
            fg="#ffffff"
            onPress={() => logout()}
          />
        </SegmentedActions>
      ) : (
        <SegmentedActions>
          <ActionButton
            label={tr.more.logout}
            icon="log-out-outline"
            bg={c.danger}
            fg="#ffffff"
            onPress={() => setConfirmingLogout(true)}
          />
        </SegmentedActions>
      )}
    </ScrollView>
  );
}
