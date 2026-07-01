import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/status-badge';
import { Send, ChefHat, RefreshCw, Check, CheckCheck } from 'lucide-react';
import { promptDialog } from '@/lib/dialogs';
import { Info, Modal } from '../_shared';

const SENDABLE_STATUSES = new Set([
  'tentative', 'definite', 'confirmed', 'completed',
]);

// Lifecycle: sent → acknowledged → completed (mirrors backend transitions).
const ORDER_STATUS_META = {
  sent: { intent: 'warning', label: 'Gönderildi' },
  acknowledged: { intent: 'info', label: 'Onaylandı' },
  completed: { intent: 'success', label: 'Tamamlandı' },
};

const FnbOrderModal = ({ event, onClose }) => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [transitioningId, setTransitioningId] = useState(null);

  const fnbLineCount = (event.resources || []).filter(
    (r) => r.type === 'fb',
  ).length;
  const statusOk = SENDABLE_STATUSES.has(event.status);
  const canSend = statusOk && fnbLineCount > 0 && !sending;

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
    const idempotencyKey = globalThis.crypto?.randomUUID?.()
      || `fnb-order-send-${event.id}-${Date.now()}-${Math.random()}`;
    try {
      setSending(true);
      await axios.post(
        `/mice/events/${event.id}/fnb-order/send`,
        { target: 'kitchen', note: note ? String(note) : null },
        { headers: { 'Idempotency-Key': idempotencyKey } },
      );
      toast.success('F&B siparişi mutfağa gönderildi');
      await loadOrders();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Sipariş gönderilemedi');
    } finally {
      setSending(false);
    }
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
                          ₺{(o.total || 0).toLocaleString('tr-TR')}
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
                      {(o.status === 'sent' || o.status === 'acknowledged') && (
                        <div className="flex justify-end gap-2 pt-1">
                          {o.status === 'sent' && (
                            <Button
                              size="sm"
                              onClick={() => acknowledge(o)}
                              disabled={busy}
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
                              disabled={busy}
                            >
                              {busy
                                ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                                : <CheckCheck className="w-4 h-4 mr-1" />}
                              Tamamla
                            </Button>
                          )}
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
