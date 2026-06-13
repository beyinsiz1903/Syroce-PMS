import React, { useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionButton,
  Badge,
  Body,
  Card,
  EmptyState,
  FadeInView,
  Field,
  H1,
  Muted,
  SegmentedActions,
  SkeletonCard,
  webCenter,
} from '../../src/components/ui';
import {
  DepartmentListState,
  SectionTitle,
} from '../../src/components/department';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import { haptic } from '../../src/hooks/useHaptic';
import { errorMessage } from '../../src/utils/errors';
import {
  PROCUREMENT_TABS,
  screenRedirectsToHub,
  type ProcurementTab,
} from '../../src/utils/departmentScreens';
import {
  listPurchaseRequests,
  listPurchaseOrders,
  getPurchaseRequest,
  getPurchaseOrder,
  changePrStatus,
  changePoStatus,
  getSupplierCreditUtilisation,
  type PurchaseRequest,
  type PurchaseOrder,
  type PrStatusAction,
  type PoStatusAction,
} from '../../src/api/procurement';
import { formatCurrency, formatDate } from '../../src/utils/format';

type Tab = ProcurementTab;
type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'primary';
type Selected = { type: 'pr' | 'po'; id: string };

function statusTone(status?: string): Tone {
  switch (status) {
    case 'approved':
    case 'received':
      return 'success';
    case 'rejected':
    case 'cancelled':
      return 'danger';
    case 'submitted':
    case 'sent':
    case 'partially_received':
      return 'warning';
    case 'converted':
      return 'info';
    default:
      return 'default';
  }
}

function prStatusLabel(status?: string): string {
  const map = tr.departments.procurement.prStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

function poStatusLabel(status?: string): string {
  const map = tr.departments.procurement.poStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

// Maps a status to its theme accent color so each list card carries a coloured
// left bar (status at-a-glance) that matches its badge tone.
function toneColor(c: ReturnType<typeof useTheme>, status?: string): string {
  switch (statusTone(status)) {
    case 'success':
      return c.success;
    case 'danger':
      return c.danger;
    case 'warning':
      return c.warning;
    case 'info':
      return c.info;
    case 'primary':
      return c.primary;
    default:
      return c.border;
  }
}

// label/value detail row, mirrors the sibling MICE detail screen layout.
const Row: React.FC<{ label: string; value?: string | number | null }> = ({
  label,
  value,
}) => {
  if (value === undefined || value === null || value === '') return null;
  return (
    <View
      style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2 }}
    >
      <Muted>{label}</Muted>
      <Body style={{ flexShrink: 1, textAlign: 'right', paddingLeft: spacing.md }}>
        {String(value)}
      </Body>
    </View>
  );
};

const t = () => tr.departments.procurement;

// A single status decision the detail screen can fire. `needsReason` toggles the
// inline reason field (backend requires reason >= 5 chars for reject/cancel).
type Decision = {
  key: string;
  label: string;
  bg: (c: ReturnType<typeof useTheme>) => string;
  fg: (c: ReturnType<typeof useTheme>) => string;
  icon: 'checkmark-circle' | 'close-circle' | 'send' | 'ban' | 'lock-closed';
  needsReason: boolean;
  confirmText: string;
  run: () => Promise<unknown>;
};

// ── PR decisions (submitted → approved/rejected) ────────────────────────────
// `run` covers the no-reason path; reason-bearing decisions (needsReason) are
// fired by DecisionBar with the captured text, so their `run` is a no-op.
function prDecisions(pr: PurchaseRequest): Decision[] {
  if (pr.status !== 'submitted') return [];
  const p = t();
  return [
    {
      key: 'reject',
      label: p.reject,
      bg: (c) => c.danger + '14',
      fg: (c) => c.danger,
      icon: 'close-circle',
      needsReason: true,
      confirmText: p.rejectReasonPlaceholder,
      run: () => Promise.resolve(),
    },
    {
      key: 'approve',
      label: p.approve,
      bg: (c) => c.success,
      fg: () => '#ffffff',
      icon: 'checkmark-circle',
      needsReason: false,
      confirmText: p.approveConfirm,
      run: () => changePrStatus(pr.id, 'approved'),
    },
  ];
}

