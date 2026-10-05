import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Card, H1, Muted, SectionTitle, SkeletonCard } from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { StatRow } from '../../src/components/StatRow';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { getToday } from '../../src/api/hub';
import { getFinanceSnapshot } from '../../src/api/reports';
import { formatCurrency } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';

// A phone report is a shift decision aid, not a compressed desktop BI screen.
// Every staff member can see live operational numbers. Financial totals are
// queried only for roles that pass the existing backend finance permission.
export default function FrontDeskReportsScreen() {
  const c = useTheme();
  const financeReports = useAuthStore((s) => s.financeReports);
  const today = useQuery({ queryKey: ['hub-today'], queryFn: getToday });
  const finance = useQuery({
    queryKey: ['report-finance-snapshot'],
    queryFn: getFinanceSnapshot,
    enabled: financeReports,
  });

  const refreshing = today.isFetching && !today.isLoading;
  const onRefresh = useCallback(() => {
    today.refetch();
    if (financeReports) finance.refetch();
  }, [today, finance, financeReports]);

  const offline = today.isError && isOffline(today.error);
  const data = today.data;
  const fin = finance.data;

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="frontdesk-reports">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>Günlük Raporlar</H1>
        <Muted>Vardiya için gerekli canlı özetler.</Muted>

        <SectionTitle title="Bugün Operasyon" />
        {today.isLoading ? (
          <>
            <KpiRow><SkeletonCard /><SkeletonCard /></KpiRow>
            <KpiRow><SkeletonCard /><SkeletonCard /></KpiRow>
          </>
        ) : today.isError ? (
          <Card><Muted>{tr.hub.loadError}</Muted></Card>
        ) : (
          <>
            <KpiRow>
              <KpiCard icon="pie-chart" label="Doluluk" value={`%${(data?.occupancy_pct ?? 0).toFixed(0)}`} tone="info" />
              <KpiCard icon="bed" label="Dolu Oda" value={`${data?.occupied_rooms ?? 0}/${data?.total_rooms ?? 0}`} tone="success" />
            </KpiRow>
            <KpiRow>
              <KpiCard icon="log-in-outline" label="Giriş" value={String(data?.check_ins ?? 0)} tone="info" />
              <KpiCard icon="log-out-outline" label="Çıkış" value={String(data?.check_outs ?? 0)} tone="default" />
            </KpiRow>
          </>
        )}

        <SectionTitle title="Açık İşler" />
        {today.isLoading ? (
          <SkeletonCard />
        ) : today.isError ? (
          <Card><Muted>{tr.hub.loadError}</Muted></Card>
        ) : (
          <Card>
            <StatRow label="Açık görev" value={String(data?.open_tasks ?? 0)} tone="warning" strong />
            <StatRow label="Acil görev" value={String(data?.urgent_tasks ?? 0)} tone="danger" />
            <StatRow label="Açık arıza" value={String(data?.open_faults ?? 0)} tone="warning" />
          </Card>
        )}

        {financeReports ? (
          <>
            <SectionTitle title="Tahsilat & Alacak" />
            {finance.isLoading ? (
              <SkeletonCard />
            ) : finance.isError ? (
              <Card><Muted>Finansal özet şu an yüklenemedi.</Muted></Card>
            ) : fin ? (
              <Card testID="frontdesk-finance-summary">
                <StatRow label="Bugünkü tahsilat" value={`${formatCurrency(fin.todays_collections.amount)} (${fin.todays_collections.payment_count})`} tone="success" strong />
                <StatRow label="Bekleyen alacak" value={formatCurrency(fin.pending_ar.total)} tone="warning" />
                <StatRow label="Vadesi geçen fatura" value={String(fin.pending_ar.overdue_invoices_count)} tone="danger" />
              </Card>
            ) : null}
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}
