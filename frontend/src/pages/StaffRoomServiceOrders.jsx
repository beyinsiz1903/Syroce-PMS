import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast }          from 'sonner';
import { confirmDialog }  from '@/lib/dialogs';
import {
  ArrowLeft, RefreshCw, Clock, BedDouble, Coffee,
  CheckCircle2, ChefHat, Truck, XCircle, Wifi, WifiOff,
  ListChecks, Loader2, Package,
} from 'lucide-react';

/* ─── constants ─────────────────────────────────────────────────── */
const STATUS_FLOW  = { pending: 'confirmed', confirmed: 'preparing', preparing: 'delivered' };
const STATUS_LABEL = { pending: 'staffRoomService.statusPending', confirmed: 'staffRoomService.statusConfirmed', preparing: 'staffRoomService.statusPreparing', delivered: 'staffRoomService.statusDelivered', cancelled: 'staffRoomService.statusCancelled' };
const STATUS_STYLE = {
  pending:   { bg: 'bg-amber-100  text-amber-800  border-amber-300',  dot: 'bg-amber-400'  },
  confirmed: { bg: 'bg-blue-100   text-blue-800   border-blue-300',   dot: 'bg-blue-400'   },
  preparing: { bg: 'bg-indigo-100 text-indigo-800 border-indigo-300', dot: 'bg-indigo-400' },
  delivered: { bg: 'bg-emerald-100 text-emerald-800 border-emerald-300', dot: 'bg-emerald-400' },
  cancelled: { bg: 'bg-gray-100   text-gray-600   border-gray-300',   dot: 'bg-gray-400'   },
};
const NEXT_LABEL = { pending: 'staffRoomService.actionConfirm', confirmed: 'staffRoomService.actionPrepare', preparing: 'staffRoomService.actionDeliver' };
const NEXT_ICON  = { pending: CheckCircle2, confirmed: ChefHat, preparing: Truck };
const NEXT_COLOR = { pending: 'bg-blue-600 hover:bg-blue-700', confirmed: 'bg-indigo-600 hover:bg-indigo-700', preparing: 'bg-emerald-600 hover:bg-emerald-700' };

