import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, Banknote, Clock3, CreditCard, Loader2, RefreshCw, ReceiptText, Utensils } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';

const paymentLabels = { cash: 'Nakit', card: 'Kredi kartı', room_charge: 'Oda hesabı', bank_transfer: 'Havale', mixed: 'Karma' };

export default function POSOperations({ outletId }) {
  const [data, setData] = useState({ open_orders: [], payment_methods: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [adjustment, setAdjustment] = useState({ adjustment_type: 'discount', calculation: 'percentage', value: '', reason: '' });
  const [saving, setSaving] = useState(false);
  const currency = cachedTenantCurrency();

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = outletId ? { outlet_id: outletId } : {};
      const response = await axios.get('/pos/v2/operations/summary', { params });
      setData(response.data || { open_orders: [], payment_methods: {} });
    } catch (err) {
      setError(err?.response?.data?.detail || 'POS operasyon özeti yüklenemedi.');
    } finally { setLoading(false); }
  }, [outletId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const openOrders = useMemo(() => data.open_orders || [], [data.open_orders]);
  const oldestMinutes = useMemo(() => openOrders.reduce((max, order) => {
    const created = Date.parse(order.created_at || '');
    return Number.isFinite(created) ? Math.max(max, Math.floor((Date.now() - created) / 60000)) : max;
  }, 0), [openOrders]);

  const applyAdjustment = async () => {
    if (!selected || !adjustment.value || adjustment.reason.trim().length < 3) {
      toast.error('Tutar/oran ve en az 3 karakterlik gerekçe zorunludur.'); return;
    }
    setSaving(true);
    try {
      await axios.post(`/pos/v2/orders/${encodeURIComponent(selected.id)}/adjustment`, { ...adjustment, value: Number(adjustment.value) });
      toast.success(adjustment.adjustment_type === 'discount' ? 'İndirim uygulandı.' : 'Servis bedeli uygulandı.');
      setSelected(null); setAdjustment({ adjustment_type: 'discount', calculation: 'percentage', value: '', reason: '' }); await load();
    } catch (err) { toast.error(err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Düzeltme uygulanamadı.'); }
    finally { setSaving(false); }
  };

  return <div className="space-y-4" data-testid="pos-operations">
    <div className="flex items-center justify-between gap-3"><div><h2 className="text-base font-bold text-gray-900">Canlı Operasyon ve Kasa</h2><p className="text-sm text-gray-500">Açık adisyon, mutfak SLA ve iş günü tahsilat mutabakatı</p></div><Button variant="outline" size="sm" onClick={load} disabled={loading}>{loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}Yenile</Button></div>
    {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <Metric icon={ReceiptText} label="Açık adisyon" value={data.open_check_count || 0} />
      <Metric icon={Banknote} label="Açık toplam" value={formatCurrency(data.open_check_total || 0, currency)} />
      <Metric icon={Clock3} label="En eski adisyon" value={`${oldestMinutes} dk`} tone={oldestMinutes >= 60 ? 'red' : 'slate'} />
      <Metric icon={Utensils} label="Mutfakta bekleyen" value={data.kitchen_open_count || 0} />
      <Metric icon={AlertTriangle} label="20 dk üzeri" value={data.kitchen_overdue_count || 0} tone={data.kitchen_overdue_count ? 'red' : 'slate'} />
    </div>
    <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
      <Card><CardHeader><CardTitle>Açık adisyonlar</CardTitle></CardHeader><CardContent className="overflow-x-auto p-0"><table className="w-full min-w-[680px] text-left text-sm"><thead className="border-y bg-gray-50 text-xs uppercase text-gray-500"><tr><th className="p-3">Adisyon</th><th>Masa/Misafir</th><th>Durum</th><th>Süre</th><th>Tutar</th><th className="pr-3 text-right">Yönetim</th></tr></thead><tbody>{openOrders.length ? openOrders.map((order) => { const mins = Math.max(0, Math.floor((Date.now() - Date.parse(order.created_at || Date.now())) / 60000)); return <tr key={order.id} className="border-b last:border-0"><td className="p-3"><strong>{order.order_number || order.id?.slice(0, 8)}</strong><p className="text-xs text-gray-500">{order.outlet_id}</p></td><td>{order.table_number ? `Masa ${order.table_number}` : order.guest_name || 'Paket'}</td><td>{order.status}</td><td className={mins >= 60 ? 'font-semibold text-red-700' : ''}>{mins} dk</td><td className="font-semibold">{formatCurrency(order.grand_total || 0, currency)}</td><td className="pr-3 text-right"><Button size="sm" variant="outline" onClick={() => setSelected(order)}>İndirim/servis</Button></td></tr>; }) : <tr><td colSpan="6" className="p-8 text-center text-gray-500">Açık adisyon yok.</td></tr>}</tbody></table></CardContent></Card>
      <Card><CardHeader><CardTitle>İş günü kasa mutabakatı</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-xs text-gray-500">PMS iş günü: {data.business_date || '—'}</p>{Object.entries(data.payment_methods || {}).map(([method, amount]) => <div key={method} className="flex items-center justify-between rounded-lg border p-3"><span className="flex items-center gap-2 text-sm"><CreditCard className="h-4 w-4 text-gray-500" />{paymentLabels[method] || method}</span><strong>{formatCurrency(amount, currency)}</strong></div>)}<div className="flex justify-between border-t pt-3 text-sm"><span>İadeler</span><strong className="text-red-700">−{formatCurrency(data.refund_total || 0, currency)}</strong></div><div className="flex justify-between text-base"><span>Net tahsilat</span><strong>{formatCurrency(data.net_collected || 0, currency)}</strong></div></CardContent></Card>
    </div>
    <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}><DialogContent><DialogHeader><DialogTitle>Adisyon düzeltmesi</DialogTitle></DialogHeader><div className="grid gap-4 sm:grid-cols-2"><div><Label>İşlem</Label><select className="mt-1 h-10 w-full rounded-md border bg-white px-3" value={adjustment.adjustment_type} onChange={(e) => setAdjustment({ ...adjustment, adjustment_type: e.target.value })}><option value="discount">İndirim</option><option value="service_charge">Servis bedeli</option></select></div><div><Label>Hesaplama</Label><select className="mt-1 h-10 w-full rounded-md border bg-white px-3" value={adjustment.calculation} onChange={(e) => setAdjustment({ ...adjustment, calculation: e.target.value })}><option value="percentage">Yüzde</option><option value="fixed">Sabit tutar</option></select></div><div><Label>{adjustment.calculation === 'percentage' ? 'Oran (%)' : `Tutar (${currency})`}</Label><Input className="mt-1" type="number" min="0.01" step="0.01" value={adjustment.value} onChange={(e) => setAdjustment({ ...adjustment, value: e.target.value })} /></div><div><Label>Gerekçe</Label><Input className="mt-1" value={adjustment.reason} onChange={(e) => setAdjustment({ ...adjustment, reason: e.target.value })} /></div></div><DialogFooter><Button variant="outline" onClick={() => setSelected(null)}>Vazgeç</Button><Button onClick={applyAdjustment} disabled={saving}>{saving ? 'Uygulanıyor…' : 'Uygula'}</Button></DialogFooter></DialogContent></Dialog>
  </div>;
}

function Metric({ icon: Icon, label, value, tone = 'slate' }) {
  return <Card><CardContent className="flex items-center gap-3 p-4"><span className={`rounded-xl p-2 ${tone === 'red' ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-700'}`}><Icon className="h-5 w-5" /></span><div><p className="text-xl font-bold text-gray-900">{value}</p><p className="text-xs text-gray-500">{label}</p></div></CardContent></Card>;
}
