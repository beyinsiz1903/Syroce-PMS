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
  getCurrentShift,
  expectedCash,
  type CashierTransaction,
} from '../../src/api/cashier';
import {
  listFolios,
  getFolioDashboardStats,
  type FolioListItem,
} from '../../src/api/folio';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';

function methodLabel(method?: string): string {
  const map = tr.departments.cashier.methods as Record<string, string>;
  return (method && map[method]) || method || tr.departments.cashier.methods.other;
}

// Read-only Cashier (Kasa) + open-folio finance surface. Both reads sit behind
// require_op("view_finance_reports") / authenticated reads server-side; the
// (departments) finance entitlement just decides whether we show this screen.
// Writes (open/close/handover shift, post payment) are intentionally NOT here.
export default function CashierScreen() {
  const c = useTheme();
  const financeReports = useAuthStore((s) => s.financeReports);

  const shiftQ = useQuery({
    queryKey: ['cashier-current-shift'],
    queryFn: getCurrentShift,
  });
  const statsQ = useQuery({
    queryKey: ['folio-dashboard-stats'],
    queryFn: getFolioDashboardStats,
  });
  const foliosQ = useQuery({
    queryKey: ['folios', 'open'],
    queryFn: () => listFolios({ status: 'open', limit: 100 }),
  });

  // Hard guard: a user without the finance entitlement is bounced to the hub.
  // Cosmetic only — the backend still enforces every read/write.
  if (!financeReports) return <Redirect href={ROUTES.departments} />;

  const shift = shiftQ.data?.shift ?? null;
  const transactions = shiftQ.data?.transactions ?? [];
  const stats = statsQ.data;

  const renderStat = (label: string, value: string) => (
    <Card style={{ flex: 1, marginBottom: 0 }}>
      <Muted>{label}</Muted>
      <Body style={{ fontWeight: '700', marginTop: spacing.xs }}>{value}</Body>
    </Card>
  );

  const renderTransaction = (t: CashierTransaction, idx: number) => {
    const isIn = (t.direction || '').toLowerCase() === 'in';
    return (
      <Card key={t.id || `txn-${idx}`} style={{ marginBottom: spacing.sm }}>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          }}
        >
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <Body style={{ fontWeight: '600' }}>{t.description || '—'}</Body>
            <Muted style={{ marginTop: 2 }}>{methodLabel(t.method)}</Muted>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 4 }}>
            <Badge
              label={
                isIn
                  ? tr.departments.cashier.directionIn
                  : tr.departments.cashier.directionOut
              }
              tone={isIn ? 'success' : 'danger'}
            />
            {typeof t.amount === 'number' ? (
              <Body style={{ fontWeight: '600', color: isIn ? c.success : c.danger }}>
                {isIn ? '+' : '-'}
                {formatCurrency(Math.abs(t.amount), shift?.currency)}
              </Body>
            ) : null}
          </View>
        </View>
        {t.created_at ? (
          <Muted style={{ marginTop: spacing.xs }}>
            {formatDate(t.created_at)} · {formatTime(t.created_at)}
          </Muted>
        ) : null}
      </Card>
    );
  };

  const renderFolio = (f: FolioListItem) => (
    <Card key={f.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>
            {f.guest_name || f.folio_number || '—'}
          </Body>
          <Muted style={{ marginTop: 2 }}>
            {f.folio_number ? `${f.folio_number}` : ''}
            {f.room_number ? ` · ${tr.departments.cashier.room} ${f.room_number}` : ''}
          </Muted>
        </View>
        {typeof f.balance === 'number' ? (
          <View style={{ alignItems: 'flex-end' }}>
            <Muted>{tr.departments.cashier.balance}</Muted>
            <Body style={{ fontWeight: '700' }}>{formatCurrency(f.balance)}</Body>
          </View>
        ) : null}
      </View>
      {f.check_in || f.check_out ? (
        <Muted style={{ marginTop: spacing.xs }}>
          {f.check_in ? formatDate(f.check_in) : ''}
          {f.check_out ? ` – ${formatDate(f.check_out)}` : ''}
        </Muted>
      ) : null}
    </Card>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.cashier.title}</H1>

      {/* Folio dashboard KPIs */}
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        {renderStat(
          tr.departments.cashier.openFolios,
          String(stats?.total_open_folios ?? 0),
        )}
        {renderStat(
          tr.departments.cashier.outstanding,
          formatCurrency(stats?.total_outstanding_balance ?? 0),
        )}
      </View>

      {/* Current cashier shift */}
      <SectionTitle title={tr.departments.cashier.shift} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={shiftQ.isLoading}
            error={shiftQ.error}
            isEmpty={!shift}
            emptyText={tr.departments.cashier.noShift}
          />
        );
        return (
          state ??
          (shift ? (
            <Card style={{ marginBottom: spacing.sm }}>
              <View
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <Body style={{ fontWeight: '600' }}>
                  {shift.cashier_name || tr.departments.cashier.cashier}
                </Body>
                {shift.opened_at ? (
                  <Muted>
                    {tr.departments.cashier.openedAt}: {formatTime(shift.opened_at)}
                  </Muted>
                ) : null}
              </View>
              <View style={{ marginTop: spacing.sm, gap: 4 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Muted>{tr.departments.cashier.openingAmount}</Muted>
                  <Body>{formatCurrency(shift.opening_amount ?? 0, shift.currency)}</Body>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Muted>{tr.departments.cashier.cashIn}</Muted>
                  <Body style={{ color: c.success }}>
                    +{formatCurrency(shift.cash_in ?? 0, shift.currency)}
                  </Body>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Muted>{tr.departments.cashier.cashOut}</Muted>
                  <Body style={{ color: c.danger }}>
                    -{formatCurrency(shift.cash_out ?? 0, shift.currency)}
                  </Body>
                </View>
                <View
                  style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    marginTop: spacing.xs,
                  }}
                >
                  <Body style={{ fontWeight: '700' }}>
                    {tr.departments.cashier.expected}
                  </Body>
                  <Body style={{ fontWeight: '700' }}>
                    {formatCurrency(expectedCash(shift), shift.currency)}
                  </Body>
                </View>
              </View>
            </Card>
          ) : null)
        );
      })()}

      {/* Shift transactions (only meaningful with an open shift) */}
      {shift ? (
        <>
          <SectionTitle title={tr.departments.cashier.transactions} />
          {transactions.length === 0 ? (
            <Card>
              <Muted>{tr.departments.cashier.noTransactions}</Muted>
            </Card>
          ) : (
            <View>{transactions.map(renderTransaction)}</View>
          )}
        </>
      ) : null}

      {/* Open folios */}
      <SectionTitle title={tr.departments.cashier.folios} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={foliosQ.isLoading}
            error={foliosQ.error}
            isEmpty={(foliosQ.data?.folios || []).length === 0}
            emptyText={tr.departments.cashier.noFolios}
          />
        );
        return state ?? <View>{(foliosQ.data?.folios || []).map(renderFolio)}</View>;
      })()}
    </ScrollView>
  );
}
