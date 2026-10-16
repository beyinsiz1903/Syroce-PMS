import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, H1, Muted, SectionTitle, SkeletonCard, webCenter } from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { StatRow } from '../../src/components/StatRow';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { getToday } from '../../src/api/hub';
import { getFinanceSnapshot } from '../../src/api/reports';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { useOnline } from '../../src/hooks/useOnline';
import { todayOccupancy } from '../../src/utils/todayPresentation';
import { reservationCurrency } from '../../src/utils/reservationPresentation';
import { reportAmountLabel, reportCountLabel, reportCurrencyBuckets } from '../../src/utils/reportPresentation';

// A phone report is a shift decision aid, not a compressed desktop BI screen.
// Every staff member can open their workload. Hotel-wide metrics may be
// omitted by backend RBAC; financial reads keep their existing permission gate.
export default function FrontDeskReportsScreen() {
  const c = useTheme();
  const online = useOnline();
  const financeReports = useAuthStore((s) => s.financeReports);
  const today = useQuery({ queryKey: ['hub-today'], queryFn: getToday });
  const finance = useQuery({
    queryKey: ['report-finance-snapshot'],
    queryFn: getFinanceSnapshot,
    enabled: financeReports,
  });

  const refreshing = today.isRefetching || (financeReports && finance.isRefetching);
  const onRefresh = useCallback(() => {
    today.refetch();
    if (financeReports) finance.refetch();
  }, [today, finance, financeReports]);

  const offline = !online || today.fetchStatus === 'paused' || (today.isError && isOffline(today.error))
    || (financeReports && (finance.fetchStatus === 'paused' || (finance.isError && isOffline(finance.error))));
  const data = today.data;
  const fin = finance.data;
  const todayReady = today.isSuccess && !today.isPlaceholderData && !!data;
  const occupancy = todayOccupancy(data, !todayReady);
  const metric = (value: unknown) => reportCountLabel(todayReady ? value : undefined);
  const loadingToday = today.isLoading && !offline;
  const collections = fin?.todays_collections;
  const collectionCurrency = reservationCurrency(collections?.currency);
  const pendingAr = reportCurrencyBuckets(fin?.pending_ar?.by_currency);
  const conversionIssues = reportCountLabel(collections?.conversion_issue_count);

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="frontdesk-reports">
      <ScrollView
        contentContainerStyle={[{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }, webCenter]}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>Günlük Raporlar</H1>
        <Muted>Vardiya özeti ve size atanan işler.</Muted>
        {offline && (todayReady || (financeReports && finance.isSuccess && fin)) ? <Muted>{tr.today.cachedData}</Muted> : null}
        {data?.date ? <Muted>Operasyon tarihi · {data.date}</Muted> : null}
        {today.isError || (!loadingToday && !todayReady) ? (
          <Card accent={c.warning}>
            <Muted accessibilityLiveRegion="polite">{errorMessage(today.error, tr.hub.loadError)}</Muted>
            <Button title={tr.app.retry} variant="secondary" onPress={() => { void today.refetch(); }} fullWidth />
          </Card>
        ) : null}

        <SectionTitle title="Operasyon Özeti" />
        {loadingToday ? (
          <>
            <KpiRow><SkeletonCard /><SkeletonCard /></KpiRow>
            <KpiRow><SkeletonCard /><SkeletonCard /></KpiRow>
          </>
        ) : (
          <>
            <KpiRow>
              <KpiCard icon="pie-chart" label="Doluluk" value={occupancy ? `%${occupancy.percentage.toFixed(0)}` : '—'} tone={occupancy ? 'info' : 'default'} testID="report-occupancy" />
              <KpiCard icon="bed" label="Dolu Oda" value={occupancy ? `${occupancy.occupied}/${occupancy.total}` : '—'} tone={occupancy ? 'success' : 'default'} testID="report-occupied-rooms" />
            </KpiRow>
            <KpiRow>
              <KpiCard icon="log-in-outline" label="Giriş" value={metric(data?.check_ins)} tone="info" testID="report-arrivals" />
              <KpiCard icon="log-out-outline" label="Çıkış" value={metric(data?.check_outs)} tone="default" testID="report-departures" />
            </KpiRow>
            <Card><StatRow label="Otel genelinde açık arıza" value={metric(data?.open_faults)} tone="warning" /></Card>
            {!occupancy || metric(data?.check_ins) === '—' || metric(data?.check_outs) === '—' || metric(data?.open_faults) === '—' ? (
              <Muted>Bazı otel geneli veriler bu hesap için doğrulanamadı. Bilinmeyen değerler — ile gösterilir.</Muted>
            ) : null}
          </>
        )}

        <SectionTitle title="Bana Atanan İşler" />
        {loadingToday ? (
          <SkeletonCard />
        ) : (
          <Card>
            <StatRow label="Açık görevim" value={metric(data?.open_tasks)} tone="warning" strong />
            <StatRow label="Öncelikli görevim" value={metric(data?.urgent_tasks)} tone="danger" />
          </Card>
        )}

        {financeReports ? (
          <>
            <SectionTitle title="Tahsilat & Alacak" />
            {finance.isLoading && !offline ? (
              <SkeletonCard />
            ) : finance.isError || !fin ? (
              <Card accent={c.warning}>
                <Muted accessibilityLiveRegion="polite">{errorMessage(finance.error, 'Finansal özet şu an yüklenemedi.')}</Muted>
                <Button title={tr.app.retry} variant="secondary" onPress={() => { void finance.refetch(); }} fullWidth />
              </Card>
            ) : fin ? (
              <Card testID="frontdesk-finance-summary">
                <Muted>PMS iş günü · {fin.business_date || fin.report_date || 'Bilgi yok'}</Muted>
                <StatRow label="İş günü tahsilatı" value={reportAmountLabel(collections?.amount, collectionCurrency)} tone="success" strong />
                <StatRow label="Ödeme sayısı" value={reportCountLabel(collections?.payment_count)} />
                {!collectionCurrency ? <Muted>Tahsilat para birimi doğrulanamadı.</Muted> : null}
                {pendingAr.kind === 'data' ? pendingAr.buckets.map((bucket, index) => (
                  <StatRow key={`ar-${bucket.currency || index}`} label={`Bekleyen alacak · ${bucket.currency || 'Para birimi yok'}`} value={reportAmountLabel(bucket.total, bucket.currency)} tone="warning" />
                )) : <Muted>{pendingAr.kind === 'empty' ? 'Bekleyen alacak kaydı yok.' : 'Alacakların para birimi dağılımı alınamadı.'}</Muted>}
                <StatRow label="Vadesi geçen fatura" value={reportCountLabel(fin.pending_ar?.overdue_invoices_count)} tone="danger" />
                {conversionIssues !== '—' && conversionIssues !== '0' ? (
                  <Muted>{conversionIssues} {tr.manager.conversionIssues}</Muted>
                ) : null}
              </Card>
            ) : null}
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}
