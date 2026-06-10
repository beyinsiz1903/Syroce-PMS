import React, { useCallback, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Body, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiPill } from '../../src/components/KpiCard';
import { StatRow } from '../../src/components/StatRow';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { FilterChips, FilterChipOption } from '../../src/components/FilterChips';
import { DatePicker } from '../../src/components/DatePicker';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import {
  SegmentStat,
  currentMonthRange,
  lastMonthRange,
  last30DaysRange,
  getCompanyAging,
  getFinanceSnapshot,
  getMarketSegment,
} from '../../src/api/reports';
import { formatCurrency } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';

type RangePreset = 'this_month' | 'last_month' | 'last_30' | 'custom';

const RANGE_OPTIONS: FilterChipOption[] = [
  { value: 'this_month', label: tr.manager.rangeThisMonth },
  { value: 'last_month', label: tr.manager.rangeLastMonth },
  { value: 'last_30', label: tr.manager.rangeLast30 },
  { value: 'custom', label: tr.manager.rangeCustom },
];

// Render an ISO (YYYY-MM-DD) range as a human-friendly Turkish label.
function formatRangeLabel(start: string, end: string): string {
  const parse = (iso: string): Date | null => {
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  };
  const fmt = (d: Date) =>
    d.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
  const s = parse(start);
  const e = parse(end);
  if (!s || !e) return `${start} → ${end}`;
  return `${fmt(s)} → ${fmt(e)}`;
}

function SectionState({ loading, error }: { loading: boolean; error: boolean }) {
  if (loading) return <SkeletonCard />;
  if (error) {
    return (
      <Card>
        <Muted>{tr.manager.loadError}</Muted>
      </Card>
    );
  }
  return null;
}

function SegmentList({ data }: { data: Record<string, SegmentStat> }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1].revenue - a[1].revenue);
  if (entries.length === 0) {
    return (
      <Card>
        <Muted>{tr.manager.noSegmentData}</Muted>
      </Card>
    );
  }
  return (
    <>
      {entries.map(([name, stat]) => (
        <Card key={name} style={{ marginBottom: spacing.sm }}>
          <H2 style={{ textTransform: 'capitalize' }}>{name}</H2>
          <StatRow label={tr.manager.revenue} value={formatCurrency(stat.revenue)} tone="success" strong />
          <StatRow label={tr.manager.bookings} value={String(stat.bookings)} />
          <StatRow label={tr.manager.nights} value={String(stat.nights)} />
          <StatRow label={tr.manager.adr} value={formatCurrency(stat.adr)} />
        </Card>
      ))}
    </>
  );
}

