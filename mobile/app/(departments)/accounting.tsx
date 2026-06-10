import React from 'react';
import { ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted } from '../../src/components/ui';
import {
  DepartmentListState,
  SectionTitle,
} from '../../src/components/department';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  getInventory,
  listExpenses,
  listInvoices,
  type AccountingInvoice,
  type Expense,
  type InventoryItem,
} from '../../src/api/accounting';
import { formatCurrency, formatDate } from '../../src/utils/format';

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

function invoiceTone(status?: string):
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

function invoiceStatusLabel(status?: string): string {
  const map = tr.departments.accounting.statuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

// Read-only Accounting screen: month-to-date expenses, invoices and a stock
// summary. Backend GET reads only need auth; the (departments) entitlement
// (view_finance_reports roles) decides whether we show this screen at all.
export default function AccountingScreen() {
  const c = useTheme();
  const financeReports = useAuthStore((s) => s.financeReports);

  const range = monthRange();

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
          <Body style={{ fontWeight: '600' }}>{e.description || e.expense_number || '—'}</Body>
          {e.category ? <Muted>{e.category}</Muted> : null}
        </View>
        <Body>{formatCurrency(e.total_amount ?? e.amount, 'TRY')}</Body>
      </View>
      <Muted style={{ marginTop: spacing.xs }}>{formatDate(e.date)}</Muted>
    </Card>
  );

  const renderInvoice = (inv: AccountingInvoice) => (
    <Card key={inv.id} style={{ marginBottom: spacing.sm }}>
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
              {tr.departments.accounting.customer}: {inv.customer_name}
            </Muted>
          ) : null}
        </View>
        <Badge label={invoiceStatusLabel(inv.status)} tone={invoiceTone(inv.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        <Muted>{formatCurrency(inv.total, 'TRY')}</Muted>
        {inv.due_date ? (
          <Muted>
            {tr.departments.accounting.due}: {formatDate(inv.due_date)}
          </Muted>
        ) : null}
      </View>
    </Card>
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
          {low ? (
            <Badge label={tr.departments.accounting.lowStock} tone="danger" />
          ) : null}
        </View>
        <Muted style={{ marginTop: spacing.xs }}>
          {tr.departments.accounting.quantity}: {it.quantity ?? 0} {it.unit || ''}
          {typeof it.reorder_level === 'number'
            ? ` · ${tr.departments.accounting.reorderLevel}: ${it.reorder_level}`
            : ''}
        </Muted>
      </Card>
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.accounting.title}</H1>

      <SectionTitle title={tr.departments.accounting.expenses} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={expensesQ.isLoading}
            error={expensesQ.error}
            isEmpty={(expensesQ.data || []).length === 0}
            emptyText={tr.departments.accounting.noExpenses}
          />
        );
        return state ?? <View>{(expensesQ.data || []).map(renderExpense)}</View>;
      })()}

      <SectionTitle title={tr.departments.accounting.invoices} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={invoicesQ.isLoading}
            error={invoicesQ.error}
            isEmpty={(invoicesQ.data || []).length === 0}
            emptyText={tr.departments.accounting.noInvoices}
          />
        );
        return state ?? <View>{(invoicesQ.data || []).map(renderInvoice)}</View>;
      })()}

      <SectionTitle title={tr.departments.accounting.inventory} />
      {inventoryQ.data ? (
        <Card style={{ marginBottom: spacing.sm }}>
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <Muted>{tr.departments.accounting.totalValue}</Muted>
            <Body style={{ fontWeight: '600' }}>
              {formatCurrency(inventoryQ.data.total_value, 'TRY')}
            </Body>
          </View>
          {inventoryQ.data.low_stock_count > 0 ? (
            <View style={{ marginTop: spacing.sm }}>
              <Badge
                label={`${tr.departments.accounting.lowStock}: ${inventoryQ.data.low_stock_count}`}
                tone="danger"
              />
            </View>
          ) : null}
        </Card>
      ) : null}
      {(() => {
        const items = inventoryQ.data?.items || [];
        const state = (
          <DepartmentListState
            loading={inventoryQ.isLoading}
            error={inventoryQ.error}
            isEmpty={items.length === 0}
            emptyText={tr.departments.accounting.noInventory}
          />
        );
        return state ?? <View>{items.map(renderInventoryItem)}</View>;
      })()}
    </ScrollView>
  );
}
