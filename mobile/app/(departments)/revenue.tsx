import React from 'react';
import { ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, H2, Muted } from '../../src/components/ui';
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
  type PriceAdjustment,
  type PricingInsight,
} from '../../src/api/revenue';
import { formatCurrency, formatDate } from '../../src/utils/format';

function marketPositionLabel(pos?: string): string {
  const map = tr.departments.revenue.marketPositions as Record<string, string>;
  return (pos && map[pos]) || pos || '—';
}

function confidenceTone(level?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info' {
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

// Read-only Revenue Management screen: pricing strategy snapshot, AI pricing
// insights and the recent price-adjustment log. Backend GET reads only require
// auth; the (departments) revenue entitlement (view_revenue =
// VIEW_FINANCIAL_REPORTS roles) decides whether we show the screen. Rate
// mutations stay backend-gated by require_op("manage_rates").
export default function RevenueScreen() {
  const c = useTheme();
  const rawRole = useAuthStore((s) => s.user?.role);
  const revenueAccess = !screenRedirectsToHub('revenue', rawRole);

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
          {tr.departments.revenue.currentRate}: {formatCurrency(ins.current_rate)} →{' '}
          {tr.departments.revenue.suggestedRate}: {formatCurrency(ins.suggested_rate)}
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
      <H1>{tr.departments.revenue.title}</H1>

      <SectionTitle title={tr.departments.revenue.strategy} />
      {strategyQ.isLoading || strategyQ.error ? (
        <DepartmentListState
          loading={strategyQ.isLoading}
          error={strategyQ.error}
          isEmpty={false}
          skeletonCount={1}
        />
      ) : strategyQ.data ? (
        <Card>
          {renderMetric(
            tr.departments.revenue.currentRate,
            formatCurrency(strategyQ.data.current_rate),
          )}
          {renderMetric(
            tr.departments.revenue.recommendedRate,
            formatCurrency(strategyQ.data.recommended_rate),
          )}
          {renderMetric(
            tr.departments.revenue.compAvgRate,
            formatCurrency(strategyQ.data.comp_avg_rate),
          )}
          {renderMetric(
            tr.departments.revenue.marketPosition,
            marketPositionLabel(strategyQ.data.market_position),
          )}
          {renderMetric(
            tr.departments.revenue.autoPricing,
            strategyQ.data.auto_pricing_enabled
              ? tr.departments.revenue.on
              : tr.departments.revenue.off,
          )}
          <View style={{ marginTop: spacing.sm }}>
            <Badge
              label={`${tr.departments.revenue.pendingRecommendations}: ${
                strategyQ.data.pending_recommendations ?? 0
              }`}
              tone={
                (strategyQ.data.pending_recommendations ?? 0) > 0 ? 'warning' : 'default'
              }
            />
          </View>
        </Card>
      ) : null}

      <SectionTitle title={tr.departments.revenue.insights} />
      {(() => {
        const items = insightsQ.data?.insights || [];
        const state = (
          <DepartmentListState
            loading={insightsQ.isLoading}
            error={insightsQ.error}
            isEmpty={items.length === 0}
            emptyText={tr.departments.revenue.noInsights}
          />
        );
        return state ?? <View>{items.map(renderInsight)}</View>;
      })()}

      <SectionTitle title={tr.departments.revenue.adjustments} />
      {(() => {
        const items = adjustmentsQ.data || [];
        const state = (
          <DepartmentListState
            loading={adjustmentsQ.isLoading}
            error={adjustmentsQ.error}
            isEmpty={items.length === 0}
            emptyText={tr.departments.revenue.noAdjustments}
          />
        );
        return state ?? <View>{items.map(renderAdjustment)}</View>;
      })()}
    </ScrollView>
  );
}
