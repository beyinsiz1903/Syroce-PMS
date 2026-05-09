import { useState, useEffect, useCallback } from 'react';
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
const SERVICE_TYPES = [
  { code: 'wash_iron', name: 'Yikama + Utuleme', multiplier: 1 },
  { code: 'dry_clean', name: 'Kuru Temizleme', multiplier: 1.5 },
  { code: 'iron_only', name: 'Sadece Utuleme', multiplier: 0.5 },
  { code: 'express', name: 'Express (3 Saat)', multiplier: 2 },
];

const FALLBACK_ITEMS = [
  { id: 'shirt', code: 'shirt', name: 'Gomlek', price: 30, active: true },
  { id: 'pants', code: 'pants', name: 'Pantolon', price: 40, active: true },
];

const LaundryTab = () => {
  const { t } = useTranslation();
  const [orders, setOrders] = useState([]);
  const [items, setItems] = useState([]);
  const [showNewOrder, setShowNewOrder] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [orderForm, setOrderForm] = useState({
    room_number: '', guest_name: '', booking_id: '', folio_id: '',
    service_type: 'wash_iron', items: [], notes: '', priority: 'normal',
  });
  const [itemToAdd, setItemToAdd] = useState({ code: '', quantity: 1 });
  const [roomLookupBusy, setRoomLookupBusy] = useState(false);

  // Ayarlar sekmesi state
  const [newItem, setNewItem] = useState({ code: '', name: '', price: '' });
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState({ name: '', price: '' });

  const activeItems = items.filter(i => i.active !== false);

  const loadOrders = useCallback(async () => {
    try {
      const res = await axios.get('/laundry/orders');
      setOrders(res.data.orders || []);
    } catch {
      toast.error('Çamaşır siparişleri yüklenemedi');
      setOrders([]);
    }
  }, []);

  const loadItems = useCallback(async () => {
    try {
      const res = await axios.get('/laundry/items');
      const list = res.data.items || [];
      setItems(list.length ? list : FALLBACK_ITEMS);
      if (list.length && !itemToAdd.code) {
        setItemToAdd(p => ({ ...p, code: list[0].code }));
      }
    } catch {
      toast.error('Urun listesi yüklenemedi');
      setItems(FALLBACK_ITEMS);
    }
  }, [itemToAdd.code]);

  useEffect(() => { loadOrders(); loadItems(); }, [loadOrders, loadItems]);

  // Oda no → aktif misafir autofill
  const lookupRoomGuest = async (roomNumber) => {
    if (!roomNumber || !roomNumber.trim()) return;
    setRoomLookupBusy(true);
    try {
      const res = await axios.get(`/bookings/active-by-room/${encodeURIComponent(roomNumber.trim())}`);
      if (res.data?.found) {
        setOrderForm(p => ({
          ...p,
          guest_name: res.data.guest_name || p.guest_name,
          booking_id: res.data.booking_id || '',
          folio_id: res.data.folio_id || '',
        }));
        toast.success(`Misafir bulundu: ${res.data.guest_name || '(isimsiz)'}`);
      } else {
        toast.info(`Oda ${roomNumber} için aktif misafir yok`);
        setOrderForm(p => ({ ...p, booking_id: '', folio_id: '' }));
      }
    } catch {
      // sessiz
    } finally {
      setRoomLookupBusy(false);
    }
  };

  const addItem = () => {
    const item = activeItems.find(i => i.code === itemToAdd.code);
    if (!item) {
      toast.error('Urun secin');
      return;
    }
    const svc = SERVICE_TYPES.find(s => s.code === orderForm.service_type);
    setOrderForm(p => ({
      ...p,
      items: [...p.items, {
        code: item.code,
        name: item.name,
        price: item.price,
        quantity: itemToAdd.quantity,
        total: item.price * itemToAdd.quantity * (svc?.multiplier || 1),
      }],
    }));
    setItemToAdd({ code: activeItems[0]?.code || '', quantity: 1 });
  };

  const removeItem = (idx) => {
    setOrderForm(p => ({ ...p, items: p.items.filter((_, i) => i !== idx) }));
  };

  const submitOrder = async () => {
    if (!orderForm.room_number || orderForm.items.length === 0) {
      toast.error('Oda numarasi ve en az bir urun gerekli');
      return;
    }
    setLoading(true);
    try {
      await axios.post('/laundry/orders', orderForm);
      toast.success('Çamaşır siparişi oluşturuldu');
      setShowNewOrder(false);
      setOrderForm({
        room_number: '', guest_name: '', booking_id: '', folio_id: '',
        service_type: 'wash_iron', items: [], notes: '', priority: 'normal',
      });
      loadOrders();
    } catch {
      toast.error('Çamaşır siparişi oluşturulamadı');
    }
    setLoading(false);
  };

  const updateStatus = async (orderId, newStatus) => {
    try {
      const res = await axios.patch(`/laundry/orders/${orderId}`, { status: newStatus });
      const charge = res.data?.folio_charge;
      if (newStatus === 'delivered') {
        if (charge?.charged) {
          toast.success(`Teslim edildi — Folio'ya ${charge.amount?.toFixed(2)} TL eklendi`);
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
    } catch {
      toast.error('Sipariş durumu guncellenemedi');
    }
  };

  // ───── Ayarlar (laundry_items CRUD) ─────
  const createItem = async () => {
    const code = newItem.code.trim().toLowerCase();
    const name = newItem.name.trim();
    const price = parseFloat(newItem.price);
    if (!code || !name || isNaN(price) || price < 0) {
      toast.error('Kod, ad ve geçerli fiyat zorunludur');
      return;
    }
    try {
      await axios.post('/laundry/items', { code, name, price });
      toast.success('Urun eklendi');
      setNewItem({ code: '', name: '', price: '' });
      loadItems();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Urun eklenemedi');
    }
  };

  const startEdit = (it) => {
    setEditingId(it.id);
    setEditDraft({ name: it.name, price: String(it.price) });
  };

  const saveEdit = async (id) => {
    const price = parseFloat(editDraft.price);
    if (!editDraft.name.trim() || isNaN(price) || price < 0) {
      toast.error('Geçerli ad ve fiyat girin');
      return;
    }
    try {
      await axios.put(`/laundry/items/${id}`, { name: editDraft.name.trim(), price });
      toast.success('Guncellendi');
      setEditingId(null);
      loadItems();
    } catch {
      toast.error('Guncellenemedi');
    }
  };

  const toggleActive = async (it) => {
    try {
      await axios.put(`/laundry/items/${it.id}`, { active: !(it.active !== false) });
      loadItems();
    } catch {
      toast.error('Durum degistirilemedi');
    }
  };

  const deleteItem = async (id) => {
    if (!await confirmDialog({ message: 'Bu urunu silmek istediginize emin misiniz?', variant: 'danger' })) return;
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
    pending: { label: 'Bekliyor', color: 'bg-yellow-100 text-yellow-700' },
    in_progress: { label: 'Isleniyor', color: 'bg-blue-100 text-blue-700' },
    ready: { label: 'Hazir', color: 'bg-emerald-100 text-emerald-700' },
    delivered: { label: 'Teslim Edildi', color: 'bg-gray-100 text-gray-600' },
  };

  const orderTotal = orderForm.items.reduce((s, i) => s + (i.total || 0), 0);

  return (
    <div className="space-y-6">
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
            <Button onClick={() => setShowNewOrder(true)} className="bg-blue-600 hover:bg-blue-700">
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
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {[
              { label: 'Bekleyen', count: orders.filter(o => o.status === 'pending').length, color: 'yellow' },
              { label: 'Islenen', count: orders.filter(o => o.status === 'in_progress').length, color: 'blue' },
              { label: 'Hazir', count: orders.filter(o => o.status === 'ready').length, color: 'emerald' },
              { label: 'Teslim', count: orders.filter(o => o.status === 'delivered').length, color: 'gray' },
            ].map((s, i) => (
              <Card key={i} className={`bg-${s.color}-50 border-${s.color}-200`}>
                <CardContent className="p-3 text-center">
                  <p className={`text-xs text-${s.color}-600`}>{s.label}</p>
                  <p className={`text-2xl font-bold text-${s.color}-700`}>{s.count}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="space-y-2">
            {filteredOrders.length === 0 ? (
              <Card className="border-dashed"><CardContent className="py-8 text-center text-gray-400">
                <Shirt className="w-10 h-10 mx-auto mb-2 opacity-30" />
                <p>{t('cm.components_pms_LaundryTab.siparis_bulunamadi')}</p>
              </CardContent></Card>
            ) : filteredOrders.map(order => {
              const sc = statusConfig[order.status] || statusConfig.pending;
              return (
                <Card key={order.id} className="hover:shadow-sm transition">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                          <span className="text-sm font-bold text-blue-700">{order.room_number}</span>
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-800">
                            {order.guest_name}
                            {order.folio_charged && (
                              <Badge className="ml-2 bg-emerald-100 text-emerald-700 text-[10px]">Folio'ya yansidi</Badge>
                            )}
                          </p>
                          <p className="text-xs text-gray-400">
                            {order.items?.map(i => `${i.name} x${i.quantity}`).join(', ')}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge className={sc.color}>{sc.label}</Badge>
                        <span className="text-sm font-bold text-gray-700">{(order.total || 0).toFixed(2)} TL</span>
                        <div className="flex gap-1">
                          {order.status === 'pending' && (
                            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => updateStatus(order.id, 'in_progress')}>Basla</Button>
                          )}
                          {order.status === 'in_progress' && (
                            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => updateStatus(order.id, 'ready')}>{t('cm.components_pms_LaundryTab.hazir_04e6f')}</Button>
                          )}
                          {order.status === 'ready' && (
                            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => updateStatus(order.id, 'delivered')}>Teslim Et</Button>
                          )}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
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
            <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <Input placeholder="Kod (orn: shirt)" value={newItem.code} onChange={e => setNewItem(p => ({ ...p, code: e.target.value }))} />
              <Input placeholder="Ad (orn: Gomlek)" value={newItem.name} onChange={e => setNewItem(p => ({ ...p, name: e.target.value }))} />
              <Input type="number" min="0" step="0.01" placeholder="Fiyat (TL)" value={newItem.price} onChange={e => setNewItem(p => ({ ...p, price: e.target.value }))} />
              <Button onClick={createItem}><Plus className="w-4 h-4 mr-1" /> {t('cm.components_pms_LaundryTab.ekle')}</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Urun Fiyat Listesi ({items.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {items.length === 0 ? (
                  <p className="text-center text-gray-400 py-6">{t('cm.components_pms_LaundryTab.henuz_urun_yok')}</p>
                ) : items.map(it => (
                  <div key={it.id} className="flex items-center justify-between border rounded-lg p-3 hover:bg-gray-50">
                    {editingId === it.id ? (
                      <>
                        <div className="flex items-center gap-3 flex-1">
                          <span className="text-xs text-gray-500 font-mono w-20">{it.code}</span>
                          <Input className="flex-1" value={editDraft.name} onChange={e => setEditDraft(p => ({ ...p, name: e.target.value }))} />
                          <Input type="number" min="0" step="0.01" className="w-28" value={editDraft.price} onChange={e => setEditDraft(p => ({ ...p, price: e.target.value }))} />
                        </div>
                        <div className="flex gap-1 ml-2">
                          <Button size="sm" variant="outline" className="h-8" onClick={() => saveEdit(it.id)}><Check className="w-4 h-4" /></Button>
                          <Button size="sm" variant="ghost" className="h-8" onClick={() => setEditingId(null)}><X className="w-4 h-4" /></Button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex items-center gap-3 flex-1">
                          <span className="text-xs text-gray-500 font-mono w-20">{it.code}</span>
                          <span className={`text-sm flex-1 ${it.active === false ? 'text-gray-400 line-through' : ''}`}>{it.name}</span>
                          <span className="text-sm font-bold text-gray-700 w-24 text-right">{Number(it.price).toFixed(2)} TL</span>
                        </div>
                        <div className="flex gap-1 ml-2">
                          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => toggleActive(it)}>
                            {it.active === false ? 'Aktif Et' : 'Pasif Yap'}
                          </Button>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => startEdit(it)}><Pencil className="w-4 h-4" /></Button>
                          <Button size="sm" variant="outline" className="h-8 text-red-600" onClick={() => deleteItem(it.id)}><Trash2 className="w-4 h-4" /></Button>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={showNewOrder} onOpenChange={setShowNewOrder}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Shirt className="w-5 h-5" /> {t('cm.components_pms_LaundryTab.yeni_camasir_siparisi')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('cm.components_pms_LaundryTab.oda_no')}</Label>
                <Input
                  value={orderForm.room_number}
                  onChange={e => setOrderForm(p => ({ ...p, room_number: e.target.value }))}
                  onBlur={e => lookupRoomGuest(e.target.value)}
                  placeholder="101"
                />
              </div>
              <div>
                <Label>
                  {t('cm.components_pms_LaundryTab.misafir_adi')}
                  {roomLookupBusy && <span className="ml-2 text-xs text-blue-500">araniyor...</span>}
                  {orderForm.booking_id && <Badge className="ml-2 bg-emerald-100 text-emerald-700 text-[10px]">{t('cm.components_pms_LaundryTab.aktif')}</Badge>}
                </Label>
                <Input value={orderForm.guest_name} onChange={e => setOrderForm(p => ({ ...p, guest_name: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Hizmet Tipi</Label>
                <Select value={orderForm.service_type} onValueChange={v => setOrderForm(p => ({ ...p, service_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SERVICE_TYPES.map(s => <SelectItem key={s.code} value={s.code}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Oncelik</Label>
                <Select value={orderForm.priority} onValueChange={v => setOrderForm(p => ({ ...p, priority: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="high">{t('cm.components_pms_LaundryTab.yuksek')}</SelectItem>
                    <SelectItem value="urgent">Acil</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="border rounded-lg p-3 space-y-2">
              <Label>{t('cm.components_pms_LaundryTab.urun_ekle')}</Label>
              <div className="flex gap-2">
                <Select value={itemToAdd.code} onValueChange={v => setItemToAdd(p => ({ ...p, code: v }))}>
                  <SelectTrigger className="flex-1"><SelectValue placeholder="Urun secin" /></SelectTrigger>
                  <SelectContent>
                    {activeItems.map(i => <SelectItem key={i.code} value={i.code}>{i.name} ({Number(i.price).toFixed(2)} TL)</SelectItem>)}
                  </SelectContent>
                </Select>
                <Input type="number" min="1" className="w-16" value={itemToAdd.quantity} onChange={e => setItemToAdd(p => ({ ...p, quantity: parseInt(e.target.value) || 1 }))} />
                <Button size="sm" onClick={addItem}><Plus className="w-4 h-4" /></Button>
              </div>
              {orderForm.items.length > 0 && (
                <div className="space-y-1 mt-2">
                  {orderForm.items.map((item, i) => (
                    <div key={i} className="flex items-center justify-between text-xs bg-gray-50 rounded px-2 py-1">
                      <span>{item.name} x{item.quantity}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{item.total?.toFixed(2)} TL</span>
                        <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-red-500" onClick={() => removeItem(i)}>x</Button>
                      </div>
                    </div>
                  ))}
                  <div className="flex justify-between text-sm font-bold pt-1 border-t">
                    <span>{t('cm.components_pms_LaundryTab.toplam')}</span>
                    <span>{orderTotal.toFixed(2)} TL</span>
                  </div>
                </div>
              )}
            </div>
            <div><Label>Not</Label><Input value={orderForm.notes} onChange={e => setOrderForm(p => ({ ...p, notes: e.target.value }))} placeholder={t('cm.components_pms_LaundryTab.ozel_talimatlar')} /></div>
            <Button onClick={submitOrder} disabled={loading} className="w-full">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_LaundryTab.siparis_olustur')}{orderTotal.toFixed(2)} TL)
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LaundryTab;
