import React, { useCallback, useMemo } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Body, Button, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiCard, KpiRow, KpiPill } from '../../src/components/KpiCard';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  Complaint,
  GmChannel,
  GmHousekeeping,
  GmMetrics,
  getComplaintManagement,
  getGmSnapshot,
} from '../../src/api/gm';
import { getApprovals } from '../../src/api/hub';
import { formatCurrency } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';

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

// Compact label/value row used by the housekeeping-status breakdown.
function StatRow({ label, value, tone }: { label: string; value: number; tone?: 'warning' | 'danger' | 'success' }) {
  const c = useTheme();
  const color = tone === 'danger' ? c.danger : tone === 'warning' ? c.warning : tone === 'success' ? c.success : c.text;
  return (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: spacing.xs,
      }}
    >
      <Muted>{label}</Muted>
      <Body style={{ color, fontWeight: '700' }}>{value}</Body>
    </View>
  );
}

function HousekeepingCard({ hk }: { hk: GmHousekeeping }) {
  return (
    <Card testID="gm-hk-status">
      <StatRow label={tr.manager.hkReady} value={hk.ready_rooms} tone="success" />
      <StatRow label={tr.manager.hkOccupied} value={hk.occupied} />
      <StatRow label={tr.manager.hkDirty} value={hk.dirty_rooms} tone="warning" />
      <StatRow label={tr.manager.hkMaintenance} value={hk.maintenance} tone="danger" />
      <StatRow label={tr.manager.hkOutOfOrder} value={hk.out_of_order} tone="danger" />
    </Card>
  );
}

function ChannelRow({ ch }: { ch: GmChannel }) {
  const c = useTheme();
  return (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: spacing.xs,
      }}
    >
      <View style={{ flex: 1 }}>
        <Body style={{ fontWeight: '600' }} numberOfLines={1}>
          {ch.source}
        </Body>
        <Muted>
          {ch.bookings} {tr.manager.bookings.toLowerCase()}
        </Muted>
      </View>
      <Body style={{ color: c.success, fontWeight: '700' }}>{formatCurrency(ch.revenue)}</Body>
    </View>
  );
}

