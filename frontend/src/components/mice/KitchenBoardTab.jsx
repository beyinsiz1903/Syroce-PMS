import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/status-badge';
import { ChefHat, RefreshCw, Check, CheckCheck } from 'lucide-react';
import { Info } from './_shared';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import FnbSnapshot from './FnbSnapshot';
import { promptDialog } from '@/lib/dialogs';

// Lifecycle: sent → acknowledged → completed (mirrors backend transitions).
const ORDER_STATUS_META = {
  sent: { intent: 'warning', label: 'Gönderildi' },
  acknowledged: { intent: 'info', label: 'Onaylandı' },
  completed: { intent: 'success', label: 'Tamamlandı' },
  cancel_requested: { intent: 'warning', label: 'İptal onayı bekliyor' },
  cancelled: { intent: 'neutral', label: 'İptal edildi' },
};

// Auto-refresh interval for the live kitchen board (ms).
const AUTO_REFRESH_MS = 30000;

const KitchenBoardTab = ({ canManage = true, active = true }) => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [transitioningId, setTransitioningId] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const loadedOnce = useRef(false);

  const loadOrders = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const r = await axios.get('/mice/fnb-orders/open');
      setOrders(r.data.orders || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Açık siparişler alınamadı');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (loadedOnce.current) return;
    loadedOnce.current = true;
    loadOrders();
  }, [loadOrders]);

  useEffect(() => {
    if (!autoRefresh || !active) return undefined;
    const id = setInterval(() => { if (!document.hidden) loadOrders(false); }, AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [autoRefresh, active, loadOrders]);

  const cancelOrder = async order => {
    const reason = await promptDialog({ title: 'Üretim iptal talebi', message: 'Mutfak iptali ayrıca kabul edecek. En az 10 karakter gerekçe girin.' });
    if (!reason) return;
    setTransitioningId(order.id);
    try { await axios.post(`/mice/events/${order.event_id}/fnb-orders/${order.id}/cancel`, { reason }); await loadOrders(false); }
    catch (error) { toast.error(error.response?.data?.detail || 'İptal talebi kaydedilemedi'); }
    finally { setTransitioningId(null); }
  };

  const transitionOrder = async (order, target, successMsg) => {
    try {
      setTransitioningId(order.id);
      await axios.post(
        `/mice/events/${order.event_id}/fnb-orders/${order.id}/transition`,
        { status: target },
      );
      toast.success(successMsg);
      await loadOrders(false);
    } catch (err) {
      // 409 = invalid lifecycle transition (e.g. another user already
      // advanced it); surface the backend's Turkish message and refresh
      // so the buttons reflect the real current state.
      toast.error(err?.response?.data?.detail || 'Sipariş durumu güncellenemedi');
      if (err?.response?.status === 409) await loadOrders(false);
    } finally {
      setTransitioningId(null);
    }
  };

  const acknowledge = (order) => transitionOrder(
    order, 'acknowledged', 'Sipariş onaylandı (mutfak teslim aldı)',
  );
  const complete = (order) => transitionOrder(
    order, 'completed', 'Sipariş tamamlandı',
  );

  const sentCount = orders.filter((o) => o.status === 'sent').length;
  const ackCount = orders.filter((o) => o.status === 'acknowledged').length;

  return (
    <div className="space-y-4 text-sm">
      <Card><CardContent className="p-3 grid grid-cols-3 gap-2 text-xs">
        <Info l="Açık Sipariş" v={orders.length} />
        <Info l="Bekleyen (Gönderildi)" v={sentCount} />
        <Info l="Hazırlanıyor (Onaylandı)" v={ackCount} />
      </CardContent></Card>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="font-semibold flex items-center gap-2">
          <ChefHat className="w-4 h-4 text-amber-600" /> Mutfak Panosu
        </h3>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-gray-500 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Otomatik yenile (30sn)
          </label>
          <Button
            size="sm"
            variant="outline"
            onClick={() => loadOrders()}
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-center text-gray-500 p-4">Yükleniyor…</p>
      ) : orders.length === 0 ? (
        <p className="text-center text-gray-500 p-6">
          Açık mutfak siparişi yok.
        </p>
      ) : (
        <div className="grid md:grid-cols-2 gap-2">
          {orders.map((o) => {
            const meta = ORDER_STATUS_META[o.status]
              || { intent: 'neutral', label: o.status };
            const busy = transitioningId === o.id;
            return (
              <Card key={o.id}>
                <CardContent className="p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2">
                      <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>
                      <span className="text-xs text-gray-500">→ {o.target}</span>
                    </div>
                    <span className="font-semibold">
                      {formatCurrency(o.total, o.currency || cachedTenantCurrency())}
                    </span>
                  </div>
                  <div className="font-semibold text-sm">{o.event_name || '—'}</div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <Info l="Satır" v={(o.lines || []).length} />
                    <Info l="Pax" v={o.expected_pax} />
                    <Info l="Gönderen" v={o.sent_by} />
                  </div>
                  <div className="text-xs text-gray-500">
                    {o.sent_at?.slice(0, 16)?.replace('T', ' ') || '—'}
                    {o.note ? ` · ${o.note}` : ''}
                  </div>
                  {o.acknowledged_at && (
                    <div className="text-xs text-gray-500">
                      Onaylayan: {o.acknowledged_by || '—'} ·{' '}
                      {o.acknowledged_at.slice(0, 16).replace('T', ' ')}
                    </div>
                  )}
                  <FnbSnapshot order={o} />
                  <div className="flex justify-end gap-2 pt-1">
                    {canManage && o.status === 'sent' && (
                      <Button size="sm" onClick={() => acknowledge(o)} disabled={transitioningId != null || Boolean(o.needs_review && o.event_fingerprint)}>
                        {busy
                          ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                          : <Check className="w-4 h-4 mr-1" />}
                        Onayla
                      </Button>
                    )}
                    {canManage && o.status === 'acknowledged' && (
                      <Button size="sm" onClick={() => complete(o)} disabled={transitioningId != null || Boolean(o.needs_review && o.event_fingerprint)}>
                        {busy
                          ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                          : <CheckCheck className="w-4 h-4 mr-1" />}
                        Tamamla
                      </Button>
                    )}
                    {canManage && ['sent', 'acknowledged'].includes(o.status) && <Button size="sm" variant="outline" disabled={transitioningId != null} onClick={() => cancelOrder(o)}>İptal talebi</Button>}
                    {canManage && o.status === 'cancel_requested' && <Button size="sm" disabled={transitioningId != null} onClick={() => transitionOrder(o, 'cancelled', 'Mutfak iptali kabul etti')}>İptali kabul et</Button>}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default KitchenBoardTab;
