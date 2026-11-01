import React, { useCallback, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, Share, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Body, Button, Card, H1, H2, Muted, SectionTitle, SkeletonCard } from '../../src/components/ui';
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
import { isOffline } from '../../src/utils/errors';
import { ROUTES } from '../../src/navigation/routes';
import { financeShareText, reportAmountLabel, reportArLabel, reportCountLabel, reportPercentLabel, reportTotalsLabel } from '../../src/utils/reportPresentation';

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
  const numberOrZero = (value: unknown) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const entries = Object.entries(data || {})
    .filter(([, stat]) => !!stat && typeof stat === 'object')
    .sort((a, b) => numberOrZero(b[1]?.revenue) - numberOrZero(a[1]?.revenue));
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
          <H2 style={{ textTransform: 'capitalize' }}>
            {!name || ['null', 'undefined', 'none'].includes(name.toLowerCase())
              ? tr.manager.unspecified
              : name.replaceAll('_', ' ')}
          </H2>
          <StatRow label="Rezervasyon tutarı" value={reportTotalsLabel(stat.revenue_by_currency)} tone="success" strong />
          <StatRow label={tr.manager.bookings} value={reportCountLabel(stat.bookings)} />
          <StatRow label={tr.manager.nights} value={reportCountLabel(stat.nights)} />
          <StatRow label="Ücretli gece ortalaması" value={reportTotalsLabel(stat.adr_by_currency)} />
          {!!stat.invalid_amounts && <Muted>{stat.invalid_amounts} kaydın tutarı doğrulanamadı.</Muted>}
        </Card>
      ))}
    </>
  );
}