// ── PO decisions (draft→sent|cancelled, sent→cancelled, received→closed) ─────
function poDecisions(po: PurchaseOrder): Decision[] {
  const p = t();
  const out: Decision[] = [];
  const status = po.status || 'draft';
  if (status === 'draft') {
    out.push({
      key: 'send',
      label: p.send,
      bg: (c) => c.primary,
      fg: (c) => c.primaryText,
      icon: 'send',
      needsReason: false,
      confirmText: p.sendConfirm,
      run: () => changePoStatus(po.id, 'sent'),
    });
  }
  if (status === 'received') {
    out.push({
      key: 'close',
      label: p.close,
      bg: (c) => c.primary,
      fg: (c) => c.primaryText,
      icon: 'lock-closed',
      needsReason: false,
      confirmText: p.closeConfirm,
      run: () => changePoStatus(po.id, 'closed'),
    });
  }
  if (['draft', 'sent', 'partially_received'].includes(status)) {
    out.push({
      key: 'cancel',
      label: p.cancel,
      bg: (c) => c.danger + '14',
      fg: (c) => c.danger,
      icon: 'ban',
      needsReason: true,
      confirmText: p.cancelReasonPlaceholder,
      run: () => Promise.resolve(),
    });
  }
  return out;
}

// Inline two-step action bar (NOT Alert.alert — a no-op on Expo Web). Tapping a
// decision reveals an inline confirm (or reason field), then fires the
// mutation. Mirrors the unified approvals screen pattern.
function DecisionBar({
  poId,
  prId,
  decisions,
  testIDPrefix = 'proc-decision',
}: {
  poId?: string;
  prId?: string;
  decisions: Decision[];
  testIDPrefix?: string;
}) {
  const c = useTheme();
  const qc = useQueryClient();
  const p = t();
  const [active, setActive] = useState<Decision | null>(null);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState(false);

  const mutation = useMutation({
    mutationFn: (vars: { decision: Decision; reason?: string }) => {
      const d = vars.decision;
      // Reason-bearing decisions need the captured text routed to the API.
      if (d.needsReason) {
        if (prId) {
          return changePrStatus(prId, 'rejected', vars.reason);
        }
        return changePoStatus(poId as string, 'cancelled', vars.reason);
      }
      return d.run();
    },
    onSuccess: () => {
      haptic.success();
      setActive(null);
      setReason('');
      setReasonError(false);
      qc.invalidateQueries({ queryKey: ['proc-prs'] });
      qc.invalidateQueries({ queryKey: ['proc-pos'] });
      if (prId) qc.invalidateQueries({ queryKey: ['proc-pr', prId] });
      if (poId) qc.invalidateQueries({ queryKey: ['proc-po', poId] });
      qc.invalidateQueries({ queryKey: ['hub-approvals'] });
    },
    onError: () => haptic.error(),
  });

  if (decisions.length === 0) return null;

  const onPick = (d: Decision) => {
    haptic.tap();
    if (mutation.isError) mutation.reset();
    setReason('');
    setReasonError(false);
    setActive((cur) => (cur?.key === d.key ? null : d));
  };

  const onConfirm = () => {
    if (!active) return;
    if (active.needsReason) {
      const trimmed = reason.trim();
      if (trimmed.length < 5) {
        setReasonError(true);
        return;
      }
      mutation.mutate({ decision: active, reason: trimmed });
      return;
    }
    mutation.mutate({ decision: active });
  };

  return (
    <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
      {mutation.isError ? (
        <Muted style={{ color: c.danger }}>
          {errorMessage(mutation.error, p.actionError)}
        </Muted>
      ) : null}

      {active ? (
        <View style={{ gap: spacing.sm }}>
          {active.needsReason ? (
            <>
              <Field
                label={p.reasonLabel}
                placeholder={active.confirmText}
                value={reason}
                onChangeText={(v) => {
                  setReason(v);
                  if (reasonError) setReasonError(false);
                }}
                multiline
                editable={!mutation.isPending}
              />
              {reasonError ? (
                <Muted style={{ color: c.danger }}>{p.reasonRequired}</Muted>
              ) : null}
            </>
          ) : (
            <Muted>{active.confirmText}</Muted>
          )}
          <SegmentedActions>
            <ActionButton
              label={p.cancelAction}
              icon="arrow-undo"
              onPress={() => {
                setActive(null);
                setReason('');
                setReasonError(false);
              }}
              bg={c.surfaceAlt}
              fg={c.text}
              disabled={mutation.isPending}
            />
            <ActionButton
              testID={`${testIDPrefix}-confirm-${active.key}`}
              label={active.label}
              icon={active.icon}
              onPress={onConfirm}
              bg={active.bg(c)}
              fg={active.fg(c)}
              loading={mutation.isPending}
            />
          </SegmentedActions>
        </View>
      ) : (
        <SegmentedActions>
          {decisions.map((d) => (
            <ActionButton
              key={d.key}
              testID={`${testIDPrefix}-${d.key}`}
              label={d.label}
              icon={d.icon}
              onPress={() => onPick(d)}
              bg={d.bg(c)}
              fg={d.fg(c)}
              disabled={mutation.isPending}
            />
          ))}
        </SegmentedActions>
      )}
    </View>
  );
}

