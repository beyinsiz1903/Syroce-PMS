import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Send, ChefHat, RefreshCw } from 'lucide-react';
import { promptDialog } from '@/lib/dialogs';
import { Info, Modal } from '../_shared';

const SENDABLE_STATUSES = new Set([
  'tentative', 'definite', 'confirmed', 'completed',
]);

const ORDER_STATUS_CLS = {
  sent: 'bg-amber-100 text-amber-800',
};

const FnbOrderModal = ({ event, onClose }) => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

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

  return (
    <Modal title={`Mutfağa Gönder — ${event.name}`} onClose={onClose} wide>
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
              <ChefHat className="w-4 h-4 text-amber-600" /> Gönderilen Siparişler
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
              {orders.map((o) => (
                <Card key={o.id}>
                  <CardContent className="p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        <Badge className={`${ORDER_STATUS_CLS[o.status] || 'bg-slate-100 text-slate-700'} border-0`}>
                          {o.status}
                        </Badge>
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
                  </CardContent>
                </Card>
              ))}
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
