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
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
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

const EMPTY_ITEM = { name: '', price: '', currency: '', tax_percent: '', category: 'drink', active: true, inventory_product_id: '', inventory_source: '' };
const STOCK_LABELS = {
  depleted: 'Stok işlendi', already_applied: 'Stok işlendi', pending: 'Stok aktarımı bekliyor', pending_retry: 'Stok yeniden denenmeli',
  unlinked: 'Stok ürünü bağlı değil', legacy_untracked: 'Eski kayıt — stok mutabakatı gerekli',
  insufficient_stock: 'Stok yetersiz', product_not_found: 'Stok ürünü bulunamadı',
  inactive_product: 'Stok ürünü pasif', invalid_stock_quantity: 'Stok miktarı geçersiz',
};

// `/pms/rooms` returns a bare array. Accept the two historic wrapped shapes as
// well, so a rollout behind a cache/proxy cannot silently leave the room picker
// empty again.
export const roomsFromResponse = (data) => {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.rooms)) return data.rooms;
  if (Array.isArray(data?.items)) return data.items;
  return [];
};

const CATALOG_ROLES = new Set(['admin', 'super_admin', 'supervisor']);
const CONSUME_ROLES = new Set([...CATALOG_ROLES, 'front_desk', 'housekeeping', 'staff']);

export const minibarCapabilities = (user) => ({
  canManageCatalog: Boolean(user?.is_super_admin) || CATALOG_ROLES.has(user?.role),
  canConsume: Boolean(user?.is_super_admin) || CONSUME_ROLES.has(user?.role),
});

const pendingStorageKey = user => `syroce:minibar:pending:${user?.tenant_id || ''}:${user?.id || ''}`;
const readPending = key => {
  try {
    const value = sessionStorage.getItem(key);
    if (!value) return {};
    const request = JSON.parse(value);
    if (typeof request.room_id !== 'string' || !request.room_id || typeof request.idempotency_key !== 'string' ||
      !request.idempotency_key || !Array.isArray(request.lines) || !request.lines.length ||
      request.lines.some(line => typeof line.item_id !== 'string' || !line.item_id || !Number.isInteger(line.quantity) || line.quantity < 1)) {
      throw new Error('invalid pending request');
    }
    return { request };
  } catch {
    return { error: 'Önceki minibar isteği güvenle okunamadı. Yeni tüketim göndermeden işlem geçmişini yetkiliyle doğrulayın.' };
  }
};

