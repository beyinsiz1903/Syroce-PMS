import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Badge } from '@/components/ui/badge';
import {
  Home, Clock, CheckCircle, AlertTriangle, RefreshCw,
  Wifi, WifiOff, ChefHat, Utensils, Bell, Filter,
  Timer, ArrowRight, Coffee, UtensilsCrossed
} from 'lucide-react';
import { toast } from 'sonner';
import { useWebSocket, websocket } from '@/lib/websocket';

/* ─── helpers ───────────────────────────────────────────────────── */

/** Elapsed minutes since orderedAt; capped at 999 to avoid huge numbers from stale test data. */
const getElapsed = (orderedAt) => {
  if (!orderedAt) return 0;
  const diff = Math.floor((Date.now() - new Date(orderedAt).getTime()) / 60000);
  return Math.max(0, Math.min(diff, 999));
};

/** Human-readable timer: "5dk" / "1sa 5dk" */
const fmtTime = (minutes) => {
  if (minutes < 60) return `${minutes}dk`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h}sa` : `${h}sa ${m}dk`;
};

/** Short order number: integer shown as "#12", UUID trimmed to last 6 chars */
const shortNum = (num) => {
  if (!num) return '—';
  const s = String(num);
  if (s.length <= 6) return `#${s}`;
  return `#${s.slice(-6).toUpperCase()}`;
};

/** Location label with safe fallback */
const locationLabel = (order) => {
  if (order.table_name) return order.table_name;
  if (order.table_number) return `Masa ${order.table_number}`;
  if (order.room_number) return `Oda ${order.room_number}`;
  return 'Genel';
};

/** Timer colour: green → amber → red */
const timerClass = (elapsed, isUrgent) => {
  if (isUrgent || elapsed > 15) return 'text-red-400';
  if (elapsed > 10) return 'text-amber-400';
  return 'text-emerald-400';
};

/** Card accent colour by status */
const cardAccent = (status, isUrgent) => {
  if (isUrgent) return 'border-red-500 shadow-red-900/40';
  if (status === 'ready') return 'border-emerald-500 shadow-emerald-900/40';
  if (status === 'preparing') return 'border-blue-500 shadow-blue-900/40';
  return 'border-amber-500 shadow-amber-900/40';
};

