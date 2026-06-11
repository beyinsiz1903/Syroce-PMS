import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { onlineManager, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Button, Card, Field, H1, Muted } from '../../src/components/ui';
import { DepartmentListState, SectionTitle } from '../../src/components/department';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  getTableLayout,
  listActiveOrders,
  listMenuItems,
  listOutlets,
  menuItemLabel,
  openQuickOrder,
  outletLabel,
  postOrderToFolio,
  closeOrder,
  transferTable,
  updateOrderStatus,
  type ActiveOrder,
  type MenuItem,
  type Outlet,
  type OrderStatus,
  type PaymentMethod,
  type TableSlot,
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

type Tab = 'order' | 'active' | 'tables' | 'folio';
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

function tableTone(s?: string): 'default' | 'success' | 'info' | 'warning' {
  switch (s) {
    case 'available':
      return 'success';
    case 'occupied':
      return 'warning';
    case 'reserved':
      return 'info';
    default:
      return 'default';
  }
}

// POS / F&B department screen (Task #331, Faz 4). Four flows over a selected
// outlet: open an order (quick-order), advance/close active orders, view the
// table layout + transfer a table, and post an order to a room folio. Every
// write is gated server-side by require_module("pos") / require_op; the mobile
// `posAccess` entitlement mirrors that role set. Cosmetic only — the backend
// still enforces. Order/transaction status semantics are not changed here.
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

  const [tab, setTab] = useState<Tab>('order');
  const [outletId, setOutletId] = useState<string>('');

  // Order-open form state.
  const [tableNumber, setTableNumber] = useState('');
  const [notes, setNotes] = useState('');
  const [cart, setCart] = useState<CartLine[]>([]);
  const [opening, setOpening] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);

  // Active-order lifecycle state.
  const [busyOrderId, setBusyOrderId] = useState<string | null>(null);
  // Close-and-pay state — tracks (order, method) so only the tapped button
  // shows its spinner.
  const [payingOrder, setPayingOrder] = useState<{ id: string; method: PaymentMethod } | null>(
    null,
  );

  // Table-transfer state.
  const [fromTable, setFromTable] = useState('');
  const [toTable, setToTable] = useState('');
  const [transferring, setTransferring] = useState(false);

  // Folio-transfer state.
  const [folioId, setFolioId] = useState<string>('');
  const [posting, setPosting] = useState(false);

  const outletsQ = useQuery({
    queryKey: ['pos-outlets'],
    queryFn: listOutlets,
    enabled: posAccess,
  });

  // Default to the first outlet once outlets load.
  const outlets = outletsQ.data || [];
  const activeOutlet = outletId || outlets[0]?.id || '';

  const menuQ = useQuery({
    queryKey: ['pos-menu', activeOutlet],
    queryFn: () => listMenuItems(activeOutlet ? { outlet_id: activeOutlet } : undefined),
    enabled: posAccess && !!activeOutlet,
  });
  const ordersQ = useQuery({
    queryKey: ['pos-active-orders', activeOutlet],
    queryFn: () => listActiveOrders(activeOutlet ? { outlet_id: activeOutlet } : undefined),
    enabled: posAccess && tab === 'active',
  });
  const tablesQ = useQuery({
    queryKey: ['pos-tables', activeOutlet],
    queryFn: () => getTableLayout(activeOutlet),
    enabled: posAccess && tab === 'tables' && !!activeOutlet,
  });
  const foliosQ = useQuery({
    queryKey: ['pos-open-folios'],
    queryFn: () => listFolios({ status: 'open', limit: 50 }),
    enabled: posAccess && tab === 'folio',
  });

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
      await openQuickOrder({ ...payload, idempotency_key: idempotencyKey });
      haptic.success();
      resetForm();
      qc.invalidateQueries({ queryKey: ['pos-active-orders'] });
      Alert.alert(tr.app.success, tr.departments.pos.orderOpened);
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

  const onCloseOrder = async (orderId: string, method: PaymentMethod) => {
    setPayingOrder({ id: orderId, method });
    // Stable per-order key generated once; reused on a queued replay so a
    // network retry of this exact close never books a second payment.
    const idempotencyKey = makeIdempotencyKey('pos_close_order', orderId);
    try {
      if (!onlineManager.isOnline()) {
        await enqueueCloseOrder({ order_id: orderId, payment_method: method }, idempotencyKey);
        haptic.success();
        Alert.alert(tr.app.success, tr.departments.pos.orderQueued);
        return;
      }
      const res = await closeOrder({
        order_id: orderId,
        payment_method: method,
        idempotency_key: idempotencyKey,
      });
      haptic.success();
      qc.invalidateQueries({ queryKey: ['pos-active-orders'] });
      Alert.alert(
        tr.app.success,
        res?.idempotent ? tr.departments.pos.orderAlreadyClosed : tr.departments.pos.orderClosed,
      );
    } catch (e: unknown) {
      if (isNetworkError(e)) {
        await enqueueCloseOrder({ order_id: orderId, payment_method: method }, idempotencyKey);
        haptic.success();
        Alert.alert(tr.app.success, tr.departments.pos.orderQueued);
        return;
      }
      Alert.alert(tr.app.error, errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setPayingOrder(null);
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
      await postOrderToFolio({ folio_id: folioId, order_items: cart });
      haptic.success();
      setCart([]);
      setFolioId('');
      qc.invalidateQueries({ queryKey: ['pos-open-folios'] });
      Alert.alert(tr.app.success, tr.departments.pos.folioPosted);
    } catch (e: unknown) {
      Alert.alert(tr.app.error, errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setPosting(false);
    }
  };

  const Chip: React.FC<{ active: boolean; label: string; onPress: () => void }> = ({
    active,
    label,
    onPress,
  }) => (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={{
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.md,
        borderRadius: radius.md,
        backgroundColor: active ? c.primary : c.surfaceAlt,
        borderWidth: 1,
        borderColor: active ? c.primary : c.border,
      }}
    >
      <Body style={{ color: active ? c.primaryText : c.text, fontWeight: '600' }}>{label}</Body>
    </Pressable>
  );

  const renderCart = () => (
    <Card style={{ marginTop: spacing.md }}>
      <Muted>{tr.departments.pos.selectedItems}</Muted>
      {cart.length === 0 ? (
        <Body style={{ marginTop: spacing.sm }}>{tr.departments.pos.noItemsSelected}</Body>
      ) : (
        <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
          {cart.map((line) => {
            const it = menuById.get(line.item_id);
            return (
              <View
                key={line.item_id}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <View style={{ flex: 1, paddingRight: spacing.sm }}>
                  <Body style={{ fontWeight: '600' }}>{it ? menuItemLabel(it) : line.item_id}</Body>
                  <Muted>{formatCurrency((it?.price ?? 0) * line.quantity)}</Muted>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
                  <Button title="-" variant="secondary" onPress={() => decFromCart(line.item_id)} />
                  <Body style={{ fontWeight: '600', minWidth: 20, textAlign: 'center' }}>
                    {line.quantity}
                  </Body>
                  <Button title="+" variant="secondary" onPress={() => addToCart(line.item_id)} />
                </View>
              </View>
            );
          })}
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              marginTop: spacing.sm,
            }}
          >
            <Body style={{ fontWeight: '700' }}>{tr.departments.pos.total}</Body>
            <Body style={{ fontWeight: '700' }}>{formatCurrency(cartTotal)}</Body>
          </View>
        </View>
      )}
    </Card>
  );

  const renderMenu = () => {
    const state = (
      <DepartmentListState
        loading={menuQ.isLoading}
        error={menuQ.error}
        isEmpty={menuItems.length === 0}
        emptyText={tr.departments.pos.noMenuItems}
      />
    );
    return (
      state ?? (
        <View style={{ gap: spacing.sm }}>
          {menuItems.map((m) => (
            <Card key={m.id}>
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <View style={{ flex: 1, paddingRight: spacing.sm }}>
                  <Body style={{ fontWeight: '600' }}>{menuItemLabel(m)}</Body>
                  <Muted>{formatCurrency(m.price)}</Muted>
                </View>
                <Button title={tr.departments.pos.addItem} onPress={() => addToCart(m.id)} />
              </View>
            </Card>
          ))}
        </View>
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
        onPress={onOpenOrder}
        loading={opening}
        fullWidth
      />

      <SectionTitle title={tr.departments.pos.menu} />
      {renderMenu()}
    </View>
  );

  const renderActiveOrder = (o: ActiveOrder) => (
    <Card key={o.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>
            {o.order_number || o.outlet_name || tr.departments.pos.title}
          </Body>
          {o.table_number ? (
            <Muted>
              {tr.departments.pos.tableNumber}: {o.table_number}
            </Muted>
          ) : null}
          {typeof o.total_amount === 'number' ? (
            <Muted>{formatCurrency(o.total_amount)}</Muted>
          ) : null}
        </View>
        <Badge label={statusLabel(o.status)} tone={statusTone(o.status)} />
      </View>
      {o.is_delayed ? (
        <View style={{ marginTop: spacing.sm }}>
          <Badge label={tr.departments.pos.delayed} tone="danger" />
        </View>
      ) : null}
      <View
        style={{ marginTop: spacing.md, flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' }}
      >
        {o.status === 'pending' ? (
          <Button
            title={tr.departments.pos.actions.preparing}
            variant="secondary"
            onPress={() => onUpdateStatus(o.id, 'preparing')}
            loading={busyOrderId === o.id}
          />
        ) : null}
        {o.status === 'preparing' ? (
          <Button
            title={tr.departments.pos.actions.ready}
            variant="secondary"
            onPress={() => onUpdateStatus(o.id, 'ready')}
            loading={busyOrderId === o.id}
          />
        ) : null}
        {o.status !== 'served' && o.status !== 'cancelled' ? (
          <Button
            title={tr.departments.pos.actions.served}
            onPress={() => onUpdateStatus(o.id, 'served')}
            loading={busyOrderId === o.id}
          />
        ) : null}
        {o.status !== 'served' && o.status !== 'cancelled' ? (
          <Button
            title={tr.departments.pos.actions.cancelled}
            variant="danger"
            onPress={() => onUpdateStatus(o.id, 'cancelled')}
            loading={busyOrderId === o.id}
          />
        ) : null}
      </View>
      {o.status !== 'cancelled' ? (
        <View style={{ marginTop: spacing.sm }}>
          {(() => {
            const due = typeof o.grand_total === 'number' ? o.grand_total : o.total_amount;
            return typeof due === 'number' ? (
              <Muted>
                {tr.departments.pos.amountDue}: {formatCurrency(due)}
              </Muted>
            ) : null;
          })()}
          <View
            style={{
              marginTop: spacing.sm,
              flexDirection: 'row',
              gap: spacing.sm,
              flexWrap: 'wrap',
            }}
          >
            <Button
              title={tr.departments.pos.payCash}
              variant="secondary"
              onPress={() => onCloseOrder(o.id, 'cash')}
              loading={payingOrder?.id === o.id && payingOrder.method === 'cash'}
            />
            <Button
              title={tr.departments.pos.payCard}
              variant="secondary"
              onPress={() => onCloseOrder(o.id, 'card')}
              loading={payingOrder?.id === o.id && payingOrder.method === 'card'}
            />
          </View>
        </View>
      ) : null}
    </Card>
  );

  const renderActiveTab = () => {
    const data = ordersQ.data?.orders || [];
    const state = (
      <DepartmentListState
        loading={ordersQ.isLoading}
        error={ordersQ.error}
        isEmpty={data.length === 0}
        emptyText={tr.departments.pos.noActiveOrders}
      />
    );
    return (
      <View>
        <SectionTitle title={tr.departments.pos.activeOrders} />
        {state ?? <View>{data.map(renderActiveOrder)}</View>}
      </View>
    );
  };

  const renderTableSlot = (t: TableSlot) => (
    <Card key={t.id || t.table_number} style={{ marginBottom: spacing.sm }}>
      <View
        style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>
            {tr.departments.pos.tableNumber} {t.table_number}
          </Body>
          {typeof t.seats === 'number' ? (
            <Muted>
              {t.seats} {tr.departments.pos.seats}
            </Muted>
          ) : null}
          {typeof t.current_bill === 'number' && t.current_bill > 0 ? (
            <Muted>{formatCurrency(t.current_bill)}</Muted>
          ) : null}
        </View>
        <Badge label={statusLabel(t.status)} tone={tableTone(t.status)} />
      </View>
    </Card>
  );

  const renderTablesTab = () => {
    const layout = tablesQ.data;
    const tables = layout?.tables || [];
    const state = (
      <DepartmentListState
        loading={tablesQ.isLoading}
        error={tablesQ.error}
        isEmpty={tables.length === 0}
        emptyText={tr.departments.pos.noTables}
      />
    );
    return (
      <View>
        <SectionTitle title={tr.departments.pos.transferTable} />
        <Card>
          <Field
            label={tr.departments.pos.fromTable}
            value={fromTable}
            onChangeText={setFromTable}
            placeholder={tr.departments.pos.transferTablePlaceholder}
          />
          <View style={{ height: spacing.sm }} />
          <Field
            label={tr.departments.pos.toTable}
            value={toTable}
            onChangeText={setToTable}
            placeholder={tr.departments.pos.transferTablePlaceholder}
          />
          <View style={{ height: spacing.md }} />
          <Button
            title={tr.departments.pos.doTransfer}
            onPress={onTransferTable}
            loading={transferring}
            fullWidth
          />
        </Card>

        <SectionTitle title={tr.departments.pos.tableLayout} />
        {layout ? (
          <View
            style={{
              flexDirection: 'row',
              gap: spacing.sm,
              flexWrap: 'wrap',
              marginBottom: spacing.md,
            }}
          >
            <Badge
              label={`${tr.departments.pos.available}: ${layout.available}`}
              tone="success"
            />
            <Badge label={`${tr.departments.pos.occupied}: ${layout.occupied}`} tone="warning" />
            <Badge label={`${tr.departments.pos.reserved}: ${layout.reserved}`} tone="info" />
          </View>
        ) : null}
        {state ?? <View>{tables.map(renderTableSlot)}</View>}
      </View>
    );
  };

  const renderFolioRow = (f: FolioListItem) => {
    const selected = folioId === f.id;
    return (
      <Pressable key={f.id} onPress={() => setFolioId(selected ? '' : f.id)}>
        <Card
          style={{
            marginBottom: spacing.sm,
            borderColor: selected ? c.primary : c.border,
            borderWidth: selected ? 2 : 1,
          }}
        >
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <View style={{ flex: 1, paddingRight: spacing.sm }}>
              <Body style={{ fontWeight: '600' }}>{f.guest_name || f.folio_number || f.id}</Body>
              {f.room_number ? (
                <Muted>
                  {tr.departments.pos.room}: {f.room_number}
                </Muted>
              ) : null}
            </View>
            <Body style={{ fontWeight: '600' }}>
              {tr.departments.pos.balance}: {formatCurrency(f.balance)}
            </Body>
          </View>
        </Card>
      </Pressable>
    );
  };

  const renderFolioTab = () => {
    const data = foliosQ.data?.folios || [];
    const state = (
      <DepartmentListState
        loading={foliosQ.isLoading}
        error={foliosQ.error}
        isEmpty={data.length === 0}
        emptyText={tr.departments.pos.noOpenFolios}
      />
    );
    return (
      <View>
        <SectionTitle title={tr.departments.pos.folioTransfer} />
        <Muted>{tr.departments.pos.folioTransferHint}</Muted>

        {renderCart()}

        <SectionTitle title={tr.departments.pos.menu} />
        {renderMenu()}

        <SectionTitle title={tr.departments.pos.selectFolio} />
        {state ?? <View>{data.map(renderFolioRow)}</View>}

        <View style={{ height: spacing.md }} />
        <Button
          title={tr.departments.pos.postToFolio}
          onPress={onPostToFolio}
          loading={posting}
          fullWidth
        />
      </View>
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.pos.title}</H1>

      {/* Offline write-queue indicator — how many orders are waiting to sync. */}
      {pendingSync > 0 ? (
        <View style={{ flexDirection: 'row', marginTop: spacing.xs, marginBottom: spacing.xs }}>
          <Badge label={`${tr.departments.pos.pendingSync}: ${pendingSync}`} tone="warning" />
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
        <View
          style={{
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: spacing.sm,
            marginBottom: spacing.md,
          }}
        >
          {outlets.map((o: Outlet) => (
            <Chip
              key={o.id}
              active={activeOutlet === o.id}
              label={outletLabel(o)}
              onPress={() => setOutletId(o.id)}
            />
          ))}
        </View>
      )}

      {/* Tab selector */}
      <View
        style={{
          flexDirection: 'row',
          flexWrap: 'wrap',
          gap: spacing.sm,
          marginBottom: spacing.md,
        }}
      >
        <Chip
          active={tab === 'order'}
          label={tr.departments.pos.tabs.order}
          onPress={() => setTab('order')}
        />
        <Chip
          active={tab === 'active'}
          label={tr.departments.pos.tabs.active}
          onPress={() => setTab('active')}
        />
        <Chip
          active={tab === 'tables'}
          label={tr.departments.pos.tabs.tables}
          onPress={() => setTab('tables')}
        />
        <Chip
          active={tab === 'folio'}
          label={tr.departments.pos.tabs.folio}
          onPress={() => setTab('folio')}
        />
      </View>

      {tab === 'order' ? renderOrderTab() : null}
      {tab === 'active' ? renderActiveTab() : null}
      {tab === 'tables' ? renderTablesTab() : null}
      {tab === 'folio' ? renderFolioTab() : null}
    </ScrollView>
  );
}