export default function ReportsScreen() {
  const c = useTheme();
  const financeReports = useAuthStore((s) => s.financeReports);

  const [preset, setPreset] = useState<RangePreset>('this_month');
  // Custom-range bounds (ISO YYYY-MM-DD), only used when preset === 'custom'.
  const [customStart, setCustomStart] = useState<string | undefined>(undefined);
  const [customEnd, setCustomEnd] = useState<string | undefined>(undefined);

  const range = useMemo(() => {
    if (preset === 'last_month') return lastMonthRange();
    if (preset === 'last_30') return last30DaysRange();
    if (preset === 'custom' && customStart && customEnd) {
      return { start: customStart, end: customEnd };
    }
    return currentMonthRange();
  }, [preset, customStart, customEnd]);

  // Only query once a custom range is fully chosen; otherwise fall back to the
  // current-month default so the section never shows a half-applied range.
  const customReady = preset !== 'custom' || (!!customStart && !!customEnd);

  const finance = useQuery({
    queryKey: ['report-finance-snapshot'],
    queryFn: getFinanceSnapshot,
    enabled: financeReports,
  });
  const segment = useQuery({
    queryKey: ['report-market-segment', range.start, range.end],
    queryFn: () => getMarketSegment(range.start, range.end),
    enabled: financeReports && customReady,
  });
  const aging = useQuery({
    queryKey: ['report-company-aging'],
    queryFn: getCompanyAging,
    enabled: financeReports,
  });

  const refreshing = finance.isFetching && !finance.isLoading;
  const onRefresh = useCallback(() => {
    finance.refetch();
    segment.refetch();
    aging.refetch();
  }, [finance, segment, aging]);

  const offline = finance.isError && isOffline(finance.error);

  // Defensive cosmetic guard — the Reports tab is already hidden for roles
  // without view_finance_reports, and the backend enforces it regardless.
  if (!financeReports) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }}>
        <H1>{tr.manager.reportsTitle}</H1>
        <Card style={{ marginTop: spacing.md }}>
          <Muted>{tr.manager.reportsNoAccess}</Muted>
        </Card>
      </View>
    );
  }

  const fin = finance.data;
  const companies = aging.data?.companies ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.manager.reportsTitle}</H1>

        {/* ── Finance snapshot ── */}
        <H2>{tr.manager.financeSnapshot}</H2>
        {finance.isLoading || finance.isError ? (
          <SectionState loading={finance.isLoading} error={finance.isError} />
        ) : fin ? (
          <Card testID="report-finance-snapshot">
            <StatRow
              label={tr.manager.pendingAr}
              value={formatCurrency(fin.pending_ar.total)}
              tone="warning"
              strong
            />
            <StatRow label={tr.manager.overdue030} value={formatCurrency(fin.pending_ar.overdue_breakdown['0-30_days'])} />
            <StatRow label={tr.manager.overdue3060} value={formatCurrency(fin.pending_ar.overdue_breakdown['30-60_days'])} />
            <StatRow label={tr.manager.overdue60plus} value={formatCurrency(fin.pending_ar.overdue_breakdown['60_plus_days'])} tone="danger" />
            <StatRow label={tr.manager.overdueInvoices} value={String(fin.pending_ar.overdue_invoices_count)} />
            <View style={{ height: 1, backgroundColor: c.border, marginVertical: spacing.sm }} />
            <StatRow
              label={tr.manager.todaysCollections}
              value={`${formatCurrency(fin.todays_collections.amount)} (${fin.todays_collections.payment_count} ${tr.manager.paymentCount})`}
              tone="success"
            />
            <StatRow label={tr.manager.mtdCollections} value={formatCurrency(fin.mtd_collections.amount)} tone="success" />
            <StatRow
              label={tr.manager.collectionRate}
              value={`%${fin.mtd_collections.collection_rate_percentage.toFixed(1)}`}
            />
            <StatRow
              label={tr.manager.pendingInvoices}
              value={`${formatCurrency(fin.accounting_invoices.pending_total)} (${fin.accounting_invoices.pending_count})`}
            />
          </Card>
        ) : null}

        {/* ── Market segment ── */}
        <H2 style={{ marginTop: spacing.sm }}>{tr.manager.marketSegment}</H2>
        <FilterChips
          options={RANGE_OPTIONS}
          value={preset}
          onChange={(v) => setPreset(v as RangePreset)}
          testID="report-segment-range"
        />
        {preset === 'custom' ? (
          <DatePicker
            mode="range"
            placeholder={tr.manager.rangePick}
            startValue={customStart}
            endValue={customEnd}
            onRangeChange={(start, end) => {
              setCustomStart(start);
              setCustomEnd(end);
            }}
            allowClear
            testID="report-segment-custom"
          />
        ) : null}
        <Muted>{customReady ? formatRangeLabel(range.start, range.end) : tr.manager.rangePick}</Muted>
        {!customReady ? null : segment.isLoading || segment.isError ? (
          <SectionState loading={segment.isLoading} error={segment.isError} />
        ) : (
          <SegmentList data={segment.data?.market_segments ?? {}} />
        )}

        {segment.data && Object.keys(segment.data.rate_types ?? {}).length > 0 ? (
          <>
            <H2 style={{ marginTop: spacing.sm }}>{tr.manager.rateTypes}</H2>
            <SegmentList data={segment.data.rate_types} />
          </>
        ) : null}

        {/* ── Company aging ── */}
        <H2 style={{ marginTop: spacing.sm }}>{tr.manager.companyAging}</H2>
        {aging.isLoading || aging.isError ? (
          <SectionState loading={aging.isLoading} error={aging.isError} />
        ) : (
          <>
            {aging.data ? (
              <Body style={{ color: c.textMuted }}>
                {tr.manager.totalAr}: {formatCurrency(aging.data.total_ar)}
              </Body>
            ) : null}
            {companies.length === 0 ? (
              <Card>
                <Muted>{tr.manager.noCompanyAr}</Muted>
              </Card>
            ) : (
              companies.map((co) => (
                <Card key={`${co.company_name}-${co.corporate_code}`} style={{ marginBottom: spacing.sm }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm }}>
                    <H2 style={{ flex: 1 }} numberOfLines={1}>{co.company_name}</H2>
                    <KpiPill label={`${co.folio_count} ${tr.manager.folios}`} />
                  </View>
                  <StatRow label={tr.manager.totalAr} value={formatCurrency(co.total_balance)} tone="warning" strong />
                  <StatRow label={tr.manager.aging07} value={formatCurrency(co.aging['0-7 days'])} />
                  <StatRow label={tr.manager.aging814} value={formatCurrency(co.aging['8-14 days'])} />
                  <StatRow label={tr.manager.aging1530} value={formatCurrency(co.aging['15-30 days'])} />
                  <StatRow label={tr.manager.aging30plus} value={formatCurrency(co.aging['30+ days'])} tone="danger" />
                </Card>
              ))
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}