// View-only supplier credit-limit exposure, surfaced on the PO detail. Mirrors
// the backend warning logic (warning >= 80%, exceeded > 100%). Gated on the
// finance-reports entitlement because the endpoint requires it server-side.
function CreditWarning({ supplierId }: { supplierId: string }) {
  const c = useTheme();
  const p = t();
  const q = useQuery({
    queryKey: ['proc-credit', supplierId],
    queryFn: () => getSupplierCreditUtilisation(supplierId),
  });
  const data = q.data;
  if (!data || data.limit === null) return null;

  const danger = data.exceeded;
  const warn = data.warning && !data.exceeded;
  const accent = danger ? c.danger : warn ? c.warning : c.border;

  return (
    <Card style={{ marginTop: spacing.sm, borderColor: accent, borderWidth: 1 }}>
      <Body style={{ fontWeight: '700' }}>{p.creditTitle}</Body>
      {danger || warn ? (
        <Muted style={{ marginTop: spacing.xs, color: accent }}>
          {danger ? p.creditExceeded : p.creditWarning}
        </Muted>
      ) : null}
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        <Row label={p.creditLimit} value={formatCurrency(data.limit)} />
        <Row label={p.creditOpenTotal} value={formatCurrency(data.open_total)} />
        {data.headroom !== null ? (
          <Row label={p.creditHeadroom} value={formatCurrency(data.headroom)} />
        ) : null}
        {data.used_pct !== null ? (
          <Row label={p.creditUsed} value={`%${data.used_pct}`} />
        ) : null}
      </View>
    </Card>
  );
}

