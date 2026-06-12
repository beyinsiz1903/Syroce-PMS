import React, { useCallback, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Body, Button, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiCard, KpiRow, KpiPill } from '../../src/components/KpiCard';
import { TrendChart } from '../../src/components/TrendChart';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  Complaint,
  GmChannel,
  GmHousekeeping,
  GmMetrics,
  getBudgetOverview,
  getComplaintManagement,
  getGmSnapshot,
  getNpsScore,
  getPickupAnalysis,
} from '../../src/api/gm';
import { getApprovals } from '../../src/api/hub';
import { expectedCash, getCurrentShift } from '../../src/api/cashier';
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

// Segmented 7 / 30 day selector for the revenue-trend chart.
function RangeToggle({
  value,
  onChange,
}: {
  value: 7 | 30;
  onChange: (v: 7 | 30) => void;
}) {
  const c = useTheme();
  const options: { v: 7 | 30; label: string }[] = [
    { v: 7, label: tr.manager.trend7 },
    { v: 30, label: tr.manager.trend30 },
  ];
  return (
    <View
      style={{
        flexDirection: 'row',
        backgroundColor: c.surfaceAlt,
        borderRadius: radius.pill,
        padding: 3,
        gap: 2,
      }}
    >
      {options.map((o) => {
        const active = o.v === value;
        return (
          <Pressable
            key={o.v}
            testID={`gm-trend-range-${o.v}`}
            onPress={() => onChange(o.v)}
            style={{
              paddingHorizontal: spacing.md,
              paddingVertical: 6,
              borderRadius: radius.pill,
              backgroundColor: active ? c.primary : 'transparent',
            }}
          >
            <Body
              style={{
                color: active ? c.primaryText : c.textMuted,
                fontSize: 12,
                fontWeight: '700',
              }}
            >
              {o.label}
            </Body>
          </Pressable>
        );
      })}
    </View>
  );
}

// Thin progress bar (sales-target actual vs target).
function ProgressBar({ ratio, color }: { ratio: number; color: string }) {
  const c = useTheme();
  const pct = Math.max(0, Math.min(ratio, 1)) * 100;
  return (
    <View
      style={{
        height: 10,
        borderRadius: radius.pill,
        backgroundColor: c.surfaceAlt,
        overflow: 'hidden',
      }}
    >
      <View style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: radius.pill }} />
    </View>
  );
}

