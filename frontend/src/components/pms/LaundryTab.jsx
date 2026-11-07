import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Shirt, Plus, RefreshCw, Search, Settings, Trash2, Pencil, Check, X } from 'lucide-react';
import { confirmDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
const SERVICE_TYPES = [{
  code: 'wash_iron',
  name: 'Yıkama + Ütüleme',
  multiplier: 1
}, {
  code: 'dry_clean',
  name: 'Kuru Temizleme',
  multiplier: 1.5
}, {
  code: 'iron_only',
  name: 'Sadece Ütüleme',
  multiplier: 0.5
}, {
  code: 'express',
  name: 'Express (3 Saat)',
  multiplier: 2
}];
const emptyOrder = (currency = 'TRY') => ({ room_number: '', guest_name: '', booking_id: '', folio_id: '', service_type: 'wash_iron', items: [], notes: '', priority: 'normal', input_currency: currency, exchange_rate: '' });
const errorMessage = (error, fallback) => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : fallback;
const money = raw => {
  const value = Number(raw);
  return String(raw).trim() !== '' && Number.isFinite(value) && value >= 0 && value <= 1e9 && Math.abs(value * 100 - Math.round(value * 100)) < 1e-6 ? value : null;
};
const lineTotal = (price, quantity, service) => Math.round((price * quantity * SERVICE_TYPES.find(s => s.code === service).multiplier + Number.EPSILON) * 100) / 100;
const LaundryTab = () => {
  const {
    t
  } = useTranslation();
  const currency = cachedTenantCurrency();
  const [orders, setOrders] = useState([]);
  const [items, setItems] = useState([]);
  const [showNewOrder, setShowNewOrder] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [orderForm, setOrderForm] = useState(() => emptyOrder(currency));
  const [folioCurrency, setFolioCurrency] = useState('');
  const [orderError, setOrderError] = useState('');
  const [statusError, setStatusError] = useState('');
  const [itemToAdd, setItemToAdd] = useState({
    code: '',
    quantity: 1
  });
  const [roomLookupBusy, setRoomLookupBusy] = useState(false);
  const [roomError, setRoomError] = useState('');
  const [folioOptions, setFolioOptions] = useState([]);
  const [ordersError, setOrdersError] = useState(false);
  const [ordersStale, setOrdersStale] = useState(true);
  const [itemsError, setItemsError] = useState(false);
  const ordersVersion = useRef(0);
  const itemsVersion = useRef(0);
  const lookupVersion = useRef(0);
  const request = useRef(null);
  const submitting = useRef(false);
  const locked = loading || Boolean(request.current);
  useEffect(() => () => { lookupVersion.current += 1; ordersVersion.current += 1; itemsVersion.current += 1; }, []);
  const changeDialog = open => {
    lookupVersion.current += 1;
    setRoomLookupBusy(false);
    if (!request.current) { setOrderForm(emptyOrder(currency)); setRoomError(''); setOrderError(''); setFolioCurrency(''); setFolioOptions([]); setItemToAdd({ code: items.find(item => item.active !== false && (item.currency || currency) === currency)?.code || '', quantity: 1 }); }
    setShowNewOrder(open);
  };
  const changeRoom = value => {
    lookupVersion.current += 1;
    setRoomLookupBusy(false); setRoomError('Oda bilgisini doğrulayın');
    setFolioOptions([]);
    setFolioCurrency(''); setOrderError('');
    setOrderForm(p => ({ ...p, room_number: value, guest_name: '', booking_id: '', folio_id: '', exchange_rate: '' }));
  };

  // Ayarlar sekmesi state
  const [newItem, setNewItem] = useState({
    code: '',
    name: '',
    price: '', currency
  });
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState({
    name: '',
    price: '', currency
  });
  const activeItems = items.filter(i => i.active !== false && (i.currency || currency) === orderForm.input_currency);
  const currencies = [...new Set([currency, 'TRY', 'USD', 'EUR', 'GBP', ...items.map(i => i.currency).filter(Boolean)])];
  const loadOrders = useCallback(async () => {
    const version = ++ordersVersion.current;
    setOrdersStale(true);
    try {
      const res = await axios.get('/laundry/orders');
      if (version !== ordersVersion.current) return;
      if (!Array.isArray(res.data.orders)) throw new Error('Invalid order list');
      setOrders(res.data.orders);
      setOrdersError(false);
      setOrdersStale(false);
    } catch {
      if (version !== ordersVersion.current) return;
      toast.error('Çamaşır siparişleri yüklenemedi');
      setOrdersError(true);
    }
  }, []);
  const loadItems = useCallback(async () => {
    const version = ++itemsVersion.current;
    try {
      const res = await axios.get('/laundry/items');
      if (version !== itemsVersion.current) return;
      if (!Array.isArray(res.data.items)) throw new Error('Invalid item list');
      const list = res.data.items;
      setItems(list);
      setItemsError(false);
      setItemToAdd(p => ({ ...p, code: p.code || list.find(item => item.active !== false && (item.currency || currency) === currency)?.code || '' }));
    } catch {
      if (version !== itemsVersion.current) return;
      toast.error('Ürün listesi yüklenemedi');
      setItemsError(true);
    }
  }, [currency]);
  useEffect(() => {
    loadOrders();
    loadItems();
  }, [loadOrders, loadItems]);

  // Oda no → aktif misafir autofill
  const lookupRoomGuest = async roomNumber => {
    if (locked) return;
    const version = ++lookupVersion.current;
    const number = roomNumber.trim();
    setOrderForm(p => ({ ...p, guest_name: '', booking_id: '', folio_id: '' }));
    setFolioCurrency('');
    setFolioOptions([]);
    if (!number) return;
    setRoomLookupBusy(true);
    setRoomError('');
    try {
      const res = await axios.get(`/bookings/active-by-room/${encodeURIComponent(number)}`);
      if (version !== lookupVersion.current) return;
      if (res.data?.found) {
        setOrderForm(p => ({
          ...p,
          guest_name: res.data.guest_name || '',
          booking_id: res.data.booking_id || '',
          folio_id: res.data.folio_id || ''
        }));
        setFolioCurrency(res.data.folio_currency || '');
        if (res.data.folio_selection_required) {
          const windows = await axios.get(`/folio-windows/booking/${encodeURIComponent(res.data.booking_id)}`);
          if (version !== lookupVersion.current) return;
          if (!Array.isArray(windows.data)) throw new Error('Invalid folio list');
          const open = windows.data.filter(row => row.status === 'open' && row.currency === res.data.booking_currency && typeof row.folio_id === 'string' && row.folio_id);
          if (new Set(open.map(row => row.folio_id)).size !== open.length) throw new Error('Ambiguous folio list');
          setFolioOptions(open);
          setOrderForm(p => ({ ...p, folio_id: '' }));
          setRoomError(open.length ? 'Ücretin işleneceği açık folyoyu seçin.' : 'Konaklamanın para biriminde açık folyo bulunamadı.');
        } else if (!res.data.folio_id) setRoomError('Bu konaklamaya ait açık folyo bulunamadı.');
        else if (!res.data.folio_currency) setRoomError('Folyo para birimi doğrulanamadı; oda bilgisini yenileyin.');
      } else {
        setRoomError(`Oda ${number} için aktif konaklama bulunamadı`);
      }
    } catch {
      if (version === lookupVersion.current) setRoomError('Oda bilgisi alınamadı; yeniden doğrulayın.');
    } finally {
      if (version === lookupVersion.current) setRoomLookupBusy(false);
    }
  };
  const addItem = () => {
    const quantity = Number(itemToAdd.quantity);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 1000) { toast.error('Miktar 1–1000 arasında tam sayı olmalıdır'); return; }
    const item = activeItems.find(i => i.code === itemToAdd.code);
    if (!item) {
      toast.error('Ürün seçin');
      return;
    }
    setOrderForm(p => ({
      ...p,
      items: [...p.items, {
        code: item.code,
        name: item.name,
        price: item.price,
        currency: orderForm.input_currency,
        quantity,
        total: lineTotal(item.price, quantity, p.service_type)
      }]
    }));
    setItemToAdd({
      code: activeItems[0]?.code || '',
      quantity: 1
    });
  };
  const removeItem = idx => {
    setOrderForm(p => ({
      ...p,
      items: p.items.filter((_, i) => i !== idx)
    }));
  };
  const submitOrder = async () => {
    if (submitting.current) return;
    if (!request.current && (itemsError || roomLookupBusy || roomError || conversionError || !orderForm.booking_id || !orderForm.folio_id || orderForm.items.length === 0)) {
      toast.error('Aktif konaklama, açık folyo ve en az bir ürün gereklidir');
      return;
    }
    submitting.current = true;
    setOrderError('');
    request.current ||= { key: crypto.randomUUID(), payload: { ...structuredClone(orderForm), folio_currency: folioCurrency, exchange_rate: orderForm.input_currency === folioCurrency ? 1 : Number(orderForm.exchange_rate) } };
    setLoading(true);
    try {
      await axios.post('/laundry/orders', request.current.payload, { headers: { 'Idempotency-Key': request.current.key } });
      request.current = null;
      toast.success('Çamaşır siparişi oluşturuldu');
      changeDialog(false);
      loadOrders();
    } catch (error) {
      if (error?.response?.status >= 400 && error.response.status < 500) {
        request.current = null;
        const message = errorMessage(error, 'Sipariş reddedildi; bilgileri kontrol edin.');
        setOrderError(message); toast.error(message);
      } else {
        const message = 'Sipariş sonucu doğrulanamadı. Aynı istek anahtarıyla yeniden kontrol edebilirsiniz; yeni sipariş oluşturmayın.';
        setOrderError(message); toast.error(message);
      }
    }
    setLoading(false);
    submitting.current = false;
  };
  const updateStatus = async (orderId, newStatus) => {
    if (ordersStale) return;
    setStatusError('');
    try {
      const res = await axios.patch(`/laundry/orders/${orderId}`, {
        status: newStatus
      });
      const charge = res.data?.folio_charge;
      if (newStatus === 'delivered') {
        if (charge?.charged) {
          toast.success(`Teslim edildi — Folyoya ${formatCurrency(charge.amount, charge.currency || currency)} eklendi`);
        } else if (charge && charge.charged === false) {
          if (charge.reason === 'no_active_booking_or_folio') {
            toast.warning('Teslim edildi, ancak aktif folio bulunamadığı için folio yansıtılmadı');
          } else if (charge.error) {
            toast.warning(`Teslim edildi, folio yansıtma hatası: ${charge.error}`);
          } else {
            toast.success('Sipariş teslim edildi');
          }
        } else {
          toast.success('Sipariş teslim edildi');
        }
      } else {
        toast.success('Sipariş durumu guncellendi');
      }
      loadOrders();
    } catch (error) {
      const message = errorMessage(error, 'Sipariş durumu güncellenemedi; kaydı yenileyin.');
      setStatusError(message); toast.error(message);
    }
  };

  // ───── Ayarlar (laundry_items CRUD) ─────
  const createItem = async () => {
    const code = newItem.code.trim().toLowerCase();
    const name = newItem.name.trim();
    const price = money(newItem.price);
    if (!code || !name || price === null) {
      toast.error('Kod, ad ve geçerli fiyat zorunludur');
      return;
    }
    try {
      await axios.post('/laundry/items', {
        code,
        name,
        price, currency: newItem.currency
      });
      toast.success('Ürün eklendi');
      setNewItem({
        code: '',
        name: '',
        price: '', currency
      });
      loadItems();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Ürün eklenemedi');
    }
  };
  const startEdit = it => {
    setEditingId(it.id);
    setEditDraft({
      name: it.name,
      price: String(it.price), currency: it.currency || currency
    });
  };
  const saveEdit = async id => {
    const price = money(editDraft.price);
    if (!editDraft.name.trim() || price === null) {
      toast.error('Geçerli ad ve fiyat girin');
      return;
    }
    try {
      await axios.put(`/laundry/items/${id}`, {
        name: editDraft.name.trim(),
        price, currency: editDraft.currency
      });
      toast.success('Guncellendi');
      setEditingId(null);
      loadItems();
    } catch {
      toast.error('Guncellenemedi');
    }
  };
  const toggleActive = async it => {
    try {
      await axios.put(`/laundry/items/${it.id}`, {
        active: !(it.active !== false)
      });
      loadItems();
    } catch {
      toast.error('Durum degistirilemedi');
    }
  };
  const deleteItem = async id => {
    if (!(await confirmDialog({
      message: 'Bu urunu silmek istediginize emin misiniz?',
      variant: 'danger'
    }))) return;
    try {
      await axios.delete(`/laundry/items/${id}`);
      toast.success('Silindi');
      loadItems();
    } catch {
      toast.error('Silinemedi');
    }
  };
  const filteredOrders = orders.filter(o => {
    if (statusFilter !== 'all' && o.status !== statusFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (o.room_number || '').toLowerCase().includes(q) || (o.guest_name || '').toLowerCase().includes(q);
    }
    return true;
  });
  const statusConfig = {
    pending: {
      label: 'Bekliyor',
      color: 'bg-yellow-100 text-yellow-700'
    },
    in_progress: {
      label: 'Isleniyor',
      color: 'bg-blue-100 text-blue-700'
    },
    ready: {
      label: 'Hazir',
      color: 'bg-emerald-100 text-emerald-700'
    },
    delivered: {
      label: 'Teslim Edildi',
      color: 'bg-gray-100 text-gray-600'
    },
    cancelled: {
      label: 'İptal Edildi',
      color: 'bg-red-50 text-red-700'
    }
  };
  const orderTotal = orderForm.items.reduce((s, i) => s + (i.total || 0), 0);
  const needsExchange = Boolean(folioCurrency && orderForm.input_currency !== folioCurrency);
  const rate = needsExchange ? Number(orderForm.exchange_rate) : 1;
  const folioTotal = Math.round((orderTotal * rate + Number.EPSILON) * 100) / 100;
  const conversionError = orderForm.folio_id && (!folioCurrency ? 'Folyo para birimi doğrulanamadı.' : needsExchange && (!Number.isFinite(rate) || rate <= 0 || rate > 1e9) ? 'Farklı para birimi için geçerli kuru girin.' : orderTotal > 0 && (!Number.isFinite(folioTotal) || folioTotal <= 0 || folioTotal > 1e9) ? 'Folyoya yazılacak tutar geçersiz.' : '');
  return <div className="space-y-6">
      {statusError && <div role="alert" className="rounded border border-amber-300 p-3 text-sm">{statusError}</div>}
      {ordersError && <div role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">Siparişlerin güncelliği doğrulanamadı. Son bilinen kayıtlar gösteriliyor; işlem yapmadan önce Yenile ile yeniden deneyin.</div>}
      {itemsError && <div role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">Ürün fiyatlarının güncelliği doğrulanamadı. Yeni sipariş için fiyat listesini yeniden yükleyin. <Button variant="outline" onClick={loadItems}>Fiyat listesini yenile</Button></div>}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <Shirt className="w-6 h-6" /> {t('cm.components_pms_LaundryTab.camasirhane_yonetimi')}
        </h2>
      </div>

      <Tabs defaultValue="orders" className="space-y-4">
        <TabsList>
          <TabsTrigger value="orders">Siparisler</TabsTrigger>
          <TabsTrigger value="settings">
            <Settings className="w-4 h-4 mr-1" /> Ayarlar
          </TabsTrigger>
        </TabsList>

        <TabsContent value="orders" className="space-y-4">
          <div className="flex justify-end gap-2">
            <Button disabled={itemsError} onClick={() => changeDialog(true)} className="bg-blue-600 hover:bg-blue-700">
              <Plus className="w-4 h-4 mr-2" /> {t('cm.components_pms_LaundryTab.yeni_siparis')}
            </Button>
            <Button variant="outline" onClick={loadOrders}>
              <RefreshCw className="w-4 h-4 mr-2" /> {t('cm.components_pms_LaundryTab.yenile')}
            </Button>
          </div>

          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
              <Input className="pl-9" placeholder={t('cm.components_pms_LaundryTab.oda_no_veya_misafir_adi_ile_ara')} value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-40"><SelectValue placeholder={t('cm.components_pms_LaundryTab.durum')} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('cm.components_pms_LaundryTab.tum_durumlar')}</SelectItem>
                <SelectItem value="pending">Bekliyor</SelectItem>
                <SelectItem value="in_progress">Isleniyor</SelectItem>
                <SelectItem value="ready">{t('cm.components_pms_LaundryTab.hazir')}</SelectItem>
                <SelectItem value="delivered">Teslim Edildi</SelectItem>
                <SelectItem value="cancelled">İptal Edildi</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {[{
            label: 'Bekleyen',
            count: orders.filter(o => o.status === 'pending').length,
            color: 'yellow'
          }, {
            label: 'Islenen',
            count: orders.filter(o => o.status === 'in_progress').length,
            color: 'blue'
          }, {
            label: 'Hazir',
            count: orders.filter(o => o.status === 'ready').length,
            color: 'emerald'
          }, {
            label: 'Teslim',
            count: orders.filter(o => o.status === 'delivered').length,
            color: 'gray'
          }].map((s, i) => <Card key={s.id || i} className={`bg-${s.color}-50 border-${s.color}-200`}>
                <CardContent className="p-3 text-center">
                  <p className={`text-xs text-${s.color}-600`}>{s.label}</p>
                  <p className={`text-2xl font-bold text-${s.color}-700`}>{ordersStale ? '—' : s.count}</p>
                </CardContent>
              </Card>)}
          </div>

          <div className="space-y-2">
            {filteredOrders.length === 0 ? <Card className="border-dashed"><CardContent className="py-8 text-center text-gray-400">
                <Shirt className="w-10 h-10 mx-auto mb-2 opacity-30" />
                <p>{ordersStale ? 'Sipariş listesi doğrulanıyor; yükleme tamamlanmadı.' : t('cm.components_pms_LaundryTab.siparis_bulunamadi')}</p>
              </CardContent></Card> : filteredOrders.map(order => {
            const sc = statusConfig[order.status] || statusConfig.pending;
            return <Card key={order.id} className="hover:shadow-sm transition">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                          <span className="text-sm font-bold text-blue-700">{order.room_number}</span>
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-800">
                            {order.guest_name}
                            {order.folio_charged && <Badge className="ml-2 bg-emerald-100 text-emerald-700 text-[10px]">Folyoya yansıdı</Badge>}
                          </p>
                          <p className="text-xs text-gray-400">
                            {order.items?.map(i => `${i.name} x${i.quantity}`).join(', ')}
                          </p>
                          {order.folio_currency && order.folio_currency !== order.currency && <p className="text-xs text-muted-foreground">Folyoya: {formatCurrency(order.folio_total, order.folio_currency)} · 1 {order.currency} = {order.exchange_rate} {order.folio_currency}</p>}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge className={sc.color}>{sc.label}</Badge>
                        <span className="text-sm font-bold text-gray-700">{formatCurrency(order.total, order.currency || currency)}</span>
                        <fieldset disabled={ordersStale} className="flex gap-1">
                          {order.status === 'pending' && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => updateStatus(order.id, 'in_progress')}>Başla</Button>}
                          {order.status === 'in_progress' && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => updateStatus(order.id, 'ready')}>{t('cm.components_pms_LaundryTab.hazir_04e6f')}</Button>}
                          {order.status === 'ready' && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => updateStatus(order.id, 'delivered')}>Teslim Et</Button>}
                          {['pending', 'in_progress', 'ready'].includes(order.status) && !order.folio_charged && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={async () => {
                            if (await confirmDialog({ message: 'Sipariş iptal edilsin mi? Kayıt korunur; folyoya ücret işlenmez.' })) updateStatus(order.id, 'cancelled');
                          }}>İptal Et</Button>}
                        </fieldset>
                      </div>
                    </div>
                  </CardContent>
                </Card>;
          })}
          </div>
        </TabsContent>

        <TabsContent value="settings" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Plus className="w-4 h-4" /> {t('cm.components_pms_LaundryTab.yeni_urun_ekle')}
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-5 gap-3">
              <Input placeholder="Kod (orn: shirt)" value={newItem.code} onChange={e => setNewItem(p => ({
              ...p,
              code: e.target.value
            }))} />
              <Input placeholder="Ad (örn. Gömlek)" value={newItem.name} onChange={e => setNewItem(p => ({
              ...p,
              name: e.target.value
            }))} />
              <Input type="number" min="0" step="0.01" placeholder={`Fiyat (${newItem.currency})`} value={newItem.price} onChange={e => setNewItem(p => ({
              ...p,
              price: e.target.value
            }))} />
              <select aria-label="Yeni ürün para birimi" className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={newItem.currency} onChange={e => setNewItem(p => ({ ...p, currency: e.target.value }))}>{currencies.map(code => <option key={code} value={code}>{code}</option>)}</select>
              <Button onClick={createItem}><Plus className="w-4 h-4 mr-1" /> {t('cm.components_pms_LaundryTab.ekle')}</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Ürün Fiyat Listesi ({items.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {items.length === 0 ? <p className="text-center text-gray-400 py-6">{t('cm.components_pms_LaundryTab.henuz_urun_yok')}</p> : items.map(it => <div key={it.id} className="flex items-center justify-between border rounded-lg p-3 hover:bg-gray-50">
                    {editingId === it.id ? <>
                        <div className="flex items-center gap-3 flex-1">
                          <span className="text-xs text-gray-500 font-mono w-20">{it.code}</span>
                          <Input className="flex-1" value={editDraft.name} onChange={e => setEditDraft(p => ({
                      ...p,
                      name: e.target.value
                    }))} />
                          <Input type="number" min="0" step="0.01" className="w-28" value={editDraft.price} onChange={e => setEditDraft(p => ({
                      ...p,
                      price: e.target.value
                    }))} />
                          <select aria-label="Ürün para birimi" className="h-9 rounded-md border border-input bg-background px-2 text-sm" value={editDraft.currency} onChange={e => setEditDraft(p => ({ ...p, currency: e.target.value }))}>{currencies.map(code => <option key={code} value={code}>{code}</option>)}</select>
                        </div>
                        <div className="flex gap-1 ml-2">
                          <Button size="sm" variant="outline" className="h-8" onClick={() => saveEdit(it.id)}><Check className="w-4 h-4" /></Button>
                          <Button size="sm" variant="ghost" className="h-8" onClick={() => setEditingId(null)}><X className="w-4 h-4" /></Button>
                        </div>
                      </> : <>
                        <div className="flex items-center gap-3 flex-1">
                          <span className="text-xs text-gray-500 font-mono w-20">{it.code}</span>
                          <span className={`text-sm flex-1 ${it.active === false ? 'text-gray-400 line-through' : ''}`}>{it.name}</span>
                          <span className="text-sm font-bold text-gray-700 w-28 text-right">{formatCurrency(it.price, it.currency || currency)}</span>
                        </div>
                        <div className="flex gap-1 ml-2">
                          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => toggleActive(it)}>
                            {it.active === false ? 'Aktif Et' : 'Pasif Yap'}
                          </Button>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => startEdit(it)}><Pencil className="w-4 h-4" /></Button>
                          <Button size="sm" variant="outline" className="h-8 text-red-600" onClick={() => deleteItem(it.id)}><Trash2 className="w-4 h-4" /></Button>
                        </div>
                      </>}
                  </div>)}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={showNewOrder} onOpenChange={changeDialog}>
        <DialogContent className="max-h-[90dvh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Shirt className="w-5 h-5" /> {t('cm.components_pms_LaundryTab.yeni_camasir_siparisi')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="laundry-room">{t('cm.components_pms_LaundryTab.oda_no')}</Label>
                <Input id="laundry-room" disabled={locked} value={orderForm.room_number} onChange={e => changeRoom(e.target.value)} onBlur={e => lookupRoomGuest(e.target.value)} placeholder="101" />
              </div>
              <div>
                <Label>
                  {t('cm.components_pms_LaundryTab.misafir_adi')}
                  {roomLookupBusy && <span className="ml-2 text-xs text-blue-500">araniyor...</span>}
                  {orderForm.booking_id && <Badge className="ml-2 bg-emerald-100 text-emerald-700 text-[10px]">{t('cm.components_pms_LaundryTab.aktif')}</Badge>}
                </Label>
                <Input aria-label="Misafir adı" value={orderForm.guest_name} readOnly />
              </div>
            </div>
            {folioOptions.length > 0 && <div className="space-y-1">
              <Label htmlFor="laundry-folio">Ücretin işleneceği folyo</Label>
              <select className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm" id="laundry-folio" aria-label="Ücretin işleneceği folyo" disabled={locked || roomLookupBusy} value={orderForm.folio_id} onChange={event => {
                const value = event.target.value;
                if (!folioOptions.some(row => row.folio_id === value)) return;
                const selected = folioOptions.find(row => row.folio_id === value);
                setFolioCurrency(selected.currency);
                setOrderForm(p => ({ ...p, folio_id: value, exchange_rate: '' })); setRoomError(''); setOrderError('');
              }}>
                <option value="" disabled>Hedef folyoyu seçin</option>
                {folioOptions.map(row => <option key={row.folio_id} value={row.folio_id}>
                  {row.folio_number || `Hesap ${row.window_number}`} · {row.folio_type === 'agency' ? 'Acente' : row.folio_type === 'company' ? 'Şirket' : 'Misafir'} · {row.currency}
                </option>)}
              </select>
            </div>}
            {roomError && <p role="alert" className="text-sm text-amber-700">{roomError}</p>}
            {orderError && <p role="alert" className="rounded border border-amber-300 p-3 text-sm">{orderError}</p>}
            {request.current && !loading && <p role="status" className="text-sm text-amber-700">Önceki isteğin sonucu belirsiz. Aynı siparişi ve istek anahtarını koruyarak yeniden deneyin.</p>}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Hizmet Tipi</Label>
                <Select disabled={locked} value={orderForm.service_type} onValueChange={v => setOrderForm(p => ({
                ...p,
                service_type: v,
                items: p.items.map(item => ({ ...item, total: lineTotal(item.price, item.quantity, v) }))
              }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SERVICE_TYPES.map(s => <SelectItem key={s.code} value={s.code}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Oncelik</Label>
                <Select disabled={locked} value={orderForm.priority} onValueChange={v => setOrderForm(p => ({
                ...p,
                priority: v
              }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="high">{t('cm.components_pms_LaundryTab.yuksek')}</SelectItem>
                    <SelectItem value="urgent">Acil</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="rounded-lg border bg-muted/30 p-3 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div><Label htmlFor="laundry-input-currency">Hizmet para birimi</Label><select id="laundry-input-currency" aria-label="Hizmet para birimi" className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" disabled={locked || orderForm.items.length > 0} value={orderForm.input_currency} onChange={e => {
                  const code = e.target.value;
                  setOrderForm(p => ({ ...p, input_currency: code, exchange_rate: '' })); setOrderError('');
                  setItemToAdd({ code: items.find(item => item.active !== false && (item.currency || currency) === code)?.code || '', quantity: 1 });
                }}>{currencies.map(code => <option key={code} value={code}>{code}</option>)}</select></div>
                <div><Label>Folyo para birimi</Label><p className="py-2 text-sm font-medium">{folioCurrency || 'Önce oda ve folyoyu seçin'}</p></div>
              </div>
              {orderForm.items.length > 0 && <p className="text-xs text-muted-foreground">Para birimini değiştirmek için eklediğiniz ürünleri kaldırın; mevcut fiyatlar başka para birimi olarak etiketlenmez.</p>}
              {needsExchange && <div><Label htmlFor="laundry-exchange-rate">Kur: 1 {orderForm.input_currency} = kaç {folioCurrency}?</Label><Input id="laundry-exchange-rate" aria-label="Folyo dönüşüm kuru" disabled={locked} type="number" min="0.000000001" step="any" value={orderForm.exchange_rate} onChange={e => { setOrderForm(p => ({ ...p, exchange_rate: e.target.value })); setOrderError(''); }} /><p className="mt-1 text-xs text-muted-foreground">PMS ek ücretlerinde olduğu gibi onayladığınız kuru girin. Kaynak tutar ve bu kur siparişte saklanır; teslimde yeni kur uygulanmaz.</p></div>}
              {conversionError && <p role="alert" className="text-sm text-amber-700">{conversionError}</p>}
              {orderTotal > 0 && folioCurrency && !conversionError && <p role="status" className="text-sm font-medium">Folyoya yazılacak: {formatCurrency(folioTotal, folioCurrency)}</p>}
            </div>
            <div className="border rounded-lg p-3 space-y-2">
              <Label>{t('cm.components_pms_LaundryTab.urun_ekle')}</Label>
              <div className="flex gap-2">
                <Select disabled={locked} value={itemToAdd.code} onValueChange={v => setItemToAdd(p => ({
                ...p,
                code: v
              }))}>
                  <SelectTrigger className="flex-1"><SelectValue placeholder="Ürün seçin" /></SelectTrigger>
                  <SelectContent>
                    {activeItems.map(i => <SelectItem key={i.code} value={i.code}>{i.name} ({formatCurrency(i.price, i.currency || currency)})</SelectItem>)}
                  </SelectContent>
                </Select>
                <Input aria-label="Ürün miktarı" disabled={locked} type="number" min="1" max="1000" step="1" className="w-20" value={itemToAdd.quantity} onChange={e => setItemToAdd(p => ({
                ...p,
                quantity: e.target.value
              }))} />
                <Button aria-label="Ürün ekle" disabled={locked} size="sm" onClick={addItem}><Plus className="w-4 h-4" /></Button>
              </div>
              {activeItems.length === 0 && <p className="text-sm text-muted-foreground">Bu para biriminde ürün yok. Ayarlar’dan bu para birimine ait fiyatlı bir ürün ekleyin; katalog fiyatı otomatik çevrilmez.</p>}
              {orderForm.items.length > 0 && <div className="space-y-1 mt-2">
                  {orderForm.items.map((item, i) => <div key={item.id || i} className="flex items-center justify-between text-xs bg-gray-50 rounded px-2 py-1">
                      <span>{item.name} x{item.quantity}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{formatCurrency(item.total, item.currency || currency)}</span>
                        <Button disabled={locked} size="sm" variant="ghost" className="h-5 w-5 p-0 text-red-500" onClick={() => removeItem(i)}>x</Button>
                      </div>
                    </div>)}
                  <div className="flex justify-between text-sm font-bold pt-1 border-t">
                    <span>{t('cm.components_pms_LaundryTab.toplam')}</span>
                    <span>{formatCurrency(orderTotal, orderForm.input_currency)}</span>
                  </div>
                </div>}
            </div>
            <div><Label>Not</Label><Input disabled={locked} value={orderForm.notes} onChange={e => setOrderForm(p => ({
              ...p,
              notes: e.target.value
            }))} placeholder={t('cm.components_pms_LaundryTab.ozel_talimatlar')} /></div>
            <Button onClick={submitOrder} disabled={loading || (!request.current && (roomLookupBusy || Boolean(roomError) || Boolean(conversionError) || !orderForm.booking_id || !orderForm.folio_id || !orderForm.items.length))} className="w-full">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_LaundryTab.siparis_olustur')} ({formatCurrency(orderTotal, orderForm.input_currency)})
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>;
};
export default LaundryTab;
