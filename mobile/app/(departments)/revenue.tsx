import React from 'react';
import { ScrollView, Text, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import { Badge, Body, Card, H1, Muted, webCenter } from '../../src/components/ui';
import { KpiCard, KpiRow, type KpiTone } from '../../src/components/KpiCard';
import {
  DepartmentListState,
  SectionTitle,
} from '../../src/components/department';
import { radius, spacing, useTheme } from '../../src/theme';
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
  getChannelPerformance,
  type PriceAdjustment,
  type PricingInsight,
  type ForecastDay,
  type RevenueOpportunity,
  type ChannelStat,
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

// Higher direct-booking share = healthier channel parity (less OTA commission
// leakage). The backend flags `direct_booking_incentive` when the direct share
// drops below its threshold; we mirror that into the cockpit tile colour.
function parityTone(incentive?: boolean, share?: number): KpiTone {
  if (typeof share !== 'number') return 'default';
  if (incentive) return 'warning';
  return 'success';
}

// Pretty channel labels for the well-known source keys; anything else is shown
// verbatim (capitalised) so new OTA channels still render sensibly.
function channelLabel(ch?: string): string {
  if (!ch) return '—';
  const map: Record<string, string> = {
    direct: 'Direkt',
    walk_in: 'Walk-in',
    'walk-in': 'Walk-in',
    phone: 'Telefon',
    website: 'Web Sitesi',
    ota: 'OTA',
  };
  if (map[ch]) return map[ch];
  return ch.charAt(0).toUpperCase() + ch.slice(1);
}

// Read-only Revenue Management screen. The KPI cockpit (ADR / RevPAR /
// occupancy / channel parity), channel mix and forecast come from the auth-only
// revenue-engine reads; the AI pricing recommendations, strategy and
// price-adjustment log come from the rms reads. The (departments) revenue
// entitlement (view_revenue = VIEW_FINANCIAL_REPORTS roles) decides whether we
// show the screen; rate mutations stay backend-gated by require_op("manage_rates").
export default function RevenueScreen() {
  const c = useTheme();
  const rawRole = useAuthStore((s) => s.user?.role);
  const revenueAccess = !screenRedirectsToHub('revenue', rawRole);

  const dashboardQ = useQuery({
    queryKey: ['rms-dashboard'],
    queryFn: getRevenueDashboard,
    enabled: revenueAccess,
  });
  const channelQ = useQuery({
    queryKey: ['rms-channel-performance'],
    queryFn: () => getChannelPerformance(30),
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

  const directShare = channelQ.data?.direct_booking_share;
  const parityValue =
    typeof directShare === 'number' ? `%${directShare.toFixed(1)}` : '—';

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

  const renderChannelRow = (s: ChannelStat, idx: number, last: boolean) => {
    const revShare = s.revenue_share_pct ?? 0;
    return (
      <View
        key={s.channel ? `${s.channel}-${idx}` : `ch-${idx}`}
        style={{
          paddingVertical: spacing.sm,
          borderBottomWidth: last ? 0 : 1,
          borderBottomColor: c.border,
          gap: spacing.xs,
        }}
      >
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: spacing.sm,
          }}
        >
          <View style={{ flex: 1 }}>
            <Body style={{ fontWeight: '600' }}>{channelLabel(s.channel)}</Body>
            <Muted style={{ fontSize: 11 }}>
              {s.bookings ?? 0} rez. · {formatCurrency(s.revenue)}
            </Muted>
          </View>
          <Badge
            label={`${t.bookingShare}: %${(s.booking_share_pct ?? 0).toFixed(1)}`}
            tone={s.channel === 'direct' ? 'success' : 'info'}
          />
        </View>
        <View
          style={{
            height: 6,
            borderRadius: radius.pill,
            backgroundColor: c.surfaceAlt,
            overflow: 'hidden',
          }}
        >
          <View
            style={{
              width: `${Math.max(0, Math.min(100, revShare))}%`,
              height: '100%',
              borderRadius: radius.pill,
              backgroundColor: s.channel === 'direct' ? c.success : c.primary,
            }}
          />
        </View>
        <Muted style={{ fontSize: 11 }}>
          {t.revenueShare}: %{revShare.toFixed(1)}
        </Muted>
      </View>
    );
  };

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

  // Premium AI recommendation card. The recommendation direction (raise / lower
  // / hold) is derived from the backend's real suggested-vs-current delta — no
  // synthetic numbers. The card is visual only: applying a rate stays backend-
  // gated (require_op manage_rates) and is intentionally not wired here.
  const renderInsight = (ins: PricingInsight, idx: number) => {
    const current = ins.current_rate ?? 0;
    const suggested = ins.suggested_rate ?? 0;
    const pct =
      typeof ins.price_change_pct === 'number'
        ? ins.price_change_pct
        : current > 0
          ? ((suggested - current) / current) * 100
          : 0;
    const dir: 'up' | 'down' | 'flat' = pct > 0.01 ? 'up' : pct < -0.01 ? 'down' : 'flat';
    const accent = dir === 'up' ? c.success : dir === 'down' ? c.warning : c.info;
    const dirIcon = dir === 'up' ? 'trending-up' : dir === 'down' ? 'trending-down' : 'remove';
    const dirLabel = dir === 'up' ? t.raisePrice : dir === 'down' ? t.lowerPrice : t.holdPrice;
    const pctText = `${pct > 0 ? '+' : ''}%${Math.abs(pct).toFixed(1)}`;

    return (
      <Card
        key={`${ins.room_type || 'rt'}-${idx}`}
        accent={accent}
        style={{ marginBottom: spacing.sm }}
      >
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: spacing.sm,
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flex: 1 }}>
            <View
              style={{
                width: 28,
                height: 28,
                borderRadius: radius.pill,
                backgroundColor: c.primary + '1f',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Ionicons name="sparkles" size={15} color={c.primary} />
            </View>
            <Body style={{ fontWeight: '700', flex: 1 }} numberOfLines={1}>
              {ins.room_type || '—'}
            </Body>
          </View>
          {ins.confidence_level ? (
            <Badge
              label={confidenceLabel(ins.confidence_level)}
              tone={confidenceTone(ins.confidence_level)}
            />
          ) : null}
        </View>

        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: spacing.xs,
            marginTop: spacing.md,
          }}
        >
          <Ionicons name={dirIcon} size={18} color={accent} />
          <Text style={{ color: accent, fontSize: 16, fontWeight: '800' }}>{dirLabel}</Text>
          <Text style={{ color: accent, fontSize: 16, fontWeight: '800' }}>{pctText}</Text>
        </View>

        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: spacing.sm,
            marginTop: spacing.sm,
          }}
        >
          <View>
            <Muted style={{ fontSize: 11 }}>{t.currentRate}</Muted>
            <Body style={{ fontWeight: '600' }}>{formatCurrency(current)}</Body>
          </View>
          <Ionicons name="arrow-forward" size={16} color={c.textMuted} />
          <View>
            <Muted style={{ fontSize: 11 }}>{t.suggestedRate}</Muted>
            <Body style={{ fontWeight: '800', color: accent }}>{formatCurrency(suggested)}</Body>
          </View>
        </View>

        {ins.reasoning ? (
          <Muted style={{ marginTop: spacing.sm }}>{ins.reasoning}</Muted>
        ) : null}
        {ins.strategy ? (
          <View style={{ marginTop: spacing.sm }}>
            <Badge label={ins.strategy} tone="info" icon="analytics-outline" />
          </View>
        ) : null}
      </Card>
    );
  };

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
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
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
              testID="kpi-channel-parity"
              label={t.channelParity}
              value={parityValue}
              icon="git-compare-outline"
              tone={parityTone(channelQ.data?.direct_booking_incentive, directShare)}
            />
          </KpiRow>
          <KpiRow>
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

      <SectionTitle title={t.channelMix} />
      {channelQ.isLoading || channelQ.error ? (
        <DepartmentListState
          loading={channelQ.isLoading}
          error={channelQ.error}
          isEmpty={false}
          skeletonCount={1}
        />
      ) : (
        (() => {
          const channels = channelQ.data?.channels || [];
          if (channels.length === 0) {
            return (
              <Card>
                <Muted>{t.noChannels}</Muted>
              </Card>
            );
          }
          const incentive = channelQ.data?.direct_booking_incentive;
          return (
            <Card>
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: spacing.xs,
                  marginBottom: spacing.xs,
                }}
              >
                <Ionicons
                  name={incentive ? 'alert-circle-outline' : 'checkmark-circle-outline'}
                  size={16}
                  color={incentive ? c.warning : c.success}
                />
                <Muted style={{ flex: 1 }}>
                  {t.directShare}: %{(directShare ?? 0).toFixed(1)} ·{' '}
                  {incentive ? t.directIncentiveHint : t.directHealthyHint}
                </Muted>
              </View>
              {channels.map((s, i) => renderChannelRow(s, i, i === channels.length - 1))}
            </Card>
          );
        })()
      )}

      <SectionTitle title={t.aiRecommendations} />
      <Muted style={{ marginBottom: spacing.sm }}>{t.aiTagline}</Muted>
      {(() => {
        const items = insightsQ.data?.insights || [];
        const summary = insightsQ.data?.summary;
        if (insightsQ.isLoading || insightsQ.error || items.length === 0) {
          return (
            <DepartmentListState
              loading={insightsQ.isLoading}
              error={insightsQ.error}
              isEmpty={items.length === 0}
              emptyText={t.noInsights}
            />
          );
        }
        return (
          <View>
            {summary ? (
              <Card style={{ marginBottom: spacing.sm }}>
                <View
                  style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    gap: spacing.sm,
                  }}
                >
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: c.text, fontSize: 20, fontWeight: '800' }}>
                      {summary.total_recommendations ?? items.length}
                    </Text>
                    <Muted style={{ fontSize: 11, textAlign: 'center' }}>{t.recCount}</Muted>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: c.info, fontSize: 20, fontWeight: '800' }}>
                      %{Math.round((summary.avg_confidence ?? 0) * 100)}
                    </Text>
                    <Muted style={{ fontSize: 11, textAlign: 'center' }}>{t.avgConfidence}</Muted>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: c.success, fontSize: 20, fontWeight: '800' }}>
                      {summary.recommended_increase ?? 0}
                    </Text>
                    <Muted style={{ fontSize: 11, textAlign: 'center' }}>{t.increaseCount}</Muted>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ color: c.warning, fontSize: 20, fontWeight: '800' }}>
                      {summary.recommended_decrease ?? 0}
                    </Text>
                    <Muted style={{ fontSize: 11, textAlign: 'center' }}>{t.decreaseCount}</Muted>
                  </View>
                </View>
              </Card>
            ) : null}
            {items.map(renderInsight)}
          </View>
        );
      })()}

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
