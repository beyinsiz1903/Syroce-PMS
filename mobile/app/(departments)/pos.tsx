import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { onlineManager, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionButton,
  Badge,
  Body,
  Button,
  Card,
  DetailRow,
  Field,
  H1,
  ListGroup,
  ListRow,
  Muted,
  SectionTitle,
  SegmentedActions,
  ActionSheet,
  webCenter,
} from '../../src/components/ui';
import { DepartmentListState } from '../../src/components/department';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  getBeo,
  getTableLayout,
  listActiveOrders,
  listBeoEvents,
  listMenuItems,
  listOutlets,
  menuItemLabel,
  openQuickOrder,
  outletLabel,
  postOrderToFolio,
  closeOrder,
  checkSplit,
  transferTable,
  updateOrderStatus,
  listReservations,
  updateReservationStatus,
  type ActiveOrder,
  type BeoSummary,
  type MenuItem,
  type Outlet,
  type OrderStatus,
  type PaymentMethod,
  type TableSlot,
  type Reservation,
} from '../../src/api/posFnb';
import { listFolios, type FolioListItem } from '../../src/api/folio';
import { ApiError } from '../../src/api/client';
import { formatCurrency } from '../../src/utils/format';
import { errorMessage } from '../../src/utils/errors';
import { makeIdempotencyKey } from '../../src/cache/posQueueCore';
import {
  enqueueCloseOrder,
  enqueueQuickOrder,
  refreshPosQueueCount,
  usePosQueueCount,
} from '../../src/cache/posQueue';

// A request that never reached the server (offline / dropped mid-flight) so we
// can safely move it into the durable queue. ApiError(0, 'NETWORK') is raised
// by the API client's fetch catch; everything else is a server response.
function isNetworkError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 0;
}

type Tab = 'tables' | 'order' | 'kitchen' | 'folio' | 'reports' | 'reservations';
type CartLine = { item_id: string; quantity: number };

function statusLabel(s?: string): string {
  const map = tr.departments.pos.status as Record<string, string>;
  return (s && map[s]) || s || '—';
}

function statusTone(s?: string): 'default' | 'success' | 'info' | 'warning' | 'danger' {
  switch (s) {
    case 'served':
      return 'success';
    case 'ready':
      return 'info';
    case 'preparing':
      return 'warning';
    case 'cancelled':
      return 'danger';
    default:
      return 'default';
  }
}

// Concrete colour (not a tone token) for the touch table-plan cells so the grid
// can tint backgrounds/borders directly by reservation status.
function tableStatusColor(s: string | undefined, c: ReturnType<typeof useTheme>): string {
  switch (s) {
    case 'available':
      return c.success;
    case 'occupied':
      return c.warning;
    case 'reserved':
      return c.info;
    default:
      return c.textMuted;
  }
}

function eventStatusLabel(s?: string): string {
  const map = tr.departments.pos.eventStatus as Record<string, string>;
  return (s && map[s]) || s || '—';
}

function eventStatusTone(s?: string): 'default' | 'success' | 'info' | 'warning' | 'danger' {
  switch (s) {
    case 'confirmed':
    case 'definite':
    case 'completed':
      return 'success';
    case 'tentative':
      return 'warning';
    case 'inquiry':
      return 'info';
    case 'cancelled':
    case 'lost':
      return 'danger';
    default:
      return 'default';
  }
}

// Trim an ISO timestamp down to "YYYY-MM-DD HH:MM" for compact space lines.
function shortStamp(value?: string | null): string {
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 16);
}

// Agenda items show only the clock window (HH:MM–HH:MM).
function agendaWindow(a: { starts_at?: string; ends_at?: string }): string {
  const s = (a.starts_at || '').slice(11, 16);
  const e = (a.ends_at || '').slice(11, 16);
  if (!s && !e) return '—';
  return `${s || '—'}–${e || '—'}`;
}