/* ─── helpers ─────────────────────────────────────────────────── */
function getElapsed(orderedAt) {
  if (!orderedAt) return 0;
  const d = new Date(orderedAt);
  return Number.isNaN(d.getTime()) ? 0 : Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
}
function getTotal(o) {
  if (typeof o.total_amount === 'number') return o.total_amount;
  return (o.items || []).reduce((s, it) => s + Number(it.price || 0) * Number(it.quantity || 1), 0);
}
export function buildStaffWsUrl({ backendUrl = import.meta.env.VITE_BACKEND_URL, origin = typeof window !== 'undefined' ? window.location.origin : '', token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null } = {}) {
  if (!token) return null;
  const raw    = (backendUrl || '/api').replace(/\/+$/, '');
  const withApi = raw.endsWith('/api') ? raw : `${raw}/api`;
  const isAbs  = /^https?:\/\//i.test(withApi);
  const http   = isAbs ? withApi : `${origin}${withApi}`;
  const ws     = http.replace(/^https:\/\//i, 'wss://').replace(/^http:\/\//i, 'ws://');
  return `${ws}/guest/staff/ws/room-service-orders?token=${encodeURIComponent(token)}`;
}

/* ─── stat card ─────────────────────────────────────────────────── */
function StatCard({ label, value, color, testId }) {
  const c = { amber: 'from-amber-50 to-amber-50 border-amber-200 text-amber-600', blue: 'from-blue-50 to-indigo-50 border-blue-200 text-blue-600', indigo: 'from-indigo-50 to-violet-50 border-indigo-200 text-indigo-600', green: 'from-emerald-50 to-green-50 border-emerald-200 text-emerald-600' }[color] || '';
  return (
    <div className={`rounded-2xl border bg-gradient-to-br ${c} p-5`}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-3xl font-extrabold text-gray-900" data-testid={testId}>{value}</p>
    </div>
  );
}

/* ─── order card ─────────────────────────────────────────────────── */
function OrderCard({ order, now, t, onAdvance, onCancel, isUpdating }) {
  const elapsed  = (() => { void now; return getElapsed(order.ordered_at); })();
  const isStale  = elapsed > 30;
  const next     = STATUS_FLOW[order.status];
  const NextIcon = next ? NEXT_ICON[order.status] : null;
  const total    = getTotal(order);
  const style    = STATUS_STYLE[order.status] || STATUS_STYLE.pending;

  return (
    <div
      data-testid={`order-card-${order.id}`}
      className={`relative bg-white rounded-2xl border-2 shadow-sm transition-all
        ${isStale ? 'border-red-400 shadow-red-100' : 'border-gray-200 hover:border-gray-300 hover:shadow-md'}`}
    >
      {/* Top accent */}
      <div className={`absolute inset-x-0 top-0 h-1 rounded-t-2xl ${style.dot}`} />

      <div className="p-5 pt-6 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <BedDouble className="w-5 h-5 text-gray-400" />
              <p className="text-xl font-bold text-gray-900">
                {order.room_number
                  ? t('staffRoomService.room', { number: order.room_number })
                  : t('staffRoomService.roomUnknown', 'Oda ?')}
              </p>
            </div>
            <p className="text-xs text-gray-400 mt-0.5 font-mono">#{(order.id || '').slice(0, 8)}</p>
          </div>
          <div className="text-right flex flex-col items-end gap-1">
            <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full border ${style.bg}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
              {t(STATUS_LABEL[order.status] || STATUS_LABEL.pending)}
            </span>
            <div className={`flex items-center gap-1 text-xs font-medium ${isStale ? 'text-red-600' : 'text-gray-400'}`}>
              <Clock className="w-3.5 h-3.5" />
              {t('staffRoomService.minutesAgo', { count: elapsed, defaultValue: `${elapsed} dk önce` })}
            </div>
          </div>
        </div>

        {/* Items */}
        <div className="bg-gray-50 rounded-xl p-3.5 space-y-1.5">
          {(order.items || []).map((item, idx) => (
            <div key={item.id || `${order.id}-item-${idx}`} className="flex items-center justify-between text-sm">
              <span className="text-gray-700">
                <span className="font-bold text-gray-900">{item.quantity || 1}×</span> {item.name}
              </span>
              <span className="text-gray-500 tabular-nums">
                {Number((item.price || 0) * (item.quantity || 1)).toFixed(2)} ₺
              </span>
            </div>
          ))}
          {order.special_instructions && (
            <p className="text-xs italic text-amber-700 pt-1.5 border-t border-amber-100 mt-1">
              📝 {order.special_instructions}
            </p>
          )}
          <div className="flex items-center justify-between pt-2 mt-1 border-t border-gray-200 font-semibold text-sm">
            <span className="text-gray-700">{t('staffRoomService.total', 'Toplam')}</span>
            <span className="text-gray-900 tabular-nums">{total.toFixed(2)} ₺</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {next && NextIcon && (
            <button
              className={`flex-1 flex items-center justify-center gap-2 h-11 rounded-xl text-white font-semibold text-sm ${NEXT_COLOR[order.status] || 'bg-gray-600'} disabled:opacity-60 transition-colors`}
              disabled={isUpdating}
              onClick={() => onAdvance(order.id, next)}
              data-testid={`advance-${order.id}`}
            >
              {isUpdating ? <Loader2 className="w-4 h-4 animate-spin" /> : <NextIcon className="w-4 h-4" />}
              {t(NEXT_LABEL[order.status])}
            </button>
          )}
          <button
            className="flex items-center justify-center gap-1.5 h-11 px-3 rounded-xl border border-gray-200 text-gray-500 hover:border-red-200 hover:text-red-600 hover:bg-red-50 text-sm transition-colors disabled:opacity-60"
            disabled={isUpdating}
            onClick={() => onCancel(order.id)}
            data-testid={`cancel-${order.id}`}
          >
            <XCircle className="w-4 h-4" />
            {t('staffRoomService.cancel', 'İptal')}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── main ─────────────────────────────────────────────────────── */
const StaffRoomServiceOrders = () => {
  const { t }        = useTranslation();
  const navigate     = useNavigate();
  const [orders,     setOrders]     = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updating,   setUpdating]   = useState(() => new Set());
  const [wsConn,     setWsConn]     = useState(false);
  const [now,        setNow]        = useState(Date.now());
  const wsRef              = useRef(null);
  const reconnectTimerRef  = useRef(null);
  const closedByUnmountRef = useRef(false);

  /* clock tick */
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);

  /* load */
  const loadOrders = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await axios.get('/guest/staff/room-service-orders');
      setOrders(Array.isArray(res.data?.orders) ? res.data.orders : []);
    } catch { toast.error(t('staffRoomService.loadError', 'Siparişler yüklenemedi')); }
    finally  { setLoading(false); setRefreshing(false); }
  }, [t]);

  /* WebSocket */
  useEffect(() => {
    closedByUnmountRef.current = false;
    const scheduleReconnect = () => {
      if (closedByUnmountRef.current || reconnectTimerRef.current) return;
      reconnectTimerRef.current = setTimeout(() => { reconnectTimerRef.current = null; connect(); }, 5000);
    };
    const connect = () => {
      const url = buildStaffWsUrl();
      if (!url) return;
      let ws;
      try { ws = new WebSocket(url); } catch { scheduleReconnect(); return; }
      wsRef.current = ws;
      ws.onopen  = () => setWsConn(true);
      ws.onclose = () => { setWsConn(false); if (!closedByUnmountRef.current) scheduleReconnect(); };
      ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
      ws.onmessage = (msg) => {
        try {
          const parsed = JSON.parse(msg.data);
          if (!parsed || parsed.type !== 'room_service_order' || !parsed.order) return;
          const incoming = parsed.order;
          setOrders(prev => {
            const idx      = prev.findIndex(o => o.id === incoming.id);
            const isClosed = ['delivered', 'cancelled'].includes(incoming.status);
            if (idx === -1) { if (isClosed) return prev; return [...prev, incoming].sort((a, b) => String(a.ordered_at || '').localeCompare(String(b.ordered_at || ''))); }
            if (isClosed)   { const next = prev.slice(); next.splice(idx, 1); return next; }
            const next = prev.slice();
            next[idx]  = { ...prev[idx], ...incoming, room_number: incoming.room_number ?? prev[idx].room_number };
            return next;
          });
        } catch { /* non-JSON */ }
      };
    };
    connect();
    return () => {
      closedByUnmountRef.current = true;
      if (reconnectTimerRef.current) { clearTimeout(reconnectTimerRef.current); reconnectTimerRef.current = null; }
      try { wsRef.current?.close(); } catch { /* ignore */ }
      wsRef.current = null;
    };
  }, []);

  /* polling fallback */
  useEffect(() => {
    loadOrders();
    const iv = setInterval(() => { if (!wsConn) loadOrders(); }, 15000);
    return () => clearInterval(iv);
  }, [loadOrders, wsConn]);

  /* actions */
  const advanceStatus = useCallback(async (orderId, nextStatus) => {
    setUpdating(prev => { const n = new Set(prev); n.add(orderId); return n; });
    try {
      await axios.patch(`/guest/room-service-orders/${orderId}/status`, { status: nextStatus });
      toast.success(t('staffRoomService.statusUpdated', { status: t(STATUS_LABEL[nextStatus] || '') }));
      setOrders(prev => {
        const idx      = prev.findIndex(o => o.id === orderId);
        if (idx === -1) return prev;
        const isClosed = ['delivered', 'cancelled'].includes(nextStatus);
        if (isClosed)   { const n = prev.slice(); n.splice(idx, 1); return n; }
        const n = prev.slice(); n[idx] = { ...prev[idx], status: nextStatus }; return n;
      });
    } catch (err) {
      const msg = err?.response?.data?.detail || t('staffRoomService.updateError', 'Güncelleme başarısız');
      toast.error(typeof msg === 'string' ? msg : t('staffRoomService.updateError', 'Güncelleme başarısız'));
    } finally {
      setUpdating(prev => { const n = new Set(prev); n.delete(orderId); return n; });
    }
  }, [t]);

  const cancelOrder = useCallback(async (orderId) => {
    if (!await confirmDialog({ message: t('staffRoomService.confirmCancel', 'Bu siparişi iptal etmek istiyor musunuz?'), variant: 'danger' })) return;
    advanceStatus(orderId, 'cancelled');
  }, [advanceStatus, t]);

  const counts = useMemo(() => {
    const c = { pending: 0, confirmed: 0, preparing: 0, total: orders.length };
    orders.forEach(o => { if (c[o.status] !== undefined) c[o.status]++; });
    return c;
  }, [orders]);

  /* ── render ── */
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm px-6 py-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-amber-100 flex items-center justify-center">
              <Coffee className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 leading-tight">
                {t('staffRoomService.title', 'Oda Servisi Siparişleri')}
              </h1>
              <p className="text-sm text-gray-500">
                {t('staffRoomService.subtitle', 'Bugünün açık siparişleri. Durumu ilerletmek için dokunun.')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* WS badge */}
            <div className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full border ${wsConn ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-gray-100 text-gray-500 border-gray-200'}`}
              data-testid="ws-status-badge">
              {wsConn ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              {wsConn ? t('staffRoomService.live', 'Canlı') : t('staffRoomService.polling', 'Yoklama')}
            </div>
            <button onClick={loadOrders} data-testid="refresh-orders"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              {t('common.refresh', 'Yenile')}
            </button>
            <button onClick={() => navigate('/pos')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gray-900 text-white text-sm font-semibold hover:bg-gray-800 transition-colors">
              <ArrowLeft className="w-4 h-4" />
              {t('staffRoomService.backToPos', 'POS Paneli')}
            </button>
          </div>
        </div>
      </div>

      <div className="px-6 py-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label={t('staffRoomService.openOrders',     'Açık Siparişler')}  value={counts.total}     color="amber"  testId="count-total"     />
          <StatCard label={t('staffRoomService.statusPending',  'Beklemede')}         value={counts.pending}   color="amber"  testId="count-pending"   />
          <StatCard label={t('staffRoomService.statusConfirmed','Onaylandı')}          value={counts.confirmed} color="blue"   testId="count-confirmed" />
          <StatCard label={t('staffRoomService.statusPreparing','Hazırlanıyor')}       value={counts.preparing} color="indigo" testId="count-preparing" />
        </div>

        {/* Orders */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 className="w-10 h-10 animate-spin text-amber-500" />
            <p className="text-gray-400 text-sm">{t('common.loading', 'Yükleniyor…')}</p>
          </div>
        ) : orders.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white py-20 text-center">
            <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
              <ListChecks className="w-8 h-8 text-gray-400" />
            </div>
            <p className="font-semibold text-gray-700">{t('staffRoomService.empty', 'Açık oda servisi siparişi yok')}</p>
            <p className="text-sm text-gray-400 mt-1">{t('staffRoomService.emptyHint', 'Yeni misafir siparişleri burada anlık görünür.')}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {orders.map(order => (
              <OrderCard
                key={order.id}
                order={order}
                now={now}
                t={t}
                onAdvance={advanceStatus}
                onCancel={cancelOrder}
                isUpdating={updating.has(order.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default StaffRoomServiceOrders;
