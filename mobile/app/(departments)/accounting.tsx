import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  ActionSheet,
  Badge,
  Body,
  Card,
  DetailHeader,
  DetailRow,
  EmptyState,
  Field,
  H1,
  Muted,
  SectionTitle,
  webCenter,
} from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import {
  BarList,
  ChartLegend,
  CompareBars,
  DonutChart,
  type ChartDatum,
} from '../../src/components/charts';
import { FilterChips, type FilterChipOption } from '../../src/components/FilterChips';
import { DepartmentListState } from '../../src/components/department';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  getFinancialSummary,
  getInventory,
  listExpenses,
  listInvoices,
  type AccountingInvoice,
  type Expense,
  type InventoryItem,
} from '../../src/api/accounting';
import { formatCurrency, formatDate } from '../../src/utils/format';

type Tab = 'summary' | 'expenses' | 'invoices' | 'inventory';
const TABS: Tab[] = ['summary', 'expenses', 'invoices', 'inventory'];

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// Current calendar month → {start_date, end_date} for the expense/invoice reads.
function monthRange(): { start_date: string; end_date: string } {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return { start_date: isoDate(start), end_date: isoDate(end) };
}

// PaymentStatus tone — shared by expense.payment_status and invoice.status.
function statusTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger' {
  switch (status) {
    case 'paid':
      return 'success';
    case 'partial':
      return 'warning';
    case 'overdue':
    case 'cancelled':
      return 'danger';
    default:
      return 'default';
  }
}

function statusLabel(status?: string): string {
  const map = tr.departments.accounting.statuses;
  return (status && map[status]) || status || '—';
}

function invoiceTypeLabel(type?: string): string {
  const map = tr.departments.accounting.invoiceTypes;
  return (type && map[type]) || type || '—';
}

function auditTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'in_progress':
    case 'running':
      return 'warning';
    case 'failed':
      return 'danger';
    default:
      return 'default';
  }
}

function auditLabel(status?: string): string {
  const map = tr.departments.accounting.auditStatuses;
  return (status && map[status]) || status || '—';
}

// An invoice counts as "pending" (awaiting collection) when it is neither paid
// nor cancelled — drives the cockpit "Bekleyen Fatura" KPI.
function isPendingInvoice(inv: AccountingInvoice): boolean {
  return inv.status !== 'paid' && inv.status !== 'cancelled';
}

