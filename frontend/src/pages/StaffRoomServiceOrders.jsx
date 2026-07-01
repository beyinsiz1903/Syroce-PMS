import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { confirmDialog } from '@/lib/dialogs';
import {
  ArrowLeft, RefreshCw, Clock, BedDouble, Coffee, CheckCircle2,
  ChefHat, Truck, XCircle, PlugZap, ListChecks,
} from 'lucide-react';

const STATUS_FLOW = {
  pending: 'confirmed',
  confirmed: 'preparing',
  preparing: 'delivered',
};

const STATUS_LABEL = {
  pending: 'staffRoomService.statusPending',
  confirmed: 'staffRoomService.statusConfirmed',
  preparing: 'staffRoomService.statusPreparing',
  delivered: 'staffRoomService.statusDelivered',
  cancelled: 'staffRoomService.statusCancelled',
};

const STATUS_TONE = {
  pending: 'bg-amber-100 text-amber-800 border-amber-300',
  confirmed: 'bg-blue-100 text-blue-800 border-blue-300',
  preparing: 'bg-indigo-100 text-indigo-800 border-indigo-300',
  delivered: 'bg-green-100 text-green-800 border-green-300',
  cancelled: 'bg-gray-100 text-gray-700 border-gray-300',
};

const NEXT_LABEL = {
  pending: 'staffRoomService.actionConfirm',
  confirmed: 'staffRoomService.actionPrepare',
  preparing: 'staffRoomService.actionDeliver',
};

const NEXT_ICON = {
  pending: CheckCircle2,
  confirmed: ChefHat,
  preparing: Truck,
};

function getElapsedMinutes(orderedAt) {
  if (!orderedAt) return 0;
  const ordered = new Date(orderedAt);
  if (Number.isNaN(ordered.getTime())) return 0;
  return Math.max(0, Math.floor((Date.now() - ordered.getTime()) / 60000));
}

function getOrderTotal(o) {
  if (typeof o.total_amount === 'number') return o.total_amount;
  if (Array.isArray(o.items)) {
    return o.items.reduce(
      (sum, it) => sum + Number(it.price || 0) * Number(it.quantity || 1),
      0,
    );
  }
  return 0;
}

