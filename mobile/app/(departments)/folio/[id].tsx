import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { Redirect, useLocalSearchParams } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionButton,
  ActionSheet,
  Badge,
  Body,
  Button,
  Card,
  DetailHeader,
  DetailRow,
  Field,
  FormActions,
  Muted,
  SectionTitle,
  SegmentedActions,
  webCenter,
} from '../../../src/components/ui';
import { DepartmentListState } from '../../../src/components/department';
import { radius, spacing, useTheme } from '../../../src/theme';
import { tr } from '../../../src/i18n/tr';
import { useAuthStore } from '../../../src/state/authStore';
import { ROUTES } from '../../../src/navigation/routes';
import {
  getFolioById,
  postFolioCharge,
  postFolioPayment,
  type FolioCharge,
  type FolioChargeCategory,
  type FolioPayment,
  type FolioPaymentMethod,
} from '../../../src/api/folio';
import { formatCurrency, formatDate, formatTime } from '../../../src/utils/format';
import { errorMessage, errorStatus } from '../../../src/utils/errors';
import { haptic } from '../../../src/hooks/useHaptic';

const d = tr.departments.cashier.detail;

type Tone = 'success' | 'warning' | 'danger' | 'default';

function statusTone(status?: string): Tone {
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

function statusLabel(status?: string): string {
  const map = d.status as Record<string, string>;
  const key = (status || '').toLowerCase();
  return map[key] || status || '-';
}

const CHARGE_CATEGORIES: FolioChargeCategory[] = [
  'food',
  'beverage',
  'minibar',
  'spa',
  'laundry',
  'phone',
  'parking',
  'service_charge',
  'other',
];

const PAYMENT_METHODS: FolioPaymentMethod[] = ['cash', 'card', 'bank_transfer', 'online'];

// Small selectable pill used inside the action sheets (category / method).
const Chip: React.FC<{ active: boolean; label: string; onPress: () => void }> = ({
  active,
  label,
  onPress,
}) => {
  const c = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={{
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.md,
        borderRadius: radius.pill,
        backgroundColor: active ? c.primary : c.surfaceAlt,
        borderWidth: 1,
        borderColor: active ? c.primary : c.border,
      }}
    >
      <Text style={{ color: active ? c.primaryText : c.text, fontWeight: '600', fontSize: 13 }}>
        {label}
      </Text>
    </Pressable>
  );
};