// Read-only Accounting screen. Cockpit (Özet) tab surfaces the daily financial
// summary KPIs; the Giderler / Faturalar tabs are searchable, status-coded
// lists; invoices open a read-only detail sheet (e-Fatura / fatura readout).
// Backend GET reads only need auth; the (departments) entitlement
// (view_finance_reports roles) decides whether we show this screen at all.
export default function AccountingScreen() {
  const c = useTheme();
  const a = tr.departments.accounting;
  const financeReports = useAuthStore((s) => s.financeReports);

  const [tab, setTab] = useState<Tab>('summary');
  const [expenseSearch, setExpenseSearch] = useState('');
  const [invoiceSearch, setInvoiceSearch] = useState('');
  const [inventorySearch, setInventorySearch] = useState('');
  const [invoiceStatus, setInvoiceStatus] = useState('all');
  const [selectedInvoice, setSelectedInvoice] = useState<AccountingInvoice | null>(null);

  const range = monthRange();

  const summaryQ = useQuery({
    queryKey: ['acc-financial-summary'],
    queryFn: () => getFinancialSummary(),
    enabled: financeReports,
  });
  const expensesQ = useQuery({
    queryKey: ['acc-expenses', range.start_date, range.end_date],
    queryFn: () => listExpenses(range),
    enabled: financeReports,
  });
  const invoicesQ = useQuery({
    queryKey: ['acc-invoices', range.start_date, range.end_date],
    queryFn: () => listInvoices(range),
    enabled: financeReports,
  });
  const inventoryQ = useQuery({
    queryKey: ['acc-inventory'],
    queryFn: getInventory,
    enabled: financeReports,
  });

  // Hard guard: a user who somehow lands here without the finance-reports
  // entitlement is sent to the hub. Cosmetic — the backend still enforces reads.
  if (!financeReports) return <Redirect href={ROUTES.departments} />;

  const expenses = expensesQ.data || [];
  const invoices = invoicesQ.data || [];
  const inventoryItems = inventoryQ.data?.items || [];

  const monthExpenseTotal = expenses.reduce(
    (sum, e) => sum + (e.total_amount ?? e.amount ?? 0),
    0,
  );
  const pendingInvoiceCount = invoices.filter(isPendingInvoice).length;

  const filteredExpenses = useMemo(() => {
    const q = expenseSearch.trim().toLocaleLowerCase('tr-TR');
    if (!q) return expenses;
    return expenses.filter((e) =>
      [e.description, e.category, e.expense_number]
        .filter(Boolean)
        .some((v) => v!.toLocaleLowerCase('tr-TR').includes(q)),
    );
  }, [expenses, expenseSearch]);

  const filteredInvoices = useMemo(() => {
    const q = invoiceSearch.trim().toLocaleLowerCase('tr-TR');
    return invoices.filter((inv) => {
      if (invoiceStatus !== 'all' && inv.status !== invoiceStatus) return false;
      if (!q) return true;
      return [inv.invoice_number, inv.customer_name]
        .filter(Boolean)
        .some((v) => v!.toLocaleLowerCase('tr-TR').includes(q));
    });
  }, [invoices, invoiceSearch, invoiceStatus]);

  const filteredInventory = useMemo(() => {
    const q = inventorySearch.trim().toLocaleLowerCase('tr-TR');
    if (!q) return inventoryItems;
    return inventoryItems.filter((it) =>
      [it.name, it.category, it.sku]
        .filter(Boolean)
        .some((v) => v!.toLocaleLowerCase('tr-TR').includes(q)),
    );
  }, [inventoryItems, inventorySearch]);

  const invoiceStatusOptions: FilterChipOption[] = [
    { value: 'all', label: a.filterAll },
    { value: 'pending', label: a.statuses.pending },
    { value: 'paid', label: a.statuses.paid },
    { value: 'partial', label: a.statuses.partial },
    { value: 'overdue', label: a.statuses.overdue },
    { value: 'cancelled', label: a.statuses.cancelled },
  ];

  const tabLabels: Record<Tab, string> = {
    summary: a.tabSummary,
    expenses: a.tabExpenses,
    invoices: a.tabInvoices,
    inventory: a.tabInventory,
  };

  const TabButton: React.FC<{ value: Tab; label: string }> = ({ value, label }) => {
    const active = tab === value;
    return (
      <Pressable
        onPress={() => setTab(value)}
        accessibilityRole="button"
        accessibilityState={{ selected: active }}
        style={{
          flex: 1,
          paddingVertical: spacing.sm,
          borderRadius: radius.md,
          alignItems: 'center',
          backgroundColor: active ? c.primary : c.surfaceAlt,
          borderWidth: 1,
          borderColor: active ? c.primary : c.border,
        }}
      >
        <Body
          style={{ color: active ? c.primaryText : c.text, fontWeight: '600' }}
          numberOfLines={1}
        >
          {label}
        </Body>
      </Pressable>
    );
  };

  // Render a list section: loading/error first (skeletons / error card), then
  // a rich EmptyState when empty, otherwise the list. DepartmentListState only
  // covers loading+error here (isEmpty=false) so the empty branch is ours.
  const listSection = (
    q: { isLoading: boolean; error: unknown },
    isEmpty: boolean,
    empty: React.ReactNode,
    list: React.ReactNode,
  ): React.ReactNode => {
    if (q.isLoading || q.error) {
      return (
        <DepartmentListState loading={q.isLoading} error={q.error} isEmpty={false} />
      );
    }
    return isEmpty ? empty : list;
  };

  const renderExpense = (e: Expense) => (
    <Card key={e.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>
            {e.description || e.expense_number || '—'}
          </Body>
          {e.category ? <Muted>{e.category}</Muted> : null}
        </View>
        <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
          <Body style={{ fontWeight: '600' }}>
            {formatCurrency(e.total_amount ?? e.amount, 'TRY')}
          </Body>
          {e.payment_status ? (
            <Badge
              label={statusLabel(e.payment_status)}
              tone={statusTone(e.payment_status)}
            />
          ) : null}
        </View>
      </View>
      <Muted style={{ marginTop: spacing.xs }}>{formatDate(e.date)}</Muted>
    </Card>
  );

  const renderInvoice = (inv: AccountingInvoice) => (
    <Pressable
      key={inv.id}
      onPress={() => setSelectedInvoice(inv)}
      accessibilityRole="button"
      accessibilityLabel={inv.invoice_number || a.invoiceDetail}
      style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
    >
      <Card style={{ marginBottom: spacing.sm }}>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          }}
        >
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <Body style={{ fontWeight: '600' }}>{inv.invoice_number || '—'}</Body>
            {inv.customer_name ? (
              <Muted>
                {a.customer}: {inv.customer_name}
              </Muted>
            ) : null}
          </View>
          <Badge label={statusLabel(inv.status)} tone={statusTone(inv.status)} />
        </View>
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: spacing.sm,
            gap: spacing.sm,
          }}
        >
          {inv.invoice_type ? (
            <Badge
              label={invoiceTypeLabel(inv.invoice_type)}
              tone={inv.invoice_type === 'e_invoice' ? 'info' : 'default'}
            />
          ) : (
            <View />
          )}
          <Body style={{ fontWeight: '600' }}>{formatCurrency(inv.total, 'TRY')}</Body>
        </View>
        {inv.due_date ? (
          <Muted style={{ marginTop: spacing.xs }}>
            {a.due}: {formatDate(inv.due_date)}
          </Muted>
        ) : null}
      </Card>
    </Pressable>
  );

  const renderInventoryItem = (it: InventoryItem) => {
    const low =
      typeof it.quantity === 'number' &&
      typeof it.reorder_level === 'number' &&
      it.quantity <= it.reorder_level;
    return (
      <Card key={it.id} style={{ marginBottom: spacing.sm }}>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          }}
        >
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <Body style={{ fontWeight: '600' }}>{it.name || '—'}</Body>
            {it.category ? <Muted>{it.category}</Muted> : null}
          </View>
          {low ? <Badge label={a.lowStock} tone="danger" /> : null}
        </View>
        <Muted style={{ marginTop: spacing.xs }}>
          {a.quantity}: {it.quantity ?? 0} {it.unit || ''}
          {typeof it.reorder_level === 'number'
            ? ` · ${a.reorderLevel}: ${it.reorder_level}`
            : ''}
        </Muted>
      </Card>
    );
  };

  const summary = summaryQ.data;
  const revenueCategories = summary
    ? Object.entries(summary.revenue.by_category).sort(
        (x, y) => (y[1]?.total ?? 0) - (x[1]?.total ?? 0),
      )
    : [];

  // ── Stripe-quality chart series (all real backend data) ───────────────────
  // Gelir: günlük finansal özetteki kategori kırılımı (vergili toplam).
  const revenueChartData: ChartDatum[] = useMemo(
    () =>
      revenueCategories
        .map(([cat, v]) => ({ label: cat, value: v?.total ?? 0 }))
        .filter((d) => d.value > 0),
    [revenueCategories],
  );

  // Gider: ay içi giderlerin kategoriye göre toplamı (listExpenses verisi).
  const expenseChartData: ChartDatum[] = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of expenses) {
      const key = e.category || a.uncategorized;
      m.set(key, (m.get(key) ?? 0) + (e.total_amount ?? e.amount ?? 0));
    }
    return Array.from(m, ([label, value]) => ({ label, value })).filter(
      (d) => d.value > 0,
    );
  }, [expenses, a.uncategorized]);

  // KDV: günlük özetteki vergi kırılımı (oran → tutar).
  const vatChartData: ChartDatum[] = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.tax.breakdown)
      .map(([rate, amount]) => ({ label: `%${rate}`, value: amount ?? 0 }))
      .filter((d) => d.value > 0);
  }, [summary]);

  // Kasa Akışı: ödeme yöntemine göre tahsilat dağılımı (günlük özet).
  const paymentChartData: ChartDatum[] = useMemo(() => {
    if (!summary) return [];
    const labels = a.paymentMethodLabels;
    return Object.entries(summary.payments.by_method)
      .map(([method, v]) => ({
        label: labels[method] || method,
        value: v?.amount ?? 0,
      }))
      .filter((d) => d.value > 0);
  }, [summary, a.paymentMethodLabels]);

  // Kasa Akışı karşılaştırması: Vergili Gelir / Tahsilat / Net Pozisyon.
  const cashFlowBars: ChartDatum[] = useMemo(() => {
    if (!summary) return [];
    return [
      { label: a.revenueWithTax, value: summary.revenue.total_with_tax },
      { label: a.payments, value: summary.payments.total },
      { label: a.netPosition, value: summary.net_position },
    ];
  }, [summary, a.revenueWithTax, a.payments, a.netPosition]);

  const fmtTRY = (n: number) => formatCurrency(n, 'TRY');

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
    >
      <H1>{a.title}</H1>

      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        {TABS.map((value) => (
          <TabButton key={value} value={value} label={tabLabels[value]} />
        ))}
      </View>

      {/* ── Özet (cockpit) ── */}
      {tab === 'summary' ? (
        <>
          <View style={{ gap: spacing.md, marginTop: spacing.md }}>
            <KpiRow>
              <KpiCard
                label={a.todayRevenue}
                value={formatCurrency(summary?.revenue.total_with_tax, 'TRY')}
                icon="cash-outline"
                tone="success"
              />
              <KpiCard
                label={a.collections}
                value={formatCurrency(summary?.payments.total, 'TRY')}
                icon="card-outline"
                tone="info"
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                label={a.netPosition}
                value={formatCurrency(summary?.net_position, 'TRY')}
                icon="trending-up-outline"
                tone={(summary?.net_position ?? 0) >= 0 ? 'default' : 'danger'}
              />
              <KpiCard
                label={a.openFolios}
                value={String(summary?.open_folios.count ?? 0)}
                icon="folder-open-outline"
                tone={(summary?.open_folios.count ?? 0) > 0 ? 'warning' : 'default'}
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                label={`${a.monthExpenses} · ${a.monthRange}`}
                value={formatCurrency(monthExpenseTotal, 'TRY')}
                icon="receipt-outline"
                tone="default"
              />
              <KpiCard
                label={a.pendingInvoices}
                value={String(pendingInvoiceCount)}
                icon="document-text-outline"
                tone={pendingInvoiceCount > 0 ? 'warning' : 'default'}
              />
            </KpiRow>
          </View>

          {/* ── Finansal Özet ── */}
          <SectionTitle title={a.sectionSummary} />
          {summaryQ.isLoading || summaryQ.error ? (
            <DepartmentListState
              loading={summaryQ.isLoading}
              error={summaryQ.error}
              isEmpty={false}
              skeletonCount={1}
            />
          ) : summary ? (
            <Card>
              <View
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: spacing.sm,
                }}
              >
                <Muted>
                  {a.businessDate}: {formatDate(summary.business_date)}
                </Muted>
                <Badge
                  label={auditLabel(summary.audit_status)}
                  tone={auditTone(summary.audit_status)}
                />
              </View>
              <SummaryRow label={a.revenueWithTax} value={formatCurrency(summary.revenue.total_with_tax, 'TRY')} />
              <SummaryRow label={a.tax} value={formatCurrency(summary.tax.total, 'TRY')} />
              <SummaryRow label={a.payments} value={formatCurrency(summary.payments.total, 'TRY')} />
              <SummaryRow label={a.netPosition} value={formatCurrency(summary.net_position, 'TRY')} />
              <SummaryRow
                label={a.openFolioBalance}
                value={`${formatCurrency(summary.open_folios.balance.total, 'TRY')} · ${summary.open_folios.count}`}
                last
              />
            </Card>
          ) : (
            <EmptyState
              icon="stats-chart-outline"
              title={a.noFinancialSummary}
            />
          )}

          {/* ── Gelir ── */}
          {summary ? (
            <>
              <SectionTitle title={a.sectionRevenue} />
              <Card>
                {revenueChartData.length > 0 ? (
                  <>
                    <View
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: spacing.lg,
                      }}
                    >
                      <DonutChart
                        data={revenueChartData}
                        centerValue={formatCurrency(summary.revenue.total_with_tax, 'TRY')}
                        centerLabel={a.centerTotal}
                      />
                      <ChartLegend data={revenueChartData} formatValue={fmtTRY} />
                    </View>
                    <View style={{ height: spacing.lg }} />
                    <BarList data={revenueChartData} formatValue={fmtTRY} />
                    <View style={{ height: spacing.md }} />
                    <SummaryRow label={a.revenueNet} value={formatCurrency(summary.revenue.total, 'TRY')} />
                    <SummaryRow label={a.revenueWithTax} value={formatCurrency(summary.revenue.total_with_tax, 'TRY')} last />
                  </>
                ) : (
                  <EmptyState icon="cash-outline" title={a.noRevenueData} />
                )}
              </Card>
            </>
          ) : null}

          {/* ── Gider ── */}
          {!expensesQ.isLoading && !expensesQ.error ? (
            <>
              <SectionTitle title={a.sectionExpense} />
              <Card>
                {expenseChartData.length > 0 ? (
                  <>
                    <View
                      style={{
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: spacing.md,
                      }}
                    >
                      <Muted>{a.expenseByCategory}</Muted>
                      <Body style={{ fontWeight: '700' }}>
                        {formatCurrency(monthExpenseTotal, 'TRY')}
                      </Body>
                    </View>
                    <BarList data={expenseChartData} formatValue={fmtTRY} />
                  </>
                ) : (
                  <EmptyState icon="receipt-outline" title={a.noExpenseData} />
                )}
              </Card>
            </>
          ) : null}

          {/* ── KDV ── */}
          {summary ? (
            <>
              <SectionTitle title={a.sectionVat} />
              <Card>
                {vatChartData.length > 0 ? (
                  <>
                    <View
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: spacing.lg,
                      }}
                    >
                      <DonutChart
                        data={vatChartData}
                        centerValue={formatCurrency(summary.tax.total, 'TRY')}
                        centerLabel={a.vat}
                      />
                      <ChartLegend data={vatChartData} formatValue={fmtTRY} />
                    </View>
                  </>
                ) : (
                  <EmptyState icon="pricetags-outline" title={a.noVatData} />
                )}
              </Card>
            </>
          ) : null}

          {/* ── Kasa Akışı ── */}
          {summary ? (
            <>
              <SectionTitle title={a.sectionCashFlow} />
              <Card>
                {cashFlowBars.length > 0 ? (
                  <>
                    <CompareBars data={cashFlowBars} formatValue={fmtTRY} />
                    {paymentChartData.length > 0 ? (
                      <>
                        <View style={{ height: spacing.lg }} />
                        <Muted style={{ marginBottom: spacing.md }}>{a.paymentMethods}</Muted>
                        <BarList data={paymentChartData} formatValue={fmtTRY} />
                      </>
                    ) : null}
                  </>
                ) : (
                  <EmptyState icon="swap-horizontal-outline" title={a.noCashFlowData} />
                )}
              </Card>
            </>
          ) : null}
        </>
      ) : null}

      {/* ── Giderler ── */}
      {tab === 'expenses' ? (
        <>
          <View style={{ marginTop: spacing.md }}>
            <Field
              placeholder={a.searchExpenses}
              value={expenseSearch}
              onChangeText={setExpenseSearch}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
          <SectionTitle title={a.expenses} />
          {listSection(
            expensesQ,
            filteredExpenses.length === 0,
            <EmptyState
              icon="receipt-outline"
              title={expenseSearch ? a.noExpensesSearch : a.noExpenses}
            />,
            <View>{filteredExpenses.map(renderExpense)}</View>,
          )}
        </>
      ) : null}

      {/* ── Faturalar ── */}
      {tab === 'invoices' ? (
        <>
          <View style={{ marginTop: spacing.md }}>
            <Field
              placeholder={a.searchInvoices}
              value={invoiceSearch}
              onChangeText={setInvoiceSearch}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
          <View style={{ marginTop: spacing.sm }}>
            <FilterChips
              options={invoiceStatusOptions}
              value={invoiceStatus}
              onChange={setInvoiceStatus}
            />
          </View>
          <SectionTitle title={a.invoices} />
          {listSection(
            invoicesQ,
            filteredInvoices.length === 0,
            <EmptyState
              icon="document-text-outline"
              title={
                invoiceSearch || invoiceStatus !== 'all'
                  ? a.noInvoicesSearch
                  : a.noInvoices
              }
            />,
            <View>{filteredInvoices.map(renderInvoice)}</View>,
          )}
        </>
      ) : null}

      {/* ── Stok ── */}
      {tab === 'inventory' ? (
        <>
          <View style={{ marginTop: spacing.md }}>
            <Field
              placeholder={a.searchInventory}
              value={inventorySearch}
              onChangeText={setInventorySearch}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
          {inventoryQ.data ? (
            <Card style={{ marginTop: spacing.sm, marginBottom: spacing.sm }}>
              <View
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <Muted>{a.totalValue}</Muted>
                <Body style={{ fontWeight: '600' }}>
                  {formatCurrency(inventoryQ.data.total_value, 'TRY')}
                </Body>
              </View>
              {inventoryQ.data.low_stock_count > 0 ? (
                <View style={{ marginTop: spacing.sm }}>
                  <Badge
                    label={`${a.lowStock}: ${inventoryQ.data.low_stock_count}`}
                    tone="danger"
                  />
                </View>
              ) : null}
            </Card>
          ) : null}
          <SectionTitle title={a.inventory} />
          {listSection(
            inventoryQ,
            filteredInventory.length === 0,
            <EmptyState
              icon="cube-outline"
              title={inventorySearch ? a.noInventorySearch : a.noInventory}
            />,
            <View>{filteredInventory.map(renderInventoryItem)}</View>,
          )}
        </>
      ) : null}

      {/* ── Invoice detail (list → detail) ── */}
      <ActionSheet
        visible={!!selectedInvoice}
        onClose={() => setSelectedInvoice(null)}
        title={a.invoiceDetail}
      >
        {selectedInvoice ? (
          <View>
            <DetailHeader
              title={selectedInvoice.invoice_number || '—'}
              subtitle={selectedInvoice.customer_name || undefined}
              badges={
                <>
                  <Badge
                    label={statusLabel(selectedInvoice.status)}
                    tone={statusTone(selectedInvoice.status)}
                  />
                  {selectedInvoice.invoice_type ? (
                    <Badge
                      label={invoiceTypeLabel(selectedInvoice.invoice_type)}
                      tone={
                        selectedInvoice.invoice_type === 'e_invoice'
                          ? 'info'
                          : 'default'
                      }
                    />
                  ) : null}
                </>
              }
            />
            <Card>
              <DetailRow
                label={a.invoiceType}
                value={invoiceTypeLabel(selectedInvoice.invoice_type)}
              />
              <DetailRow
                label={a.subtotal}
                value={formatCurrency(selectedInvoice.subtotal, 'TRY')}
              />
              <DetailRow
                label={a.vat}
                value={formatCurrency(selectedInvoice.total_vat, 'TRY')}
              />
              <DetailRow
                label={a.total}
                value={formatCurrency(selectedInvoice.total, 'TRY')}
              />
              <DetailRow
                label={a.issueDate}
                value={formatDate(selectedInvoice.issue_date)}
              />
              <DetailRow
                label={a.due}
                value={formatDate(selectedInvoice.due_date)}
              />
              {selectedInvoice.payment_date ? (
                <DetailRow
                  label={a.paymentDate}
                  value={formatDate(selectedInvoice.payment_date)}
                />
              ) : null}
              {selectedInvoice.notes ? (
                <DetailRow label={a.notes} value={selectedInvoice.notes} />
              ) : null}
            </Card>
          </View>
        ) : null}
      </ActionSheet>
    </ScrollView>
  );
}

// Compact label/value line for the daily-summary card. Optional trailing
// divider so a list of rows reads cleanly inside one Card.
const SummaryRow: React.FC<{ label: string; value: string; last?: boolean }> = ({
  label,
  value,
  last,
}) => {
  const c = useTheme();
  return (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingVertical: spacing.xs,
        borderBottomWidth: last ? 0 : 1,
        borderBottomColor: c.border,
      }}
    >
      <Muted style={{ flex: 1, paddingRight: spacing.sm }} numberOfLines={1}>
        {label}
      </Muted>
      <Body style={{ fontWeight: '600' }}>{value}</Body>
    </View>
  );
};
