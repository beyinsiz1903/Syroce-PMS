import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { confirmDialog } from '@/lib/dialogs';
import {
  Wine, Plus, RefreshCw, Trash2, Pencil, Receipt,
  Boxes, PackageCheck, AlertTriangle, Minus,
} from 'lucide-react';

const CATEGORY_OPTIONS = [
  { value: 'drink', label: 'İçecek' },
  { value: 'alcohol', label: 'Alkollü İçecek' },
  { value: 'snack', label: 'Atıştırmalık' },
  { value: 'other', label: 'Diğer' },
];
const CATEGORY_LABELS = Object.fromEntries(CATEGORY_OPTIONS.map((c) => [c.value, c.label]));

const EMPTY_ITEM = { name: '', price: '', category: 'drink', active: true, inventory_product_id: '' };

const MinibarPage = () => {
  useTranslation();
  const [tab, setTab] = useState('consume');

  // Katalog
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);
  const [showItemDialog, setShowItemDialog] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [itemForm, setItemForm] = useState(EMPTY_ITEM);

  // Tüketim
  const [rooms, setRooms] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState('');
  const [cart, setCart] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [consumptions, setConsumptions] = useState([]);
  const [lateCharges, setLateCharges] = useState([]);
  // Stabil idempotency anahtarı: bir gönderim denemesi için bir kez üretilir,
  // başarıyla işlenene kadar (retry'larda) yeniden kullanılır → çift faturalama yok.
  const pendingKeyRef = useRef(null);

  const activeItems = items.filter((i) => i.active);

  const loadItems = useCallback(async () => {
    setLoadingItems(true);
    try {
      const res = await axios.get('/minibar/items', { params: { include_inactive: true } });
      setItems(res.data?.items || []);
    } catch (e) {
      console.error('Minibar items load error', e);
    } finally {
      setLoadingItems(false);
    }
  }, []);

  const loadRooms = useCallback(async () => {
    try {
      const res = await axios.get('/pms/rooms');
      setRooms(res.data?.rooms || []);
    } catch (e) {
      console.error('Rooms load error', e);
    }
  }, []);

  const loadLateCharges = useCallback(async () => {
    try {
      const res = await axios.get('/minibar/late-charges');
      setLateCharges(res.data?.late_charges || []);
    } catch (e) {
      console.error('Late charges load error', e);
    }
  }, []);

  const loadConsumptions = useCallback(async (roomId) => {
    try {
      const params = roomId ? { room_id: roomId } : {};
      const res = await axios.get('/minibar/consumptions', { params });
      setConsumptions(res.data?.consumptions || []);
    } catch (e) {
      console.error('Consumptions load error', e);
    }
  }, []);

  useEffect(() => {
    loadItems();
    loadRooms();
    loadLateCharges();
    loadConsumptions();
  }, [loadItems, loadRooms, loadLateCharges, loadConsumptions]);

  useEffect(() => {
    loadConsumptions(selectedRoom);
  }, [selectedRoom, loadConsumptions]);

  // ── Katalog işlemleri ──
  const openCreateItem = () => {
    setEditItem(null);
    setItemForm(EMPTY_ITEM);
    setShowItemDialog(true);
  };

  const openEditItem = (item) => {
    setEditItem(item);
    setItemForm({
      name: item.name || '',
      price: String(item.price ?? ''),
      category: item.category || 'drink',
      active: item.active !== false,
      inventory_product_id: item.inventory_product_id || '',
    });
    setShowItemDialog(true);
  };

  const saveItem = async () => {
    if (!itemForm.name.trim()) {
      toast.error('Ürün adı zorunlu');
      return;
    }
    const price = parseFloat(itemForm.price);
    if (Number.isNaN(price) || price < 0) {
      toast.error('Geçerli bir fiyat girin');
      return;
    }
    const body = {
      name: itemForm.name.trim(),
      price,
      category: itemForm.category,
      active: itemForm.active,
      inventory_product_id: itemForm.inventory_product_id.trim() || null,
    };
    try {
      if (editItem) {
        await axios.put(`/minibar/items/${editItem.id}`, body);
        toast.success('Ürün güncellendi');
      } else {
        await axios.post('/minibar/items', body);
        toast.success('Ürün eklendi');
      }
      setShowItemDialog(false);
      loadItems();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
  };

  const deactivateItem = async (item) => {
    const ok = await confirmDialog({
      title: 'Ürünü pasifleştir',
      message: `"${item.name}" minibar listesinden kaldırılacak (geçmiş kayıtlar korunur). Devam edilsin mi?`,
      confirmText: 'Pasifleştir',
      cancelText: 'Vazgeç',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await axios.delete(`/minibar/items/${item.id}`);
      toast.success('Ürün pasifleştirildi');
      loadItems();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
  };

  // ── Tüketim işlemleri ──
  const cartCount = Object.values(cart).reduce((a, b) => a + b, 0);
  const cartTotal = activeItems.reduce(
    (sum, it) => sum + (cart[it.id] || 0) * (it.price || 0),
    0,
  );

  const setQty = (itemId, qty) => {
    setCart((prev) => {
      const next = { ...prev };
      if (qty <= 0) delete next[itemId];
      else next[itemId] = qty;
      return next;
    });
  };

  const submitConsumption = async () => {
    if (!selectedRoom) {
      toast.error('Önce oda seçin');
      return;
    }
    const lines = Object.entries(cart)
      .filter(([, q]) => q > 0)
      .map(([item_id, quantity]) => ({ item_id, quantity }));
    if (lines.length === 0) {
      toast.error('En az bir ürün ekleyin');
      return;
    }
    if (!pendingKeyRef.current) {
      pendingKeyRef.current =
        (crypto?.randomUUID?.() ?? `minibar-${selectedRoom}-${Date.now()}-${Math.random()}`);
    }
    setSubmitting(true);
    try {
      const res = await axios.post('/minibar/consume', {
        room_id: selectedRoom,
        lines,
        idempotency_key: pendingKeyRef.current,
      });
      if (res.data?.posted_to_folio) {
        toast.success('Tüketim folio\'ya işlendi');
      } else {
        toast.warning('Folio açık değil — late-charge kaydına yönlendirildi');
      }
      pendingKeyRef.current = null;
      setCart({});
      loadConsumptions(selectedRoom);
      loadLateCharges();
      loadItems();
    } catch (e) {
      // Anahtarı KORU: kullanıcı tekrar denerse aynı key gider, backend çift yazmaz.
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSubmitting(false);
    }
  };

  const fmt = (n) => Number(n || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <>
      <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto" data-testid="minibar-page">
        <PageHeader
          icon={Wine}
          iconClassName="text-amber-600"
          title="Minibar"
          subtitle="Oda minibar tüketimini folio'ya işleyin ve ürün kataloğunu yönetin"
          actions={
            <Button
              variant="outline"
              size="sm"
              onClick={() => { loadItems(); loadRooms(); loadLateCharges(); loadConsumptions(selectedRoom); }}
            >
              <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
            </Button>
          }
        />

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={Boxes} label="Aktif Ürün" value={activeItems.length} intent="info" />
          <KpiCard icon={Receipt} label="Toplam Tüketim Kaydı" value={consumptions.length} intent="default" />
          <KpiCard icon={PackageCheck} label="Sepet Adedi" value={cartCount} intent="success" />
          <KpiCard icon={AlertTriangle} label="Late-Charge" value={lateCharges.length} intent={lateCharges.length ? 'warning' : 'default'} />
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="consume" data-testid="tab-consume">Tüketim Gir</TabsTrigger>
            <TabsTrigger value="catalog" data-testid="tab-catalog">Katalog</TabsTrigger>
          </TabsList>

          {/* ── Tüketim ── */}
          <TabsContent value="consume" className="space-y-4 mt-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div className="min-w-[220px]">
                <Label className="text-xs">Oda</Label>
                <select
                  value={selectedRoom}
                  onChange={(e) => setSelectedRoom(e.target.value)}
                  className="h-9 w-full border rounded-md px-3 text-sm"
                  data-testid="minibar-room-select"
                >
                  <option value="">Oda seçin...</option>
                  {rooms
                    .slice()
                    .sort((a, b) => String(a.room_number).localeCompare(String(b.room_number), 'tr', { numeric: true }))
                    .map((r) => (
                      <option key={r.id} value={r.id}>
                        Oda {r.room_number}{r.room_type ? ` — ${r.room_type}` : ''}
                      </option>
                    ))}
                </select>
              </div>
            </div>

            {activeItems.length === 0 ? (
              <Card className="p-12 text-center">
                <Wine className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500 mb-4">Henüz minibar ürünü tanımlanmamış</p>
                <Button size="sm" onClick={() => setTab('catalog')}>
                  <Plus className="w-4 h-4 mr-1.5" /> Katalog Oluştur
                </Button>
              </Card>
            ) : (
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {activeItems.map((it) => {
                  const qty = cart[it.id] || 0;
                  return (
                    <Card key={it.id} className={qty ? 'border-amber-300 bg-amber-50/40' : ''}>
                      <CardContent className="p-3 flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-medium truncate">{it.name}</div>
                          <div className="text-xs text-gray-500">
                            {CATEGORY_LABELS[it.category] || it.category} · {fmt(it.price)} TL
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setQty(it.id, qty - 1)} disabled={qty <= 0}>
                            <Minus className="w-3.5 h-3.5" />
                          </Button>
                          <span className="w-6 text-center text-sm tabular-nums">{qty}</span>
                          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setQty(it.id, qty + 1)}>
                            <Plus className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}

            {cartCount > 0 && (
              <Card className="sticky bottom-3 border-amber-300">
                <CardContent className="p-3 flex items-center justify-between gap-3">
                  <div className="text-sm">
                    <span className="font-semibold">{cartCount}</span> ürün ·{' '}
                    <span className="font-semibold">{fmt(cartTotal)} TL</span>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setCart({})}>Temizle</Button>
                    <Button size="sm" onClick={submitConsumption} disabled={submitting || !selectedRoom} data-testid="minibar-submit">
                      <Receipt className="w-4 h-4 mr-1.5" /> {submitting ? 'İşleniyor...' : 'Folio\'ya İşle'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Son Tüketimler</h3>
              {consumptions.length === 0 ? (
                <p className="text-sm text-gray-400 py-4">Kayıt yok</p>
              ) : (
                <div className="grid gap-2">
                  {consumptions.slice(0, 20).map((c) => (
                    <Card key={c.id}>
                      <CardContent className="p-3 flex items-center justify-between gap-3 text-sm">
                        <div className="min-w-0">
                          <div className="font-medium">
                            Oda {c.room_number} · {fmt(c.total)} TL
                          </div>
                          <div className="text-xs text-gray-500 truncate">
                            {(c.lines || []).map((l) => `${l.item_name} x${l.quantity}`).join(', ')}
                          </div>
                        </div>
                        <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${
                          c.status === 'posted'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border-amber-200'
                        }`}>
                          {c.status === 'posted' ? 'Folio' : 'Late-charge'}
                        </span>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          </TabsContent>

          {/* ── Katalog ── */}
          <TabsContent value="catalog" className="space-y-4 mt-4">
            <div className="flex justify-end">
              <Button size="sm" onClick={openCreateItem} data-testid="minibar-create-item">
                <Plus className="w-4 h-4 mr-1.5" /> Yeni Ürün
              </Button>
            </div>

            {loadingItems ? (
              <div className="text-center py-12 text-gray-400">Yükleniyor...</div>
            ) : items.length === 0 ? (
              <Card className="p-12 text-center">
                <Boxes className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500 mb-4">Henüz ürün yok</p>
                <Button size="sm" onClick={openCreateItem}>
                  <Plus className="w-4 h-4 mr-1.5" /> İlk Ürünü Ekle
                </Button>
              </Card>
            ) : (
              <div className="grid gap-2">
                {items.map((it) => (
                  <Card key={it.id} className={it.active ? '' : 'opacity-60'}>
                    <CardContent className="p-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-medium truncate">
                          {it.name}
                          {!it.active && <span className="ml-2 text-xs text-gray-400">(pasif)</span>}
                        </div>
                        <div className="text-xs text-gray-500">
                          {CATEGORY_LABELS[it.category] || it.category} · {fmt(it.price)} TL
                          {it.inventory_product_id ? ' · stok bağlı' : ''}
                        </div>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => openEditItem(it)}>
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        {it.active && (
                          <Button variant="outline" size="icon" className="h-8 w-8 text-red-600" onClick={() => deactivateItem(it)}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Ürün ekle/düzenle dialog */}
      <Dialog open={showItemDialog} onOpenChange={setShowItemDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editItem ? 'Ürünü Düzenle' : 'Yeni Minibar Ürünü'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Ürün Adı</Label>
              <Input value={itemForm.name} onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })} placeholder="Örn. Su 0.5L" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Fiyat (TL)</Label>
                <Input type="number" min="0" step="0.01" value={itemForm.price} onChange={(e) => setItemForm({ ...itemForm, price: e.target.value })} />
              </div>
              <div>
                <Label className="text-xs">Kategori</Label>
                <select
                  value={itemForm.category}
                  onChange={(e) => setItemForm({ ...itemForm, category: e.target.value })}
                  className="h-9 w-full border rounded-md px-3 text-sm"
                >
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <Label className="text-xs">Envanter Ürün ID (opsiyonel — stok düşümü için)</Label>
              <Input value={itemForm.inventory_product_id} onChange={(e) => setItemForm({ ...itemForm, inventory_product_id: e.target.value })} placeholder="Boş bırakılabilir" />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={itemForm.active} onChange={(e) => setItemForm({ ...itemForm, active: e.target.checked })} />
              Aktif (tüketim ekranında görünür)
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowItemDialog(false)}>Vazgeç</Button>
            <Button onClick={saveItem}>{editItem ? 'Kaydet' : 'Ekle'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default MinibarPage;
