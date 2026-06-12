import React from 'react';
import { ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted } from '../../src/components/ui';
import { KpiCard, KpiRow, type KpiTone } from '../../src/components/KpiCard';
import {
  DepartmentListState,
  SectionTitle,
} from '../../src/components/department';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import { screenRedirectsToHub } from '../../src/utils/departmentScreens';
import {
  getPricingStrategy,
  listPriceAdjustments,
  getPricingInsights,
  getRevenueDashboard,
  getOccupancyForecast,
  type PriceAdjustment,
  type PricingInsight,
  type ForecastDay,
  type RevenueOpportunity,
} from '../../src/api/revenue';
import { formatCurrency, formatDate } from '../../src/utils/format';

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info';

function marketPositionLabel(pos?: string): string {
  const map = tr.departments.revenue.marketPositions as Record<string, string>;
  return (pos && map[pos]) || pos || '—';
}

function confidenceTone(level?: string): Tone {
  switch (level) {
    case 'high':
      return 'success';
    case 'medium':
      return 'warning';
    case 'low':
      return 'danger';
    default:
      return 'default';
  }
}

function confidenceLabel(level?: string): string {
  const map = tr.departments.revenue.confidenceLevels as Record<string, string>;
  return (level && map[level]) || level || '—';
}

// Occupancy is good news when high, so colour the cockpit tile accordingly.
function occupancyTone(pct?: number): KpiTone {
  const v = pct ?? 0;
  if (v >= 75) return 'success';
  if (v >= 50) return 'info';
  return 'warning';
}

// Demand level doubles as the displacement-risk signal: a high-demand day is a
// high displacement risk (discounted/group business crowds out higher rates).
function demandTone(level?: string): Tone {
  switch (level) {
    case 'high':
      return 'danger';
    case 'medium':
      return 'warning';
    case 'low':
      return 'success';
    default:
      return 'default';
  }
}

function demandLabel(level?: string): string {
  const map = tr.departments.revenue.demandLevels as Record<string, string>;
  return (level && map[level]) || level || '—';
}

function riskLabel(level?: string): string {
  const map = tr.departments.revenue.displacementRisk as Record<string, string>;
  return (level && map[level]) || level || '—';
}