// ── Purchase Request detail ─────────────────────────────────────────────────
function RequestDetail({
  id,
  canManage,
  onBack,
}: {
  id: string;
  canManage: boolean;
  onBack: () => void;
}) {
  const p = t();
  const q = useQuery({
    queryKey: ['proc-pr', id],
    queryFn: () => getPurchaseRequest(id),
    enabled: !!id,
  });
  const pr = q.data;

  return (
    <DetailScaffold
      onBack={onBack}
      loading={q.isLoading}
      error={!!q.error || !pr}
    >
      {pr ? (
        <>
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: spacing.sm,
            }}
          >
            <H1 style={{ flex: 1 }}>{pr.pr_no || p.requestDetail}</H1>
            <Badge label={prStatusLabel(pr.status)} tone={statusTone(pr.status)} />
          </View>

          <Card style={{ marginTop: spacing.md }}>
            <Row label={p.department} value={pr.department} />
            <Row label={p.requester} value={pr.requester} />
            <Row
              label={p.neededBy}
              value={pr.needed_by ? formatDate(pr.needed_by) : undefined}
            />
            <Row
              label={p.total}
              value={
                typeof pr.lines_total === 'number'
                  ? formatCurrency(pr.lines_total)
                  : undefined
              }
            />
          </Card>

          <SectionTitle title={p.lineItems} />
          {(pr.lines || []).length === 0 ? (
            <Card>
              <Muted>{p.noLineItems}</Muted>
            </Card>
          ) : (
            (pr.lines || []).map((ln, i) => (
              <Card key={`${ln.item_name}-${i}`} style={{ marginBottom: spacing.sm }}>
                <Body style={{ fontWeight: '600' }}>{ln.item_name || '—'}</Body>
                <View style={{ marginTop: spacing.xs, gap: 2 }}>
                  {typeof ln.quantity === 'number' ? (
                    <Row
                      label={p.quantity}
                      value={`${ln.quantity}${ln.unit ? ` ${ln.unit}` : ''}`}
                    />
                  ) : null}
                  {typeof ln.est_unit_cost === 'number' ? (
                    <Row label={p.unitCost} value={formatCurrency(ln.est_unit_cost)} />
                  ) : null}
                </View>
              </Card>
            ))
          )}

          {pr.notes ? (
            <>
              <SectionTitle title={p.notes} />
              <Card>
                <Body>{pr.notes}</Body>
              </Card>
            </>
          ) : null}

          {canManage ? <DecisionBar prId={pr.id} decisions={prDecisions(pr)} /> : null}
        </>
      ) : null}
    </DetailScaffold>
  );
}

// ── Purchase Order detail ───────────────────────────────────────────────────
function OrderDetail({
  id,
  canManage,
  canViewCredit,
  onBack,
}: {
  id: string;
  canManage: boolean;
  canViewCredit: boolean;
  onBack: () => void;
}) {
  const p = t();
  const q = useQuery({
    queryKey: ['proc-po', id],
    queryFn: () => getPurchaseOrder(id),
    enabled: !!id,
  });
  const po = q.data;

  return (
    <DetailScaffold
      onBack={onBack}
      loading={q.isLoading}
      error={!!q.error || !po}
    >
      {po ? (
        <>
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: spacing.sm,
            }}
          >
            <H1 style={{ flex: 1 }}>{po.po_no || p.orderDetail}</H1>
            <Badge label={poStatusLabel(po.status)} tone={statusTone(po.status)} />
          </View>

          <Card style={{ marginTop: spacing.md }}>
            <Row label={p.supplier} value={po.supplier_name} />
            <Row
              label={p.expectedDelivery}
              value={po.expected_delivery ? formatDate(po.expected_delivery) : undefined}
            />
            <Row
              label={p.subtotal}
              value={
                typeof po.subtotal === 'number'
                  ? formatCurrency(po.subtotal, po.currency)
                  : undefined
              }
            />
            <Row
              label={p.taxTotal}
              value={
                typeof po.tax_total === 'number'
                  ? formatCurrency(po.tax_total, po.currency)
                  : undefined
              }
            />
            <Row
              label={p.grandTotal}
              value={
                typeof po.grand_total === 'number'
                  ? formatCurrency(po.grand_total, po.currency)
                  : undefined
              }
            />
            <Row label={p.reason} value={po.status_reason} />
          </Card>

          {canViewCredit && po.supplier_id ? (
            <CreditWarning supplierId={po.supplier_id} />
          ) : null}

          <SectionTitle title={p.lineItems} />
          {(po.lines || []).length === 0 ? (
            <Card>
              <Muted>{p.noLineItems}</Muted>
            </Card>
          ) : (
            (po.lines || []).map((ln, i) => (
              <Card key={`${ln.item_name}-${i}`} style={{ marginBottom: spacing.sm }}>
                <Body style={{ fontWeight: '600' }}>{ln.item_name || '—'}</Body>
                <View style={{ marginTop: spacing.xs, gap: 2 }}>
                  {typeof ln.quantity === 'number' ? (
                    <Row
                      label={p.quantity}
                      value={`${ln.quantity}${ln.unit ? ` ${ln.unit}` : ''}`}
                    />
                  ) : null}
                  {typeof ln.unit_cost === 'number' ? (
                    <Row
                      label={p.unitCost}
                      value={formatCurrency(ln.unit_cost, po.currency)}
                    />
                  ) : null}
                  {typeof ln.line_total === 'number' ? (
                    <Row
                      label={p.lineTotal}
                      value={formatCurrency(ln.line_total, po.currency)}
                    />
                  ) : null}
                  {typeof ln.received_qty === 'number' && ln.received_qty > 0 ? (
                    <Row label={p.receivedQty} value={ln.received_qty} />
                  ) : null}
                </View>
              </Card>
            ))
          )}

          {(po.grns || []).length > 0 ? (
            <>
              <SectionTitle title={p.goodsReceipts} />
              {(po.grns || []).map((g, i) => (
                <Card key={`${g.id}-${i}`} style={{ marginBottom: spacing.sm }}>
                  <Body style={{ fontWeight: '600' }}>{g.grn_no || '—'}</Body>
                  <View style={{ marginTop: spacing.xs, gap: 2 }}>
                    <Row
                      label={p.receivedAt}
                      value={g.received_at ? formatDate(g.received_at) : undefined}
                    />
                    <Row label={p.requester} value={g.received_by} />
                  </View>
                </Card>
              ))}
            </>
          ) : null}

          {po.notes ? (
            <>
              <SectionTitle title={p.notes} />
              <Card>
                <Body>{po.notes}</Body>
              </Card>
            </>
          ) : null}

          {canManage ? <DecisionBar poId={po.id} decisions={poDecisions(po)} /> : null}
        </>
      ) : null}
    </DetailScaffold>
  );
}