// Build the staff WS URL by mirroring axiosConfig's BACKEND_URL rules
// so we never end up with `/api/api/...` when VITE_BACKEND_URL already
// contains the `/api` suffix (and so we work both with the dev proxy
// and an absolute prod backend URL).
export function buildStaffWsUrl({
  backendUrl = import.meta.env.VITE_BACKEND_URL,
  origin = typeof window !== 'undefined' ? window.location.origin : '',
  token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null,
} = {}) {
  if (!token) return null;
  const raw = (backendUrl || '/api').replace(/\/+$/, '');
  const withApi = raw.endsWith('/api') ? raw : `${raw}/api`;
  // Resolve relative bases (e.g. the default "/api") against the
  // current origin so we can produce a real ws:// URL.
  const isAbsolute = /^https?:\/\//i.test(withApi);
  const httpFull = isAbsolute ? withApi : `${origin}${withApi}`;
  const wsBase = httpFull
    .replace(/^https:\/\//i, 'wss://')
    .replace(/^http:\/\//i, 'ws://');
  return `${wsBase}/guest/staff/ws/room-service-orders?token=${encodeURIComponent(token)}`;
}

const StaffRoomServiceOrders = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  // `loading` controls the full-page placeholder; we only want that on
  // first paint. `refreshing` drives the spin animation on the refresh
  // button (and the silent 15s poll) without replacing the list view.
  const [refreshing, setRefreshing] = useState(false);
  const [updating, setUpdating] = useState(() => new Set());
  const [wsConnected, setWsConnected] = useState(false);
  const [now, setNow] = useState(Date.now());
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const closedByUnmountRef = useRef(false);

  // Tick every 30s so the elapsed-time chip updates without a refetch.
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(tick);
  }, []);

  const loadOrders = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await axios.get('/guest/staff/room-service-orders');
      const list = Array.isArray(res.data?.orders) ? res.data.orders : [];
      setOrders(list);
    } catch (err) {
      console.error('Room service orders yüklenemedi', err);
      toast.error(t('staffRoomService.loadError'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [t]);

  // ── Realtime: subscribe to the tenant-wide staff WS so multiple
  // devices stay in sync. Falls back to the polling loop below.
  useEffect(() => {
    closedByUnmountRef.current = false;

    const connect = () => {
      const url = buildStaffWsUrl();
      if (!url) return;
      let ws;
      try {
        ws = new WebSocket(url);
      } catch (err) {
        console.warn('Staff WS init failed', err);
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        if (!closedByUnmountRef.current) scheduleReconnect();
      };
      ws.onerror = () => {
        try { ws.close(); } catch { /* ignore */ }
      };
      ws.onmessage = (msg) => {
        try {
          const parsed = JSON.parse(msg.data);
          if (!parsed || parsed.type !== 'room_service_order' || !parsed.order) return;
          const incoming = parsed.order;
          setOrders((prev) => {
            const idx = prev.findIndex((o) => o.id === incoming.id);
            // Drop terminally-closed orders from the open list.
            const isClosed = ['delivered', 'cancelled'].includes(incoming.status);
            if (idx === -1) {
              if (isClosed) return prev;
              return [...prev, incoming].sort(
                (a, b) => String(a.ordered_at || '').localeCompare(String(b.ordered_at || '')),
              );
            }
            if (isClosed) {
              const next = prev.slice();
              next.splice(idx, 1);
              return next;
            }
            const next = prev.slice();
            // Preserve the cached room_number if the WS frame doesn't include it.
            next[idx] = { ...prev[idx], ...incoming, room_number: incoming.room_number ?? prev[idx].room_number };
            return next;
          });
        } catch {
          /* ignore non-JSON frames */
        }
      };
    };

    const scheduleReconnect = () => {
      if (closedByUnmountRef.current) return;
      if (reconnectTimerRef.current) return;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, 5000);
    };

    connect();

    return () => {
      closedByUnmountRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      try { wsRef.current?.close(); } catch { /* ignore */ }
      wsRef.current = null;
    };
  }, []);

  // Initial load + slow polling fallback (15 s) when the WS is down.
  useEffect(() => {
    loadOrders();
    const interval = setInterval(() => {
      if (!wsConnected) loadOrders();
    }, 15000);
    return () => clearInterval(interval);
  }, [loadOrders, wsConnected]);

  const advanceStatus = useCallback(async (orderId, nextStatus) => {
    setUpdating((prev) => {
      const next = new Set(prev);
      next.add(orderId);
      return next;
    });
    try {
      await axios.patch(
        `/guest/room-service-orders/${orderId}/status`,
        { status: nextStatus },
      );
      toast.success(t('staffRoomService.statusUpdated', {
        status: t(STATUS_LABEL[nextStatus] || ''),
      }));
      // The WS will push the change too, but optimistic-update so the
      // tap feels instant on this device even if the WS is slow.
      setOrders((prev) => {
        const idx = prev.findIndex((o) => o.id === orderId);
        if (idx === -1) return prev;
        const isClosed = ['delivered', 'cancelled'].includes(nextStatus);
        if (isClosed) {
          const next = prev.slice();
          next.splice(idx, 1);
          return next;
        }
        const next = prev.slice();
        next[idx] = { ...prev[idx], status: nextStatus };
        return next;
      });
    } catch (err) {
      console.error('Status update failed', err);
      const msg = err?.response?.data?.detail || t('staffRoomService.updateError');
      toast.error(typeof msg === 'string' ? msg : t('staffRoomService.updateError'));
    } finally {
      setUpdating((prev) => {
        const next = new Set(prev);
        next.delete(orderId);
        return next;
      });
    }
  }, [t]);

  const cancelOrder = useCallback(async (orderId) => {
    if (!await confirmDialog({ message: t('staffRoomService.confirmCancel'), variant: 'danger' })) return;
    advanceStatus(orderId, 'cancelled');
  }, [advanceStatus, t]);

  const counts = useMemo(() => {
    const c = { pending: 0, confirmed: 0, preparing: 0, total: orders.length };
    orders.forEach((o) => {
      if (c[o.status] !== undefined) c[o.status] += 1;
    });
    return c;
  }, [orders]);

  return (
    <>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Coffee className="w-8 h-8 text-amber-600" />
              {t('staffRoomService.title')}
            </h1>
            <p className="text-gray-600 mt-1">{t('staffRoomService.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              className={wsConnected
                ? 'bg-green-600 text-white'
                : 'bg-gray-400 text-white'}
              data-testid="ws-status-badge"
            >
              <PlugZap className="w-3 h-3 mr-1" />
              {wsConnected ? t('staffRoomService.live') : t('staffRoomService.polling')}
            </Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={loadOrders}
              data-testid="refresh-orders"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
              {t('common.refresh')}
            </Button>
            <Button variant="outline" onClick={() => navigate('/pos')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('staffRoomService.backToPos')}
            </Button>
          </div>
        </div>

        {/* Counts */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <p className="text-sm text-gray-600">{t('staffRoomService.openOrders')}</p>
              <p className="text-3xl font-bold text-amber-600" data-testid="count-total">
                {counts.total}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-sm text-gray-600">{t('staffRoomService.statusPending')}</p>
              <p className="text-3xl font-bold text-amber-600" data-testid="count-pending">
                {counts.pending}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-sm text-gray-600">{t('staffRoomService.statusConfirmed')}</p>
              <p className="text-3xl font-bold text-blue-600" data-testid="count-confirmed">
                {counts.confirmed}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-sm text-gray-600">{t('staffRoomService.statusPreparing')}</p>
              <p className="text-3xl font-bold text-indigo-600" data-testid="count-preparing">
                {counts.preparing}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Orders list */}
        {loading ? (
          <Card>
            <CardContent className="p-12 text-center text-gray-500">
              <RefreshCw className="w-12 h-12 mx-auto mb-3 text-gray-300 animate-spin" />
              <p>{t('common.loading')}</p>
            </CardContent>
          </Card>
        ) : orders.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center text-gray-500">
              <ListChecks className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p className="text-lg">{t('staffRoomService.empty')}</p>
              <p className="text-sm mt-1">{t('staffRoomService.emptyHint')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {orders.map((order) => {
              const elapsed = (() => {
                // `now` triggers re-render every 30s for live elapsed.
                void now;
                return getElapsedMinutes(order.ordered_at);
              })();
              const isStale = elapsed > 30;
              const next = STATUS_FLOW[order.status];
              const NextIcon = next ? NEXT_ICON[order.status] : null;
              const total = getOrderTotal(order);
              const isUpdating = updating.has(order.id);
              return (
                <Card
                  key={order.id}
                  className={isStale ? 'border-red-300 shadow-md' : ''}
                  data-testid={`order-card-${order.id}`}
                >
                  <CardContent className="p-5 space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <BedDouble className="w-5 h-5 text-gray-500" />
                          <p className="text-xl font-bold">
                            {order.room_number
                              ? t('staffRoomService.room', { number: order.room_number })
                              : t('staffRoomService.roomUnknown')}
                          </p>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          #{(order.id || '').slice(0, 8)}
                        </p>
                      </div>
                      <div className="text-right">
                        <Badge className={STATUS_TONE[order.status] || STATUS_TONE.pending}>
                          {t(STATUS_LABEL[order.status] || STATUS_LABEL.pending)}
                        </Badge>
                        <div className={`mt-2 flex items-center justify-end gap-1 text-sm ${
                          isStale ? 'text-red-600 font-semibold' : 'text-gray-600'
                        }`}>
                          <Clock className="w-4 h-4" />
                          <span>{t('staffRoomService.minutesAgo', { count: elapsed })}</span>
                        </div>
                      </div>
                    </div>

                    <div className="bg-gray-50 rounded-lg p-3 space-y-1.5">
                      {(order.items || []).map((item, idx) => (
                        <div
                          key={item.id || `${order.id}-item-${idx}`}
                          className="flex items-center justify-between text-sm"
                        >
                          <span>
                            <span className="font-semibold">{item.quantity || 1}x</span>{' '}
                            {item.name}
                          </span>
                          <span className="text-gray-600">
                            {Number((item.price || 0) * (item.quantity || 1)).toFixed(2)}
                          </span>
                        </div>
                      ))}
                      {order.special_instructions && (
                        <p className="text-xs italic text-amber-700 mt-2">
                          {order.special_instructions}
                        </p>
                      )}
                      <div className="border-t mt-2 pt-2 flex items-center justify-between font-semibold text-sm">
                        <span>{t('staffRoomService.total')}</span>
                        <span>{total.toFixed(2)}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {next && NextIcon ? (
                        <Button
                          className="flex-1 h-12 text-base font-semibold"
                          disabled={isUpdating}
                          onClick={() => advanceStatus(order.id, next)}
                          data-testid={`advance-${order.id}`}
                        >
                          <NextIcon className="w-5 h-5 mr-2" />
                          {t(NEXT_LABEL[order.status])}
                        </Button>
                      ) : null}
                      <Button
                        variant="outline"
                        className="h-12"
                        disabled={isUpdating}
                        onClick={() => cancelOrder(order.id)}
                        data-testid={`cancel-${order.id}`}
                      >
                        <XCircle className="w-4 h-4 mr-1" />
                        {t('staffRoomService.cancel')}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
};

export default StaffRoomServiceOrders;