// POS / F&B department screen (Task #331, Faz 4; design-system migration Task
// #463). Five flows over a selected outlet: open an order (quick-order),
// advance/close active orders, view the table layout + transfer a table, post
// an order to a room folio, and read a banquet event's BEO summary. Every write
// is gated server-side by require_module("pos") / require_op; the mobile
// `posAccess` entitlement mirrors that role set. Cosmetic only — the backend
// still enforces. Order/transaction status semantics are not changed here. The
// offline durable write queue + per-attempt idempotency keys are preserved
// exactly; only the presentation migrated to the shared ui.tsx kit.
export default function PosScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const posAccess = useAuthStore((s) => s.posAccess);

  // Count of POS writes (quick-order / close) waiting on the durable offline
  // queue. Drives the header badge; re-read from disk on mount so a restart
  // surfaces anything that was queued before the app was killed.
  const pendingSync = usePosQueueCount();
  useEffect(() => {
    refreshPosQueueCount().catch(() => {});
  }, []);

  const [tab, setTab] = useState<Tab>('tables');
  const [outletId, setOutletId] = useState<string>('');

  // Order-open form state.
  const [tableNumber, setTableNumber] = useState('');
  const [notes, setNotes] = useState('');
  const [cart, setCart] = useState<CartLine[]>([]);
  const [opening, setOpening] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);
  // Per genuine attempt; retry (timeout/warm-up/double-tap) reuses the SAME key,
  // cleared only on success → backend never opens/posts a duplicate (Task #373).
  const postFolioKeyRef = useRef<string | null>(null);

  // Active-order lifecycle state.
  const [busyOrderId, setBusyOrderId] = useState<string | null>(null);
  // Close-and-pay state. The collect flow opens a sheet (`payOrder`) where the
  // operator picks a method and an optional split before confirming, instead of
  // closing inline at full cash/card. `paying` drives the confirm spinner.
  const [payOrder, setPayOrder] = useState<ActiveOrder | null>(null);
  const [payMethod, setPayMethod] = useState<PaymentMethod>('cash');
  const [payMode, setPayMode] = useState<'full' | 'equal' | 'custom'>('full');
  const [splitCount, setSplitCount] = useState(2);
  const [customAmounts, setCustomAmounts] = useState<string[]>(['', '']);
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);
  // Active-order detail sheet — derived live from the query so a status change
  // refresh keeps the sheet in sync (and auto-closes when the order leaves the
  // active list).
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  // Table-transfer state.
  const [fromTable, setFromTable] = useState('');
  const [toTable, setToTable] = useState('');
  const [transferring, setTransferring] = useState(false);

  // Folio-transfer state.
  const [folioId, setFolioId] = useState<string>('');
  const [posting, setPosting] = useState(false);

  // BEO read state — the tapped event opens a read-only summary sheet.
  const [selectedBeoId, setSelectedBeoId] = useState<string | null>(null);

  const outletsQ = useQuery({
    queryKey: ['pos-outlets'],
    queryFn: listOutlets,
    enabled: posAccess,
  });

  // Default to the first outlet once outlets load.
  const outlets = outletsQ.data || [];
  const activeOutlet = outletId || outlets[0]?.id || '';
  const activeOutletObj = outlets.find((o) => o.id === activeOutlet);

  const menuQ = useQuery({
    queryKey: ['pos-menu', activeOutlet],
    queryFn: () => listMenuItems(activeOutlet ? { outlet_id: activeOutlet } : undefined),
    enabled: posAccess && !!activeOutlet,
  });
  const ordersQ = useQuery({
    queryKey: ['pos-active-orders', activeOutlet],
    queryFn: () => listActiveOrders(activeOutlet ? { outlet_id: activeOutlet } : undefined),
    enabled:
      posAccess && (tab === 'order' || tab === 'kitchen' || tab === 'folio' || tab === 'reports'),
  });
  const tablesQ = useQuery({
    queryKey: ['pos-tables', activeOutlet],
    queryFn: () => getTableLayout(activeOutlet),
    enabled: posAccess && (tab === 'tables' || tab === 'reports') && !!activeOutlet,
  });
  const foliosQ = useQuery({
    queryKey: ['pos-open-folios'],
    queryFn: () => listFolios({ status: 'open', limit: 50 }),
    enabled: posAccess && tab === 'folio',
  });
  const beoEventsQ = useQuery({
    queryKey: ['pos-beo-events'],
    queryFn: () => listBeoEvents(),
    enabled: posAccess && tab === 'reports',
  });
  const beoDetailQ = useQuery({
    queryKey: ['pos-beo', selectedBeoId],
    queryFn: () => getBeo(selectedBeoId!),
    enabled: !!selectedBeoId,
  });

  const reservationsQ = useQuery({
    queryKey: ['pos-reservations', activeOutlet],
    queryFn: () => listReservations({ outlet_id: activeOutlet }),
    enabled: posAccess && tab === 'reservations' && !!activeOutlet,
  });

  // Calculate table stats when layouts load (for the summary Kpis).
  const tableStats = useMemo(() => {
    const m = new Map<string, MenuItem>();
    for (const it of menuItems) m.set(it.id, it);
    return m;
  }, [menuItems]);

  const menuItems = menuQ.data || [];
  const menuById = useMemo(() => {
    const m = new Map<string, MenuItem>();
    for (const it of menuItems) m.set(it.id, it);
    return m;
  }, [menuItems]);

  const cartTotal = useMemo(
    () =>
      cart.reduce((sum, line) => {
        const price = menuById.get(line.item_id)?.price ?? 0;
        return sum + price * line.quantity;
      }, 0),
    [cart, menuById],
  );

  // Hard guard — a user without POS entitlement is sent back to the hub.
  if (!posAccess) return <Redirect href={ROUTES.departments} />;

  const addToCart = (itemId: string) => {
    setCart((prev) => {
      const existing = prev.find((l) => l.item_id === itemId);
      if (existing) {
        return prev.map((l) =>
          l.item_id === itemId ? { ...l, quantity: l.quantity + 1 } : l,
        );
      }
      return [...prev, { item_id: itemId, quantity: 1 }];
    });
    haptic.tap();
  };

  const decFromCart = (itemId: string) => {
    setCart((prev) =>
      prev
        .map((l) => (l.item_id === itemId ? { ...l, quantity: l.quantity - 1 } : l))
        .filter((l) => l.quantity > 0),
    );
  };

  const onOpenOrder = async () => {
    setOrderError(null);
    if (!activeOutlet) {
      setOrderError(tr.departments.pos.selectOutlet);
      haptic.warning();
      return;
    }
    if (cart.length === 0) {
      setOrderError(tr.departments.pos.addItemsFirst);
      haptic.warning();
      return;
    }
    setOpening(true);
    // Stable key generated BEFORE the first attempt so a queued replay (or a
    // committed-but-response-lost retry) reuses it and the backend dedupes.
    const idempotencyKey = makeIdempotencyKey('pos_quick_order');
    const payload = {
      outlet_id: activeOutlet,
      table_number: tableNumber || undefined,
      items: cart,
      notes: notes || undefined,
    };
    const resetForm = () => {
      setCart([]);
      setTableNumber('');
      setNotes('');
    };
    try {
      if (!onlineManager.isOnline()) {
        // Known offline — persist straight to the durable queue, no failed call.
        await enqueueQuickOrder(payload, idempotencyKey);
        haptic.success();
        resetForm();
        Alert.alert(tr.app.success, tr.departments.pos.orderQueued);
        return;
      }
      const res = await openQuickOrder({ ...payload, idempotency_key: idempotencyKey });
      haptic.success();
      resetForm();
      qc.invalidateQueries({ queryKey: ['pos-active-orders'] });
      Alert.alert(
        tr.app.success,
        res?.idempotent_replay
          ? tr.departments.pos.orderAlreadyOpened
          : tr.departments.pos.orderOpened,
      );
    } catch (e: unknown) {
      if (isNetworkError(e)) {
        // Dropped mid-flight — move it to the durable queue (same key) so the
        // reconnect replay finishes it exactly once.
        await enqueueQuickOrder(payload, idempotencyKey);
        haptic.success();
        resetForm();
        Alert.alert(tr.app.success, tr.departments.pos.orderQueued);
      } else {
        setOrderError(errorMessage(e, tr.errors.generic));
        haptic.error();
      }
    } finally {
      setOpening(false);
    }
  };

  const onUpdateStatus = async (orderId: string, status: OrderStatus) => {
    setBusyOrderId(orderId);
    try {
      await updateOrderStatus(orderId, status);
      haptic.success();
      qc.invalidateQueries({ queryKey: ['pos-active-orders'] });
      Alert.alert(tr.app.success, tr.departments.pos.statusUpdated);
    } catch (e: unknown) {
      Alert.alert(tr.app.error, errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusyOrderId(null);
    }
  };

  // Open the collect sheet for an order, resetting it to a full single payment.
  const openPaySheet = (o: ActiveOrder) => {
    setPayOrder(o);
    setPayMethod('cash');
    setPayMode('full');
    setSplitCount(2);
    setCustomAmounts(['', '']);
    setPayError(null);
  };
  const closePaySheet = () => {
    if (paying) return;
    setPayOrder(null);
  };

  // Drives both the equal-split person count and the number of custom-amount
  // rows so the two modes stay in lockstep; clamped to 2..8 payers.
  const setPayerCount = (n: number) => {
    const clamped = Math.max(2, Math.min(8, n));
    setSplitCount(clamped);
    setCustomAmounts((prev) => {
      const next = prev.slice(0, clamped);
      while (next.length < clamped) next.push('');
      return next;
    });
  };

  const parseAmount = (s: string): number => {
    const n = parseFloat((s || '').replace(',', '.'));
    return Number.isFinite(n) ? n : NaN;
  };

  const onConfirmPayment = async () => {
    if (!payOrder) return;
    const orderId = payOrder.id;
    const due =
      typeof payOrder.grand_total === 'number'
        ? payOrder.grand_total
        : (payOrder.total_amount ?? 0);
    setPayError(null);

    // For a custom split, validate the per-payer amounts reconcile to the
    // collected total BEFORE taking any money so a mismatch can never leave a
    // paid order with a rejected split.
    let splitDetails: Record<string, number> | undefined;
    if (payMode === 'custom') {
      const parsed = customAmounts.map(parseAmount);
      if (parsed.some((n) => !Number.isFinite(n) || n < 0)) {
        setPayError(tr.departments.pos.invalidAmounts);
        haptic.warning();
        return;
      }
      const sum = parsed.reduce((acc, n) => acc + n, 0);
      if (Math.abs(sum - due) > 0.01) {
        setPayError(tr.departments.pos.splitMismatch);
        haptic.warning();
        return;
      }
      splitDetails = {};
      parsed.forEach((n, i) => {
        splitDetails![String(i + 1)] = Math.round(n * 100) / 100;
      });
    }

    setPaying(true);
    // Stable per-order key generated once; reused on a queued replay so a
    // network retry of this exact close never books a second payment.
    const idempotencyKey = makeIdempotencyKey('pos_close_order', orderId);
    try {
      if (!onlineManager.isOnline()) {
        // The COLLECTION is durable via the offline queue exactly as before.
        // A split is online-only bookkeeping (it needs the closed transaction
        // id), so it cannot be recorded now — say so rather than dropping it
        // silently.
        await enqueueCloseOrder(
          { order_id: orderId, payment_method: payMethod },
          idempotencyKey,
        );
        haptic.success();
        closePaySheet();
        Alert.alert(
          tr.app.success,
          payMode === 'full'
            ? tr.departments.pos.orderQueued
            : tr.departments.pos.orderQueuedSplitSkipped,
        );
        return;
      }
      const res = await closeOrder({
        order_id: orderId,
        payment_method: payMethod,
        idempotency_key: idempotencyKey,
      });
      // Record the split breakdown only when a fresh transaction was created
      // (an idempotent replay already closed it — never re-split it).
      let splitOk = false;
      if (payMode !== 'full' && !res?.idempotent && res?.transaction_id) {
        try {
          const sp = await checkSplit({
            transaction_id: res.transaction_id,
            split_type: payMode === 'equal' ? 'equal' : 'custom',
            split_count: payMode === 'equal' ? splitCount : undefined,
            split_details: splitDetails,
          });
          // Equal splits can carry an inherent rounding remainder, so trust the
          // backend `success`; a custom split was already balanced above.
          splitOk = !!sp?.success;
        } catch {
          splitOk = false;
        }
      }
      haptic.success();
      closePaySheet();
      qc.invalidateQueries({ queryKey: ['pos-active-orders'] });
      const msg = res?.idempotent
        ? tr.departments.pos.orderAlreadyClosed
        : payMode === 'full'
          ? tr.departments.pos.orderClosed
          : splitOk
            ? tr.departments.pos.orderClosedSplit
            : tr.departments.pos.orderClosedSplitFailed;
      Alert.alert(tr.app.success, msg);
    } catch (e: unknown) {
      if (isNetworkError(e)) {
        await enqueueCloseOrder(
          { order_id: orderId, payment_method: payMethod },
          idempotencyKey,
        );
        haptic.success();
        closePaySheet();
        Alert.alert(
          tr.app.success,
          payMode === 'full'
            ? tr.departments.pos.orderQueued
            : tr.departments.pos.orderQueuedSplitSkipped,
        );
        return;
      }
      setPayError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setPaying(false);
    }
  };

  const onTransferTable = async () => {
    if (!activeOutlet || !fromTable || !toTable) {
      haptic.warning();
      return;
    }
    setTransferring(true);
    try {
      await transferTable({ from_table: fromTable, to_table: toTable, outlet_id: activeOutlet });
      haptic.success();
      setFromTable('');
      setToTable('');
      qc.invalidateQueries({ queryKey: ['pos-tables'] });
      Alert.alert(tr.app.success, tr.departments.pos.tableTransferred);
    } catch (e: unknown) {
      Alert.alert(tr.app.error, errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setTransferring(false);
    }
  };

  const onPostToFolio = async () => {
    if (!folioId) {
      Alert.alert(tr.app.error, tr.departments.pos.selectFolioFirst);
      haptic.warning();
      return;
    }
    if (cart.length === 0) {
      Alert.alert(tr.app.error, tr.departments.pos.addItemsFirst);
      haptic.warning();
      return;
    }
    setPosting(true);
    try {
      if (!postFolioKeyRef.current) {
        postFolioKeyRef.current = `mob-folio-${Date.now()}-${Math.round(Math.random() * 1e9)}`;
      }
      const res = await postOrderToFolio({
        folio_id: folioId,
        order_items: cart,
        idempotency_key: postFolioKeyRef.current,
      });
      // Success → next post gets a fresh key.
      postFolioKeyRef.current = null;
      haptic.success();
      setCart([]);
      setFolioId('');
      qc.invalidateQueries({ queryKey: ['pos-open-folios'] });
      Alert.alert(
        tr.app.success,
        res?.idempotent_replay
          ? tr.departments.pos.folioAlreadyPosted
          : tr.departments.pos.folioPosted,
      );
    } catch (e: unknown) {
      // Error → keep the key so a retry reuses it.
      Alert.alert(tr.app.error, errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setPosting(false);
    }
  };

  // Compact pill toggle reused for the outlet picker and the tab bar; both rows
  // scroll horizontally so 5 tabs / many outlets stay reachable on small phones.
  const Chip: React.FC<{
    active: boolean;
    label: string;
    onPress: () => void;
    icon?: React.ComponentProps<typeof Ionicons>['name'];
  }> = ({ active, label, onPress, icon }) => (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.xs,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
        borderRadius: radius.pill,
        backgroundColor: active ? c.primary : c.surfaceAlt,
        borderWidth: 1,
        borderColor: active ? c.primary : c.border,
      }}
    >
      {icon ? (
        <Ionicons name={icon} size={15} color={active ? c.primaryText : c.textMuted} />
      ) : null}
      <Body style={{ color: active ? c.primaryText : c.text, fontWeight: '600' }}>{label}</Body>
    </Pressable>
  );

  // Quantity stepper for cart rows — two 32px hit targets around the count.
  const Stepper: React.FC<{ itemId: string; quantity: number }> = ({ itemId, quantity }) => {
    const stepStyle = {
      width: 32,
      height: 32,
      borderRadius: radius.sm,
      backgroundColor: c.surfaceAlt,
      borderWidth: 1,
      borderColor: c.border,
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
    };
    return (
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
        <Pressable
          onPress={() => decFromCart(itemId)}
          accessibilityRole="button"
          accessibilityLabel="-"
          hitSlop={6}
          style={stepStyle}
        >
          <Ionicons name="remove" size={18} color={c.text} />
        </Pressable>
        <Body style={{ fontWeight: '700', minWidth: 20, textAlign: 'center' }}>{quantity}</Body>
        <Pressable
          onPress={() => addToCart(itemId)}
          accessibilityRole="button"
          accessibilityLabel="+"
          hitSlop={6}
          style={stepStyle}
        >
          <Ionicons name="add" size={18} color={c.text} />
        </Pressable>
      </View>
    );
  };

  const renderCart = () => {
    if (cart.length === 0) {
      return (
        <Card style={{ marginTop: spacing.md }}>
          <Muted>{tr.departments.pos.selectedItems}</Muted>
          <Body style={{ marginTop: spacing.sm }}>{tr.departments.pos.noItemsSelected}</Body>
        </Card>
      );
    }
    return (
      <ListGroup
        title={tr.departments.pos.selectedItems}
        footer={
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              paddingHorizontal: spacing.lg,
              paddingVertical: spacing.md,
              borderTopWidth: 1,
              borderTopColor: c.border,
            }}
          >
            <Body style={{ fontWeight: '700' }}>{tr.departments.pos.total}</Body>
            <Body style={{ fontWeight: '700' }}>{formatCurrency(cartTotal)}</Body>
          </View>
        }
      >
        {cart.map((line, idx) => {
          const it = menuById.get(line.item_id);
          const unit = it?.price ?? 0;
          return (
            <ListRow
              key={line.item_id}
              icon="fast-food-outline"
              label={it ? menuItemLabel(it) : line.item_id}
              sublabel={formatCurrency(unit * line.quantity)}
              showChevron={false}
              last={idx === cart.length - 1}
              right={<Stepper itemId={line.item_id} quantity={line.quantity} />}
            />
          );
        })}
      </ListGroup>
    );
  };

  const renderMenu = () => {
    const showList = !menuQ.isLoading && !menuQ.error && menuItems.length > 0;
    return (
      !showList ? (
        <DepartmentListState
          loading={menuQ.isLoading}
          error={menuQ.error}
          isEmpty={menuItems.length === 0}
          emptyText={tr.departments.pos.noMenuItems}
        />
      ) : (
        <ListGroup>
          {menuItems.map((m, idx) => (
            <ListRow
              key={m.id}
              icon="restaurant-outline"
              label={menuItemLabel(m)}
              value={formatCurrency(m.price)}
              onPress={() => addToCart(m.id)}
              showChevron={false}
              last={idx === menuItems.length - 1}
              right={<Ionicons name="add-circle" size={24} color={c.primary} />}
              accessibilityLabel={`${menuItemLabel(m)} ${tr.departments.pos.addItem}`}
            />
          ))}
        </ListGroup>
      )
    );
  };

  const renderOrderTab = () => (
    <View>
      <SectionTitle title={tr.departments.pos.newOrder} />
      <Card>
        {orderError ? (
          <Body style={{ color: c.danger, marginBottom: spacing.sm }}>{orderError}</Body>
        ) : null}
        <Field
          label={tr.departments.pos.tableNumber}
          value={tableNumber}
          onChangeText={setTableNumber}
          placeholder={tr.departments.pos.tableNumberPlaceholder}
        />
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.departments.pos.notes}
          value={notes}
          onChangeText={setNotes}
          placeholder={tr.departments.pos.notesPlaceholder}
          multiline
        />
      </Card>

      {renderCart()}

      <View style={{ height: spacing.md }} />
      <Button
        title={tr.departments.pos.openOrder}
        icon="checkmark-circle-outline"
        onPress={onOpenOrder}
        loading={opening}
        fullWidth
      />

      <SectionTitle title={tr.departments.pos.menu} />
      {renderMenu()}

      {renderActiveTab()}
    </View>
  );

  const renderActiveTab = () => {
    const data = ordersQ.data?.orders || [];
    const showList = !ordersQ.isLoading && !ordersQ.error && data.length > 0;
    return (
      <View style={{ marginTop: spacing.md }}>
        <SectionTitle title={tr.departments.pos.activeOrders} />
        {!showList ? (
          <DepartmentListState
            loading={ordersQ.isLoading}
            error={ordersQ.error}
            isEmpty={data.length === 0}
            emptyText={tr.departments.pos.noActiveOrders}
          />
        ) : (
          <ListGroup>
            {data.map((o, idx) => {
              const due = typeof o.grand_total === 'number' ? o.grand_total : o.total_amount;
              const sub = [
                o.table_number ? `${tr.departments.pos.tableNumber}: ${o.table_number}` : null,
                typeof due === 'number' ? formatCurrency(due) : null,
              ]
                .filter(Boolean)
                .join(' · ');
              return (
                <ListRow
                  key={o.id}
                  icon="receipt-outline"
                  iconColor={o.is_delayed ? c.danger : undefined}
                  label={o.order_number || o.outlet_name || tr.departments.pos.title}
                  sublabel={sub || undefined}
                  last={idx === data.length - 1}
                  onPress={() => setSelectedOrderId(o.id)}
                  right={
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs }}>
                      {o.is_delayed ? (
                        <Badge label={tr.departments.pos.delayed} tone="danger" />
                      ) : null}
                      <Badge label={statusLabel(o.status)} tone={statusTone(o.status)} />
                    </View>
                  }
                />
              );
            })}
          </ListGroup>
        )}
      </View>
    );
  };

  // Kitchen Display: the same active-orders feed, filtered to the prep pipeline
  // (pending/preparing/ready) with one fast inline "advance" action per ticket.
  // Uses the SAME onUpdateStatus handler — no new business logic.
  const renderKitchenTab = () => {
    const all = ordersQ.data?.orders || [];
    const queue = all.filter(
      (o) => o.status === 'pending' || o.status === 'preparing' || o.status === 'ready',
    );
    const advance: Record<string, { next: OrderStatus; label: string }> = {
      pending: { next: 'preparing', label: tr.departments.pos.actions.preparing },
      preparing: { next: 'ready', label: tr.departments.pos.actions.ready },
      ready: { next: 'served', label: tr.departments.pos.actions.served },
    };
    const showList = !ordersQ.isLoading && !ordersQ.error && queue.length > 0;
    return (
      <View>
        <SectionTitle title={tr.departments.pos.kitchenTitle} />
        <Muted>{tr.departments.pos.kitchenHint}</Muted>
        <View style={{ height: spacing.sm }} />
        {!showList ? (
          <DepartmentListState
            loading={ordersQ.isLoading}
            error={ordersQ.error}
            isEmpty={queue.length === 0}
            emptyText={tr.departments.pos.noKitchenOrders}
          />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {queue.map((o) => {
              const step = advance[o.status as string];
              const accent =
                o.status === 'ready' ? c.success : o.status === 'preparing' ? c.warning : c.info;
              return (
                <Card key={o.id} accent={o.is_delayed ? c.danger : accent}>
                  <View
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: spacing.sm,
                    }}
                  >
                    <View style={{ flex: 1 }}>
                      <Body style={{ fontWeight: '700', color: c.text }}>
                        {o.order_number || o.outlet_name || tr.departments.pos.title}
                      </Body>
                      <Muted style={{ fontSize: 12 }}>
                        {o.table_number
                          ? `${tr.departments.pos.tableNumber}: ${o.table_number}`
                          : tr.departments.pos.emptyTable}
                      </Muted>
                      <View
                        style={{
                          flexDirection: 'row',
                          gap: spacing.xs,
                          marginTop: spacing.xs,
                          flexWrap: 'wrap',
                        }}
                      >
                        {o.is_delayed ? (
                          <Badge label={tr.departments.pos.delayed} tone="danger" />
                        ) : null}
                        <Badge label={statusLabel(o.status)} tone={statusTone(o.status)} />
                      </View>
                    </View>
                    {step ? (
                      <Button
                        title={step.label}
                        icon="arrow-forward-circle-outline"
                        onPress={() => onUpdateStatus(o.id, step.next)}
                        loading={busyOrderId === o.id}
                        disabled={busyOrderId === o.id}
                      />
                    ) : null}
                  </View>
                </Card>
              );
            })}
          </View>
        )}
      </View>
    );
  };

  // Tap a table to drive the transfer flow without typing: first tap picks the
  // source, second tap the destination; tapping again restarts from a new
  // source. Feeds the SAME fromTable/toTable state the manual fields use, so
  // the backend transferTable call is unchanged.
  const onTableTap = (num?: string) => {
    if (!num) return;
    haptic.tap();
    if (!fromTable || (fromTable && toTable)) {
      setFromTable(num);
      setToTable('');
      return;
    }
    if (num === fromTable) {
      setFromTable('');
      return;
    }
    setToTable(num);
  };

  const renderTablesTab = () => {
    const layout = tablesQ.data;
    const tables = layout?.tables || [];
    const showList = !tablesQ.isLoading && !tablesQ.error && tables.length > 0;
    return (
      <View>
        <SectionTitle title={tr.departments.pos.tablePlan} />
        <Muted>{tr.departments.pos.tablePlanHint}</Muted>

        {/* Live occupancy summary across the selected outlet's floor. */}
        {layout ? (
          <KpiRow>
            <KpiCard
              label={tr.departments.pos.available}
              value={String(layout.available)}
              tone="success"
              icon="checkmark-circle-outline"
            />
            <KpiCard
              label={tr.departments.pos.occupied}
              value={String(layout.occupied)}
              tone="warning"
              icon="people-outline"
            />
            <KpiCard
              label={tr.departments.pos.reserved}
              value={String(layout.reserved)}
              tone="info"
              icon="bookmark-outline"
            />
          </KpiRow>
        ) : null}

        {/* Transfer selection — driven by tapping tables OR manual entry. */}
        <View style={{ height: spacing.md }} />
        <Card accent={fromTable ? c.primary : undefined}>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Muted>{tr.departments.pos.transferSelection}</Muted>
            {fromTable || toTable ? (
              <Pressable
                onPress={() => {
                  setFromTable('');
                  setToTable('');
                }}
                accessibilityRole="button"
              >
                <Body style={{ color: c.primary, fontWeight: '700' }}>
                  {tr.departments.pos.clearSelection}
                </Body>
              </Pressable>
            ) : null}
          </View>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: spacing.sm,
              marginTop: spacing.sm,
            }}
          >
            <View style={{ flex: 1 }}>
              <Field
                label={tr.departments.pos.fromTable}
                value={fromTable}
                onChangeText={setFromTable}
                placeholder={tr.departments.pos.transferTablePlaceholder}
              />
            </View>
            <Ionicons
              name="arrow-forward"
              size={18}
              color={c.textMuted}
              style={{ marginTop: spacing.lg }}
            />
            <View style={{ flex: 1 }}>
              <Field
                label={tr.departments.pos.toTable}
                value={toTable}
                onChangeText={setToTable}
                placeholder={tr.departments.pos.transferTablePlaceholder}
              />
            </View>
          </View>
          <View style={{ height: spacing.md }} />
          <Button
            title={tr.departments.pos.doTransfer}
            icon="swap-horizontal-outline"
            onPress={onTransferTable}
            loading={transferring}
            disabled={!fromTable || !toTable}
            fullWidth
          />
        </Card>

        <SectionTitle title={tr.departments.pos.tableLayout} />
        {!showList ? (
          <DepartmentListState
            loading={tablesQ.isLoading}
            error={tablesQ.error}
            isEmpty={tables.length === 0}
            emptyText={tr.departments.pos.noTables}
          />
        ) : (
          <View
            style={{
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: spacing.sm,
            }}
          >
            {tables.map((t: TableSlot, idx) => {
              const color = tableStatusColor(t.status, c);
              const num = t.table_number;
              const selectedFrom = !!num && num === fromTable;
              const selectedTo = !!num && num === toTable;
              const selected = selectedFrom || selectedTo;
              return (
                <Pressable
                  key={t.id || t.table_number || String(idx)}
                  onPress={() => onTableTap(num)}
                  accessibilityRole="button"
                  accessibilityLabel={`${tr.departments.pos.tableNumber} ${num ?? '—'} · ${statusLabel(t.status)}`}
                  style={({ pressed }) => ({
                    width: '31%',
                    minWidth: 96,
                    flexGrow: 1,
                    borderRadius: radius.lg,
                    borderWidth: selected ? 2 : 1,
                    borderColor: selected ? c.primary : color + '55',
                    backgroundColor: color + (selected ? '33' : '14'),
                    padding: spacing.md,
                    gap: 4,
                    opacity: pressed ? 0.75 : 1,
                  })}
                >
                  <View
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <Body style={{ fontWeight: '800', fontSize: 18, color: c.text }}>
                      {num ?? '—'}
                    </Body>
                    <View
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: radius.pill,
                        backgroundColor: color,
                      }}
                    />
                  </View>
                  <Muted style={{ fontSize: 11 }}>{statusLabel(t.status)}</Muted>
                  {typeof t.seats === 'number' ? (
                    <Muted style={{ fontSize: 11 }}>
                      {t.seats} {tr.departments.pos.seats}
                    </Muted>
                  ) : null}
                  {typeof t.current_bill === 'number' && t.current_bill > 0 ? (
                    <Body style={{ fontSize: 12, fontWeight: '700', color }}>
                      {formatCurrency(t.current_bill)}
                    </Body>
                  ) : null}
                  {selectedFrom ? (
                    <Badge label={tr.departments.pos.fromTable} tone="primary" />
                  ) : selectedTo ? (
                    <Badge label={tr.departments.pos.toTable} tone="primary" />
                  ) : null}
                </Pressable>
              );
            })}
          </View>
        )}
      </View>
    );
  };

  const renderFolioTab = () => {
    const data = foliosQ.data?.folios || [];
    const showList = !foliosQ.isLoading && !foliosQ.error && data.length > 0;
    const orders = ordersQ.data?.orders || [];
    const collectQueue = orders.filter((o) => o.status !== 'cancelled');
    const showCollect = !ordersQ.isLoading && !ordersQ.error && collectQueue.length > 0;
    return (
      <View>
        <SectionTitle title={tr.departments.pos.collectTitle} />
        <Muted>{tr.departments.pos.collectHint}</Muted>
        <View style={{ height: spacing.sm }} />
        {!showCollect ? (
          <DepartmentListState
            loading={ordersQ.isLoading}
            error={ordersQ.error}
            isEmpty={collectQueue.length === 0}
            emptyText={tr.departments.pos.noCollectOrders}
          />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {collectQueue.map((o) => {
              const due = typeof o.grand_total === 'number' ? o.grand_total : o.total_amount;
              return (
                <Card key={o.id} accent={o.status === 'served' ? c.success : undefined}>
                  <View
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: spacing.sm,
                    }}
                  >
                    <View style={{ flex: 1 }}>
                      <Body style={{ fontWeight: '700', color: c.text }}>
                        {o.order_number || o.outlet_name || tr.departments.pos.title}
                      </Body>
                      <Muted style={{ fontSize: 12 }}>
                        {[
                          o.table_number
                            ? `${tr.departments.pos.tableNumber}: ${o.table_number}`
                            : null,
                          typeof due === 'number' ? formatCurrency(due) : null,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </Muted>
                    </View>
                    <Badge label={statusLabel(o.status)} tone={statusTone(o.status)} />
                  </View>
                  <SegmentedActions>
                    <ActionButton
                      label={tr.departments.pos.collect}
                      icon="cash-outline"
                      bg={c.primary}
                      fg={c.primaryText}
                      onPress={() => openPaySheet(o)}
                      disabled={paying}
                      testID={`pos-collect-${o.id}`}
                    />
                  </SegmentedActions>
                </Card>
              );
            })}
          </View>
        )}

        <SectionTitle title={tr.departments.pos.folioTransfer} />
        <Muted>{tr.departments.pos.folioTransferHint}</Muted>

        {renderCart()}

        <SectionTitle title={tr.departments.pos.menu} />
        {renderMenu()}

        <SectionTitle title={tr.departments.pos.selectFolio} />
        {!showList ? (
          <DepartmentListState
            loading={foliosQ.isLoading}
            error={foliosQ.error}
            isEmpty={data.length === 0}
            emptyText={tr.departments.pos.noOpenFolios}
          />
        ) : (
          <ListGroup>
            {data.map((f: FolioListItem, idx) => (
              <ListRow
                key={f.id}
                icon="bed-outline"
                label={f.guest_name || f.folio_number || f.id}
                sublabel={f.room_number ? `${tr.departments.pos.room}: ${f.room_number}` : undefined}
                value={`${tr.departments.pos.balance}: ${formatCurrency(f.balance)}`}
                active={folioId === f.id}
                last={idx === data.length - 1}
                onPress={() => setFolioId(folioId === f.id ? '' : f.id)}
              />
            ))}
          </ListGroup>
        )}

        <View style={{ height: spacing.md }} />
        <Button
          title={tr.departments.pos.postToFolio}
          icon="arrow-forward-circle-outline"
          onPress={onPostToFolio}
          loading={posting}
          fullWidth
        />
      </View>
    );
  };

  // Reports: at-a-glance operational KPIs from the live outlet/table/order
  // feeds, then the read-only BEO (banquet) event list folded in.
  const renderReportsTab = () => {
    const layout = tablesQ.data;
    const orders = ordersQ.data?.orders || [];
    const activeCount = orders.length;
    const delayedCount = orders.filter((o) => o.is_delayed).length;
    const todayTx =
      typeof activeOutletObj?.today_transactions === 'number'
        ? activeOutletObj.today_transactions
        : null;
    const occupancy = layout ? `${layout.occupied}/${layout.total_tables}` : '—';
    return (
      <View>
        <SectionTitle title={tr.departments.pos.reportsTitle} />
        <Muted>{tr.departments.pos.reportsHint}</Muted>
        <View style={{ height: spacing.sm }} />
        <KpiRow>
          <KpiCard
            label={tr.departments.pos.kpiTodayTx}
            value={todayTx !== null ? String(todayTx) : '—'}
            icon="receipt-outline"
          />
          <KpiCard
            label={tr.departments.pos.kpiOccupancy}
            value={occupancy}
            tone="info"
            icon="grid-outline"
          />
        </KpiRow>
        <View style={{ height: spacing.sm }} />
        <KpiRow>
          <KpiCard
            label={tr.departments.pos.kpiActive}
            value={String(activeCount)}
            tone="warning"
            icon="restaurant-outline"
          />
          <KpiCard
            label={tr.departments.pos.kpiDelayed}
            value={String(delayedCount)}
            tone={delayedCount > 0 ? 'danger' : 'default'}
            icon="alarm-outline"
          />
        </KpiRow>

        <SectionTitle title={tr.departments.pos.banquetSection} />
        {renderBeoTab()}
      </View>
    );
  };

  const renderBeoTab = () => {
    const events = beoEventsQ.data || [];
    const showList = !beoEventsQ.isLoading && !beoEventsQ.error && events.length > 0;
    return (
      <View>
        <SectionTitle title={tr.departments.pos.beo.listTitle} />
        <Muted>{tr.departments.pos.beo.hint}</Muted>
        <View style={{ height: spacing.sm }} />
        {!showList ? (
          <DepartmentListState
            loading={beoEventsQ.isLoading}
            error={beoEventsQ.error}
            isEmpty={events.length === 0}
            emptyText={tr.departments.pos.beo.noEvents}
          />
        ) : (
          <ListGroup>
            {events.map((ev, idx) => {
              const sub = [
                ev.client_name || null,
                ev.start_date
                  ? `${ev.start_date}${ev.end_date && ev.end_date !== ev.start_date ? ` → ${ev.end_date}` : ''}`
                  : null,
              ]
                .filter(Boolean)
                .join(' · ');
              return (
                <ListRow
                  key={ev.id}
                  icon="calendar-outline"
                  label={ev.name || ev.id}
                  sublabel={sub || undefined}
                  last={idx === events.length - 1}
                  onPress={() => setSelectedBeoId(ev.id)}
                  right={
                    <Badge label={eventStatusLabel(ev.status)} tone={eventStatusTone(ev.status)} />
                  }
                />
              );
            })}
          </ListGroup>
        )}
      </View>
    );
  };

  const renderBeoDetail = (beo: BeoSummary) => {
    const ev = beo.event;
    const totals = ev.totals || {};
    const tech = beo.technical_requirements;
    const staff = beo.staff_assignments || [];
    const ent = beo.entertainment || null;
    const yn = (v: unknown) => (v ? tr.departments.pos.beo.yes : tr.departments.pos.beo.no);
    return (
      <View style={{ gap: spacing.md }}>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
          <Badge label={eventStatusLabel(ev.status)} tone={eventStatusTone(ev.status)} />
          {typeof ev.expected_pax === 'number' ? (
            <Badge label={`${tr.departments.pos.beo.pax}: ${ev.expected_pax}`} tone="info" />
          ) : null}
        </View>

        <Card>
          <DetailRow label={tr.departments.pos.beo.client} value={ev.client_name} />
          <DetailRow label={tr.departments.pos.beo.eventType} value={ev.event_type} />
          <DetailRow
            label={tr.departments.pos.beo.dates}
            value={
              ev.start_date
                ? `${ev.start_date}${ev.end_date && ev.end_date !== ev.start_date ? ` → ${ev.end_date}` : ''}`
                : '—'
            }
          />
          <DetailRow label={tr.departments.pos.beo.organizer} value={ev.organizer_user ?? undefined} />
          <DetailRow label={tr.departments.pos.beo.email} value={ev.client_email ?? undefined} />
          <DetailRow label={tr.departments.pos.beo.phone} value={ev.client_phone ?? undefined} />
          {ev.notes ? <DetailRow label={tr.departments.pos.beo.notes} value={ev.notes} /> : null}
        </Card>

        <SectionTitle title={tr.departments.pos.beo.spaces} />
        {beo.spaces.length === 0 ? (
          <Card>
            <Muted>{tr.departments.pos.beo.noSpaces}</Muted>
          </Card>
        ) : (
          <ListGroup>
            {beo.spaces.map((s, idx) => {
              const sub = [
                s.setup_style ? `${tr.departments.pos.beo.setup}: ${s.setup_style}` : null,
                `${shortStamp(s.starts_at)} – ${shortStamp(s.ends_at)}`,
              ]
                .filter(Boolean)
                .join(' · ');
              return (
                <ListRow
                  key={`${s.space_name ?? 'space'}-${idx}`}
                  icon="business-outline"
                  label={s.space_name || '—'}
                  sublabel={sub}
                  value={
                    typeof s.expected_pax === 'number'
                      ? `${s.expected_pax} ${tr.departments.pos.beo.pax}`
                      : undefined
                  }
                  showChevron={false}
                  last={idx === beo.spaces.length - 1}
                />
              );
            })}
          </ListGroup>
        )}

        <SectionTitle title={tr.departments.pos.beo.agenda} />
        {beo.agenda.length === 0 ? (
          <Card>
            <Muted>{tr.departments.pos.beo.noAgenda}</Muted>
          </Card>
        ) : (
          <ListGroup>
            {beo.agenda.map((a, idx) => (
              <ListRow
                key={`agenda-${idx}`}
                icon="time-outline"
                label={a.title || '—'}
                sublabel={[a.kind || null, a.owner || null].filter(Boolean).join(' · ') || undefined}
                value={agendaWindow(a)}
                showChevron={false}
                last={idx === beo.agenda.length - 1}
              />
            ))}
          </ListGroup>
        )}

        <SectionTitle title={tr.departments.pos.beo.resources} />
        {beo.resources.length === 0 ? (
          <Card>
            <Muted>{tr.departments.pos.beo.noResources}</Muted>
          </Card>
        ) : (
          <ListGroup>
            {beo.resources.map((r, idx) => (
              <ListRow
                key={`res-${idx}`}
                icon="cube-outline"
                label={r.name || '—'}
                sublabel={r.type || undefined}
                value={
                  typeof r.quantity === 'number'
                    ? `${tr.departments.pos.beo.qty}: ${r.quantity}`
                    : undefined
                }
                showChevron={false}
                last={idx === beo.resources.length - 1}
              />
            ))}
          </ListGroup>
        )}

        <SectionTitle title={tr.departments.pos.beo.paymentSchedule} />
        {beo.payment_schedule.length === 0 ? (
          <Card>
            <Muted>{tr.departments.pos.beo.noPaymentSchedule}</Muted>
          </Card>
        ) : (
          <ListGroup>
            {beo.payment_schedule.map((p, idx) => (
              <ListRow
                key={`pay-${idx}`}
                icon="card-outline"
                label={p.label || '—'}
                sublabel={p.due_date || undefined}
                value={formatCurrency(p.amount)}
                showChevron={false}
                last={idx === beo.payment_schedule.length - 1}
                right={
                  <Badge
                    label={p.paid ? tr.departments.pos.beo.paid : tr.departments.pos.beo.pending}
                    tone={p.paid ? 'success' : 'warning'}
                  />
                }
              />
            ))}
          </ListGroup>
        )}

        <SectionTitle title={tr.departments.pos.beo.technical} />
        {tech ? (
          <Card>
            <DetailRow label="Projeksiyon" value={yn(tech.projector)} />
            <DetailRow label="Perde / Ekran" value={yn(tech.screen)} />
            <DetailRow label="Kablolu Mikrofon" value={`${tech.microphone_wired ?? 0} adet`} />
            <DetailRow label="Kablosuz Mikrofon" value={`${tech.microphone_wireless ?? 0} adet`} />
            <DetailRow label="Ses Sistemi" value={yn(tech.sound_system)} />
            <DetailRow label="Sahne" value={yn(tech.stage)} />
            <DetailRow label="Aydınlatma" value={yn(tech.lighting)} />
            <DetailRow label="Canlı Yayın" value={yn(tech.livestream)} />
            <DetailRow label="İnternet" value={`${tech.internet_mbps ?? 0} Mbps`} />
            <DetailRow label="Çeviri Kabini" value={`${tech.translation_booths ?? 0} adet`} />
            {tech.notes ? <DetailRow label={tr.departments.pos.beo.notes} value={tech.notes} /> : null}
          </Card>
        ) : (
          <Card>
            <Muted>{tr.departments.pos.beo.noTechnical}</Muted>
          </Card>
        )}

        <SectionTitle title={tr.departments.pos.beo.staff} />
        {staff.length === 0 ? (
          <Card>
            <Muted>{tr.departments.pos.beo.noStaff}</Muted>
          </Card>
        ) : (
          <ListGroup>
            {staff.map((s, idx) => (
              <ListRow
                key={`staff-${idx}`}
                icon="person-outline"
                label={s.role || '—'}
                sublabel={s.name || s.user || undefined}
                value={s.notes || undefined}
                showChevron={false}
                last={idx === staff.length - 1}
              />
            ))}
          </ListGroup>
        )}

        {ent && Object.keys(ent).length > 0 ? (
          <Card>
            {Object.entries(ent).map(([k, v]) => (
              <DetailRow key={k} label={k} value={v == null ? '—' : String(v)} />
            ))}
          </Card>
        ) : null}

        <SectionTitle title={tr.departments.pos.beo.totals} />
        <Card>
          <DetailRow
            label={tr.departments.pos.beo.spaceTotal}
            value={formatCurrency(totals.space_total)}
          />
          <DetailRow
            label={tr.departments.pos.beo.resourcesTotal}
            value={formatCurrency(totals.resources_total)}
          />
          <DetailRow
            label={tr.departments.pos.beo.grandTotal}
            value={formatCurrency(totals.grand_total)}
          />
        </Card>
      </View>
    );
  };

  // Active order resolved live from the query so the detail sheet tracks status
  // changes and closes itself once the order leaves the active list.
  const selectedOrder = (ordersQ.data?.orders || []).find((o) => o.id === selectedOrderId) || null;

  const renderOrderActions = (o: ActiveOrder) => {
    const lifecycle: { label: string; status: OrderStatus; bg: string; fg: string }[] = [];
    if (o.status === 'pending') {
      lifecycle.push({
        label: tr.departments.pos.actions.preparing,
        status: 'preparing',
        bg: c.surfaceAlt,
        fg: c.text,
      });
    }
    if (o.status === 'preparing') {
      lifecycle.push({
        label: tr.departments.pos.actions.ready,
        status: 'ready',
        bg: c.surfaceAlt,
        fg: c.text,
      });
    }
    if (o.status !== 'served' && o.status !== 'cancelled') {
      lifecycle.push({
        label: tr.departments.pos.actions.served,
        status: 'served',
        bg: c.primary,
        fg: c.primaryText,
      });
      lifecycle.push({
        label: tr.departments.pos.actions.cancelled,
        status: 'cancelled',
        bg: c.danger,
        fg: '#ffffff',
      });
    }
    const due = typeof o.grand_total === 'number' ? o.grand_total : o.total_amount;
    return (
      <View style={{ gap: spacing.md }}>
        <Card>
          {o.table_number ? (
            <DetailRow label={tr.departments.pos.tableNumber} value={o.table_number} />
          ) : null}
          {typeof due === 'number' ? (
            <DetailRow label={tr.departments.pos.amountDue} value={formatCurrency(due)} />
          ) : null}
        </Card>

        {lifecycle.length > 0 ? (
          <SegmentedActions>
            {lifecycle.map((a) => (
              <ActionButton
                key={a.status}
                label={a.label}
                bg={a.bg}
                fg={a.fg}
                onPress={() => onUpdateStatus(o.id, a.status)}
                loading={busyOrderId === o.id}
                disabled={busyOrderId === o.id}
              />
            ))}
          </SegmentedActions>
        ) : null}

        {o.status !== 'cancelled' ? (
          <SegmentedActions>
            <ActionButton
              label={tr.departments.pos.collect}
              icon="cash-outline"
              bg={c.primary}
              fg={c.primaryText}
              onPress={() => openPaySheet(o)}
              disabled={paying}
              testID={`pos-detail-collect-${o.id}`}
            />
          </SegmentedActions>
        ) : null}
      </View>
    );
  };

  // Collect sheet — pick a payment method and optionally split the bill before
  // closing. The money is always taken in full by closeOrder (the backend has
  // no leave-open partial close); "Eşit Böl" / "Özel Tutar" additionally record
  // how that full payment was divided via check-split.
  const renderPaySheet = () => {
    if (!payOrder) return null;
    const due =
      typeof payOrder.grand_total === 'number'
        ? payOrder.grand_total
        : (payOrder.total_amount ?? 0);
    const perPerson = splitCount > 0 ? due / splitCount : due;
    const customSum = customAmounts.reduce((acc, s) => {
      const n = parseAmount(s);
      return acc + (Number.isFinite(n) ? n : 0);
    }, 0);
    const customMatches = Math.abs(customSum - due) <= 0.01;

    const methods: {
      key: PaymentMethod;
      label: string;
      icon: keyof typeof Ionicons.glyphMap;
    }[] = [
      { key: 'cash', label: tr.departments.pos.methodCash, icon: 'cash-outline' },
      { key: 'card', label: tr.departments.pos.methodCard, icon: 'card-outline' },
      { key: 'transfer', label: tr.departments.pos.methodTransfer, icon: 'swap-horizontal-outline' },
    ];
    const modes: { key: 'full' | 'equal' | 'custom'; label: string }[] = [
      { key: 'full', label: tr.departments.pos.modeFull },
      { key: 'equal', label: tr.departments.pos.modeEqual },
      { key: 'custom', label: tr.departments.pos.modeCustom },
    ];

    return (
      <View style={{ gap: spacing.md }}>
        <Card>
          <DetailRow label={tr.departments.pos.amountDue} value={formatCurrency(due)} />
        </Card>

        <Muted>{tr.departments.pos.paymentMethod}</Muted>
        <SegmentedActions>
          {methods.map((m) => (
            <ActionButton
              key={m.key}
              label={m.label}
              icon={m.icon}
              bg={payMethod === m.key ? c.primary : c.surfaceAlt}
              fg={payMethod === m.key ? c.primaryText : c.text}
              onPress={() => setPayMethod(m.key)}
              testID={`pos-method-${m.key}`}
            />
          ))}
        </SegmentedActions>

        <Muted>{tr.departments.pos.collectMode}</Muted>
        <SegmentedActions>
          {modes.map((m) => (
            <ActionButton
              key={m.key}
              label={m.label}
              bg={payMode === m.key ? c.primary : c.surfaceAlt}
              fg={payMode === m.key ? c.primaryText : c.text}
              onPress={() => setPayMode(m.key)}
              testID={`pos-mode-${m.key}`}
            />
          ))}
        </SegmentedActions>

        {payMode === 'equal' ? (
          <Card>
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Body style={{ color: c.text }}>{tr.departments.pos.personCount}</Body>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
                <ActionButton
                  label="−"
                  bg={c.surfaceAlt}
                  fg={c.text}
                  onPress={() => setPayerCount(splitCount - 1)}
                  disabled={splitCount <= 2}
                  testID="pos-split-dec"
                />
                <Body style={{ color: c.text, fontWeight: '700', minWidth: 24, textAlign: 'center' }}>
                  {splitCount}
                </Body>
                <ActionButton
                  label="+"
                  bg={c.surfaceAlt}
                  fg={c.text}
                  onPress={() => setPayerCount(splitCount + 1)}
                  disabled={splitCount >= 8}
                  testID="pos-split-inc"
                />
              </View>
            </View>
            <DetailRow label={tr.departments.pos.perPerson} value={formatCurrency(perPerson)} />
          </Card>
        ) : null}

        {payMode === 'custom' ? (
          <Card>
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: spacing.sm,
              }}
            >
              <Body style={{ color: c.text }}>{tr.departments.pos.personCount}</Body>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
                <ActionButton
                  label="−"
                  bg={c.surfaceAlt}
                  fg={c.text}
                  onPress={() => setPayerCount(splitCount - 1)}
                  disabled={splitCount <= 2}
                  testID="pos-custom-dec"
                />
                <Body style={{ color: c.text, fontWeight: '700', minWidth: 24, textAlign: 'center' }}>
                  {splitCount}
                </Body>
                <ActionButton
                  label="+"
                  bg={c.surfaceAlt}
                  fg={c.text}
                  onPress={() => setPayerCount(splitCount + 1)}
                  disabled={splitCount >= 8}
                  testID="pos-custom-inc"
                />
              </View>
            </View>
            {customAmounts.map((amt, i) => (
              <Field
                key={i}
                label={`${tr.departments.pos.payer} ${i + 1}`}
                value={amt}
                onChangeText={(t) =>
                  setCustomAmounts((prev) => prev.map((v, idx) => (idx === i ? t : v)))
                }
                keyboardType="numeric"
                placeholder="0"
                testID={`pos-custom-amount-${i}`}
              />
            ))}
            <DetailRow
              label={tr.departments.pos.enteredTotal}
              value={`${formatCurrency(customSum)} / ${formatCurrency(due)}`}
            />
            {!customMatches ? (
              <Muted style={{ color: c.danger }}>{tr.departments.pos.splitMismatch}</Muted>
            ) : null}
          </Card>
        ) : null}

        {payError ? <Muted style={{ color: c.danger }}>{payError}</Muted> : null}

        <Button
          title={tr.departments.pos.confirmPayment}
          onPress={onConfirmPayment}
          loading={paying}
          disabled={paying || (payMode === 'custom' && !customMatches)}
          testID="pos-confirm-payment"
        />
      </View>
    );
  };

  const renderReservationsTab = () => {
    const data = reservationsQ.data || [];
    const showList = !reservationsQ.isLoading && !reservationsQ.error && data.length > 0;
    return (
      <View>
        <SectionTitle title={tr.departments.pos.tabs?.reservations || 'Rezervasyonlar'} />
        <Muted>Aktif masa rezervasyonları</Muted>
        <View style={{ height: spacing.sm }} />
        {!showList ? (
          <DepartmentListState
            loading={reservationsQ.isLoading}
            error={reservationsQ.error}
            isEmpty={data.length === 0}
            emptyText="Rezervasyon bulunamadı."
          />
        ) : (
          <ListGroup>
            {data.map((r, idx) => (
              <ListRow
                key={r.id}
                icon="calendar-outline"
                label={`${r.guest_name} - ${r.pax} Pax`}
                sublabel={`${r.res_date} ${r.res_time} | Masa: ${r.table_id}`}
                last={idx === data.length - 1}
                right={<Badge label={statusLabel(r.status)} tone={statusTone(r.status)} />}
              />
            ))}
          </ListGroup>
        )}
      </View>
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
    >
      <H1>{tr.departments.pos.title}</H1>

      {/* Offline write-queue indicator — how many orders are waiting to sync. */}
      {pendingSync > 0 ? (
        <View style={{ flexDirection: 'row', marginTop: spacing.xs, marginBottom: spacing.xs }}>
          <Badge
            label={`${tr.departments.pos.pendingSync}: ${pendingSync}`}
            tone="warning"
            icon="cloud-offline-outline"
          />
        </View>
      ) : null}

      {/* Outlet selector */}
      <SectionTitle title={tr.departments.pos.outlet} />
      {outletsQ.isLoading ? (
        <DepartmentListState loading error={null} isEmpty={false} emptyText="" />
      ) : outlets.length === 0 ? (
        <Card>
          <Muted>{tr.departments.pos.noOutlets}</Muted>
        </Card>
      ) : (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.xs }}
          style={{ marginBottom: spacing.sm }}
        >
          {outlets.map((o: Outlet) => (
            <Chip
              key={o.id}
              active={activeOutlet === o.id}
              label={outletLabel(o)}
              onPress={() => setOutletId(o.id)}
            />
          ))}
        </ScrollView>
      )}

      {/* Tab selector */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.xs }}
        style={{ marginBottom: spacing.md }}
      >
        <Chip
          active={tab === 'tables'}
          icon="grid-outline"
          label={tr.departments.pos.tabs.tables}
          onPress={() => setTab('tables')}
        />
        <Chip
          active={tab === 'order'}
          icon="restaurant-outline"
          label={tr.departments.pos.tabs.order}
          onPress={() => setTab('order')}
        />
        <Chip
          active={tab === 'kitchen'}
          icon="flame-outline"
          label={tr.departments.pos.tabs.kitchen}
          onPress={() => setTab('kitchen')}
        />
        <Chip
          active={tab === 'folio'}
          icon="card-outline"
          label={tr.departments.pos.tabs.folio}
          onPress={() => setTab('folio')}
        />
        <Chip
          active={tab === 'reports'}
          icon="stats-chart-outline"
          label={tr.departments.pos.tabs.reports}
          onPress={() => setTab('reports')}
        />
        <Chip
          active={tab === 'reservations'}
          icon="calendar-outline"
          label={tr.departments.pos.tabs?.reservations || 'Rezervasyon'}
          onPress={() => setTab('reservations')}
        />
      </ScrollView>

      {tab === 'tables' ? renderTablesTab() : null}
      {tab === 'order' ? renderOrderTab() : null}
      {tab === 'kitchen' ? renderKitchenTab() : null}
      {tab === 'folio' ? renderFolioTab() : null}
      {tab === 'reports' ? renderReportsTab() : null}
      {tab === 'reservations' ? renderReservationsTab() : null}

      {/* Active-order detail + actions sheet. */}
      <ActionSheet
        visible={!!selectedOrder}
        onClose={() => setSelectedOrderId(null)}
        title={
          selectedOrder
            ? selectedOrder.order_number || selectedOrder.outlet_name || tr.departments.pos.title
            : undefined
        }
      >
        {selectedOrder ? renderOrderActions(selectedOrder) : null}
      </ActionSheet>

      {/* Collect / split-payment sheet. */}
      <ActionSheet
        visible={!!payOrder}
        onClose={closePaySheet}
        title={tr.departments.pos.payTitle}
        testID="pos-pay-sheet"
      >
        {renderPaySheet()}
      </ActionSheet>

      {/* Read-only BEO summary sheet. */}
      <ActionSheet
        visible={!!selectedBeoId}
        onClose={() => setSelectedBeoId(null)}
        title={beoDetailQ.data?.event?.name || tr.departments.pos.beo.title}
      >
        {beoDetailQ.isLoading || beoDetailQ.error ? (
          <DepartmentListState
            loading={beoDetailQ.isLoading}
            error={beoDetailQ.error}
            isEmpty={false}
            emptyText={tr.departments.pos.beo.loadError}
          />
        ) : beoDetailQ.data ? (
          renderBeoDetail(beoDetailQ.data)
        ) : null}
      </ActionSheet>
    </ScrollView>
  );
}