// Read-only Revenue Management screen. The KPI cockpit (ADR / RevPAR /
// occupancy) and forecast come from the auth-only revenue-engine reads; the
// pricing strategy, AI insights and price-adjustment log come from the rms
// reads. The (departments) revenue entitlement (view_revenue =
// VIEW_FINANCIAL_REPORTS roles) decides whether we show the screen; rate
// mutations stay backend-gated by require_op("manage_rates").
export default function RevenueScreen() {
  const c = useTheme();
  const rawRole = useAuthStore((s) => s.user?.role);
  const revenueAccess = !screenRedirectsToHub('revenue', rawRole);

  const dashboardQ = useQuery({
    queryKey: ['rms-dashboard'],
    queryFn: getRevenueDashboard,
    enabled: revenueAccess,
  });
  const forecastQ = useQuery({
    queryKey: ['rms-forecast'],
    queryFn: () => getOccupancyForecast(7),
    enabled: revenueAccess,
  });
  const strategyQ = useQuery({
    queryKey: ['rms-strategy'],
    queryFn: getPricingStrategy,
    enabled: revenueAccess,
  });
  const insightsQ = useQuery({
    queryKey: ['rms-insights'],
    queryFn: () => getPricingInsights(),
    enabled: revenueAccess,
  });
  const adjustmentsQ = useQuery({
    queryKey: ['rms-adjustments'],
    queryFn: () => listPriceAdjustments(),
    enabled: revenueAccess,
  });

  if (!revenueAccess) return <Redirect href={ROUTES.departments} />;

  const t = tr.departments.revenue;

  const renderMetric = (label: string, value: React.ReactNode) => (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: spacing.xs,
      }}
    >
      <Muted>{label}</Muted>
      <Body style={{ fontWeight: '600' }}>{value}</Body>
    </View>
  );

  const renderForecastDay = (d: ForecastDay, idx: number, last: boolean) => (
    <View
      key={d.date || `fc-${idx}`}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingVertical: spacing.sm,
        borderBottomWidth: last ? 0 : 1,
        borderBottomColor: c.border,
        gap: spacing.sm,
      }}
    >
      <View style={{ flex: 1 }}>
        <Body style={{ fontWeight: '600' }}>{formatDate(d.date)}</Body>
        <Muted>
          {t.occupancy}: %{(d.occupancy_pct ?? 0).toFixed(1)} · {d.available ?? 0}{' '}
          {t.roomsAvailable}
        </Muted>
      </View>
      <View style={{ alignItems: 'flex-end', gap: 4 }}>
        <Badge label={demandLabel(d.demand_level)} tone={demandTone(d.demand_level)} />
        <Muted style={{ fontSize: 11 }}>{riskLabel(d.demand_level)}</Muted>
      </View>
    </View>
  );

  const renderOpportunity = (o: RevenueOpportunity, idx: number) => (
    <Card key={o.date ? `${o.date}-${idx}` : `opp-${idx}`} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: spacing.sm,
        }}
      >
        <View style={{ flex: 1 }}>
          {o.date ? <Muted>{formatDate(o.date)}</Muted> : null}
          <Body style={{ marginTop: 2 }}>{o.message || '—'}</Body>
        </View>
        {typeof o.potential_revenue === 'number' ? (
          <View style={{ alignItems: 'flex-end' }}>
            <Muted style={{ fontSize: 11 }}>{t.potential}</Muted>
            <Body style={{ fontWeight: '700', color: c.success }}>
              {formatCurrency(o.potential_revenue)}
            </Body>
          </View>
        ) : null}
      </View>
    </Card>
  );

  const renderInsight = (ins: PricingInsight, idx: number) => (
    <Card key={`${ins.room_type || 'rt'}-${idx}`} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{ins.room_type || '—'}</Body>
          {ins.strategy ? <Muted>{ins.strategy}</Muted> : null}
        </View>
        {ins.confidence_level ? (
          <Badge
            label={confidenceLabel(ins.confidence_level)}
            tone={confidenceTone(ins.confidence_level)}
          />
        ) : null}
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        <Muted>
          {t.currentRate}: {formatCurrency(ins.current_rate)} →{' '}
          {t.suggestedRate}: {formatCurrency(ins.suggested_rate)}
        </Muted>
        {ins.reasoning ? <Muted>{ins.reasoning}</Muted> : null}
      </View>
    </Card>
  );

  const renderAdjustment = (a: PriceAdjustment, idx: number) => (
    <Card key={a.id || `adj-${idx}`} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{a.room_type || '—'}</Body>
          {a.reason ? <Muted>{a.reason}</Muted> : null}
        </View>
        <Body>
          {formatCurrency(a.old_rate)} → {formatCurrency(a.new_rate)}
        </Body>
      </View>
      {a.date ? <Muted style={{ marginTop: spacing.xs }}>{formatDate(a.date)}</Muted> : null}
    </Card>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{t.title}</H1>

      <SectionTitle title={t.cockpit} />
      {dashboardQ.isLoading || dashboardQ.error ? (
        <DepartmentListState
          loading={dashboardQ.isLoading}
          error={dashboardQ.error}
          isEmpty={false}
          skeletonCount={2}
        />
      ) : (
        <View style={{ gap: spacing.md }}>
          <KpiRow>
            <KpiCard
              testID="kpi-adr"
              label={t.adr}
              value={formatCurrency(dashboardQ.data?.period_30d?.adr ?? 0)}
              icon="cash-outline"
              tone="info"
            />
            <KpiCard
              testID="kpi-revpar"
              label={t.revpar}
              value={formatCurrency(dashboardQ.data?.period_30d?.revpar ?? 0)}
              icon="trending-up-outline"
              tone="info"
            />
          </KpiRow>
          <KpiRow>
            <KpiCard
              testID="kpi-occupancy"
              label={t.occupancyToday}
              value={`%${(dashboardQ.data?.today_occupancy_pct ?? 0).toFixed(1)}`}
              icon="bed-outline"
              tone={occupancyTone(dashboardQ.data?.today_occupancy_pct)}
            />
            <KpiCard
              testID="kpi-revenue-30d"
              label={t.revenue30d}
              value={formatCurrency(dashboardQ.data?.period_30d?.total_revenue ?? 0)}
              icon="wallet-outline"
              tone="success"
            />
          </KpiRow>
        </View>
      )}

      <SectionTitle title={t.strategy} />
      {strategyQ.isLoading || strategyQ.error ? (
        <DepartmentListState
          loading={strategyQ.isLoading}
          error={strategyQ.error}
          isEmpty={false}
          skeletonCount={1}
        />
      ) : strategyQ.data ? (
        <Card>
          {renderMetric(t.currentRate, formatCurrency(strategyQ.data.current_rate))}
          {renderMetric(t.recommendedRate, formatCurrency(strategyQ.data.recommended_rate))}
          {renderMetric(t.compAvgRate, formatCurrency(strategyQ.data.comp_avg_rate))}
          {renderMetric(t.marketPosition, marketPositionLabel(strategyQ.data.market_position))}
          {renderMetric(
            t.autoPricing,
            strategyQ.data.auto_pricing_enabled ? t.on : t.off,
          )}
          <View style={{ marginTop: spacing.sm }}>
            <Badge
              label={`${t.pendingRecommendations}: ${strategyQ.data.pending_recommendations ?? 0}`}
              tone={(strategyQ.data.pending_recommendations ?? 0) > 0 ? 'warning' : 'default'}
            />
          </View>
        </Card>
      ) : null}

      <SectionTitle title={t.forecast} />
      {forecastQ.isLoading || forecastQ.error ? (
        <DepartmentListState
          loading={forecastQ.isLoading}
          error={forecastQ.error}
          isEmpty={false}
          skeletonCount={1}
        />
      ) : (
        (() => {
          const days = forecastQ.data?.forecast || [];
          if (days.length === 0) {
            return (
              <Card>
                <Muted>{t.noForecast}</Muted>
              </Card>
            );
          }
          return (
            <Card>
              {days.map((d, i) => renderForecastDay(d, i, i === days.length - 1))}
            </Card>
          );
        })()
      )}

      <SectionTitle title={t.opportunities} />
      {dashboardQ.isLoading || dashboardQ.error ? null : (
        (() => {
          const items = dashboardQ.data?.opportunities || [];
          if (items.length === 0) {
            return (
              <Card>
                <Muted>{t.noOpportunities}</Muted>
              </Card>
            );
          }
          return <View>{items.map(renderOpportunity)}</View>;
        })()
      )}

      <SectionTitle title={t.insights} />
      {(() => {
        const items = insightsQ.data?.insights || [];
        const state = (
          <DepartmentListState
            loading={insightsQ.isLoading}
            error={insightsQ.error}
            isEmpty={items.length === 0}
            emptyText={t.noInsights}
          />
        );
        return state ?? <View>{items.map(renderInsight)}</View>;
      })()}

      <SectionTitle title={t.adjustments} />
      {(() => {
        const items = adjustmentsQ.data || [];
        const state = (
          <DepartmentListState
            loading={adjustmentsQ.isLoading}
            error={adjustmentsQ.error}
            isEmpty={items.length === 0}
            emptyText={t.noAdjustments}
          />
        );
        return state ?? <View>{items.map(renderAdjustment)}</View>;
      })()}
    </ScrollView>
  );
}