export default function GMOverview() {
  const c = useTheme();
  const router = useRouter();
  const { user } = useAuthStore();
  const financeReports = useAuthStore((s) => s.financeReports);

  const [trendRange, setTrendRange] = useState<7 | 30>(7);

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

  // Real per-day revenue trend (JWT-only). We always fetch 30 days and slice
  // the tail for the 7-day view, so the toggle never triggers a second request.
  const pickup = useQuery({
    queryKey: ['gm-pickup'],
    queryFn: () => getPickupAnalysis(30),
  });
  // Real guest-satisfaction (NPS) and sales-target (budget) feeds — both
  // JWT-only, so a manager always gets a 200 (no 403 console noise).
  const nps = useQuery({ queryKey: ['gm-nps'], queryFn: () => getNpsScore(30) });
  const budget = useQuery({ queryKey: ['gm-budget'], queryFn: getBudgetOverview });
  // Cash-on-hand (Kasa) is gated server-side by view_finance_reports; only call
  // it when the manager holds that flag so we never provoke a 403.
  const shift = useQuery({
    queryKey: ['gm-cashier-shift'],
    queryFn: getCurrentShift,
    enabled: financeReports,
  });

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
    pickup.refetch();
    nps.refetch();
    budget.refetch();
    if (financeReports) shift.refetch();
  }, [snapshot, complaints, approvals, pickup, nps, budget, shift, financeReports]);

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

  // Revenue trend: chart ONLY the real `historical` series (never the backend's
  // simulated `forecast`). `historical` is oldest→newest, so slice the tail.
  const historical = pickup.data?.historical ?? [];
  const trendPoints = useMemo(
    () => (trendRange === 7 ? historical.slice(-7) : historical),
    [historical, trendRange],
  );
  const trendValues = trendPoints.map((p) => p.revenue);
  const trendPeak = trendValues.length ? Math.max(...trendValues) : 0;
  const trendAvg = trendValues.length
    ? trendValues.reduce((s, v) => s + v, 0) / trendValues.length
    : 0;
  const hasTrend = trendValues.some((v) => v > 0);

  // Kasa (cash drawer) — only when finance-gated AND an open shift exists.
  const openShift = shift.data?.shift && shift.data.shift.status === 'open' ? shift.data.shift : null;
  const showKasa = financeReports && !!openShift;

  // Sales target — only the current month, and only when a real target is set
  // (rev_target > 0). Never render a placeholder/zero target.
  const currentMonthBudget = useMemo(() => {
    const m = new Date().getMonth() + 1;
    return budget.data?.months.find((mo) => mo.month === m) ?? null;
  }, [budget.data]);
  const showTarget = !!currentMonthBudget && currentMonthBudget.rev_target > 0;
  const targetRatio = showTarget ? currentMonthBudget!.rev_actual / currentMonthBudget!.rev_target : 0;

  // Guest satisfaction (NPS) — only when there is at least one real response.
  const npsData = nps.data;
  const showNps = !!npsData && npsData.total_responses > 0;
  const npsTone: 'success' | 'warning' | 'danger' = showNps
    ? npsData!.nps_score >= 50
      ? 'success'
      : npsData!.nps_score >= 0
        ? 'warning'
        : 'danger'
    : 'warning';
  const npsColor = npsTone === 'success' ? c.success : npsTone === 'danger' ? c.danger : c.warning;

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
            {showKasa ? (
              <KpiRow>
                <KpiCard
                  testID="kpi-kasa"
                  icon="wallet-outline"
                  label={tr.manager.kasa}
                  value={formatCurrency(expectedCash(openShift), openShift?.currency || 'TRY')}
                  tone="success"
                />
                <View style={{ flex: 1 }} />
              </KpiRow>
            ) : null}
          </>
        )}

        {/* Revenue trend (last 7 / 30 days) — real historical data only. */}
        {!snapshot.isError ? (
          <Card testID="gm-revenue-trend" style={{ gap: spacing.sm }}>
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: spacing.sm,
              }}
            >
              <View style={{ flex: 1 }}>
                <Body style={{ fontWeight: '700' }}>{tr.manager.revenueTrendTitle}</Body>
                <Muted>{tr.manager.revenueTrendHint}</Muted>
              </View>
              <RangeToggle value={trendRange} onChange={setTrendRange} />
            </View>

            {pickup.isLoading ? (
              <View style={{ height: 168, justifyContent: 'center' }}>
                <SkeletonCard />
              </View>
            ) : hasTrend ? (
              <>
                <TrendChart data={trendValues} color={c.primary} />
                <View
                  style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    marginTop: spacing.xs,
                  }}
                >
                  <View>
                    <Muted>{tr.manager.peak}</Muted>
                    <Body style={{ fontWeight: '700', color: c.primary }}>
                      {formatCurrency(trendPeak)}
                    </Body>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Muted>{tr.manager.avg}</Muted>
                    <Body style={{ fontWeight: '700' }}>{formatCurrency(trendAvg)}</Body>
                  </View>
                </View>
              </>
            ) : (
              <View style={{ height: 120, justifyContent: 'center' }}>
                <Muted>{tr.manager.noTrendData}</Muted>
              </View>
            )}
          </Card>
        ) : null}

        {/* Secondary operational KPIs. */}
        {!snapshot.isLoading && !snapshot.isError ? (
          <>
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
        ) : null}

        {/* Operasyon Panosu — live widgets (all real-data, gated/guarded). */}
        <H2 style={{ marginTop: spacing.sm }}>{tr.manager.widgetsTitle}</H2>

        {/* Satış Hedefi — current month, only when a real target is configured. */}
        {showTarget ? (
          <Card testID="gm-sales-target" style={{ gap: spacing.sm }}>
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <Body style={{ fontWeight: '700' }}>{tr.manager.salesTargetTitle}</Body>
              <KpiPill
                label={`%${(targetRatio * 100).toFixed(0)}`}
                tone={targetRatio >= 1 ? 'success' : targetRatio >= 0.7 ? 'warning' : 'danger'}
              />
            </View>
            <Muted>{tr.manager.salesTargetThisMonth}</Muted>
            <ProgressBar
              ratio={targetRatio}
              color={targetRatio >= 1 ? c.success : targetRatio >= 0.7 ? c.warning : c.danger}
            />
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <View>
                <Muted>{tr.manager.actual}</Muted>
                <Body style={{ fontWeight: '700', color: c.success }}>
                  {formatCurrency(currentMonthBudget!.rev_actual, budget.data?.currency || 'TRY')}
                </Body>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Muted>{tr.manager.target}</Muted>
                <Body style={{ fontWeight: '700' }}>
                  {formatCurrency(currentMonthBudget!.rev_target, budget.data?.currency || 'TRY')}
                </Body>
              </View>
            </View>
          </Card>
        ) : null}

        {/* Misafir Memnuniyeti — NPS, only when there are real responses. */}
        {showNps ? (
          <Card testID="gm-nps" style={{ gap: spacing.sm }}>
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
              }}
            >
              <View style={{ flex: 1 }}>
                <Body style={{ fontWeight: '700' }}>{tr.manager.satisfactionTitle}</Body>
                <Muted>
                  {npsData!.total_responses} {tr.manager.npsResponses} · {tr.manager.last30}
                </Muted>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Body style={{ color: npsColor, fontSize: 32, fontWeight: '800', letterSpacing: -1 }}>
                  {npsData!.nps_score.toFixed(0)}
                </Body>
                <Muted>{tr.manager.npsScore}</Muted>
              </View>
            </View>
            <View
              style={{
                flexDirection: 'row',
                height: 10,
                borderRadius: radius.pill,
                overflow: 'hidden',
                backgroundColor: c.surfaceAlt,
              }}
            >
              <View style={{ flex: Math.max(npsData!.promoters, 0), backgroundColor: c.success }} />
              <View style={{ flex: Math.max(npsData!.passives, 0), backgroundColor: c.warning }} />
              <View style={{ flex: Math.max(npsData!.detractors, 0), backgroundColor: c.danger }} />
            </View>
            <StatRow label={tr.manager.npsPromoters} value={npsData!.promoters} tone="success" />
            <StatRow label={tr.manager.npsPassives} value={npsData!.passives} tone="warning" />
            <StatRow label={tr.manager.npsDetractors} value={npsData!.detractors} tone="danger" />
          </Card>
        ) : null}

        {/* Açık Arızalar widget — concise count surfacing the snapshot fault total. */}
        {!snapshot.isLoading && !snapshot.isError ? (
          <Card testID="gm-open-faults">
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <Body style={{ fontWeight: '700' }}>{tr.manager.openFaultsTitle}</Body>
              {openFaults > 0 ? (
                <Body style={{ color: c.danger, fontWeight: '800', fontSize: 22 }}>{openFaults}</Body>
              ) : (
                <Muted>{tr.manager.noFaults}</Muted>
              )}
            </View>
          </Card>
        ) : null}

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