// Shared detail chrome: a back affordance + loading / error handling so both
// PR and PO detail render identically.
function DetailScaffold({
  onBack,
  loading,
  error,
  children,
}: {
  onBack: () => void;
  loading: boolean;
  error: boolean;
  children: React.ReactNode;
}) {
  const c = useTheme();
  const p = t();
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
    >
      <Pressable
        onPress={onBack}
        accessibilityRole="button"
        testID="proc-detail-back"
        style={{ flexDirection: 'row', alignItems: 'center', marginBottom: spacing.md }}
      >
        <Body style={{ color: c.primary, fontSize: 18 }}>‹ </Body>
        <Body style={{ color: c.primary, fontWeight: '600' }}>{p.back}</Body>
      </Pressable>

      {loading ? (
        <SkeletonCard />
      ) : error ? (
        <Card>
          <Body>{p.loadError}</Body>
        </Card>
      ) : (
        children
      )}
    </ScrollView>
  );
}

// Read+approve Procurement screen. Four sections (Talepler / Onay Bekleyenler /
// Siparişler / Teslimatlar) presented as a scrollable premium pill bar. Each
// list card carries a status-coloured accent and drills into a detail with
// permission-gated two-step approve/reject (PR) and send/cancel/close (PO)
// actions; the "Onay Bekleyenler" section also surfaces the big thumb-zone
// approve/reject inline on every card. All writes stay backend-gated by
// require_op("manage_sales") + require_procurement; the credit-limit warning is
// view-only.
export default function ProcurementScreen() {
  const c = useTheme();
  const rawRole = useAuthStore((s) => s.user?.role);
  const procurementAccess = !screenRedirectsToHub('procurement', rawRole);
  const financeReports = useAuthStore((s) => s.financeReports);
  const [tab, setTab] = useState<Tab>('requests');
  const [selected, setSelected] = useState<Selected | null>(null);
  const p = tr.departments.procurement;

  // Both lists feed two sections each (PRs → Talepler + Onay Bekleyenler, POs →
  // Siparişler + Teslimatlar), so fetch each once whenever the list is shown
  // rather than per-tab. Reads stay backend-gated; this just makes tab switches
  // instant and keeps the pending/delivery counts live.
  const prQ = useQuery({
    queryKey: ['proc-prs'],
    queryFn: () => listPurchaseRequests(),
    enabled: procurementAccess && !selected,
  });
  const poQ = useQuery({
    queryKey: ['proc-pos'],
    queryFn: () => listPurchaseOrders(),
    enabled: procurementAccess && !selected,
  });

  if (screenRedirectsToHub('procurement', rawRole)) {
    return <Redirect href={ROUTES.departments} />;
  }

  if (selected) {
    const onBack = () => setSelected(null);
    return selected.type === 'pr' ? (
      <RequestDetail id={selected.id} canManage={procurementAccess} onBack={onBack} />
    ) : (
      <OrderDetail
        id={selected.id}
        canManage={procurementAccess}
        canViewCredit={financeReports}
        onBack={onBack}
      />
    );
  }

  const prs = prQ.data || [];
  const pos = poQ.data || [];
  // Onay Bekleyenler = submitted PRs (the only PR state that carries an
  // approve/reject decision). Teslimatlar = POs whose goods have started or
  // finished arriving.
  const pendingPrs = prs.filter((pr) => pr.status === 'submitted');
  const deliveries = pos.filter((po) =>
    ['partially_received', 'received', 'closed'].includes(po.status || ''),
  );

  // Label + live count per section, keyed by tab. The rendered order/set is
  // derived from PROCUREMENT_TABS (single source of truth the unit test guards),
  // not a second hardcoded list.
  const tabMeta: Record<ProcurementTab, { label: string; count: number }> = {
    requests: { label: p.tabRequests, count: prs.length },
    pending: { label: p.tabPending, count: pendingPrs.length },
    orders: { label: p.tabOrders, count: pos.length },
    deliveries: { label: p.tabDeliveries, count: deliveries.length },
  };
  const tabs = PROCUREMENT_TABS.map((value) => ({ value, ...tabMeta[value] }));

  const TabPill: React.FC<{ value: Tab; label: string; count: number }> = ({
    value,
    label,
    count,
  }) => {
    const active = tab === value;
    return (
      <Pressable
        onPress={() => {
          haptic.tap();
          setTab(value);
        }}
        accessibilityRole="button"
        accessibilityState={{ selected: active }}
        testID={`proc-tab-${value}`}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: spacing.xs,
          paddingVertical: spacing.sm,
          paddingHorizontal: spacing.lg,
          borderRadius: radius.pill,
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
        {count > 0 ? (
          <View
            style={{
              minWidth: 20,
              paddingHorizontal: 6,
              paddingVertical: 1,
              borderRadius: radius.pill,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: active ? 'rgba(255,255,255,0.22)' : c.primarySoft,
            }}
          >
            <Body
              style={{
                color: active ? c.primaryText : c.primary,
                fontSize: 12,
                fontWeight: '700',
              }}
            >
              {count}
            </Body>
          </View>
        ) : null}
      </Pressable>
    );
  };

  const renderRequest = (pr: PurchaseRequest, i: number) => (
    <FadeInView key={pr.id} delay={Math.min(i, 6) * 40}>
      <Pressable
        onPress={() => setSelected({ type: 'pr', id: pr.id })}
        accessibilityRole="button"
        testID={`proc-pr-${pr.id}`}
      >
        {({ pressed }) => (
          <Card
            accent={toneColor(c, pr.status)}
            style={{ marginBottom: spacing.sm, opacity: pressed ? 0.85 : 1 }}
          >
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
              }}
            >
              <View style={{ flex: 1, paddingRight: spacing.sm }}>
                <Body style={{ fontWeight: '600' }}>{pr.pr_no || '—'}</Body>
                {pr.department ? (
                  <Muted>
                    {p.department}: {pr.department}
                  </Muted>
                ) : null}
              </View>
              <Badge label={prStatusLabel(pr.status)} tone={statusTone(pr.status)} />
            </View>
            <View style={{ marginTop: spacing.sm, gap: 2 }}>
              {pr.requester ? (
                <Muted>
                  {p.requester}: {pr.requester}
                </Muted>
              ) : null}
              {pr.needed_by ? (
                <Muted>
                  {p.neededBy}: {formatDate(pr.needed_by)}
                </Muted>
              ) : null}
              <Muted>
                {p.lines}: {(pr.lines || []).length}
              </Muted>
              {typeof pr.lines_total === 'number' ? (
                <Muted>
                  {p.total}: {formatCurrency(pr.lines_total)}
                </Muted>
              ) : null}
            </View>
          </Card>
        )}
      </Pressable>
    </FadeInView>
  );

  // Onay Bekleyenler card: same summary as a request, but the big thumb-zone
  // approve/reject (DecisionBar) is surfaced inline so an approver acts without
  // opening the detail; tapping the summary still drills in for line items.
  // Writes stay backend-gated (require_op manage_sales + require_procurement);
  // canManage mirrors the detail screen's gate. A namespaced testIDPrefix keeps
  // each card's decision buttons unique (the detail keeps proc-decision-*).
  const renderPending = (pr: PurchaseRequest, i: number) => (
    <FadeInView key={pr.id} delay={Math.min(i, 6) * 40}>
      <Card accent={toneColor(c, pr.status)} style={{ marginBottom: spacing.sm }}>
        <Pressable
          onPress={() => setSelected({ type: 'pr', id: pr.id })}
          accessibilityRole="button"
          testID={`proc-pending-${pr.id}`}
        >
          {({ pressed }) => (
            <View style={{ opacity: pressed ? 0.85 : 1 }}>
              <View
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                }}
              >
                <View style={{ flex: 1, paddingRight: spacing.sm }}>
                  <Body style={{ fontWeight: '600' }}>{pr.pr_no || '—'}</Body>
                  {pr.department ? (
                    <Muted>
                      {p.department}: {pr.department}
                    </Muted>
                  ) : null}
                </View>
                <Badge label={prStatusLabel(pr.status)} tone={statusTone(pr.status)} />
              </View>
              <View style={{ marginTop: spacing.sm, gap: 2 }}>
                {pr.requester ? (
                  <Muted>
                    {p.requester}: {pr.requester}
                  </Muted>
                ) : null}
                {pr.needed_by ? (
                  <Muted>
                    {p.neededBy}: {formatDate(pr.needed_by)}
                  </Muted>
                ) : null}
                {typeof pr.lines_total === 'number' ? (
                  <Muted>
                    {p.total}: {formatCurrency(pr.lines_total)}
                  </Muted>
                ) : null}
              </View>
            </View>
          )}
        </Pressable>
        {procurementAccess ? (
          <DecisionBar
            prId={pr.id}
            decisions={prDecisions(pr)}
            testIDPrefix={`proc-pending-${pr.id}-decision`}
          />
        ) : null}
      </Card>
    </FadeInView>
  );

  const renderOrder = (po: PurchaseOrder, i: number) => (
    <FadeInView key={po.id} delay={Math.min(i, 6) * 40}>
      <Pressable
        onPress={() => setSelected({ type: 'po', id: po.id })}
        accessibilityRole="button"
        testID={`proc-po-${po.id}`}
      >
        {({ pressed }) => (
          <Card
            accent={toneColor(c, po.status)}
            style={{ marginBottom: spacing.sm, opacity: pressed ? 0.85 : 1 }}
          >
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
              }}
            >
              <View style={{ flex: 1, paddingRight: spacing.sm }}>
                <Body style={{ fontWeight: '600' }}>{po.po_no || '—'}</Body>
                {po.supplier_name ? (
                  <Muted>
                    {p.supplier}: {po.supplier_name}
                  </Muted>
                ) : null}
              </View>
              <Badge label={poStatusLabel(po.status)} tone={statusTone(po.status)} />
            </View>
            <View style={{ marginTop: spacing.sm, gap: 2 }}>
              {po.expected_delivery ? (
                <Muted>
                  {p.expectedDelivery}: {formatDate(po.expected_delivery)}
                </Muted>
              ) : null}
              <Muted>
                {p.lines}: {(po.lines || []).length}
              </Muted>
              {typeof po.grand_total === 'number' ? (
                <Muted>
                  {p.total}: {formatCurrency(po.grand_total, po.currency)}
                </Muted>
              ) : null}
            </View>
          </Card>
        )}
      </Pressable>
    </FadeInView>
  );

  // Teslimatlar card: a PO in a delivery state, emphasising received progress
  // (kaç kalem teslim alındı) over financials; drills into the PO detail which
  // lists the goods-receipt records.
  const renderDelivery = (po: PurchaseOrder, i: number) => {
    const lines = po.lines || [];
    const receivedCount = lines.filter((l) => (l.received_qty || 0) > 0).length;
    return (
      <FadeInView key={po.id} delay={Math.min(i, 6) * 40}>
        <Pressable
          onPress={() => setSelected({ type: 'po', id: po.id })}
          accessibilityRole="button"
          testID={`proc-delivery-${po.id}`}
        >
          {({ pressed }) => (
            <Card
              accent={toneColor(c, po.status)}
              style={{ marginBottom: spacing.sm, opacity: pressed ? 0.85 : 1 }}
            >
              <View
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                }}
              >
                <View style={{ flex: 1, paddingRight: spacing.sm }}>
                  <Body style={{ fontWeight: '600' }}>{po.po_no || '—'}</Body>
                  {po.supplier_name ? (
                    <Muted>
                      {p.supplier}: {po.supplier_name}
                    </Muted>
                  ) : null}
                </View>
                <Badge label={poStatusLabel(po.status)} tone={statusTone(po.status)} />
              </View>
              <View style={{ marginTop: spacing.sm, gap: 2 }}>
                {po.expected_delivery ? (
                  <Muted>
                    {p.expectedDelivery}: {formatDate(po.expected_delivery)}
                  </Muted>
                ) : null}
                {lines.length > 0 ? (
                  <Muted>
                    {p.receivedItems}: {receivedCount} / {lines.length}
                  </Muted>
                ) : null}
              </View>
            </Card>
          )}
        </Pressable>
      </FadeInView>
    );
  };

  // Shared loading/error/empty/data wrapper so the four sections resolve their
  // state machine identically.
  const renderSection = (
    query: { isLoading: boolean; error: unknown },
    rows: React.ReactNode,
    isEmpty: boolean,
    emptyIcon: React.ComponentProps<typeof EmptyState>['icon'],
    emptyTitle: string,
  ) => {
    if (query.isLoading || query.error) {
      return (
        <DepartmentListState loading={query.isLoading} error={query.error} isEmpty={false} />
      );
    }
    if (isEmpty) {
      return <EmptyState icon={emptyIcon} title={emptyTitle} />;
    }
    return <View>{rows}</View>;
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
    >
      <H1>{p.title}</H1>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={{ marginTop: spacing.md }}
        contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.xs }}
      >
        {tabs.map(({ value, label, count }) => (
          <TabPill key={value} value={value} label={label} count={count} />
        ))}
      </ScrollView>

      {tab === 'requests' ? (
        <>
          <SectionTitle title={p.requests} />
          {renderSection(
            prQ,
            prs.map(renderRequest),
            prs.length === 0,
            'document-text-outline',
            p.noRequests,
          )}
        </>
      ) : null}

      {tab === 'pending' ? (
        <>
          <SectionTitle title={p.pending} />
          {renderSection(
            prQ,
            pendingPrs.map(renderPending),
            pendingPrs.length === 0,
            'hourglass-outline',
            p.noPending,
          )}
        </>
      ) : null}

      {tab === 'orders' ? (
        <>
          <SectionTitle title={p.orders} />
          {renderSection(
            poQ,
            pos.map(renderOrder),
            pos.length === 0,
            'cart-outline',
            p.noOrders,
          )}
        </>
      ) : null}

      {tab === 'deliveries' ? (
        <>
          <SectionTitle title={p.deliveries} />
          {renderSection(
            poQ,
            deliveries.map(renderDelivery),
            deliveries.length === 0,
            'cube-outline',
            p.noDeliveries,
          )}
        </>
      ) : null}
    </ScrollView>
  );
}
