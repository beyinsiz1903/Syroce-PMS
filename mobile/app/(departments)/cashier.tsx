import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import {
  Badge,
  Body,
  Button,
  Card,
  Field,
  FadeInView,
  H1,
  Muted,
} from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { DepartmentListState, SectionTitle } from '../../src/components/department';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  getCurrentShift,
  expectedCash,
  collectionBreakdown,
  type CashierTransaction,
} from '../../src/api/cashier';
import {
  listFolios,
  getFolioDashboardStats,
  type FolioListItem,
} from '../../src/api/folio';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';

const t = tr.departments.cashier;

function methodLabel(method?: string): string {
  const map = t.methods as Record<string, string>;
  return (method && map[method]) || method || t.methods.other;
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
  const map = t.detail.status as Record<string, string>;
  return map[(status || '').toLowerCase()] || status || '-';
}

// One Nakit/Kart/Cari column inside the "Bugünkü Tahsilat" card. Real money
// (from the open shift's transactions) under a tinted icon dot.
const BreakdownTile: React.FC<{
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: number;
  tint: string;
}> = ({ icon, label, value, tint }) => {
  const c = useTheme();
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: c.surfaceAlt,
        borderRadius: radius.md,
        borderWidth: 1,
        borderColor: c.border,
        padding: spacing.md,
        gap: spacing.xs,
      }}
    >
      <View
        style={{
          width: 28,
          height: 28,
          borderRadius: radius.pill,
          backgroundColor: tint + '1f',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Ionicons name={icon} size={16} color={tint} />
      </View>
      <Text style={{ color: c.textMuted, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>
        {label}
      </Text>
      <Text
        style={{ color: c.text, fontSize: 15, fontWeight: '700' }}
        numberOfLines={1}
        adjustsFontSizeToFit
      >
        {formatCurrency(value)}
      </Text>
    </View>
  );
};

// Premium open-folio card: guest + status, room/folyo line, last-activity time,
// a prominent balance and a "Tahsilat Al" CTA. Tapping the body opens the folio
// detail (read); the CTA opens the same detail with the payment sheet primed —
// the actual collection still runs through the shared folio-detail flow.
const FolioCard: React.FC<{
  folio: FolioListItem;
  index: number;
  onOpen: (f: FolioListItem) => void;
  onCollect: (f: FolioListItem) => void;
}> = ({ folio, index, onOpen, onCollect }) => {
  const c = useTheme();
  const tone = folioStatusTone(folio.status);
  const accent =
    tone === 'success' ? c.success : tone === 'danger' ? c.danger : c.warning;
  const last = folio.updated_at || folio.created_at;
  const balance = typeof folio.balance === 'number' ? folio.balance : 0;
  const owes = balance > 0;
  return (
    <Card accent={accent} style={{ marginBottom: spacing.md, gap: spacing.sm }}>
      <Pressable
        onPress={() => onOpen(folio)}
        accessibilityRole="button"
        accessibilityLabel={folio.guest_name || folio.folio_number || t.balance}
        testID={`smoke-cashier-folio-${index}`}
        style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1, gap: spacing.sm })}
      >
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <Body style={{ fontWeight: '700', fontSize: 16 }} numberOfLines={1}>
              {folio.guest_name || folio.folio_number || '-'}
            </Body>
            <Muted style={{ marginTop: 2 }} numberOfLines={1}>
              {[
                folio.folio_number || null,
                folio.room_number ? `${t.room} ${folio.room_number}` : null,
              ]
                .filter(Boolean)
                .join(' · ') || '-'}
            </Muted>
          </View>
          <Badge label={folioStatusLabel(folio.status)} tone={tone} />
        </View>

        <View
          style={{
            flexDirection: 'row',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap: spacing.sm,
          }}
        >
          <View>
            <Muted style={{ fontSize: 11 }}>{t.balance}</Muted>
            <Text
              style={{
                color: owes ? c.danger : c.success,
                fontSize: 22,
                fontWeight: '800',
                marginTop: 1,
              }}
            >
              {formatCurrency(balance)}
            </Text>
          </View>
          {last ? (
            <View style={{ alignItems: 'flex-end' }}>
              <Muted style={{ fontSize: 11 }}>
                {folio.updated_at ? t.lastActivity : t.openedAtShort}
              </Muted>
              <Muted style={{ fontSize: 12, marginTop: 1 }}>
                {formatDate(last)} · {formatTime(last)}
              </Muted>
            </View>
          ) : null}
        </View>
      </Pressable>

      <Button
        title={t.collect}
        icon="cash-outline"
        fullWidth
        onPress={() => onCollect(folio)}
        testID={`smoke-cashier-pay-${index}`}
      />
    </Card>
  );
};

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
  const collection = collectionBreakdown(transactions);

  const openFolio = (f: FolioListItem, pay?: boolean) => {
    const qs = new URLSearchParams();
    if (f.guest_name) qs.set('guest', f.guest_name);
    if (f.room_number) qs.set('room', f.room_number);
    if (pay) qs.set('pay', '1');
    const suffix = qs.toString();
    router.push(`${ROUTES.folioDetail}/${f.id}${suffix ? `?${suffix}` : ''}`);
  };

  const renderTransaction = (txn: CashierTransaction, idx: number) => {
    const isIn = (txn.direction || '').toLowerCase() === 'in';
    return (
      <Card key={txn.id || `txn-${idx}`} style={{ marginBottom: spacing.sm }}>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          }}
        >
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <Body style={{ fontWeight: '600' }}>{txn.description || '-'}</Body>
            <Muted style={{ marginTop: 2 }}>{methodLabel(txn.method)}</Muted>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 4 }}>
            <Badge
              label={isIn ? t.directionIn : t.directionOut}
              tone={isIn ? 'success' : 'danger'}
            />
            {typeof txn.amount === 'number' ? (
              <Body style={{ fontWeight: '600', color: isIn ? c.success : c.danger }}>
                {isIn ? '+' : '-'}
                {formatCurrency(Math.abs(txn.amount), shift?.currency)}
              </Body>
            ) : null}
          </View>
        </View>
        {txn.created_at ? (
          <Muted style={{ marginTop: spacing.xs }}>
            {formatDate(txn.created_at)} · {formatTime(txn.created_at)}
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
      <H1>{t.title}</H1>
      <Muted style={{ marginTop: spacing.xs }}>{t.tileSubtitle}</Muted>

      {/* ── Bugünkü Tahsilat: hero total + Nakit / Kart / Cari kırılımı ──────
          Computed from the open shift's real transactions; with no open shift
          there is nothing to collect yet, so the card stays hidden. */}
      {shift ? (
        <FadeInView style={{ marginTop: spacing.lg }}>
          <Card accent={c.success} testID="smoke-cashier-collection">
            <Muted style={{ fontSize: 12, fontWeight: '600' }}>{t.todayCollection}</Muted>
            <Text
              style={{
                color: c.text,
                fontSize: 34,
                fontWeight: '800',
                letterSpacing: -0.8,
                marginTop: 2,
              }}
              numberOfLines={1}
              adjustsFontSizeToFit
            >
              {formatCurrency(collection.total, shift.currency)}
            </Text>
            <Muted style={{ fontSize: 12, marginBottom: spacing.md }}>{t.collectionHint}</Muted>
            <View style={{ flexDirection: 'row', gap: spacing.sm }}>
              <BreakdownTile
                icon="cash-outline"
                label={t.methods.cash}
                value={collection.cash}
                tint={c.success}
              />
              <BreakdownTile
                icon="card-outline"
                label={t.methods.card}
                value={collection.card}
                tint={c.info}
              />
              <BreakdownTile
                icon="business-outline"
                label={t.cari}
                value={collection.cari}
                tint={c.vip}
              />
            </View>
          </Card>
        </FadeInView>
      ) : null}

      {/* ── Shift cockpit: single-glance cash status ───────────────────────── */}
      <SectionTitle title={t.shift} />
      {(() => {
        // DepartmentListState is a render FUNCTION returning null on data; CALL
        // it (a JSX element would always be truthy) and only short-circuit on a
        // non-null state node.
        const state = DepartmentListState({
          loading: shiftQ.isLoading,
          error: shiftQ.error,
          isEmpty: !shift,
          emptyText: t.noShift,
        });
        if (state) return state;
        if (!shift) return null;
        return (
          <View style={{ gap: spacing.md }} testID="smoke-cashier-cockpit">
            <KpiRow>
              <KpiCard
                label={t.expected}
                value={formatCurrency(expectedCash(shift), shift.currency)}
                icon="wallet-outline"
                tone="info"
              />
              <KpiCard
                label={t.openingAmount}
                value={formatCurrency(shift.opening_amount ?? 0, shift.currency)}
                icon="lock-open-outline"
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                label={t.cashIn}
                value={`+${formatCurrency(shift.cash_in ?? 0, shift.currency)}`}
                icon="arrow-down-circle-outline"
                tone="success"
              />
              <KpiCard
                label={t.cashOut}
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
                  {shift.cashier_name || t.cashier}
                </Body>
                {shift.opened_at ? (
                  <Muted>
                    {t.openedAt}: {formatTime(shift.opened_at)}
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
          <SectionTitle title={t.transactions} />
          {transactions.length === 0 ? (
            <Card>
              <Muted>{t.noTransactions}</Muted>
            </Card>
          ) : (
            <View>{transactions.map(renderTransaction)}</View>
          )}
        </>
      ) : null}

      {/* ── Open folios: searchable + status-coded folio cards ──────────────── */}
      <SectionTitle title={t.folios} />
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md }}>
        <KpiCard
          label={t.openFolios}
          value={String(stats?.total_open_folios ?? 0)}
          icon="documents-outline"
        />
        <KpiCard
          label={t.outstanding}
          value={formatCurrency(stats?.total_outstanding_balance ?? 0)}
          icon="trending-up-outline"
          tone="warning"
        />
      </View>

      <View style={{ marginBottom: spacing.md }}>
        <Field
          value={query}
          onChangeText={setQuery}
          placeholder={t.searchFolios}
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
          emptyText: t.noFolios,
        });
        if (state) return state;
        if (filtered.length === 0) {
          return (
            <Card>
              <Muted>{t.noFolioMatch}</Muted>
            </Card>
          );
        }
        return (
          <View>
            {filtered.map((f, idx) => (
              <FolioCard
                key={f.id}
                folio={f}
                index={idx}
                onOpen={(folio) => openFolio(folio)}
                onCollect={(folio) => openFolio(folio, true)}
              />
            ))}
          </View>
        );
      })()}
    </ScrollView>
  );
}
