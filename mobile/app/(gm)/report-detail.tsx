import React from 'react';
import { ScrollView, Share, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Body, Button, Card, H1, Muted, SectionTitle, SkeletonCard } from '../../src/components/ui';
import { StatRow } from '../../src/components/StatRow';
import { getCompanyAging, getFinanceSnapshot } from '../../src/api/reports';
import { formatCurrency } from '../../src/utils/format';
import { spacing, useTheme } from '../../src/theme';

export default function ReportDetailScreen() {
  const c = useTheme();
  const finance = useQuery({ queryKey: ['report-finance-snapshot'], queryFn: getFinanceSnapshot });
  const aging = useQuery({ queryKey: ['report-company-aging'], queryFn: getCompanyAging });
  const share = async () => {
    const value = finance.data?.pending_ar?.total ?? 0;
    await Share.share({ title: 'Syroce finans raporu', message: `Bekleyen alacak: ${formatCurrency(value)}\nBu finansal özeti yalnızca yetkili kişilerle paylaşın.` });
  };
  return <View style={{ flex: 1, backgroundColor: c.bg }}><ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 100 }}><H1>Finansal rapor detayı</H1><Muted>Canlı veriler yetkili backend raporlarından alınır.</Muted>{finance.isLoading ? <SkeletonCard /> : finance.data ? <Card><StatRow label="Bekleyen alacak" value={formatCurrency(finance.data.pending_ar.total)} tone="warning" strong /><StatRow label="Vadesi geçmiş fatura" value={String(finance.data.pending_ar.overdue_invoices_count)} /><StatRow label="Ay içi tahsilat" value={formatCurrency(finance.data.mtd_collections.amount)} tone="success" /></Card> : <Card><Muted>Rapor yüklenemedi.</Muted></Card>}<SectionTitle title="Cari hesaplar" />{aging.data?.companies?.map((company) => <Card key={`${company.corporate_code}-${company.company_name}`}><Body>{company.company_name}</Body><StatRow label="Bakiye" value={formatCurrency(company.total_balance)} tone="warning" /></Card>)}<Button title="Bu özeti paylaş" variant="secondary" disabled={!finance.data} onPress={share} fullWidth /></ScrollView></View>;
}
