import React, { useMemo, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Card,
  Field,
  H1,
  ListGroup,
  ListRow,
  Muted,
} from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { DepartmentListState, SectionTitle } from '../../src/components/department';
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

type FolioTone = 'success' | 'default' | 'danger' | 'warning';

function folioStatusTone(status?: string): FolioTone {
  switch ((status || '').toLowerCase()) {
    case 'open':
      return 'success';
    case 'closed':
      return 'default';
    case 'cancelled':
    case 'canceled':
      return 'danger';
    default:
      return 'warning';
  }
}

function folioStatusLabel(status?: string): string {
  const map = tr.departments.cashier.detail.status as Record<string, string>;
  return map[(status || '').toLowerCase()] || status || '-';
}

// Cashier (Kasa) shift cockpit + open-folio finance surface. The shift reads
// are read-only here; tapping a folio opens the shared folio-detail screen
// (Task #457) where charge / payment writes happen. All reads sit behind
// require_op("view_finance_reports") server-side; the (departments) finance
// entitlement just decides whether we show this screen.
export default function CashierScreen() {
  const c = useTheme();
  const router = useRouter();
  const financeReports = useAuthStore((s) => s.financeReports);
  const [query, setQuery] = useState('');

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

  const folios = foliosQ.data?.folios || [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return folios;
    return folios.filter((f) =>
      [f.guest_name, f.folio_number, f.room_number]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [folios, query]);

  // Hard guard: a user without the finance entitlement is bounced to the hub.
  // Cosmetic only — the backend still enforces every read/write.
  if (!financeReports) return <Redirect href={ROUTES.departments} />;

  const shift = shiftQ.data?.shift ?? null;
  const transactions = shiftQ.data?.transactions ?? [];
  const stats = statsQ.data;

  const openFolio = (f: FolioListItem) => {
    const qs = new URLSearchParams();
    if (f.guest_name) qs.set('guest', f.guest_name);
    if (f.room_number) qs.set('room', f.room_number);
    const suffix = qs.toString();
    router.push(`${ROUTES.folioDetail}/${f.id}${suffix ? `?${suffix}` : ''}`);
  };

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
            <Body style={{ fontWeight: '600' }}>{t.description || '-'}</Body>
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

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
      testID="smoke-cashier"
    >
      <H1>{tr.departments.cashier.title}</H1>

      {/* ── Shift cockpit: single-glance cash status ───────────────────────── */}
      <SectionTitle title={tr.departments.cashier.shift} />
      {(() => {
        // DepartmentListState is a render FUNCTION returning null on data; CALL
        // it (a JSX element would always be truthy) and only short-circuit on a
        // non-null state node.
        const state = DepartmentListState({
          loading: shiftQ.isLoading,
          error: shiftQ.error,
          isEmpty: !shift,
          emptyText: tr.departments.cashier.noShift,
        });
        if (state) return state;
        if (!shift) return null;
        return (
          <View style={{ gap: spacing.md }} testID="smoke-cashier-cockpit">
            <KpiRow>
              <KpiCard
                label={tr.departments.cashier.expected}
                value={formatCurrency(expectedCash(shift), shift.currency)}
                icon="wallet-outline"
                tone="info"
              />
              <KpiCard
                label={tr.departments.cashier.openingAmount}
                value={formatCurrency(shift.opening_amount ?? 0, shift.currency)}
                icon="lock-open-outline"
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                label={tr.departments.cashier.cashIn}
                value={`+${formatCurrency(shift.cash_in ?? 0, shift.currency)}`}
                icon="arrow-down-circle-outline"
                tone="success"
              />
              <KpiCard
                label={tr.departments.cashier.cashOut}
                value={`-${formatCurrency(shift.cash_out ?? 0, shift.currency)}`}
                icon="arrow-up-circle-outline"
                tone="danger"
              />
            </KpiRow>
            <Card>
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
            </Card>
          </View>
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

      {/* ── Open folios: searchable + status-coded, tap to open detail ─────── */}
      <SectionTitle title={tr.departments.cashier.folios} />
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md }}>
        <KpiCard
          label={tr.departments.cashier.openFolios}
          value={String(stats?.total_open_folios ?? 0)}
          icon="documents-outline"
        />
        <KpiCard
          label={tr.departments.cashier.outstanding}
          value={formatCurrency(stats?.total_outstanding_balance ?? 0)}
          icon="trending-up-outline"
          tone="warning"
        />
      </View>

      <View style={{ marginBottom: spacing.md }}>
        <Field
          value={query}
          onChangeText={setQuery}
          placeholder={tr.departments.cashier.searchFolios}
          autoCapitalize="none"
          autoCorrect={false}
          testID="smoke-cashier-search"
        />
      </View>

      {(() => {
        const state = DepartmentListState({
          loading: foliosQ.isLoading,
          error: foliosQ.error,
          isEmpty: folios.length === 0,
          emptyText: tr.departments.cashier.noFolios,
        });
        if (state) return state;
        if (filtered.length === 0) {
          return (
            <Card>
              <Muted>{tr.departments.cashier.noFolioMatch}</Muted>
            </Card>
          );
        }
        return (
          <ListGroup>
            {filtered.map((f, idx) => (
              <ListRow
                key={f.id}
                icon="receipt-outline"
                label={f.guest_name || f.folio_number || '-'}
                sublabel={[
                  f.folio_number || null,
                  f.room_number ? `${tr.departments.cashier.room} ${f.room_number}` : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                value={
                  typeof f.balance === 'number' ? formatCurrency(f.balance) : undefined
                }
                right={
                  <Badge label={folioStatusLabel(f.status)} tone={folioStatusTone(f.status)} />
                }
                last={idx === filtered.length - 1}
                onPress={() => openFolio(f)}
                testID={`smoke-cashier-folio-${idx}`}
              />
            ))}
          </ListGroup>
        );
      })()}
    </ScrollView>
  );
}
