import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/status-badge';
import { Send, ChefHat, RefreshCw, Check, CheckCheck } from 'lucide-react';
import { promptDialog } from '@/lib/dialogs';
import { Info, Modal } from '../_shared';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import FnbSnapshot from '../FnbSnapshot';

const SENDABLE_STATUSES = new Set([
  'tentative', 'definite', 'confirmed', 'completed',
]);

// Lifecycle: sent → acknowledged → completed (mirrors backend transitions).
const ORDER_STATUS_META = {
  sent: { intent: 'warning', label: 'Gönderildi' },
  acknowledged: { intent: 'info', label: 'Onaylandı' },
  completed: { intent: 'success', label: 'Tamamlandı' },
  cancel_requested: { intent: 'warning', label: 'İptal onayı bekliyor' },
  cancelled: { intent: 'neutral', label: 'İptal edildi' },
};

const FnbOrderModal = ({ event, onClose, canManage = true }) => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [transitioningId, setTransitioningId] = useState(null);
  const sendKey = useRef(crypto.randomUUID());
  const sendPayload = useRef('');

  const fnbLineCount = (event.resources || []).filter(
    (r) => r.type === 'fb',
  ).length;
  const statusOk = SENDABLE_STATUSES.has(event.status);
  const canSend = canManage && statusOk && fnbLineCount > 0 && !sending;

  const loadOrders = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`/mice/events/${event.id}/fnb-orders`);
      setOrders(r.data.orders || []);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Gönderilen siparişler alınamadı');
    } finally {
      setLoading(false);
    }
  }, [event.id]);

  useEffect(() => { loadOrders(); }, [loadOrders]);

  const sendToKitchen = async () => {
    const note = await promptDialog({
      title: 'Mutfağa Gönder',
      message: 'Mutfak için kısa bir üretim notu ekleyebilirsiniz (opsiyonel).',
      defaultValue: '',
      placeholder: 'Servis 19:00, glutensiz 5 pax...',
      confirmText: 'Gönder',
    });
    if (note === null || note === undefined) return;
    const payload = { target: 'kitchen', note: note ? String(note) : null, ...(orders.find(o => o.status === 'cancelled') ? { replaces_order_id: orders.find(o => o.status === 'cancelled').id } : {}) };
    const serialized = JSON.stringify(payload);
    if (sendPayload.current && sendPayload.current !== serialized) sendKey.current = crypto.randomUUID();
    sendPayload.current = serialized;
    const idempotencyKey = sendKey.current;
    try {
      setSending(true);
      const response = await axios.post(
        `/mice/events/${event.id}/fnb-order/send`,
        payload,
        { headers: { 'Idempotency-Key': idempotencyKey } },
      );
      toast.success(response.data.replayed ? 'Bu üretim sürümü zaten kayıtlı' : 'F&B siparişi mutfağa gönderildi');
      sendKey.current = crypto.randomUUID();
      await loadOrders();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Sipariş gönderilemedi');
    } finally {
      setSending(false);
    }
  };

  const cancelOrder = async order => {
    const reason = await promptDialog({ title: 'Üretim iptal talebi', message: 'Mutfak iptali ayrıca kabul edecek. En az 10 karakter gerekçe girin.' });
    if (!reason) return;
    setTransitioningId(order.id);
    try { await axios.post(`/mice/events/${event.id}/fnb-orders/${order.id}/cancel`, { reason }); await loadOrders(); }
    catch (error) { toast.error(error.response?.data?.detail || 'İptal talebi kaydedilemedi'); }
    finally { setTransitioningId(null); }
  };

  const transitionOrder = async (order, target, successMsg) => {
    try {
      setTransitioningId(order.id);
      await axios.post(
        `/mice/events/${event.id}/fnb-orders/${order.id}/transition`,
        { status: target },
      );
      toast.success(successMsg);
      await loadOrders();
    } catch (err) {
      // 409 = invalid lifecycle transition (e.g. another user already
      // advanced it); surface the backend's Turkish message.
      toast.error(err?.response?.data?.detail || 'Sipariş durumu güncellenemedi');
      // Refresh so the buttons reflect the real current state after a 409.
      if (err?.response?.status === 409) await loadOrders();
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

  return (
    <Modal title={`Mutfak Siparişleri — ${event.name}`} onClose={onClose} wide>
      <div className="space-y-4 text-sm">
        <Card><CardContent className="p-3 grid grid-cols-3 gap-2 text-xs">
          <Info l="Beklenen Pax" v={event.expected_pax} />
          <Info l="F&B Satırı" v={fnbLineCount} />
          <Info l="Gönderilen Sipariş" v={orders.length} />
        </CardContent></Card>

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="text-xs text-gray-500">
            {!statusOk && (
              <span className="text-amber-700">
                Etkinlik durumu en az "Beklemede" olmalı (mevcut: {event.status}).
              </span>
            )}
            {statusOk && fnbLineCount === 0 && (
              <span className="text-amber-700">
                Etkinlikte gönderilecek F&B (yiyecek-içecek) satırı yok.
              </span>
            )}
            {canSend && (
              <span>{fnbLineCount} F&B satırı mutfağa gönderilmeye hazır.</span>
            )}
          </div>
          <Button onClick={sendToKitchen} disabled={!canSend}>
            {sending
              ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              : <Send className="w-4 h-4 mr-1" />}
            Mutfağa Gönder
          </Button>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold flex items-center gap-2">
              <ChefHat className="w-4 h-4 text-amber-600" /> Gelen Siparişler
            </h3>
            <Button size="sm" variant="ghost" onClick={loadOrders} disabled={loading}>
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
          {loading ? (
            <p className="text-center text-gray-500 p-4">Yükleniyor…</p>
          ) : orders.length === 0 ? (
            <p className="text-center text-gray-500 p-4">
              Henüz mutfağa sipariş gönderilmemiş.
            </p>
          ) : (
            <div className="space-y-2">
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
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <Info l="Satır" v={(o.lines || []).length} />
                        <Info l="Pax" v={o.expected_pax} />
                        <Info l="Gönderen" v={o.sent_by} />
                      </div>
                      <div className="text-xs text-gray-500">
                        {o.sent_at?.slice(0, 16)?.replace('T', ' ') || '—'}
                        {o.note ? ` · ${o.note}` : ''}
                      </div>
                      {(o.acknowledged_at || o.completed_at) && (
                        <div className="text-xs text-gray-500 space-y-0.5">
                          {o.acknowledged_at && (
                            <div>
                              Onaylayan: {o.acknowledged_by || '—'} ·{' '}
                              {o.acknowledged_at.slice(0, 16).replace('T', ' ')}
                            </div>
                          )}
                          {o.completed_at && (
                            <div>
                              Tamamlayan: {o.completed_by || '—'} ·{' '}
                              {o.completed_at.slice(0, 16).replace('T', ' ')}
                            </div>
                          )}
                        </div>
                      )}
                      <FnbSnapshot order={o} />
                      {canManage && o.status === 'cancel_requested' && <Button size="sm" disabled={transitioningId != null} onClick={() => transitionOrder(o, 'cancelled', 'Mutfak iptali kabul etti')}>İptali kabul et</Button>}
                      {canManage && (o.status === 'sent' || o.status === 'acknowledged') && (
                        <div className="flex justify-end gap-2 pt-1">
                          {o.status === 'sent' && (
                            <Button
                              size="sm"
                              onClick={() => acknowledge(o)}
                              disabled={transitioningId != null || Boolean(o.needs_review && o.event_fingerprint)}
                            >
                              {busy
                                ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                                : <Check className="w-4 h-4 mr-1" />}
                              Onayla
                            </Button>
                          )}
                          {o.status === 'acknowledged' && (
                            <Button
                              size="sm"
                              onClick={() => complete(o)}
                              disabled={transitioningId != null || Boolean(o.needs_review && o.event_fingerprint)}
                            >
                              {busy
                                ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                                : <CheckCheck className="w-4 h-4 mr-1" />}
                              Tamamla
                            </Button>
                          )}
                          <Button size="sm" variant="outline" disabled={transitioningId != null} onClick={() => cancelOrder(o)}>İptal talebi</Button>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        <div className="text-right">
          <Button variant="ghost" onClick={onClose}>Kapat</Button>
        </div>
      </div>
    </Modal>
  );
};

export default FnbOrderModal;