const MinibarWorkspace = ({ user }) => {
  useTranslation();
  const currency = cachedTenantCurrency();
  const { canManageCatalog, canConsume } = minibarCapabilities(user);
  const [tab, setTab] = useState('consume');

  // Katalog
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);
  const [showItemDialog, setShowItemDialog] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [itemForm, setItemForm] = useState(EMPTY_ITEM);
  const [inventoryProducts, setInventoryProducts] = useState([]);
  const [loadErrors, setLoadErrors] = useState({});
  const [stockDialog, setStockDialog] = useState(null);
  const [stockBindings, setStockBindings] = useState({});
  const [stockReason, setStockReason] = useState('');
  const [stockBusy, setStockBusy] = useState(false);

  // Tüketim
  const [rooms, setRooms] = useState([]);
  const [loadingRooms, setLoadingRooms] = useState(true);
  const [roomsError, setRoomsError] = useState('');
  const storageKey = pendingStorageKey(user);
  const [restored] = useState(() => readPending(storageKey));
  const [storageError, setStorageError] = useState(restored.error || '');
  const [selectedRoom, setSelectedRoom] = useState(restored.request?.room_id || '');
  const [cart, setCart] = useState(() => Object.fromEntries((restored.request?.lines || []).map(line => [line.item_id, line.quantity])));
  const [submitting, setSubmitting] = useState(false);
  const [consumptions, setConsumptions] = useState([]);
  const [lateCharges, setLateCharges] = useState([]);
  // Stabil idempotency anahtarı: bir gönderim denemesi için bir kez üretilir,
  // başarıyla işlenene kadar (retry'larda) yeniden kullanılır → çift faturalama yok.
  const pendingKeyRef = useRef(restored.request || null);
  const [pendingRetry, setPendingRetry] = useState(Boolean(restored.request));
  const consumptionRequestRef = useRef(0);
  const setLoadError = (name, message = '') => setLoadErrors(previous => ({ ...previous, [name]: message }));

  const activeItems = items.filter((i) => i.active);

  const loadItems = useCallback(async () => {
    setLoadingItems(true);
    try {
      const res = await axios.get('/minibar/items', { params: { include_inactive: true } });
      setItems(res.data?.items || []);
      setLoadError('items');
    } catch (e) {
      console.error('Minibar items load error', e);
      setLoadError('items', 'Minibar kataloğu doğrulanamadı. Yenile ile tekrar deneyin.');
    } finally {
      setLoadingItems(false);
    }
  }, []);

  const loadRooms = useCallback(async () => {
    setLoadingRooms(true);
    setRoomsError('');
    try {
      const res = await axios.get('/pms/rooms');
      setRooms(roomsFromResponse(res.data));
    } catch (e) {
      console.error('Rooms load error', e);
      setRooms([]);
      setRoomsError('Odalar yüklenemedi. Bağlantıyı kontrol edip yeniden deneyin.');
    } finally {
      setLoadingRooms(false);
    }
  }, []);

  const loadLateCharges = useCallback(async () => {
    try {
      const res = await axios.get('/minibar/late-charges');
      setLateCharges(res.data?.late_charges || []);
      setLoadError('late');
    } catch (e) {
      console.error('Late charges load error', e);
      setLoadError('late', 'Geç ücret kayıtları yüklenemedi; liste tamamlanmış sayılmaz.');
    }
  }, []);

  const loadConsumptions = useCallback(async (roomId) => {
    const request = ++consumptionRequestRef.current;
    try {
      const params = roomId ? { room_id: roomId } : {};
      const res = await axios.get('/minibar/consumptions', { params });
      if (request === consumptionRequestRef.current) {
        setConsumptions(res.data?.consumptions || []);
        setLoadError('consumptions');
      }
    } catch (e) {
      console.error('Consumptions load error', e);
      if (request === consumptionRequestRef.current) setLoadError('consumptions', 'Tüketim ve stok durumu doğrulanamadı. Yenile ile tekrar deneyin.');
    }
  }, []);

  const loadInventoryProducts = useCallback(async () => {
    if (!canManageCatalog) return;
    try {
      const response = await axios.get('/minibar/inventory-products');
      setInventoryProducts(response.data?.items || []);
      setLoadError('inventory');
    } catch {
      setLoadError('inventory', 'Merkezî stok ürünleri yüklenemedi; stok bağlantısını değiştirmeyin.');
    }
  }, [canManageCatalog]);

  useEffect(() => {
    loadItems();
    loadRooms();
    loadLateCharges();
    loadConsumptions();
    loadInventoryProducts();
  }, [loadItems, loadRooms, loadLateCharges, loadConsumptions, loadInventoryProducts]);

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
      currency: item.currency || currency,
      tax_percent: item.tax_rate == null ? '' : String(item.tax_rate * 100),
      category: item.category || 'drink',
      active: item.active !== false,
      inventory_product_id: item.inventory_product_id || '',
      inventory_source: item.inventory_source || (item.inventory_product_id ? 'legacy' : ''),
    });
    setShowItemDialog(true);
  };

  const saveItem = async () => {
    if (!itemForm.name.trim()) {
      toast.error('Ürün adı zorunlu');
      return;
    }
    const price = parseFloat(itemForm.price);
    if (!Number.isFinite(price) || price < 0) {
      toast.error('Geçerli bir fiyat girin');
      return;
    }
    const taxPercent = Number(itemForm.tax_percent);
    if (itemForm.tax_percent === '' || !Number.isFinite(taxPercent) || taxPercent < 0 || taxPercent > 100) {
      toast.error('KDV oranını doğrulayın; bilinmeyen vergi sıfır sayılmaz');
      return;
    }
    const body = {
      name: itemForm.name.trim(),
      price,
      currency: itemForm.currency || currency,
      tax_rate: taxPercent / 100,
      category: itemForm.category,
      active: itemForm.active,
      inventory_product_id: itemForm.inventory_product_id.trim() || null,
      inventory_source: itemForm.inventory_product_id ? itemForm.inventory_source : null,
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
      toast.error('İşlem Hatası: ' + (e.response?.data?.detail || e.message));
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
      toast.error('İşlem Hatası: ' + (e.response?.data?.detail || e.message));
    }
  };

  // ── Tüketim işlemleri ──
  const cartCount = Object.values(cart).reduce((a, b) => a + b, 0);
  const cartTotal = activeItems.reduce(
    (sum, it) => sum + (cart[it.id] || 0) * (it.price || 0),
    0,
  );
  const selectedItems = activeItems.filter(item => (cart[item.id] || 0) > 0);
  const cartCurrencies = [...new Set(selectedItems.map(item => item.currency).filter(Boolean))];
  const cartCurrency = cartCurrencies.length === 1 && selectedItems.every(item => item.currency) ? cartCurrencies[0] : null;

  const setQty = (itemId, qty) => {
    setCart((prev) => {
      const next = { ...prev };
      if (qty <= 0) delete next[itemId];
      else next[itemId] = qty;
      return next;
    });
  };

  const submitConsumption = async () => {
    if (!canConsume || submitting || storageError) return;
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
    if (!pendingKeyRef.current && (!cartCurrency || selectedItems.some(item => item.tax_rate == null))) {
      toast.error('Ürünlerin para birimi ve KDV oranını doğrulayın; farklı para birimlerini ayrı aktarın');
      return;
    }
    if (!pendingKeyRef.current) {
      pendingKeyRef.current = {
        room_id: selectedRoom, lines,
        idempotency_key: (globalThis.crypto?.randomUUID?.() ?? `minibar-${selectedRoom}-${Date.now()}-${Math.random()}`),
      };
    }
    // Persist BEFORE the HTTP write. A reload after a lost response must replay
    // this exact request, even if the catalog has changed in the meantime.
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(pendingKeyRef.current));
    } catch {
      setStorageError('Tüketim isteği güvenle saklanamadı; çift ücret riskini önlemek için gönderilmedi.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await axios.post('/minibar/consume', pendingKeyRef.current);
      if (res.data?.posted_to_folio) {
        toast.success('Tüketim folio\'ya işlendi');
      } else {
        toast.warning('Folio açık değil — late-charge kaydına yönlendirildi');
      }
      if (res.data?.stock_complete === false || (res.data?.stock || []).some(row => !['depleted', 'already_applied'].includes(row.status))) {
        toast.warning('Tüketim kaydedildi fakat bazı stok hareketleri tamamlanamadı; stok kayıtlarını inceleyin.');
      }
      sessionStorage.removeItem(storageKey);
      pendingKeyRef.current = null;
      setPendingRetry(false);
      setCart({});
      loadConsumptions(selectedRoom);
      loadLateCharges();
      loadItems();
    } catch (e) {
      // Anahtarı KORU: kullanıcı tekrar denerse aynı key gider, backend çift yazmaz.
      if ([400, 403, 404, 409, 422].includes(e.response?.status)) {
        try {
          sessionStorage.removeItem(storageKey);
          pendingKeyRef.current = null;
          setPendingRetry(false);
        } catch { setPendingRetry(true); }
      } else setPendingRetry(true);
      toast.error('İşlem Hatası: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSubmitting(false);
    }
  };

  const openStockDialog = (consumption) => {
    setStockDialog(consumption);
    setStockReason('');
    setStockBindings({});
  };

  const repairStock = async () => {
    if (stockReason.trim().length < 5) return toast.error('En az 5 karakterlik işlem gerekçesi yazın');
    const missing = (stockDialog.stock || []).filter(job => ['unlinked', 'legacy_untracked'].includes(job.status));
    const bindings = missing.map(job => {
      const product = inventoryProducts.find(p => `${p.inventory_source}:${p.id}` === stockBindings[job.line_no]);
      return product && { line_no: job.line_no, inventory_product_id: product.id, inventory_source: product.inventory_source };
    });
    if (bindings.some(binding => !binding)) return toast.error('Her eksik satır için stok ürünü seçin');
    setStockBusy(true);
    try {
      const path = bindings.length ? 'reconcile-stock' : 'retry-stock';
      const response = await axios.post(`/minibar/consumptions/${stockDialog.id}/${path}`, {
        reason: stockReason.trim(), ...(bindings.length ? { bindings } : {}),
      });
      const complete = Boolean(response.data?.stock?.length) && response.data.stock.every(job => ['depleted', 'already_applied'].includes(job.status));
      if (complete) toast.success('Stok hareketleri tamamlandı; yeni folyo borcu oluşturulmadı');
      else toast.warning('Bazı stok hareketleri bekliyor. Miktar ve ürün bağlantılarını kontrol edin.');
      setStockDialog(null);
      loadConsumptions(selectedRoom);
      loadInventoryProducts();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Stok işlemi doğrulanamadı; aynı işlem güvenle yeniden denenebilir');
    } finally { setStockBusy(false); }
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
              onClick={() => { loadItems(); loadRooms(); loadLateCharges(); loadConsumptions(selectedRoom); loadInventoryProducts(); }}
            >
              <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
            </Button>
          }
        />
        {Object.entries(loadErrors).filter(([, message]) => message).map(([name, message]) => (
          <p key={name} role="alert" className="text-sm text-destructive">{message}</p>
        ))}
        {storageError && <p role="alert" className="text-sm text-destructive">{storageError}</p>}
        {pendingRetry && <p role="alert" className="text-sm text-destructive">
          Son tüketim isteğinin sonucu doğrulanamadı. Oda/sepet korunuyor; aynı isteği yeniden gönderin, yeni işlem oluşturulmaz.
        </p>}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={Boxes} label="Aktif Ürün" value={activeItems.length} intent="info" />
          <KpiCard icon={Receipt} label="Toplam Tüketim Kaydı" value={consumptions.length} intent="default" />
          <KpiCard icon={PackageCheck} label="Sepet Adedi" value={cartCount} intent="success" />
          <KpiCard icon={AlertTriangle} label="Late-Charge" value={lateCharges.length} intent={lateCharges.length ? 'warning' : 'default'} />
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="consume" data-testid="tab-consume">Tüketim Gir</TabsTrigger>
            {canManageCatalog && <TabsTrigger value="catalog" data-testid="tab-catalog">Katalog</TabsTrigger>}
          </TabsList>

          {/* ── Tüketim ── */}
          <TabsContent value="consume" className="space-y-4 mt-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div className="min-w-[220px]">
                <Label className="text-xs">Oda</Label>
                <select
                  value={selectedRoom}
                  onChange={(e) => setSelectedRoom(e.target.value)}
                  disabled={loadingRooms || Boolean(roomsError) || submitting || pendingRetry || !canConsume}
                  className="h-9 w-full border rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  data-testid="minibar-room-select"
                >
                  <option value="">{loadingRooms ? 'Odalar yükleniyor...' : 'Oda seçin...'}</option>
                  {rooms
                    .slice()
                    .sort((a, b) => String(a.room_number).localeCompare(String(b.room_number), 'tr', { numeric: true }))
                    .map((r) => (
                      <option key={r.id} value={r.id}>
                        Oda {r.room_number}{r.room_type ? ` — ${r.room_type}` : ''}
                      </option>
                    ))}
                </select>
                {roomsError && (
                  <p className="mt-1.5 text-xs text-destructive" role="alert">{roomsError}</p>
                )}
                {!loadingRooms && !roomsError && rooms.length === 0 && (
                  <p className="mt-1.5 text-xs text-muted-foreground">Seçilebilir oda bulunamadı.</p>
                )}
              </div>
            </div>

            {activeItems.length === 0 ? (
              <Card className="p-12 text-center">
                <Wine className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500 mb-4">Henüz minibar ürünü tanımlanmamış</p>
                {canManageCatalog && (
                  <Button size="sm" onClick={() => setTab('catalog')}>
                    <Plus className="w-4 h-4 mr-1.5" /> Katalog Oluştur
                  </Button>
                )}
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
                            {CATEGORY_LABELS[it.category] || it.category} · {formatCurrency(it.price, it.currency || currency)}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => setQty(it.id, qty - 1)}
                            disabled={qty <= 0 || submitting || pendingRetry || !canConsume}
                            aria-label={`${it.name} miktarını azalt`}
                            title="Miktarı azalt"
                          >
                            <Minus className="w-3.5 h-3.5" />
                          </Button>
                          <span className="w-6 text-center text-sm tabular-nums">{qty}</span>
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => setQty(it.id, qty + 1)}
                            disabled={submitting || pendingRetry || !canConsume}
                            aria-label={`${it.name} miktarını artır`}
                            title="Miktarı artır"
                          >
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
                    <span className="font-semibold">{pendingRetry ? 'Önceki tüketim isteği doğrulanıyor' : cartCurrency ? formatCurrency(cartTotal, cartCurrency) : 'Para birimlerini ayrı aktarın'}</span>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setCart({})} disabled={submitting || pendingRetry}>Temizle</Button>
                    <Button size="sm" onClick={submitConsumption} disabled={submitting || !selectedRoom || !canConsume || Boolean(storageError) || (!pendingRetry && Boolean(loadErrors.items))} data-testid="minibar-submit">
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
                            Oda {c.room_number} · {formatCurrency(c.total, c.currency || currency)}
                          </div>
                          <div className="text-xs text-gray-500 truncate">
                            {(c.lines || []).map((l) => `${l.item_name} x${l.quantity}`).join(', ')}
                          </div>
                          <div className="text-xs text-muted-foreground" data-testid={`minibar-stock-${c.id}`}>
                            {(c.stock || []).map(job => `${job.item_name || 'Ürün'}: ${STOCK_LABELS[job.status] || 'Stok doğrulanamadı'}`).join(' · ')}
                            {c.stock_complete === false && canManageCatalog && <Button size="sm" variant="outline" className="ml-2 h-7"
                              onClick={() => openStockDialog(c)}>Stok işlemini tamamla</Button>}
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
          {canManageCatalog && <TabsContent value="catalog" className="space-y-4 mt-4">
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
                          {CATEGORY_LABELS[it.category] || it.category} · {formatCurrency(it.price, it.currency || currency)}
                          {it.inventory_product_id ? ' · stok bağlı' : ' · stok takibi bağlı değil'}
                        </div>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Button
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => openEditItem(it)}
                          aria-label={`${it.name} ürününü düzenle`}
                          title="Ürünü düzenle"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        {it.active && (
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-8 w-8 text-red-600"
                            onClick={() => deactivateItem(it)}
                            aria-label={`${it.name} ürününü pasifleştir`}
                            title="Ürünü pasifleştir"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>}
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
                <Label className="text-xs">KDV dahil fiyat ({itemForm.currency || currency})</Label>
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
              <Label className="text-xs">Para birimi</Label>
              <select value={itemForm.currency || currency} onChange={(e) => setItemForm({ ...itemForm, currency: e.target.value })} className="h-9 w-full border rounded-md px-3 text-sm">
                {['TRY', 'USD', 'EUR', 'GBP', 'CHF'].map(code => <option key={code}>{code}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs">KDV oranı (%)</Label>
              <Input type="number" min="0" max="100" step="0.01" value={itemForm.tax_percent} onChange={(e) => setItemForm({ ...itemForm, tax_percent: e.target.value })} />
              <p className="text-xs text-muted-foreground mt-1">Ürün ve folyo aynı para biriminde olmalıdır. Full comp misafirin tüketimi kaydedilir, borç oluşmaz.</p>
            </div>
            <div>
              <Label htmlFor="minibar-inventory-product" className="text-xs">Merkezî stok ürünü</Label>
              <select id="minibar-inventory-product" disabled={Boolean(loadErrors.inventory)} className="h-9 w-full border rounded-md px-3 text-sm"
                value={itemForm.inventory_product_id ? `${itemForm.inventory_source}:${itemForm.inventory_product_id}` : ''}
                onChange={event => {
                  const product = inventoryProducts.find(p => `${p.inventory_source}:${p.id}` === event.target.value);
                  setItemForm({ ...itemForm, inventory_product_id: product?.id || '', inventory_source: product?.inventory_source || '' });
                }}>
                <option value="">Stok takibi yok</option>
                {inventoryProducts.map(product => <option key={`${product.inventory_source}:${product.id}`} value={`${product.inventory_source}:${product.id}`}>
                  {product.name} · {product.quantity ?? 'Miktar bilinmiyor'} {product.unit} {product.inventory_source === 'legacy' ? '(eski mobil stok)' : '(merkezî depo)'}
                </option>)}
              </select>
              <p className="text-xs text-muted-foreground mt-1">Bağlantı sonraki tüketimlerde kullanılır. Eski kayıtlar gerekçeli stok mutabakatıyla tamamlanır; folyo yeniden borçlandırılmaz.</p>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={itemForm.active} onChange={(e) => setItemForm({ ...itemForm, active: e.target.checked })} />
              Aktif (tüketim ekranında görünür)
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowItemDialog(false)}>Vazgeç</Button>
            <Button onClick={saveItem} disabled={Boolean(loadErrors.inventory)}>{editItem ? 'Kaydet' : 'Ekle'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(stockDialog)} onOpenChange={open => { if (!open && !stockBusy) setStockDialog(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Minibar stok mutabakatı</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Yalnız stok aktarılır; yeni ücret veya ödeme oluşmaz. Eski takip edilmemiş satırlar bugünkü açık iş gününde, gerekçenizle kaydedilir.</p>
          {(stockDialog?.stock || []).filter(job => ['unlinked', 'legacy_untracked'].includes(job.status)).map(job => (
            <div key={job.line_no}>
              <Label htmlFor={`stock-binding-${job.line_no}`}>{job.item_name || 'Ürün'} × {job.quantity}</Label>
              <select id={`stock-binding-${job.line_no}`} className="h-9 w-full border rounded-md px-3 text-sm" disabled={stockBusy || Boolean(loadErrors.inventory)}
                value={stockBindings[job.line_no] || ''} onChange={event => setStockBindings({ ...stockBindings, [job.line_no]: event.target.value })}>
                <option value="">Stok ürünü seçin</option>
                {inventoryProducts.map(product => <option key={`${product.inventory_source}:${product.id}`} value={`${product.inventory_source}:${product.id}`}>
                  {product.name} · {product.quantity ?? 'Miktar bilinmiyor'} {product.unit}
                </option>)}
              </select>
            </div>
          ))}
          <Label htmlFor="minibar-stock-reason">İşlem gerekçesi</Label>
          <Input id="minibar-stock-reason" value={stockReason} onChange={event => setStockReason(event.target.value)} disabled={stockBusy} />
          <DialogFooter><Button variant="outline" disabled={stockBusy} onClick={() => setStockDialog(null)}>Vazgeç</Button>
            <Button onClick={repairStock} disabled={stockBusy || Boolean(loadErrors.inventory)}>{stockBusy ? 'İşleniyor...' : 'Stok işlemini tamamla'}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

// A property/account switch must never reuse another actor's pending request.
const MinibarPage = ({ user }) => <MinibarWorkspace key={pendingStorageKey(user)} user={user} />;
export default MinibarPage;