// ── Folio detail (Task #457) ───────────────────────────────────────────────
// Deep-linkable folio detail: the cashier open-folios list, plus the front-desk
// and POS screens, link into here by folio id. Renders its own loading / empty
// / error (a cold link has no warm list cache). Charge + payment writes go
// through the shared kit's ActionSheet with a two-step confirm; closed folios
// are read-only with a clear notice, and the backend's closed-folio rejection
// is surfaced as a plain Turkish error.
export default function FolioDetailScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const financeReports = useAuthStore((s) => s.financeReports);
  const params = useLocalSearchParams<{
    id: string;
    guest?: string;
    room?: string;
    pay?: string;
  }>();
  const folioId = Array.isArray(params.id) ? params.id[0] : params.id;
  const headerGuest = Array.isArray(params.guest) ? params.guest[0] : params.guest;
  const headerRoom = Array.isArray(params.room) ? params.room[0] : params.room;
  const wantsPay = (Array.isArray(params.pay) ? params.pay[0] : params.pay) === '1';

  const [chargeOpen, setChargeOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(false);

  // Charge form state.
  const [chargeStep, setChargeStep] = useState<'form' | 'confirm'>('form');
  const [chargeDesc, setChargeDesc] = useState('');
  const [chargeAmount, setChargeAmount] = useState('');
  const [chargeQty, setChargeQty] = useState('1');
  const [chargeCat, setChargeCat] = useState<FolioChargeCategory>('other');
  const [chargeError, setChargeError] = useState('');
  const chargeKeyRef = useRef<string | null>(null);

  // Payment form state.
  const [paymentStep, setPaymentStep] = useState<'form' | 'confirm'>('form');
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState<FolioPaymentMethod>('cash');
  const [paymentError, setPaymentError] = useState('');
  const paymentKeyRef = useRef<string | null>(null);

  const folioQ = useQuery({
    queryKey: ['folio-detail', folioId],
    queryFn: () => getFolioById(folioId),
    enabled: !!folioId,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['folio-detail', folioId] });
    qc.invalidateQueries({ queryKey: ['folios', 'open'] });
    qc.invalidateQueries({ queryKey: ['folio-dashboard-stats'] });
  };

  const chargeMut = useMutation({
    mutationFn: () => {
      if (!chargeKeyRef.current) {
        chargeKeyRef.current = `mob-charge-${Date.now()}-${Math.round(Math.random() * 1e9)}`;
      }
      return postFolioCharge(
        folioId,
        {
          charge_category: chargeCat,
          description: chargeDesc.trim(),
          amount: Number(chargeAmount.replace(',', '.')),
          quantity: Math.max(1, Number(chargeQty) || 1),
        },
        chargeKeyRef.current,
      );
    },
    onSuccess: () => {
      chargeKeyRef.current = null;
      haptic.success();
      setChargeOpen(false);
      refresh();
    },
    onError: (e: unknown) => {
      haptic.error();
      const status = errorStatus(e);
      setChargeError(status === 404 ? d.closedError : errorMessage(e, tr.errors.generic));
    },
  });

  const paymentMut = useMutation({
    mutationFn: () => {
      if (!paymentKeyRef.current) {
        paymentKeyRef.current = `mob-payment-${Date.now()}-${Math.round(Math.random() * 1e9)}`;
      }
      return postFolioPayment(
        folioId,
        {
          amount: Number(paymentAmount.replace(',', '.')),
          method: paymentMethod,
        },
        paymentKeyRef.current,
      );
    },
    onSuccess: () => {
      paymentKeyRef.current = null;
      haptic.success();
      setPaymentOpen(false);
      refresh();
    },
    onError: (e: unknown) => {
      haptic.error();
      const status = errorStatus(e);
      setPaymentError(status === 404 ? d.closedError : errorMessage(e, tr.errors.generic));
    },
  });

  // Quick-collection deep link: the cashier "Tahsilat Al" CTA links here with
  // ?pay=1 to prime the payment sheet straight away. Fire once, only for an
  // open folio — the actual write still runs through the shared payment flow.
  const autoPayRef = useRef(false);
  useEffect(() => {
    if (autoPayRef.current || !wantsPay) return;
    const f = folioQ.data;
    if (!f || (f.status || '').toLowerCase() !== 'open') return;
    autoPayRef.current = true;
    setPaymentStep('form');
    setPaymentAmount(f.balance && f.balance > 0 ? String(f.balance) : '');
    setPaymentMethod('cash');
    setPaymentError('');
    paymentKeyRef.current = null;
    haptic.tap();
    setPaymentOpen(true);
  }, [folioQ.data, wantsPay]);

  // Hard guard: a user without the finance entitlement is bounced to the hub.
  // Cosmetic only — the backend still enforces every read/write.
  if (!financeReports) return <Redirect href={ROUTES.departments} />;

  const folio = folioQ.data ?? null;
  const isOpen = (folio?.status || '').toLowerCase() === 'open';

  const openChargeSheet = () => {
    setChargeStep('form');
    setChargeDesc('');
    setChargeAmount('');
    setChargeQty('1');
    setChargeCat('other');
    setChargeError('');
    chargeKeyRef.current = null;
    haptic.tap();
    setChargeOpen(true);
  };

  const openPaymentSheet = () => {
    setPaymentStep('form');
    setPaymentAmount(folio?.balance && folio.balance > 0 ? String(folio.balance) : '');
    setPaymentMethod('cash');
    setPaymentError('');
    paymentKeyRef.current = null;
    haptic.tap();
    setPaymentOpen(true);
  };

  const chargeAmountNum = Number(chargeAmount.replace(',', '.'));
  const paymentAmountNum = Number(paymentAmount.replace(',', '.'));

  const onChargeContinue = () => {
    setChargeError('');
    if (!chargeDesc.trim()) {
      setChargeError(d.descriptionRequired);
      haptic.warning();
      return;
    }
    if (!(chargeAmountNum > 0)) {
      setChargeError(d.amountRequired);
      haptic.warning();
      return;
    }
    setChargeStep('confirm');
  };

  const onPaymentContinue = () => {
    setPaymentError('');
    if (!(paymentAmountNum > 0)) {
      setPaymentError(d.amountRequired);
      haptic.warning();
      return;
    }
    setPaymentStep('confirm');
  };

  const renderCharge = (ch: FolioCharge, idx: number, last: boolean) => {
    const amount = typeof ch.total === 'number' ? ch.total : ch.amount;
    return (
      <View
        key={ch.id || `charge-${idx}`}
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          paddingVertical: spacing.sm,
          borderBottomWidth: last ? 0 : 1,
          borderBottomColor: c.border,
          gap: spacing.sm,
        }}
      >
        <View style={{ flex: 1 }}>
          <Body style={{ fontWeight: '600' }}>{ch.description || '-'}</Body>
          {ch.posted_at ? (
            <Muted style={{ marginTop: 2 }}>
              {formatDate(ch.posted_at)} · {formatTime(ch.posted_at)}
            </Muted>
          ) : null}
        </View>
        <Body style={{ fontWeight: '700' }}>{formatCurrency(amount)}</Body>
      </View>
    );
  };

  const renderPayment = (pm: FolioPayment, idx: number, last: boolean) => {
    const map = tr.departments.cashier.methods as Record<string, string>;
    return (
      <View
        key={pm.id || `payment-${idx}`}
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          paddingVertical: spacing.sm,
          borderBottomWidth: last ? 0 : 1,
          borderBottomColor: c.border,
          gap: spacing.sm,
        }}
      >
        <View style={{ flex: 1 }}>
          <Body style={{ fontWeight: '600' }}>
            {(pm.method && map[pm.method]) || pm.method || map.other}
          </Body>
          {pm.processed_at ? (
            <Muted style={{ marginTop: 2 }}>
              {formatDate(pm.processed_at)} · {formatTime(pm.processed_at)}
            </Muted>
          ) : null}
        </View>
        <Body style={{ fontWeight: '700', color: c.success }}>
          {formatCurrency(pm.amount)}
        </Body>
      </View>
    );
  };

  // Loading / error / not-found states (cold deep link safe). DepartmentListState
  // is a render FUNCTION that returns null when there is data, so we CALL it (a
  // JSX element would always be truthy) and only early-return a non-null node.
  const listState = DepartmentListState({
    loading: folioQ.isLoading,
    error: folioQ.error,
    isEmpty: !folio,
    emptyText: d.notFound,
  });
  if (listState) {
    return (
      <ScrollView
        style={{ flex: 1, backgroundColor: c.bg }}
        contentContainerStyle={[{ padding: spacing.lg }, webCenter]}
        testID="smoke-folio-detail"
      >
        {listState}
      </ScrollView>
    );
  }

  const charges = folio?.charges ?? [];
  const payments = folio?.payments ?? [];
  const balance = folio?.balance ?? 0;
  const owes = balance > 0;
  const balanceAccent = owes ? c.danger : c.success;
  const chargesTotal = charges.reduce(
    (s, ch) => s + (typeof ch.total === 'number' ? ch.total : ch.amount ?? 0),
    0,
  );
  const paymentsTotal = payments.reduce((s, pm) => s + (pm.amount ?? 0), 0);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
      testID="smoke-folio-detail"
    >
      <DetailHeader
        title={headerGuest || folio?.folio_number || d.folio}
        subtitle={
          [
            folio?.folio_number ? `${d.folio} ${folio.folio_number}` : null,
            headerRoom ? `${tr.departments.cashier.room} ${headerRoom}` : null,
          ]
            .filter(Boolean)
            .join(' · ') || undefined
        }
        badges={<Badge label={statusLabel(folio?.status)} tone={statusTone(folio?.status)} />}
      />

      {/* Balance hero — accent-coded, with charge/payment totals beneath. */}
      <Card accent={balanceAccent} style={{ marginTop: spacing.md }}>
        <Muted style={{ fontSize: 12, fontWeight: '600' }}>{tr.departments.cashier.balance}</Muted>
        <Text
          style={{
            color: balanceAccent,
            fontSize: 34,
            fontWeight: '800',
            letterSpacing: -0.8,
            marginTop: 2,
          }}
          numberOfLines={1}
          adjustsFontSizeToFit
        >
          {formatCurrency(balance)}
        </Text>
        <Muted style={{ fontSize: 12, marginTop: 2 }}>
          {owes ? d.balanceDue : d.balanceSettled}
        </Muted>
        <View
          style={{
            flexDirection: 'row',
            marginTop: spacing.md,
            borderTopWidth: 1,
            borderTopColor: c.border,
            paddingTop: spacing.md,
          }}
        >
          <View style={{ flex: 1 }}>
            <Muted style={{ fontSize: 11 }}>{d.charges}</Muted>
            <Body style={{ fontWeight: '700', marginTop: 1 }}>
              {formatCurrency(chargesTotal)}
            </Body>
          </View>
          <View style={{ flex: 1 }}>
            <Muted style={{ fontSize: 11 }}>{d.payments}</Muted>
            <Body style={{ fontWeight: '700', color: c.success, marginTop: 1 }}>
              {formatCurrency(paymentsTotal)}
            </Body>
          </View>
        </View>
      </Card>

      {/* Charges */}
      <SectionTitle title={d.charges} />
      <Card>
        {charges.length === 0 ? (
          <Muted>{d.noCharges}</Muted>
        ) : (
          charges.map((ch, i) => renderCharge(ch, i, i === charges.length - 1))
        )}
      </Card>

      {/* Payments */}
      <SectionTitle title={d.payments} />
      <Card>
        {payments.length === 0 ? (
          <Muted>{d.noPayments}</Muted>
        ) : (
          payments.map((pm, i) => renderPayment(pm, i, i === payments.length - 1))
        )}
      </Card>

      {/* Actions — closed folios are read-only with a clear notice. */}
      {isOpen ? (
        <View style={{ marginTop: spacing.lg }}>
          <SegmentedActions testID="smoke-folio-actions">
            <ActionButton
              label={d.addCharge}
              icon="add-circle-outline"
              onPress={openChargeSheet}
              bg={c.surfaceAlt}
              fg={c.text}
              testID="smoke-folio-add-charge"
            />
            <ActionButton
              label={d.takePayment}
              icon="cash-outline"
              onPress={openPaymentSheet}
              bg={c.primary}
              fg={c.primaryText}
              testID="smoke-folio-take-payment"
            />
          </SegmentedActions>
        </View>
      ) : (
        <Card style={{ marginTop: spacing.lg }} accent={c.warning}>
          <Body style={{ color: c.textMuted }}>{d.closedNotice}</Body>
        </Card>
      )}

      {/* ── Charge action sheet (two-step confirm) ─────────────────────────── */}
      <ActionSheet
        visible={chargeOpen}
        onClose={() => setChargeOpen(false)}
        title={d.chargeSheetTitle}
        testID="smoke-folio-charge-sheet"
      >
        {chargeStep === 'form' ? (
          <>
            <Field
              label={d.description}
              value={chargeDesc}
              onChangeText={setChargeDesc}
              placeholder={d.descriptionPlaceholder}
              testID="smoke-folio-charge-desc"
            />
            <Field
              label={d.amount}
              value={chargeAmount}
              onChangeText={setChargeAmount}
              placeholder="0"
              keyboardType="decimal-pad"
              testID="smoke-folio-charge-amount"
            />
            <Field
              label={d.quantity}
              value={chargeQty}
              onChangeText={setChargeQty}
              placeholder="1"
              keyboardType="number-pad"
            />
            <Muted>{d.category}</Muted>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
              {CHARGE_CATEGORIES.map((cat) => (
                <Chip
                  key={cat}
                  active={chargeCat === cat}
                  label={(d.categories as Record<string, string>)[cat] || cat}
                  onPress={() => setChargeCat(cat)}
                />
              ))}
            </View>
            {chargeError ? (
              <Body style={{ color: c.danger }}>{chargeError}</Body>
            ) : null}
            <FormActions>
              <Button title={d.cancel} variant="secondary" onPress={() => setChargeOpen(false)} />
              <Button title={d.continue} onPress={onChargeContinue} />
            </FormActions>
          </>
        ) : (
          <>
            <Body>{d.reviewCharge}</Body>
            <Card>
              <DetailRow label={d.description} value={chargeDesc.trim()} />
              <DetailRow
                label={d.category}
                value={(d.categories as Record<string, string>)[chargeCat] || chargeCat}
              />
              <DetailRow label={d.quantity} value={String(Math.max(1, Number(chargeQty) || 1))} />
              <DetailRow
                label={d.amount}
                value={formatCurrency(chargeAmountNum * Math.max(1, Number(chargeQty) || 1))}
              />
            </Card>
            {chargeError ? <Body style={{ color: c.danger }}>{chargeError}</Body> : null}
            <FormActions>
              <Button
                title={d.back}
                variant="secondary"
                onPress={() => setChargeStep('form')}
                disabled={chargeMut.isPending}
              />
              <Button
                title={d.submit}
                onPress={() => chargeMut.mutate()}
                loading={chargeMut.isPending}
                testID="smoke-folio-charge-submit"
              />
            </FormActions>
          </>
        )}
      </ActionSheet>

      {/* ── Payment action sheet (two-step confirm) ────────────────────────── */}
      <ActionSheet
        visible={paymentOpen}
        onClose={() => setPaymentOpen(false)}
        title={d.paymentSheetTitle}
        testID="smoke-folio-payment-sheet"
      >
        {paymentStep === 'form' ? (
          <>
            <Field
              label={d.amount}
              value={paymentAmount}
              onChangeText={setPaymentAmount}
              placeholder="0"
              keyboardType="decimal-pad"
              testID="smoke-folio-payment-amount"
            />
            <Muted>{d.paymentMethod}</Muted>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
              {PAYMENT_METHODS.map((m) => (
                <Chip
                  key={m}
                  active={paymentMethod === m}
                  label={(tr.departments.cashier.methods as Record<string, string>)[m] || m}
                  onPress={() => setPaymentMethod(m)}
                />
              ))}
            </View>
            {paymentError ? <Body style={{ color: c.danger }}>{paymentError}</Body> : null}
            <FormActions>
              <Button title={d.cancel} variant="secondary" onPress={() => setPaymentOpen(false)} />
              <Button title={d.continue} onPress={onPaymentContinue} />
            </FormActions>
          </>
        ) : (
          <>
            <Body>{d.reviewPayment}</Body>
            <Card>
              <DetailRow
                label={d.paymentMethod}
                value={
                  (tr.departments.cashier.methods as Record<string, string>)[paymentMethod] ||
                  paymentMethod
                }
              />
              <DetailRow label={d.amount} value={formatCurrency(paymentAmountNum)} />
            </Card>
            {paymentError ? <Body style={{ color: c.danger }}>{paymentError}</Body> : null}
            <FormActions>
              <Button
                title={d.back}
                variant="secondary"
                onPress={() => setPaymentStep('form')}
                disabled={paymentMut.isPending}
              />
              <Button
                title={d.submit}
                onPress={() => paymentMut.mutate()}
                loading={paymentMut.isPending}
                testID="smoke-folio-payment-submit"
              />
            </FormActions>
          </>
        )}
      </ActionSheet>
    </ScrollView>
  );
}