const statusLabel = {
  pending:    { text: 'Bekliyor',   bg: 'bg-amber-500/20 text-amber-300  border-amber-500/30' },
  preparing:  { text: 'Hazırlanıyor', bg: 'bg-blue-500/20  text-blue-300   border-blue-500/30' },
  ready:      { text: 'Hazır',      bg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
};

/* ─── sub-components ─────────────────────────────────────────────── */

function OrderCard({ order, onReady, onServed, onStart }) {
  const elapsed  = getElapsed(order.ordered_at);
  const isUrgent = elapsed > 15 || order.priority === 'urgent';
  const status   = order.status || 'pending';
  const sl       = statusLabel[status] || statusLabel.pending;

  return (
    <div
      className={`
        relative flex flex-col rounded-2xl border-2 bg-gray-900
        shadow-lg transition-all duration-300
        ${cardAccent(status, isUrgent)}
        ${isUrgent ? 'ring-2 ring-red-500/40' : ''}
        hover:scale-[1.015] hover:shadow-xl
      `}
    >
      {/* Urgent ribbon */}
      {isUrgent && (
        <div className="absolute -top-3 left-4 flex items-center gap-1 bg-red-600 text-white text-xs font-bold px-3 py-0.5 rounded-full shadow-lg">
          <Bell className="w-3 h-3" /> ACİL
        </div>
      )}

      {/* Card header */}
      <div className="flex items-start justify-between p-4 pb-3 border-b border-white/8">
        <div>
          <p className="text-2xl font-extrabold text-white tracking-tight leading-none">
            {shortNum(order.order_number)}
          </p>
          <p className="text-sm text-gray-400 mt-1 flex items-center gap-1">
            <Utensils className="w-3.5 h-3.5" />
            {locationLabel(order)}
          </p>
        </div>

        <div className="flex flex-col items-end gap-1">
          {/* Timer */}
          <div className={`flex items-center gap-1.5 font-mono font-bold text-lg ${timerClass(elapsed, isUrgent)}`}>
            <Timer className="w-4 h-4" />
            {fmtTime(elapsed)}
          </div>
          {/* Status badge */}
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${sl.bg}`}>
            {sl.text}
          </span>
        </div>
      </div>

      {/* Items */}
      <div className="flex-1 p-4 space-y-2">
        {order.items?.length > 0 ? order.items.map((item, i) => (
          <div key={item.id || i} className="flex items-start gap-3 bg-white/5 rounded-xl p-3">
            {/* Quantity pill */}
            <span className="shrink-0 w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-sm font-bold text-white">
              {item.quantity}
            </span>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-white leading-tight">{item.name || '—'}</p>
              {item.notes && (
                <p className="text-xs text-amber-300 mt-0.5">📝 {item.notes}</p>
              )}
              {item.modifications?.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {item.modifications.map((mod, mi) => (
                    <span key={mi} className="text-xs bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded-md border border-purple-500/30">
                      {mod}
                    </span>
                  ))}
                </div>
              )}
            </div>
            {item.station && (
              <span className="shrink-0 text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded-md self-start">
                {item.station}
              </span>
            )}
          </div>
        )) : (
          <p className="text-gray-500 text-sm italic text-center py-2">Kalem bilgisi yok</p>
        )}
      </div>

      {/* Action button */}
      <div className="p-4 pt-2">
        {status === 'pending' && (
          <button
            onClick={() => onStart(order.id)}
            className="w-full h-11 rounded-xl font-bold text-sm bg-blue-600 hover:bg-blue-500 text-white transition-colors flex items-center justify-center gap-2"
          >
            <ChefHat className="w-4 h-4" /> Hazırlamaya Başla
          </button>
        )}
        {status === 'preparing' && (
          <button
            onClick={() => onReady(order.id)}
            className="w-full h-12 rounded-xl font-bold text-base bg-emerald-600 hover:bg-emerald-500 text-white transition-colors flex items-center justify-center gap-2 shadow-md shadow-emerald-900/40"
          >
            <CheckCircle className="w-5 h-5" /> SİPARİŞ HAZIR
          </button>
        )}
        {status === 'ready' && (
          <button
            onClick={() => onServed(order.id)}
            className="w-full h-12 rounded-xl font-bold text-base bg-gray-600 hover:bg-gray-500 text-white transition-colors flex items-center justify-center gap-2"
          >
            <ArrowRight className="w-5 h-5" /> SERVİS EDİLDİ
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── main page ──────────────────────────────────────────────────── */

const KitchenDisplay = () => {
  const navigate = useNavigate();
  const [orders, setOrders]           = useState([]);
  const [loading, setLoading]         = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [stationFilter, setStationFilter] = useState('all');
  const [statusFilter, setStatusFilter]   = useState('active');
  const [lastUpdate, setLastUpdate]       = useState(null);
  const [clock, setClock]                 = useState(new Date());
  const notifiedRef = useRef(new Set());
  const { isConnected } = useWebSocket('kitchen');

  /* clock tick */
  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  /* WebSocket live push */
  useEffect(() => {
    const unsub = websocket.on('kitchen_orders', (payload) => {
      if (!payload) return;
      setOrders(payload.orders || []);
      setLastUpdate(payload.timestamp || new Date().toISOString());
    });
    return () => { if (unsub) unsub(); };
  }, []);

  /* HTTP polling */
  const loadOrders = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/fnb/kitchen-display');
      setOrders(res.data.orders || []);
      setLastUpdate(new Date().toISOString());
    } catch {
      /* silent — toast only on user action */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOrders();
    if (autoRefresh) {
      const t = setInterval(loadOrders, 5000);
      return () => clearInterval(t);
    }
  }, [autoRefresh, loadOrders]);

  /* order actions */
  const updateStatus = async (orderId, status) => {
    try {
      await axios.put(`/fnb/kitchen-order/${orderId}/status`, null, { params: { status } });
      toast.success(status === 'preparing' ? 'Hazırlanmaya başlandı' : `Durum: ${status}`);
      loadOrders();
    } catch { toast.error('Durum güncellenemedi'); }
  };
  const completeOrder = async (orderId) => {
    try {
      await axios.post(`/fnb/kitchen-order/${orderId}/complete`);
      toast.success('Sipariş hazır! 🍽️');
      loadOrders();
    } catch { toast.error('Güncelleme başarısız'); }
  };
  const serveOrder = (id) => updateStatus(id, 'served');
  const startOrder = (id) => updateStatus(id, 'preparing');

  /* derived data */
  const stationOptions = useMemo(() => {
    const s = new Set();
    orders.forEach(o => o.items?.forEach(i => i.station && s.add(i.station)));
    return Array.from(s);
  }, [orders]);

  const filteredOrders = useMemo(() => {
    return orders.filter(order => {
      const stMatch = stationFilter === 'all' ||
        order.items?.some(i => i.station === stationFilter);
      const stStatus = order.status || 'pending';
      const stStatus2 = statusFilter === 'active'
        ? ['pending', 'preparing'].includes(stStatus)
        : statusFilter === 'ready'
          ? stStatus === 'ready'
          : true;
      return stMatch && stStatus2;
    });
  }, [orders, stationFilter, statusFilter]);

  const urgentOrders = useMemo(() =>
    orders.filter(o => getElapsed(o.ordered_at) > 12 || o.priority === 'urgent').slice(0, 6),
    [orders]
  );

  /* stats */
  const stats = useMemo(() => ({
    pending:   orders.filter(o => (o.status || 'pending') === 'pending').length,
    preparing: orders.filter(o => o.status === 'preparing').length,
    ready:     orders.filter(o => o.status === 'ready').length,
  }), [orders]);

  /* browser notifications */
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);
  useEffect(() => {
    urgentOrders.forEach(order => {
      if (!order?.id || notifiedRef.current.has(order.id)) return;
      notifiedRef.current.add(order.id);
      const elapsed = getElapsed(order.ordered_at);
      const title = `${locationLabel(order)} gecikiyor`;
      const body  = `Sipariş ${fmtTime(elapsed)} önce verildi`;
      if ('Notification' in window && Notification.permission === 'granted') {
        navigator.serviceWorker?.ready.then(reg =>
          reg.showNotification(title, { body, tag: `kitchen-${order.id}`, data: { url: '/kitchen-display' } })
        ).catch(() => toast.warning(title, { description: body }));
      } else {
        toast.warning(title, { description: body });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urgentOrders]);

  /* ── render ── */
  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col">

      {/* ── Header ── */}
      <header className="sticky top-0 z-50 bg-gradient-to-r from-gray-900 via-gray-900 to-gray-800 border-b border-white/10 shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4">
          {/* Left: brand */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/')}
              className="p-2 rounded-xl text-gray-400 hover:bg-white/10 hover:text-white transition-colors"
            >
              <Home className="w-5 h-5" />
            </button>
            <div className="w-px h-8 bg-white/10" />
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-xl bg-orange-500/20 border border-orange-500/30 flex items-center justify-center">
                <UtensilsCrossed className="w-5 h-5 text-orange-400" />
              </div>
              <div>
                <h1 className="text-lg font-bold leading-tight">Mutfak Ekranı</h1>
                <p className="text-xs text-gray-500 leading-none">Gerçek Zamanlı Sipariş Takibi</p>
              </div>
            </div>
          </div>

          {/* Center: stats */}
          <div className="hidden md:flex items-center gap-3">
            <StatPill label="Bekliyor" value={stats.pending} color="amber" />
            <StatPill label="Hazırlanıyor" value={stats.preparing} color="blue" />
            <StatPill label="Hazır" value={stats.ready} color="emerald" />
          </div>

          {/* Right: meta */}
          <div className="flex items-center gap-3">
            {/* Clock */}
            <div className="hidden sm:block text-right">
              <p className="text-xl font-mono font-bold text-white tabular-nums">
                {clock.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </p>
              <p className="text-xs text-gray-500">
                {lastUpdate
                  ? `Güncellendi: ${new Date(lastUpdate).toLocaleTimeString('tr-TR')}`
                  : 'Yükleniyor…'}
              </p>
            </div>

            {/* Connection */}
            <div className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full border ${
              isConnected
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-gray-700/50 text-gray-400 border-gray-600'
            }`}>
              {isConnected
                ? <><Wifi className="w-3.5 h-3.5" /> Canlı</>
                : <><WifiOff className="w-3.5 h-3.5" /> Polling</>}
            </div>

            {/* Refresh */}
            <button
              onClick={() => { setAutoRefresh(a => !a); loadOrders(); }}
              title={autoRefresh ? 'Otomatik yenileme açık' : 'Otomatik yenileme kapalı'}
              className={`p-2 rounded-xl border transition-colors ${
                autoRefresh
                  ? 'bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20'
                  : 'bg-white/5 border-white/10 text-gray-400 hover:bg-white/10'
              }`}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* ── Filter bar ── */}
        <div className="flex items-center gap-2 px-6 py-3 border-t border-white/5 overflow-x-auto">
          <Filter className="w-4 h-4 text-gray-500 shrink-0" />

          {/* Status filters */}
          <div className="flex items-center gap-1 bg-gray-800/60 p-1 rounded-xl border border-white/8 shrink-0">
            {[
              { key: 'active', label: 'Aktif' },
              { key: 'ready',  label: 'Hazır' },
              { key: 'all',    label: 'Tümü'  },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setStatusFilter(key)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  statusFilter === key
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Divider */}
          {stationOptions.length > 0 && (
            <>
              <div className="w-px h-5 bg-white/10 shrink-0" />
              <span className="text-xs text-gray-500 uppercase tracking-widest shrink-0">İstasyon</span>
              <div className="flex items-center gap-1 flex-wrap">
                <StationBtn active={stationFilter === 'all'} onClick={() => setStationFilter('all')}>
                  Hepsi
                </StationBtn>
                {stationOptions.map(s => (
                  <StationBtn key={s} active={stationFilter === s} onClick={() => setStationFilter(s)}>
                    {s}
                  </StationBtn>
                ))}
              </div>
            </>
          )}
        </div>
      </header>

      {/* ── Urgent Rail ── */}
      {urgentOrders.length > 0 && (
        <div className="bg-red-950/40 border-b border-red-800/40 px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 shrink-0">
              <AlertTriangle className="w-4 h-4 text-red-400 animate-pulse" />
              <span className="text-sm font-bold text-red-300 uppercase tracking-wide">Acil</span>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-0.5">
              {urgentOrders.map(order => (
                <div
                  key={order.id}
                  className="shrink-0 flex items-center gap-2.5 bg-red-800/30 border border-red-700/50 rounded-xl px-3 py-2"
                >
                  <div>
                    <p className="font-bold text-white text-sm leading-none">{shortNum(order.order_number)}</p>
                    <p className="text-xs text-red-300 mt-0.5">{locationLabel(order)}</p>
                  </div>
                  <div className={`flex items-center gap-1 text-sm font-mono font-bold ${timerClass(getElapsed(order.ordered_at), true)}`}>
                    <Clock className="w-3.5 h-3.5" />
                    {fmtTime(getElapsed(order.ordered_at))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Orders Grid ── */}
      <main className="flex-1 p-6">
        {filteredOrders.length === 0 ? (
          <EmptyState statusFilter={statusFilter} />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {filteredOrders.map(order => (
              <OrderCard
                key={order.id}
                order={order}
                onReady={completeOrder}
                onServed={serveOrder}
                onStart={startOrder}
              />
            ))}
          </div>
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-white/5 bg-gray-900/60 px-6 py-2 flex items-center justify-between text-xs text-gray-600">
        <span>Syroce PMS · Mutfak Ekranı</span>
        <span>{filteredOrders.length} sipariş görüntüleniyor</span>
      </footer>
    </div>
  );
};

/* ─── tiny shared components ─────────────────────────────────────── */

function StatPill({ label, value, color }) {
  const c = {
    amber:   'bg-amber-500/10 border-amber-500/30 text-amber-300',
    blue:    'bg-blue-500/10  border-blue-500/30  text-blue-300',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300',
  }[color];
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-sm font-semibold ${c}`}>
      <span className="text-lg font-extrabold tabular-nums">{value}</span>
      <span className="text-xs font-medium opacity-80">{label}</span>
    </div>
  );
}

function StationBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
        active
          ? 'bg-indigo-600 border-indigo-500 text-white'
          : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500 hover:text-white'
      }`}
    >
      {children}
    </button>
  );
}

function EmptyState({ statusFilter }) {
  const msgs = {
    active: { icon: <Coffee className="w-16 h-16 text-emerald-500/60" />, title: 'Bekleyen sipariş yok', sub: 'Tüm aktif siparişler tamamlandı 🎉' },
    ready:  { icon: <CheckCircle className="w-16 h-16 text-blue-500/60" />, title: 'Hazır sipariş yok', sub: 'Servise hazır sipariş bulunmuyor' },
    all:    { icon: <UtensilsCrossed className="w-16 h-16 text-gray-600" />, title: 'Sipariş yok', sub: 'Henüz sipariş oluşturulmamış' },
  };
  const m = msgs[statusFilter] || msgs.all;
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center gap-4">
      {m.icon}
      <p className="text-xl font-bold text-gray-300">{m.title}</p>
      <p className="text-gray-500">{m.sub}</p>
    </div>
  );
}

export default KitchenDisplay;