export default function GMOverview() {
  const c = useTheme();
  const router = useRouter();
  const { user } = useAuthStore();

  const snapshot = useQuery({ queryKey: ['gm-snapshot'], queryFn: getGmSnapshot });
  const complaints = useQuery({
    queryKey: ['gm-complaints'],
    queryFn: getComplaintManagement,
  });
  // Reuse the existing RBAC-guarded approvals feed (no new endpoint). The strip
  // only renders when there is something pending, so a 403/empty result for a
  // manager who cannot approve simply hides it — no error surface, no console
  // noise (keeps the zero-console Expo Web gate green).
  const approvals = useQuery({ queryKey: ['gm-approvals'], queryFn: getApprovals });

  const urgentApprovals = useMemo(() => {
    const items = (approvals.data?.categories || []).flatMap((cat) => cat.items);
    const rank = (p: string) => (p === 'urgent' ? 0 : p === 'high' ? 1 : 2);
    return [...items].sort((a, b) => rank(a.priority) - rank(b.priority)).slice(0, 8);
  }, [approvals.data]);

  const refreshing = snapshot.isFetching && !snapshot.isLoading;
  const onRefresh = useCallback(() => {
    snapshot.refetch();
    complaints.refetch();
    approvals.refetch();
  }, [snapshot, complaints, approvals]);

  const offline = snapshot.isError && isOffline(snapshot.error);

  // Only today's figures are real, live values. The snapshot's `yesterday` /
  // `last_week` are arithmetic simulations on the backend (see task note), so
  // we no longer render "vs. yesterday" deltas as if they were genuine
  // day-over-day movement. The cockpit (hero) KpiCards mirror the unified
  // staff "Bugün" cockpit: big colour-coded value + watermark icon, no delta.
  const today: GmMetrics | undefined = snapshot.data?.today;

  const openFaults = snapshot.data?.open_faults ?? 0;
  const hk = snapshot.data?.housekeeping;
  const channels = snapshot.data?.channels ?? [];
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

        {urgentApprovals.length > 0 ? (
          <View style={{ gap: spacing.sm }}>
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <H2>{tr.manager.urgentApprovalsTitle}</H2>
              <Button
                title={tr.manager.viewAllApprovals}
                variant="ghost"
                icon="chevron-forward"
                onPress={() => router.push(ROUTES.homeApprovals)}
              />
            </View>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.xs }}
            >
              {urgentApprovals.map((item) => (
                <Pressable key={item.id} onPress={() => router.push(ROUTES.homeApprovals)}>
                  <Card
                    accent={item.priority === 'urgent' ? c.danger : c.warning}
                    style={{ width: 220 }}
                  >
                    <View
                      style={{
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: spacing.xs,
                      }}
                    >
                      <Body style={{ flex: 1, fontWeight: '700' }} numberOfLines={1}>
                        {item.title}
                      </Body>
                      {item.priority && item.priority !== 'normal' ? (
                        <KpiPill
                          label={
                            item.priority === 'urgent'
                              ? tr.hub.priorityUrgent
                              : tr.hub.priorityHigh
                          }
                          tone={item.priority === 'urgent' ? 'danger' : 'warning'}
                        />
                      ) : null}
                    </View>
                    {item.requested_by ? (
                      <Muted numberOfLines={1} style={{ marginTop: spacing.xs }}>
                        {item.requested_by}
                      </Muted>
                    ) : null}
                    {typeof item.amount === 'number' ? (
                      <Body style={{ fontWeight: '700', marginTop: spacing.xs }}>
                        {formatCurrency(item.amount)}
                      </Body>
                    ) : null}
                  </Card>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        ) : null}

        <H2>{tr.manager.kpis}</H2>
        <Muted>{tr.manager.kpisHint}</Muted>

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
                icon="bed-outline"
                label={tr.manager.occupancy}
                value={`%${(today?.occupancy ?? 0).toFixed(1)}`}
                tone="info"
              />
              <KpiCard
                testID="kpi-revenue"
                icon="cash-outline"
                label={tr.manager.revenue}
                value={formatCurrency(today?.revenue ?? 0)}
                tone="success"
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="kpi-adr"
                icon="pricetag-outline"
                label={tr.manager.adr}
                value={formatCurrency(today?.adr ?? 0)}
                tone="info"
              />
              <KpiCard
                testID="kpi-revpar"
                icon="stats-chart-outline"
                label={tr.manager.revpar}
                value={formatCurrency(today?.revpar ?? 0)}
                tone="info"
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="kpi-arrivals"
                icon="enter-outline"
                label={tr.manager.arrivals}
                value={String(today?.check_ins ?? 0)}
              />
              <KpiCard
                testID="kpi-departures"
                icon="exit-outline"
                label={tr.manager.departures}
                value={String(today?.check_outs ?? 0)}
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="kpi-pending-tasks"
                icon="list-outline"
                label={tr.manager.pendingTasks}
                value={String(today?.pending_tasks ?? 0)}
                tone={(today?.pending_tasks ?? 0) > 0 ? 'warning' : 'default'}
              />
              <KpiCard
                testID="kpi-open-faults"
                icon="construct-outline"
                label={tr.manager.openFaults}
                value={String(openFaults)}
                tone={openFaults > 0 ? 'danger' : 'default'}
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="kpi-complaints"
                icon="chatbox-ellipses-outline"
                label={tr.manager.complaints}
                value={String(today?.complaints ?? 0)}
                tone={(today?.complaints ?? 0) > 0 ? 'danger' : 'default'}
              />
              <View style={{ flex: 1 }} />
            </KpiRow>
          </>
        )}

        {!snapshot.isLoading && !snapshot.isError && hk ? (
          <>
            <H2 style={{ marginTop: spacing.sm }}>{tr.manager.hkStatusTitle}</H2>
            <HousekeepingCard hk={hk} />
          </>
        ) : null}

        {!snapshot.isLoading && !snapshot.isError ? (
          <>
            <H2 style={{ marginTop: spacing.sm }}>{tr.manager.channelsTitle}</H2>
            <Muted>{tr.manager.last30}</Muted>
            {channels.length === 0 ? (
              <Card testID="gm-channels">
                <Muted>{tr.manager.noChannelData}</Muted>
              </Card>
            ) : (
              <Card testID="gm-channels">
                {channels.map((ch, idx) => (
                  <ChannelRow key={`${ch.source}-${idx}`} ch={ch} />
                ))}
              </Card>
            )}
          </>
        ) : null}

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
