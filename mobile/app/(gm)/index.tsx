import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Body, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiCard, KpiRow, KpiPill } from '../../src/components/KpiCard';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import {
  Complaint,
  GmMetrics,
  getComplaintManagement,
  getGmSnapshot,
} from '../../src/api/gm';
import { formatCurrency } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';
import type { KpiTrend } from '../../src/components/KpiCard';

type DeltaKind = 'count' | 'currency' | 'percent';

// Build the at-a-glance comparison line + trend marker from today vs.
// yesterday. `higherIsBetter=false` flips colour semantics for metrics like
// complaints / pending tasks where a rise is bad.
function buildDelta(
  today: number,
  yesterday: number,
  kind: DeltaKind,
  higherIsBetter = true,
): { delta: string; trend: KpiTrend } {
  const diff = Math.round((today - yesterday) * 100) / 100;
  let trend: KpiTrend = 'flat';
  if (diff > 0) trend = higherIsBetter ? 'up' : 'down';
  else if (diff < 0) trend = higherIsBetter ? 'down' : 'up';

  const sign = diff > 0 ? '+' : '';
  let body: string;
  if (kind === 'currency') body = `${sign}${formatCurrency(diff)}`;
  else if (kind === 'percent') body = `${sign}${diff.toFixed(1)}%`;
  else body = `${sign}${diff}`;

  return { delta: `${body} ${tr.manager.vsYesterday}`, trend };
}

function ComplaintRow({ comp }: { comp: Complaint }) {
  const c = useTheme();
  const urgent = comp.days_open > 2;
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
            <H2>{comp.guest_name || '—'}</H2>
            {urgent ? <KpiPill label={tr.manager.urgent} tone="danger" /> : null}
          </View>
          {comp.comment ? (
            <Body style={{ color: c.textMuted, marginTop: spacing.xs }} numberOfLines={2}>
              {comp.comment}
            </Body>
          ) : null}
          <Muted style={{ marginTop: spacing.xs }}>
            {comp.days_open} {tr.manager.daysOpen} · {comp.rating}★
          </Muted>
        </View>
      </View>
    </Card>
  );
}

export default function GMOverview() {
  const c = useTheme();
  const { user } = useAuthStore();

  const snapshot = useQuery({ queryKey: ['gm-snapshot'], queryFn: getGmSnapshot });
  const complaints = useQuery({
    queryKey: ['gm-complaints'],
    queryFn: getComplaintManagement,
  });

  const refreshing = snapshot.isFetching && !snapshot.isLoading;
  const onRefresh = useCallback(() => {
    snapshot.refetch();
    complaints.refetch();
  }, [snapshot, complaints]);

  const offline = snapshot.isError && isOffline(snapshot.error);

  const today: GmMetrics | undefined = snapshot.data?.today;
  const yest: GmMetrics | undefined = snapshot.data?.yesterday;

  const occ = buildDelta(today?.occupancy ?? 0, yest?.occupancy ?? 0, 'percent');
  const rev = buildDelta(today?.revenue ?? 0, yest?.revenue ?? 0, 'currency');
  const arr = buildDelta(today?.check_ins ?? 0, yest?.check_ins ?? 0, 'count');
  const dep = buildDelta(today?.check_outs ?? 0, yest?.check_outs ?? 0, 'count');
  const tasks = buildDelta(today?.pending_tasks ?? 0, yest?.pending_tasks ?? 0, 'count', false);
  const comp = buildDelta(today?.complaints ?? 0, yest?.complaints ?? 0, 'count', false);

  const activeComplaints = complaints.data?.active_complaints ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />

        <H1>{tr.manager.dashboardTitle}</H1>
        <Muted>
          {tr.manager.welcome}, {user?.name || user?.username || user?.email}
        </Muted>

        <RoleSwitcher />

        <H2>{tr.manager.kpis}</H2>

        {snapshot.isLoading ? (
          <>
            <KpiRow>
              <SkeletonCard />
              <SkeletonCard />
            </KpiRow>
            <KpiRow>
              <SkeletonCard />
              <SkeletonCard />
            </KpiRow>
          </>
        ) : snapshot.isError ? (
          <Card>
            <Muted>{tr.manager.loadError}</Muted>
          </Card>
        ) : (
          <>
            <KpiRow>
              <KpiCard
                testID="kpi-occupancy"
                label={tr.manager.occupancy}
                value={`%${(today?.occupancy ?? 0).toFixed(1)}`}
                delta={occ.delta}
                trend={occ.trend}
                tone="info"
              />
              <KpiCard
                testID="kpi-revenue"
                label={tr.manager.revenue}
                value={formatCurrency(today?.revenue ?? 0)}
                delta={rev.delta}
                trend={rev.trend}
                tone="success"
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="kpi-arrivals"
                label={tr.manager.arrivals}
                value={String(today?.check_ins ?? 0)}
                delta={arr.delta}
                trend={arr.trend}
              />
              <KpiCard
                testID="kpi-departures"
                label={tr.manager.departures}
                value={String(today?.check_outs ?? 0)}
                delta={dep.delta}
                trend={dep.trend}
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="kpi-pending-tasks"
                label={tr.manager.pendingTasks}
                value={String(today?.pending_tasks ?? 0)}
                delta={tasks.delta}
                trend={tasks.trend}
                tone={(today?.pending_tasks ?? 0) > 0 ? 'warning' : 'default'}
              />
              <KpiCard
                testID="kpi-complaints"
                label={tr.manager.complaints}
                value={String(today?.complaints ?? 0)}
                delta={comp.delta}
                trend={comp.trend}
                tone={(today?.complaints ?? 0) > 0 ? 'danger' : 'default'}
              />
            </KpiRow>
          </>
        )}

        <H2 style={{ marginTop: spacing.sm }}>{tr.manager.alertsTitle}</H2>
        {complaints.isLoading ? (
          <SkeletonCard />
        ) : complaints.isError ? (
          <Card>
            <Muted>{tr.manager.loadError}</Muted>
          </Card>
        ) : activeComplaints.length === 0 ? (
          <Card>
            <Muted>{tr.manager.noComplaints}</Muted>
          </Card>
        ) : (
          <>
            {complaints.data ? (
              <Muted>
                {tr.manager.avgResolution}: {complaints.data.avg_resolution_time_hours}{' '}
                {tr.manager.hours}
              </Muted>
            ) : null}
            {activeComplaints.map((item) => (
              <ComplaintRow key={item.id} comp={item} />
            ))}
          </>
        )}
      </ScrollView>
    </View>
  );
}
