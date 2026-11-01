import React from 'react';
import { ScrollView, Share, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Body, Button, Card, H1, Muted, SectionTitle, SkeletonCard } from '../../src/components/ui';
import { StatRow } from '../../src/components/StatRow';
import { getCompanyAging, getFinanceSnapshot } from '../../src/api/reports';
import { useAuthStore } from '../../src/state/authStore';
import { financeShareText, reportAmountLabel, reportArLabel, reportCountLabel, reportTotalsLabel } from '../../src/utils/reportPresentation';
import { spacing, useTheme } from '../../src/theme';

export default function ReportDetailScreen() {
  const c = useTheme();
  const allowed = useAuthStore((s) => s.financeReports);
  const finance = useQuery({ queryKey: ['report-finance-snapshot'], queryFn: getFinanceSnapshot, enabled: allowed });
  const aging = useQuery({ queryKey: ['report-company-aging'], queryFn: getCompanyAging, enabled: allowed });
  const fin = finance.data;
  const share = async () => {
    if (!allowed || !fin || finance.isError) return;
    await Share.share({ title: 'Syroce finans raporu', message: financeShareText(fin) });
  };
  if (!allowed) return <Card><Muted>Bu finansal rapor için yetkiniz yok.</Muted></Card>;
  return <View style={{ flex: 1, backgroundColor: c.bg }}>
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 100 }}>
      <H1>Finansal rapor detayı</H1>
      <Muted>PMS iş günü · {fin?.business_date || fin?.report_date || 'Bilgi yok'}</Muted>
      {finance.isLoading ? <SkeletonCard /> : finance.isError || !fin ? <Card>
        <Muted>Finansal özet yüklenemedi. Önceki veri paylaşılmaz.</Muted>
        <Button title="Yeniden dene" onPress={() => { void finance.refetch(); }} />
      </Card> : <Card>
        <StatRow label="Bekleyen alacak" value={reportArLabel(fin.pending_ar.by_currency)} tone="warning" strong />
        {fin.pending_ar.complete === false ? <Muted>Kaynaklar eksik; alacak tutarları kısmi.</Muted> : null}
        <StatRow label="Vadesi geçmiş fatura" value={reportCountLabel(fin.pending_ar.overdue_invoices_count)} />
        <StatRow label="Ay içi tahsilat" value={reportAmountLabel(fin.mtd_collections.amount, fin.mtd_collections.currency)} tone="success" />
        {!!fin.mtd_collections.conversion_issue_count && <Muted>Kur verisi eksik; tahsilat özeti kısmi.</Muted>}
      </Card>}
      <SectionTitle title="Cari hesaplar" />
      {aging.isLoading ? <SkeletonCard /> : aging.isError || !aging.data ? <Card>
        <Muted>Cari hesaplar yüklenemedi.</Muted><Button title="Yeniden dene" onPress={() => { void aging.refetch(); }} />
      </Card> : <>
        <Muted>Toplam alacak · {reportTotalsLabel(aging.data.total_ar_by_currency)}</Muted>
        {aging.data.complete === false && <Muted>Cari kaynakları eksik; bakiye kısmi.</Muted>}
        {!aging.data.companies.length && <Card><Muted>Bu iş gününde cari alacak kaydı yok.</Muted></Card>}
        {aging.data.companies.map((company) => <Card key={`${company.company_id}-${company.account_id}-${company.corporate_code}-${company.currency}`}>
          <Body>{company.company_name}</Body>
          <StatRow label="Bakiye" value={reportAmountLabel(company.total_balance, company.currency)} tone="warning" />
          {!!company.unaged_balance && <StatRow label="Vadesi belirlenemeyen" value={reportAmountLabel(company.unaged_balance, company.currency)} />}
        </Card>)}
      </>}
      <Button title="Bu özeti paylaş" variant="secondary" disabled={!fin || finance.isError || finance.isFetching} onPress={share} fullWidth />
    </ScrollView>
  </View>;
}
