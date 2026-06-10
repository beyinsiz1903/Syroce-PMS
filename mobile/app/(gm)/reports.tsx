import React, { useCallback, useMemo } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Body, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiPill } from '../../src/components/KpiCard';
import { StatRow } from '../../src/components/StatRow';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import {
  SegmentStat,
  currentMonthRange,
  getCompanyAging,
  getFinanceSnapshot,
  getMarketSegment,
} from '../../src/api/reports';
import { formatCurrency } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';

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
  const range = useMemo(() => currentMonthRange(), []);

  const finance = useQuery({
    queryKey: ['report-finance-snapshot'],
    queryFn: getFinanceSnapshot,
    enabled: financeReports,
  });
  const segment = useQuery({
    queryKey: ['report-market-segment', range.start, range.end],
    queryFn: () => getMarketSegment(range.start, range.end),
    enabled: financeReports,
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
        <Muted>{tr.manager.segmentPeriod}</Muted>
        {segment.isLoading || segment.isError ? (
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