export default function ReportsScreen() {
  const c = useTheme();
  const router = useRouter();
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

  // Custom-range selection states. A fully chosen custom range queries those
  // dates; clearing it (allowClear → both bounds undefined) falls back to the
  // current-month default (see `range` above) and re-fires the query. Only the
  // half-applied state (a start without an end) gates the query, so the section
  // never flickers a partial range while the user is mid-selection.
  const customComplete = !!customStart && !!customEnd;
  const customHalfApplied = preset === 'custom' && !!customStart !== !!customEnd;
  const showRangePrompt = preset === 'custom' && !customComplete;

  const finance = useQuery({
    queryKey: ['report-finance-snapshot'],
    queryFn: getFinanceSnapshot,
    enabled: financeReports,
  });
  const segment = useQuery({
    queryKey: ['report-market-segment', range.start, range.end],
    queryFn: () => getMarketSegment(range.start, range.end),
    enabled: financeReports && !customHalfApplied,
  });
  const aging = useQuery({
    queryKey: ['report-company-aging'],
    queryFn: getCompanyAging,
    enabled: financeReports,
  });

  const refreshing = finance.isFetching && !finance.isLoading;
  const onRefresh = useCallback(() => {
    if (!financeReports) return;
    finance.refetch();
    if (!customHalfApplied) segment.refetch();
    aging.refetch();
  }, [finance, segment, aging, financeReports, customHalfApplied]);

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
  const pendingArByCurrency = fin?.pending_ar.by_currency ?? {};
  const shareReport = async () => {
    if (!fin || finance.isError || !financeReports) return;
    await Share.share({
      title: 'Syroce operasyon özeti',
      message: financeShareText(fin),
    });
  };

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
        <Button title="Rapor özetini paylaş" variant="secondary" onPress={shareReport} disabled={!fin || finance.isError || finance.isFetching} fullWidth />
        <Button title="Finansal rapor detayını aç" variant="outline" onPress={() => router.push(ROUTES.reportDetail)} fullWidth />

        {/* ── Finance snapshot ── */}
        <SectionTitle title={tr.manager.financeSnapshot} />
        {finance.isLoading || finance.isError ? (
          <SectionState loading={finance.isLoading} error={finance.isError} />
        ) : fin ? (
          <Card testID="report-finance-snapshot">
            <StatRow
              label={tr.manager.pendingAr}
              value={reportArLabel(fin.pending_ar.by_currency)}
              tone="warning"
              strong
            />
            {fin.pending_ar.complete === false ? <Muted>Alacak kaynakları eksik; tutarlar kısmi.</Muted> : null}
            {Object.entries(pendingArByCurrency).map(([currency, bucket]) => (
              <React.Fragment key={`ar-${currency}`}>
                <StatRow label={`${tr.manager.overdue030} · ${currency}`} value={reportAmountLabel(bucket['0-30_days'], currency)} />
                <StatRow label={`${tr.manager.overdue3060} · ${currency}`} value={reportAmountLabel(bucket['30-60_days'], currency)} />
                <StatRow label={`${tr.manager.overdue60plus} · ${currency}`} value={reportAmountLabel(bucket['60_plus_days'], currency)} tone="danger" />
              </React.Fragment>
            ))}
            <StatRow label={tr.manager.overdueInvoices} value={String(fin.pending_ar.overdue_invoices_count)} />
            <View style={{ height: 1, backgroundColor: c.border, marginVertical: spacing.sm }} />
            <StatRow label={tr.manager.businessDateLabel} value={fin.business_date || fin.report_date} />
            <StatRow
              label={tr.manager.todaysCollections}
              value={`${reportAmountLabel(fin.todays_collections.amount, fin.todays_collections.currency)} (${reportCountLabel(fin.todays_collections.payment_count)} ${tr.manager.paymentCount})`}
              tone="success"
            />
            {fin.todays_collections.conversion_issue_count ? (
              <Muted>{fin.todays_collections.conversion_issue_count} {tr.manager.conversionIssues}</Muted>
            ) : null}
            <StatRow label={tr.manager.mtdCollections} value={reportAmountLabel(fin.mtd_collections.amount, fin.mtd_collections.currency)} tone="success" />
            <StatRow
              label={tr.manager.collectionRate}
              value={reportPercentLabel(fin.mtd_collections.collection_rate_percentage)}
            />
            {fin.mtd_collections.collection_rate_complete === false || !!fin.mtd_collections.conversion_issue_count
              ? <Muted>Kur veya gelir kaynağı eksik; ay içi özet kısmi ve tahsilat oranı doğrulanamadı.</Muted> : null}
            <StatRow
              label={tr.manager.pendingInvoices}
              value={`${reportTotalsLabel(fin.accounting_invoices.by_currency)} (${reportCountLabel(fin.accounting_invoices.pending_count)})`}
            />
          </Card>
        ) : null}

        {/* ── Market segment ── */}
        <SectionTitle title={tr.manager.marketSegment} />
        <Muted>Seçili giriş tarihindeki rezervasyon tutarlarıdır; işlenmiş gelir veya tahsilat değildir. Tarih filtresi yalnız bu bölüme uygulanır.</Muted>
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
        <Muted>{showRangePrompt ? tr.manager.rangePick : formatRangeLabel(range.start, range.end)}</Muted>
        {customHalfApplied ? null : segment.isLoading || segment.isError ? (
          <SectionState loading={segment.isLoading} error={segment.isError} />
        ) : (
          <SegmentList data={segment.data?.market_segments ?? {}} />
        )}

        {segment.data && Object.keys(segment.data.rate_types ?? {}).length > 0 ? (
          <>
            <SectionTitle title={tr.manager.rateTypes} />
            <SegmentList data={segment.data.rate_types} />
          </>
        ) : null}

        {/* ── Company aging ── */}
        <SectionTitle title={tr.manager.companyAging} />
        {aging.isLoading || aging.isError ? (
          <SectionState loading={aging.isLoading} error={aging.isError} />
        ) : (
          <>
            {aging.data ? (
              <Body style={{ color: c.textMuted }}>
                {tr.manager.totalAr}: {reportTotalsLabel(aging.data.total_ar_by_currency)}
              </Body>
            ) : null}
            {aging.data?.complete === false ? <Muted>Cari kaynakları eksik; bakiye kısmi.</Muted> : null}
            {companies.length === 0 ? (
              <Card>
                <Muted>{tr.manager.noCompanyAr}</Muted>
              </Card>
            ) : (
              companies.map((co) => (
                <Card key={`${co.company_id}-${co.account_id}-${co.corporate_code}-${co.currency}`} style={{ marginBottom: spacing.sm }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm }}>
                    <H2 style={{ flex: 1 }} numberOfLines={1}>{co.company_name}</H2>
                    <KpiPill label={`${co.folio_count} ${tr.manager.folios}`} />
                  </View>
                  <StatRow label={tr.manager.totalAr} value={reportAmountLabel(co.total_balance, co.currency)} tone="warning" strong />
                  <StatRow label={tr.manager.aging07} value={reportAmountLabel(co.aging['0-7 days'], co.currency)} />
                  <StatRow label={tr.manager.aging814} value={reportAmountLabel(co.aging['8-14 days'], co.currency)} />
                  <StatRow label={tr.manager.aging1530} value={reportAmountLabel(co.aging['15-30 days'], co.currency)} />
                  <StatRow label={tr.manager.aging30plus} value={reportAmountLabel(co.aging['30+ days'], co.currency)} tone="danger" />
                  {!!co.unaged_balance && <StatRow label="Vadesi belirlenemeyen" value={reportAmountLabel(co.unaged_balance, co.currency)} tone="warning" />}
                </Card>
              ))
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}
