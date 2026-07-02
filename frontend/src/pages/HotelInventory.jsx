import React, { useState, useEffect } from 'react';
import { runIdle } from '@/lib/idle';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Package, AlertTriangle, TrendingDown, ShoppingCart, RefreshCw, FileText, BarChart3, CheckCircle, Plus, BookOpen, X, ArrowDownCircle, ArrowUpCircle, Edit3, BedDouble, Droplet, Trash2, Play, ArrowRightLeft } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslation } from 'react-i18next';
import { confirmDialog } from '@/lib/dialogs';
import VirtualizedGrid from '@/components/VirtualizedGrid';
const EMPTY_ITEM = {
  name: '',
  sku: '',
  category: 'Oda Ürünleri',
  unit: 'adet',
  quantity: 0,
  unit_cost: 0,
  reorder_level: 0,
  location: '',
  notes: '',
  is_consumable: true
};
const CATEGORIES = ['Oda Ürünleri', 'Banyo Ürünleri', 'Yatak Ürünleri', 'Temizlik', 'F&B', 'Kırtasiye', 'Diğer'];
const UNITS = ['adet', 'kg', 'gr', 'lt', 'ml', 'paket', 'kutu', 'metre'];
const HotelInventory = ({
  user,
  tenant,
  onLogout
}) => {
  const {
    t
  } = useTranslation();
  const navigate = useNavigate();
  const [newItem, setNewItem] = useState(null);
  const [saving, setSaving] = useState(false);
  const [movement, setMovement] = useState(null); // { item, type, quantity, reference, notes }
  const [transfer, setTransfer] = useState(null); // { source_item_id, destination_item_id, quantity, reference, notes }
  const [bulkTransfer, setBulkTransfer] = useState(null); // { source_location, destination_location, reference, notes, lines:[{source_item_id, quantity}] }
  const [kits, setKits] = useState([]);
  const [kitForm, setKitForm] = useState(null); // { name, description, lines: [{item_id, item_name, unit, quantity}] }
  const [applyKit, setApplyKit] = useState(null); // { kit, multiplier, notes }

  const loadKits = async () => {
    try {
      const r = await axios.get('/accounting/setup-kits');
      setKits(r.data.items || []);
    } catch {/* sessiz */}
  };
  const saveKit = async () => {
    const valid = (kitForm.lines || []).filter(l => l.item_id && Number(l.quantity) > 0);
    if (!kitForm.name?.trim() || kitForm.name.trim().length < 2) {
      toast.error('Kit adı en az 2 karakter olmalı');
      return;
    }
    if (!valid.length) {
      toast.error('En az bir kalem ekleyin');
      return;
    }
    setSaving(true);
    try {
      await axios.post('/accounting/setup-kits', {
        name: kitForm.name.trim(),
        description: kitForm.description || '',
        lines: valid.map(l => ({
          item_id: l.item_id,
          item_name: l.item_name,
          unit: l.unit,
          quantity: Number(l.quantity)
        }))
      });
      toast.success('Kit kaydedildi');
      setKitForm(null);
      loadKits();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Kit kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };
  const toggleConsumable = async item => {
    const newVal = !(item.is_consumable !== false);
    try {
      await axios.patch(`/accounting/inventory/${item.id}`, {
        is_consumable: newVal
      });
      toast.success(newVal ? `${item.name}: tek kullanımlık` : `${item.name}: çok kullanımlık (stoktan düşmez)`);
      loadInventory();
    } catch {
      toast.error('Güncellenemedi');
    }
  };
  const deleteKit = async id => {
    if (!(await confirmDialog({
      message: 'Bu kit silinsin mi?',
      variant: 'danger'
    }))) return;
    try {
      await axios.delete(`/accounting/setup-kits/${id}`);
      toast.success('Silindi');
      loadKits();
    } catch (e) {
      toast.error('Silinemedi');
    }
  };
  const runApplyKit = async () => {
    const m = Number(applyKit.multiplier);
    if (!m || m <= 0) {
      toast.error('Geçerli bir adet girin');
      return;
    }
    setSaving(true);
    try {
      const r = await axios.post(`/accounting/setup-kits/${applyKit.kit.id}/apply`, {
        multiplier: m,
        reference: 'room_setup',
        notes: applyKit.notes || ''
      });
      toast.success(`${r.data.kit_name} × ${m} uygulandı (${r.data.applied.length} kalem stoktan düştü)`);
      setApplyKit(null);
      loadInventory();
      loadAlerts();
    } catch (e) {
      const det = e.response?.data?.detail;
      if (typeof det === 'object' && det?.shortages) {
        const list = det.shortages.map(s => s.reason ? `${s.item_name}: ${s.reason}` : `${s.item_name}: gereken ${s.needed}, mevcut ${s.available} ${s.unit || ''}`).join(' · ');
        toast.error(`Yetersiz stok — ${list}`);
      } else {
        toast.error(det || 'Uygulanamadı');
      }
    } finally {
      setSaving(false);
    }
  };
  const openBulkTransfer = () => {
    setBulkTransfer({
      source_location: '',
      destination_location: '',
      reference: '',
      notes: '',
      lines: [{
        source_item_id: '',
        quantity: 1
      }]
    });
  };
  const resolveBulkDest = (sourceItem, destLoc) => {
    if (!sourceItem || !destLoc) return null;
    return inventory.find(x => x.id !== sourceItem.id && x.location === destLoc && (sourceItem.sku && x.sku && x.sku === sourceItem.sku || x.name === sourceItem.name)) || null;
  };
  const saveBulkTransfer = async () => {
    if (!bulkTransfer.source_location) {
      toast.error('Kaynak depo seçin');
      return;
    }
    if (!bulkTransfer.destination_location) {
      toast.error('Hedef depo seçin');
      return;
    }
    if (bulkTransfer.source_location === bulkTransfer.destination_location) {
      toast.error('Kaynak ve hedef depo farklı olmalı');
      return;
    }
    const rawLines = (bulkTransfer.lines || []).filter(l => l.source_item_id);
    if (!rawLines.length) {
      toast.error('En az bir kalem ekleyin');
      return;
    }
    const payloadLines = [];
    for (let i = 0; i < rawLines.length; i += 1) {
      const ln = rawLines[i];
      const src = inventory.find(x => x.id === ln.source_item_id);
      if (!src) {
        toast.error(`Satır ${i + 1}: kaynak ürün bulunamadı`);
        return;
      }
      const qty = Number(ln.quantity);
      if (!qty || qty <= 0) {
        toast.error(`Satır ${i + 1}: geçerli miktar girin`);
        return;
      }
      const dst = resolveBulkDest(src, bulkTransfer.destination_location);
      if (!dst) {
        toast.error(`Satır ${i + 1}: "${src.name}" için hedef depoda eşleşen kalem yok. Önce hedefte aynı SKU/isimle bir kalem oluşturun.`);
        return;
      }
      payloadLines.push({
        source_item_id: src.id,
        destination_item_id: dst.id,
        quantity: qty,
        unit_cost: src.unit_cost || 0
      });
    }
    // Aggregate check per source_item_id
    const sumBySrc = payloadLines.reduce((acc, l) => {
      acc[l.source_item_id] = (acc[l.source_item_id] || 0) + l.quantity;
      return acc;
    }, {});
    for (const [sid, total] of Object.entries(sumBySrc)) {
      const src = inventory.find(x => x.id === sid);
      if (src && total > (src.quantity || 0)) {
        toast.error(`"${src.name}" için kaynakta sadece ${src.quantity} ${src.unit} var (talep: ${total})`);
        return;
      }
    }
    setSaving(true);
    try {
      const r = await axios.post('/accounting/inventory/transfer-bulk', {
        lines: payloadLines,
        reference: bulkTransfer.reference || null,
        notes: bulkTransfer.notes || null
      });
      toast.success(`Transfer belgesi oluşturuldu: ${payloadLines.length} kalem · #${(r.data?.transfer_id || '').slice(0, 8)}`);
      setBulkTransfer(null);
      loadInventory();
      loadAlerts();
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : 'Transfer belgesi gönderilemedi';
      if (status === 409) toast.error(msg);else if (status === 422) toast.error(msg);else if (status === 404) toast.error(msg);else toast.error(msg);
    } finally {
      setSaving(false);
    }
  };
  const openTransfer = (item = null) => {
    setTransfer({
      source_item_id: item?.id || '',
      destination_item_id: '',
      quantity: 1,
      reference: '',
      notes: ''
    });
  };
  const saveTransfer = async () => {
    const qty = Number(transfer.quantity);
    if (!transfer.source_item_id) {
      toast.error('Kaynak ürün seçin');
      return;
    }
    if (!transfer.destination_item_id) {
      toast.error('Hedef ürün seçin');
      return;
    }
    if (transfer.source_item_id === transfer.destination_item_id) {
      toast.error('Kaynak ve hedef farklı olmalı');
      return;
    }
    if (!qty || qty <= 0) {
      toast.error('Geçerli bir miktar girin');
      return;
    }
    const src = inventory.find(x => x.id === transfer.source_item_id);
    const dst = inventory.find(x => x.id === transfer.destination_item_id);
    // Task #75 — block mismatched units client-side. Backend rejects too,
    // but disabling here avoids a useless round-trip and silent data corruption.
    if (src && dst && src.unit && dst.unit && src.unit !== dst.unit) {
      toast.error(`Birimler uyuşmuyor: kaynak ${src.unit}, hedef ${dst.unit}. ` + `Farklı birimler arası transfer şu an desteklenmiyor.`);
      return;
    }
    if (src && qty > (src.quantity || 0)) {
      toast.error(`Kaynakta sadece ${src.quantity} ${src.unit} var`);
      return;
    }
    setSaving(true);
    try {
      await axios.post('/accounting/inventory/transfer', {
        source_item_id: transfer.source_item_id,
        destination_item_id: transfer.destination_item_id,
        quantity: qty,
        unit_cost: src?.unit_cost || 0,
        reference: transfer.reference || null,
        notes: transfer.notes || null
      });
      toast.success(`${qty} ${src?.unit || ''} aktarıldı: ${src?.name || ''}${src?.location ? ` (${src.location})` : ''} → ${dst?.name || ''}${dst?.location ? ` (${dst.location})` : ''}`);
      setTransfer(null);
      loadInventory();
      loadAlerts();
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      if (status === 409) {
        toast.error(typeof detail === 'string' ? detail : 'Kaynakta yeterli stok yok');
      } else if (status === 422) {
        toast.error(typeof detail === 'string' ? detail : 'Kaynak ve hedef ürün farklı olmalı');
      } else {
        toast.error(typeof detail === 'string' ? detail : 'Transfer başarısız');
      }
    } finally {
      setSaving(false);
    }
  };
  const openMovement = (item, type) => {
    setMovement({
      item,
      type,
      quantity: type === 'adjustment' ? item.quantity || 0 : 1,
      reference: '',
      notes: ''
    });
  };
  const saveMovement = async () => {
    const qty = Number(movement.quantity);
    if (!qty || qty < 0) {
      toast.error('Geçerli bir miktar girin');
      return;
    }
    if (movement.type === 'out' && qty > (movement.item.quantity || 0)) {
      toast.error(`Stokta sadece ${movement.item.quantity} ${movement.item.unit} var`);
      return;
    }
    setSaving(true);
    try {
      await axios.post('/accounting/inventory/movement', null, {
        params: {
          item_id: movement.item.id,
          movement_type: movement.type,
          quantity: qty,
          unit_cost: movement.item.unit_cost || 0,
          reference: movement.reference || undefined,
          notes: movement.notes || undefined
        }
      });
      const labels = {
        in: 'eklendi',
        out: 'düşürüldü',
        adjustment: 'güncellendi'
      };
      toast.success(`${movement.item.name} stoğu ${labels[movement.type]}`);
      setMovement(null);
      loadInventory();
      loadAlerts();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Stok hareketi kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };
  const saveNewItem = async () => {
    if (!newItem.name?.trim() || newItem.name.trim().length < 2) {
      toast.error('Ürün adı en az 2 karakter olmalı');
      return;
    }
    setSaving(true);
    try {
      await axios.post('/accounting/inventory', {
        name: newItem.name.trim(),
        category: newItem.category,
        unit: newItem.unit,
        quantity: Number(newItem.quantity) || 0,
        unit_cost: Number(newItem.unit_cost) || 0,
        reorder_level: Number(newItem.reorder_level) || 0,
        sku: newItem.sku || null,
        location: newItem.location || null,
        notes: newItem.notes || null
      });
      toast.success(`${newItem.name} eklendi`);
      setNewItem(null);
      loadInventory();
      loadAlerts();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ürün eklenemedi');
    } finally {
      setSaving(false);
    }
  };
  const createPRForItem = (item, suggestedQty) => {
    navigate('/app/procurement', {
      state: {
        newPRItem: {
          id: item.id || item._id,
          name: item.name || item.item_name,
          sku: item.sku,
          unit: item.unit || 'adet',
          unit_cost: item.unit_cost || 0,
          quantity: item.quantity ?? item.current_stock ?? 0,
          reorder_level: item.reorder_level ?? item.critical_level ?? 0,
          suggested_quantity: suggestedQty,
          department: item.category || ''
        }
      }
    });
  };
  const [inventory, setInventory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalItems: 0,
    lowStockCount: 0,
    totalValue: 0
  });
  useEffect(() => {
    // Mount: birincil envanter listesini hemen çek; ikincil widget'lar
    // (uyarılar + kit'ler) idle anına ertelenir → ilk paint hızlanır.
    loadInventory();
    const cancel = runIdle(() => {
      loadAlerts();
      loadKits();
    }, {
      timeout: 600
    });
    return cancel;
  }, []);
  const loadInventory = async () => {
    try {
      const response = await axios.get('/accounting/inventory');
      setInventory(response.data.items || []);
      setStats({
        totalItems: response.data.items?.length || 0,
        lowStockCount: response.data.low_stock_count || 0,
        totalValue: response.data.total_value || 0
      });
    } catch (error) {
      console.error('Failed to load inventory:', error);
      toast.error('Stok bilgisi yüklenemedi');
    } finally {
      setLoading(false);
    }
  };
  const loadAlerts = async () => {
    try {
      const response = await axios.get('/inventory/alerts');
      setAlerts(response.data.alerts || []);
    } catch (error) {
      console.error('Failed to load alerts:', error);
    }
  };
  const getStockStatus = (quantity, reorderLevel) => {
    if (quantity === 0) return {
      label: 'Tükendi',
      color: 'bg-red-500',
      textColor: 'text-red-700'
    };
    if (quantity <= reorderLevel / 2) return {
      label: 'Kritik',
      color: 'bg-amber-500',
      textColor: 'text-amber-700'
    };
    if (quantity <= reorderLevel) return {
      label: 'Düşük',
      color: 'bg-yellow-500',
      textColor: 'text-yellow-700'
    };
    return {
      label: 'Normal',
      color: 'bg-green-500',
      textColor: 'text-green-700'
    };
  };
  const getCategoryIcon = category => {
    const icons = {
      'Banyo Ürünleri': '',
      'Oda Ürünleri': '',
      'Yatak Ürünleri': '',
      'Temizlik': ''
    };
    return icons[category] || '';
  };
  if (loading) {
    return <>
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      </>;
  }
  return <>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">Otel Ekipman Stok Yönetimi</h1>
            <p className="text-gray-600 mt-1">Oda malzemeleri ve ekipman takibi</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="outline" onClick={() => navigate('/app/stock-rehber')}>
              <BookOpen className="w-4 h-4 mr-2" />
              Nasıl Çalışır?
            </Button>
            <Button variant="outline" onClick={() => {
            loadInventory();
            loadAlerts();
            toast.success('Veriler yenilendi');
          }}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Yenile
            </Button>
            <Button variant="outline" onClick={() => openTransfer()} disabled={inventory.length < 2}>
              <ArrowRightLeft className="w-4 h-4 mr-2" />
              Stok Transferi
            </Button>
            <Button variant="outline" onClick={openBulkTransfer} disabled={inventory.length < 2}>
              <FileText className="w-4 h-4 mr-2" />
              Yeni Transfer Belgesi
            </Button>
            <Button variant="outline" onClick={() => navigate('/hotel-inventory/transfers')} data-testid="transfer-history-link">
              <FileText className="w-4 h-4 mr-2" />
              Transfer Geçmişi
            </Button>
            <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => setNewItem({
            ...EMPTY_ITEM
          })}>
              <Plus className="w-4 h-4 mr-2" />
              Yeni Ürün
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Toplam Ürün</p>
                  <p className="text-2xl font-bold">{stats.totalItems}</p>
                </div>
                <Package className="w-10 h-10 text-blue-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Düşük Stok</p>
                  <p className="text-2xl font-bold text-amber-500">{stats.lowStockCount}</p>
                </div>
                <AlertTriangle className="w-10 h-10 text-amber-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Sipariş Gerekli</p>
                  <p className="text-2xl font-bold text-red-500">{alerts.filter(a => a.priority === 'URGENT').length}</p>
                </div>
                <ShoppingCart className="w-10 h-10 text-red-500" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600">Toplam Değer</p>
                  <p className="text-2xl font-bold">₺{stats.totalValue.toFixed(0)}</p>
                </div>
                <BarChart3 className="w-10 h-10 text-green-500" />
              </div>
            </CardContent>
          </Card>
        </div>

        <Tabs defaultValue="inventory">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="inventory">
              <Package className="w-4 h-4 mr-2" />
              Stok Durumu
            </TabsTrigger>
            <TabsTrigger value="alerts">
              <AlertTriangle className="w-4 h-4 mr-2" />
              Uyarılar ({alerts.length})
            </TabsTrigger>
            <TabsTrigger value="kits">
              <BedDouble className="w-4 h-4 mr-2" />
              Hazırlık Kitleri ({kits.length})
            </TabsTrigger>
            <TabsTrigger value="orders">
              <ShoppingCart className="w-4 h-4 mr-2" />
              Sipariş Önerileri
            </TabsTrigger>
          </TabsList>

          {/* Inventory Tab */}
          <TabsContent value="inventory">
            <Card>
              <CardHeader>
                <CardTitle>Otel Ekipman Stoğu</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <VirtualizedGrid
                    items={inventory}
                    renderCard={(item) => {
                      const status = getStockStatus(item.quantity, item.reorder_level);
                      return (
                        <Card key={item.id} className="hover:shadow-md transition-shadow h-full">
                          <CardContent className="p-4 flex flex-col h-full">
                            <div className="flex justify-between items-start mb-2">
                              <div>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <p className="font-semibold">{item.name}</p>
                                  {item.is_consumable === false && (
                                    <Badge className="bg-indigo-100 text-indigo-700 text-[10px] px-1.5 py-0">
                                      Çok Kullanımlık
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-sm text-gray-600">{item.sku}</p>
                              </div>
                              <Badge className={status.color}>{status.label}</Badge>
                            </div>
                            <div className="space-y-1 text-sm flex-1">
                              <div className="flex justify-between">
                                <span className="text-gray-600">Mevcut:</span>
                                <span className={`font-semibold ${status.textColor}`}>
                                  {item.quantity} {item.unit}
                                </span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-600">Min. Seviye:</span>
                                <span>{item.reorder_level} {item.unit}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-600">Birim Fiyat:</span>
                                <span>₺{item.unit_cost.toFixed(2)}</span>
                              </div>
                              <div className="flex justify-between border-t pt-1 mt-1">
                                <span className="text-gray-600">Toplam Değer:</span>
                                <span className="font-semibold">₺{(item.quantity * item.unit_cost).toFixed(2)}</span>
                              </div>
                            </div>
                            <div className="flex gap-1 mt-3">
                              <Button size="sm" variant="outline" className="flex-1 text-xs px-2 border-amber-300 text-amber-700 hover:bg-amber-50" onClick={() => openMovement(item, 'out')} title="Stoktan düş (kullanım/tüketim)">
                                <ArrowDownCircle className="w-3.5 h-3.5 mr-1" /> Düş
                              </Button>
                              <Button size="sm" variant="outline" className="flex-1 text-xs px-2 border-emerald-300 text-emerald-700 hover:bg-emerald-50" onClick={() => openMovement(item, 'in')} title="Stoğa ekle (manuel giriş)">
                                <ArrowUpCircle className="w-3.5 h-3.5 mr-1" /> Ekle
                              </Button>
                              <Button size="sm" variant="outline" className="text-xs px-2" onClick={() => openMovement(item, 'adjustment')} title="Sayım sonucu düzeltme">
                                <Edit3 className="w-3.5 h-3.5" />
                              </Button>
                              <Button size="sm" variant="outline" className="text-xs px-2 border-sky-300 text-sky-700 hover:bg-sky-50" onClick={() => openTransfer(item)} title="Başka bir depoya/konuma transfer et">
                                <ArrowRightLeft className="w-3.5 h-3.5" />
                              </Button>
                              <Button size="sm" variant="outline" className={`text-xs px-2 ${item.is_consumable === false ? 'border-indigo-300 text-indigo-700' : 'border-gray-300'}`} onClick={() => toggleConsumable(item)} title={item.is_consumable === false ? 'Çok kullanımlık (stoktan düşmez) — değiştir' : 'Tek kullanımlık — değiştir'}>
                                {item.is_consumable === false ? <BedDouble className="w-3.5 h-3.5" /> : <Droplet className="w-3.5 h-3.5" />}
                              </Button>
                            </div>
                            {item.quantity <= item.reorder_level && (
                              <Button size="sm" className="w-full mt-2 bg-blue-600 hover:bg-blue-700" onClick={() => createPRForItem(item, Math.max(1, item.reorder_level * 2 - item.quantity))}>
                                <Plus className="w-3.5 h-3.5 mr-1" />
                                Talep Oluştur
                              </Button>
                            )}
                          </CardContent>
                        </Card>
                      );
                    }}
                    categoryHeader={(category, count) => (
                      <h3 className="font-semibold text-lg flex items-center">
                        <span className="mr-2">{getCategoryIcon(category)}</span>
                        {category} ({count})
                      </h3>
                    )}
                    itemHeight={270}
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Alerts Tab */}
          <TabsContent value="alerts">
            <Card>
              <CardHeader>
                <CardTitle>Stok Uyarıları</CardTitle>
              </CardHeader>
              <CardContent>
                {alerts.length === 0 ? <div className="text-center py-8">
                    <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-3" />
                    <p className="text-lg font-semibold">Tüm stoklar normal seviyede</p>
                    <p className="text-gray-600">Herhangi bir uyarı bulunmamaktadır</p>
                  </div> : <div className="space-y-3">
                    {alerts.map((alert, idx) => <Card key={idx} className={`border-l-4 ${alert.priority === 'URGENT' ? 'border-red-500' : alert.priority === 'HIGH' ? 'border-amber-500' : 'border-yellow-500'}`}>
                        <CardContent className="p-4">
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <AlertTriangle className={`w-5 h-5 ${alert.priority === 'URGENT' ? 'text-red-500' : alert.priority === 'HIGH' ? 'text-amber-500' : 'text-yellow-500'}`} />
                                <p className="font-semibold">{alert.item_name}</p>
                                <Badge variant={alert.priority === 'URGENT' ? 'destructive' : 'default'}>
                                  {alert.priority}
                                </Badge>
                              </div>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                <div>
                                  <p className="text-gray-600">Mevcut Stok:</p>
                                  <p className="font-semibold text-red-600">{alert.current_stock}</p>
                                </div>
                                <div>
                                  <p className="text-gray-600">Kritik Seviye:</p>
                                  <p className="font-semibold">{alert.critical_level}</p>
                                </div>
                                <div>
                                  <p className="text-gray-600">Önerilen Sipariş:</p>
                                  <p className="font-semibold text-blue-600">{alert.suggested_order_quantity}</p>
                                </div>
                                <div>
                                  <p className="text-gray-600">Tahmini Maliyet:</p>
                                  <p className="font-semibold">₺{alert.estimated_cost.toFixed(2)}</p>
                                </div>
                              </div>
                            </div>
                            <Button size="sm" className="ml-4 bg-blue-600 hover:bg-blue-700" onClick={() => createPRForItem({
                        id: alert.item_id || alert.id,
                        name: alert.item_name,
                        sku: alert.sku,
                        unit: alert.unit || 'adet',
                        unit_cost: alert.unit_cost || (alert.estimated_cost && alert.suggested_order_quantity ? alert.estimated_cost / alert.suggested_order_quantity : 0),
                        quantity: alert.current_stock,
                        reorder_level: alert.critical_level
                      }, alert.suggested_order_quantity)}>
                              <Plus className="w-4 h-4 mr-1" />
                              Talep Oluştur
                            </Button>
                          </div>
                        </CardContent>
                      </Card>)}
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Setup Kits Tab */}
          <TabsContent value="kits">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Hazırlık Kitleri</CardTitle>
                    <p className="text-sm text-gray-600 mt-1">
                      Standart ürün setlerini tanımlayın (örn. Standart Oda Kiti). Tek tıkla X oda için stoktan otomatik düşürün.
                    </p>
                  </div>
                  <Button className="bg-indigo-600 hover:bg-indigo-700" onClick={() => setKitForm({
                  name: '',
                  description: '',
                  lines: [{
                    item_id: '',
                    item_name: '',
                    unit: 'adet',
                    quantity: 1
                  }]
                })}>
                    <Plus className="w-4 h-4 mr-1" /> Yeni Kit
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {kits.length === 0 ? <div className="text-center py-12 text-gray-500">
                    <BedDouble className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p className="font-medium">Henüz hazırlık kiti yok</p>
                    <p className="text-sm mt-1">
                      Örnek: <em>Standart Oda Kiti</em> = 2 şampuan + 1 sabun + 2 havlu + 1 diş fırçası seti
                    </p>
                  </div> : <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {kits.map(kit => <Card key={kit.id} className="border hover:shadow-md transition">
                        <CardContent className="p-4">
                          <div className="flex items-start justify-between mb-2">
                            <div>
                              <h3 className="font-semibold flex items-center gap-2">
                                <BedDouble className="w-4 h-4 text-indigo-600" />
                                {kit.name}
                              </h3>
                              {kit.description && <p className="text-xs text-gray-500 mt-0.5">{kit.description}</p>}
                            </div>
                            <Button size="sm" variant="ghost" className="text-red-600 hover:bg-red-50 h-7 w-7 p-0" onClick={() => deleteKit(kit.id)}>
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                          <div className="space-y-1 my-3 text-sm">
                            {kit.lines.map((ln, i) => <div key={ln.id || i} className="flex justify-between border-b border-dashed border-gray-100 py-0.5">
                                <span className="text-gray-700">{ln.item_name}</span>
                                <span className="font-medium text-gray-900">{ln.quantity} {ln.unit}</span>
                              </div>)}
                          </div>
                          <Button size="sm" className="w-full bg-indigo-600 hover:bg-indigo-700" onClick={() => setApplyKit({
                      kit,
                      multiplier: 1,
                      notes: ''
                    })}>
                            <Play className="w-3.5 h-3.5 mr-1" /> Stoktan Düş (Uygula)
                          </Button>
                        </CardContent>
                      </Card>)}
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Orders Tab */}
          <TabsContent value="orders">
            <Card>
              <CardHeader>
                <CardTitle>Sipariş Önerileri</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-gray-600 mb-4">
                  Sistem otomatik olarak düşük stok seviyelerini tespit ederek sipariş önerileri oluşturur.
                </p>
                {alerts.length > 0 ? <div className="space-y-2">
                    <div className="bg-blue-50 p-4 rounded-lg mb-4">
                      <p className="font-semibold mb-2">Toplu Sipariş Özeti</p>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                        <div>
                          <p className="text-gray-600">Toplam Ürün:</p>
                          <p className="font-bold text-lg">{alerts.length}</p>
                        </div>
                        <div>
                          <p className="text-gray-600">Toplam Maliyet:</p>
                          <p className="font-bold text-lg text-blue-600">
                            ₺{alerts.reduce((sum, a) => sum + a.estimated_cost, 0).toFixed(2)}
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-600">Acil Ürün:</p>
                          <p className="font-bold text-lg text-red-600">
                            {alerts.filter(a => a.priority === 'URGENT').length}
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-600">Yüksek Öncelik:</p>
                          <p className="font-bold text-lg text-amber-600">
                            {alerts.filter(a => a.priority === 'HIGH').length}
                          </p>
                        </div>
                      </div>
                    </div>
                    <Button className="w-full bg-blue-600 hover:bg-blue-700" size="lg" onClick={() => navigate('/app/procurement')}>
                      <ShoppingCart className="w-5 h-5 mr-2" />
                      Satın Alma Ekranına Git
                    </Button>
                  </div> : <div className="text-center py-8">
                    <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-3" />
                    <p className="text-lg font-semibold">Sipariş gerekmiyor</p>
                    <p className="text-gray-600">Tüm stoklar yeterli seviyede</p>
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      {/* ── Kit Oluştur Modal ──────────────────────────── */}
      {kitForm && <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setKitForm(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="border-b p-4 bg-indigo-50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <BedDouble className="w-6 h-6 text-indigo-600" />
                <div>
                  <h2 className="font-bold">Yeni Hazırlık Kiti</h2>
                  <p className="text-xs text-gray-600">Standart ürün setini bir kez tanımlayın, sonra tek tıkla uygulayın.</p>
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setKitForm(null)} disabled={saving}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="p-5 space-y-3 overflow-y-auto">
              <div>
                <Label>Kit Adı *</Label>
                <Input autoFocus value={kitForm.name} placeholder="Örn: Standart Oda Kiti" onChange={e => setKitForm({
              ...kitForm,
              name: e.target.value
            })} />
              </div>
              <div>
                <Label>Açıklama</Label>
                <Input value={kitForm.description} placeholder="Örn: Çift kişilik oda check-in hazırlığı" onChange={e => setKitForm({
              ...kitForm,
              description: e.target.value
            })} />
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <Label>Kit İçindeki Ürünler</Label>
                  <Button size="sm" variant="outline" onClick={() => setKitForm({
                ...kitForm,
                lines: [...(kitForm.lines || []), {
                  item_id: '',
                  item_name: '',
                  unit: 'adet',
                  quantity: 1
                }]
              })}>
                    <Plus className="w-3.5 h-3.5 mr-1" /> Kalem Ekle
                  </Button>
                </div>
                <div className="space-y-2">
                  {(kitForm.lines || []).map((ln, idx) => <div key={idx} className="flex gap-2 items-start">
                      <select className="flex-1 border rounded-md p-2 text-sm" value={ln.item_id} onChange={e => {
                  const it = inventory.find(x => x.id === e.target.value);
                  const lines = [...kitForm.lines];
                  lines[idx] = {
                    ...lines[idx],
                    item_id: e.target.value,
                    item_name: it?.name || '',
                    unit: it?.unit || 'adet'
                  };
                  setKitForm({
                    ...kitForm,
                    lines
                  });
                }}>
                        <option value="">— Ürün seç —</option>
                        {inventory.map(it => <option key={it.id} value={it.id}>
                            {it.name} ({it.quantity} {it.unit}){it.is_consumable === false ? ' — çok kullanımlık' : ''}
                          </option>)}
                      </select>
                      <Input type="number" min="0.01" step="0.01" className="w-24" value={ln.quantity} onChange={e => {
                  const lines = [...kitForm.lines];
                  lines[idx] = {
                    ...lines[idx],
                    quantity: e.target.value
                  };
                  setKitForm({
                    ...kitForm,
                    lines
                  });
                }} />
                      <span className="text-sm text-gray-500 self-center w-10">{ln.unit}</span>
                      <Button size="sm" variant="ghost" className="text-red-600 h-9 w-9 p-0" onClick={() => setKitForm({
                  ...kitForm,
                  lines: kitForm.lines.filter((_, i) => i !== idx)
                })}>
                        <X className="w-4 h-4" />
                      </Button>
                    </div>)}
                </div>
                {inventory.length === 0 && <p className="text-xs text-amber-600 mt-2">Önce stok ekranında ürün tanımlamanız gerekir.</p>}
              </div>
            </div>
            <div className="border-t p-4 flex items-center justify-end gap-2 bg-gray-50">
              <Button variant="outline" onClick={() => setKitForm(null)} disabled={saving}>Vazgeç</Button>
              <Button className="bg-indigo-600 hover:bg-indigo-700" onClick={saveKit} disabled={saving}>
                {saving ? 'Kaydediliyor…' : 'Kiti Kaydet'}
              </Button>
            </div>
          </div>
        </div>}

      {/* ── Kit Uygula Modal ───────────────────────────── */}
      {applyKit && <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setApplyKit(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full" onClick={e => e.stopPropagation()}>
            <div className="border-b p-4 bg-indigo-50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Play className="w-6 h-6 text-indigo-600" />
                <div>
                  <h2 className="font-bold">Kit Uygula</h2>
                  <p className="text-xs text-gray-600">{applyKit.kit.name}</p>
                </div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setApplyKit(null)} disabled={saving}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <Label>Kaç oda / kez için uygulanacak?</Label>
                <Input type="number" min="1" autoFocus value={applyKit.multiplier} onChange={e => setApplyKit({
              ...applyKit,
              multiplier: e.target.value
            })} />
              </div>
              {(() => {
            const m = Number(applyKit.multiplier) || 0;
            const consumables = applyKit.kit.lines.filter(ln => {
              const it = inventory.find(x => x.id === ln.item_id);
              return !it || it.is_consumable !== false;
            });
            const reusables = applyKit.kit.lines.filter(ln => {
              const it = inventory.find(x => x.id === ln.item_id);
              return it && it.is_consumable === false;
            });
            const fmt = q => q.toFixed(2).replace(/\.?0+$/, '');
            return <>
                    {consumables.length > 0 && <div className="bg-amber-50 border border-amber-100 rounded-lg p-3 text-sm">
                        <p className="font-medium text-amber-900 mb-2">Stoktan düşecek (tek kullanımlık):</p>
                        <ul className="space-y-1">
                          {consumables.map((ln, i) => <li key={ln.id || i} className="flex justify-between">
                              <span className="text-gray-700">{ln.item_name}</span>
                              <span className="font-semibold">{fmt(ln.quantity * m)} {ln.unit}</span>
                            </li>)}
                        </ul>
                      </div>}
                    {reusables.length > 0 && <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3 text-sm">
                        <p className="font-medium text-indigo-900 mb-2">Sadece odaya konacak (çok kullanımlık — stoktan düşmez):</p>
                        <ul className="space-y-1">
                          {reusables.map((ln, i) => <li key={ln.id || i} className="flex justify-between">
                              <span className="text-gray-700">{ln.item_name}</span>
                              <span className="font-semibold">{fmt(ln.quantity * m)} {ln.unit}</span>
                            </li>)}
                        </ul>
                      </div>}
                  </>;
          })()}
              <div>
                <Label>Açıklama (opsiyonel)</Label>
                <Input value={applyKit.notes} placeholder="Örn: 12.04 sabah hazırlığı" onChange={e => setApplyKit({
              ...applyKit,
              notes: e.target.value
            })} />
              </div>
            </div>
            <div className="border-t p-4 flex items-center justify-end gap-2 bg-gray-50">
              <Button variant="outline" onClick={() => setApplyKit(null)} disabled={saving}>Vazgeç</Button>
              <Button className="bg-indigo-600 hover:bg-indigo-700" onClick={runApplyKit} disabled={saving}>
                {saving ? 'Uygulanıyor…' : 'Onayla & Stoktan Düş'}
              </Button>
            </div>
          </div>
        </div>}

      {/* ── Stok Hareketi Modal ────────────────────────── */}
      {movement && (() => {
      const cfg = {
        out: {
          title: 'Stoktan Düş',
          desc: 'Tüketim, kullanım veya kayıp girişi.',
          headerCls: 'bg-amber-50',
          iconCls: 'text-amber-600',
          icon: ArrowDownCircle
        },
        in: {
          title: 'Stoğa Ekle',
          desc: 'Manuel giriş (mal kabul dışında).',
          headerCls: 'bg-emerald-50',
          iconCls: 'text-emerald-600',
          icon: ArrowUpCircle
        },
        adjustment: {
          title: 'Sayım Düzeltmesi',
          desc: 'Fiziksel sayım sonucu yeni miktarı girin.',
          headerCls: 'bg-slate-50',
          iconCls: 'text-slate-600',
          icon: Edit3
        }
      }[movement.type];
      const Ic = cfg.icon;
      return <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setMovement(null)}>
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full" onClick={e => e.stopPropagation()}>
              <div className={`border-b p-4 flex items-center justify-between ${cfg.headerCls}`}>
                <div className="flex items-center gap-3">
                  <Ic className={`w-6 h-6 ${cfg.iconCls}`} />
                  <div>
                    <h2 className="font-bold">{cfg.title}</h2>
                    <p className="text-xs text-gray-600">{movement.item.name} · Mevcut: {movement.item.quantity} {movement.item.unit}</p>
                  </div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setMovement(null)} disabled={saving}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <div className="p-5 space-y-3">
                <p className="text-xs text-gray-600">{cfg.desc}</p>
                <div>
                  <Label>
                    {movement.type === 'adjustment' ? `Yeni Miktar (${movement.item.unit})` : `Miktar (${movement.item.unit})`}
                  </Label>
                  <Input type="number" min="0" autoFocus value={movement.quantity} onChange={e => setMovement({
                ...movement,
                quantity: e.target.value
              })} />
                  {movement.type === 'out' && <p className="text-xs text-gray-500 mt-1">
                      Kalan: {Math.max(0, (movement.item.quantity || 0) - (Number(movement.quantity) || 0))} {movement.item.unit}
                    </p>}
                </div>
                <div>
                  <Label>Neden / Referans</Label>
                  <select className="w-full border rounded-md p-2 text-sm" value={movement.reference} onChange={e => setMovement({
                ...movement,
                reference: e.target.value
              })}>
                    <option value="">— Seç —</option>
                    {movement.type === 'out' && <>
                      <option value="housekeeping">Housekeeping kullanımı</option>
                      <option value="guest_consumption">Misafir tüketimi</option>
                      <option value="fnb">F&B / Mutfak</option>
                      <option value="maintenance">Bakım/Onarım</option>
                      <option value="damage">Kırık/Bozuk</option>
                      <option value="lost">Kayıp</option>
                      <option value="transfer">Departman transferi</option>
                    </>}
                    {movement.type === 'in' && <>
                      <option value="manual_in">Manuel giriş</option>
                      <option value="return">İade</option>
                      <option value="found">Bulunan ürün</option>
                      <option value="transfer">Departman transferi</option>
                    </>}
                    {movement.type === 'adjustment' && <>
                      <option value="stock_count">Sayım</option>
                      <option value="correction">Hata düzeltme</option>
                    </>}
                  </select>
                </div>
                <div>
                  <Label>Açıklama</Label>
                  <Input value={movement.notes} placeholder="Örn: 5 oda hazırlığı için" onChange={e => setMovement({
                ...movement,
                notes: e.target.value
              })} />
                </div>
              </div>
              <div className="border-t p-4 flex items-center justify-end gap-2 bg-gray-50">
                <Button variant="outline" onClick={() => setMovement(null)} disabled={saving}>Vazgeç</Button>
                <Button className={movement.type === 'out' ? 'bg-amber-600 hover:bg-amber-700' : movement.type === 'in' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-blue-600 hover:bg-blue-700'} onClick={saveMovement} disabled={saving}>
                  {saving ? 'Kaydediliyor…' : 'Onayla'}
                </Button>
              </div>
            </div>
          </div>;
    })()}

      {/* ── Yeni Transfer Belgesi Modal (çok kalemli) ──── */}
      {bulkTransfer && (() => {
      const locations = Array.from(new Set(inventory.map(x => x.location).filter(Boolean))).sort();
      const srcLoc = bulkTransfer.source_location;
      const dstLoc = bulkTransfer.destination_location;
      const sourceItems = srcLoc ? inventory.filter(x => x.location === srcLoc) : [];
      const setLines = lines => setBulkTransfer({
        ...bulkTransfer,
        lines
      });
      const addLine = () => setLines([...(bulkTransfer.lines || []), {
        source_item_id: '',
        quantity: 1
      }]);
      const removeLine = idx => setLines(bulkTransfer.lines.filter((_, i) => i !== idx));
      const updateLine = (idx, patch) => setLines(bulkTransfer.lines.map((l, i) => i === idx ? {
        ...l,
        ...patch
      } : l));
      // Aggregate per source row for live insufficient-stock hint
      const sumBySrc = (bulkTransfer.lines || []).reduce((acc, l) => {
        if (!l.source_item_id) return acc;
        const q = Number(l.quantity) || 0;
        acc[l.source_item_id] = (acc[l.source_item_id] || 0) + q;
        return acc;
      }, {});
      return <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setBulkTransfer(null)}>
            <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
              <div className="border-b p-4 bg-sky-50 flex items-center justify-between sticky top-0">
                <div className="flex items-center gap-3">
                  <FileText className="w-6 h-6 text-sky-600" />
                  <div>
                    <h2 className="font-bold">Yeni Transfer Belgesi</h2>
                    <p className="text-xs text-gray-600">Tek belgede birden çok kalemi tek seferde aktarın. Tüm satırlar aynı referans altında işlenir.</p>
                  </div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setBulkTransfer(null)} disabled={saving}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <div className="p-5 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label>Kaynak Depo *</Label>
                    <select className="w-full border rounded-md p-2 text-sm" value={srcLoc} onChange={e => setBulkTransfer({
                  ...bulkTransfer,
                  source_location: e.target.value,
                  lines: [{
                    source_item_id: '',
                    quantity: 1
                  }]
                })}>
                      <option value="">— Kaynak depo seç —</option>
                      {locations.map(loc => <option key={loc} value={loc}>{loc}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label>Hedef Depo *</Label>
                    <select className="w-full border rounded-md p-2 text-sm" value={dstLoc} onChange={e => setBulkTransfer({
                  ...bulkTransfer,
                  destination_location: e.target.value
                })}>
                      <option value="">— Hedef depo seç —</option>
                      {locations.filter(l => l !== srcLoc).map(loc => <option key={loc} value={loc}>{loc}</option>)}
                    </select>
                    {srcLoc && dstLoc && srcLoc === dstLoc && <p className="text-xs text-red-600 mt-1">Kaynak ve hedef depo aynı olamaz.</p>}
                  </div>
                </div>

                <div className="border rounded-lg">
                  <div className="grid grid-cols-12 gap-2 px-3 py-2 bg-gray-50 text-xs font-semibold text-gray-600 border-b">
                    <div className="col-span-7">Kalem (kaynak depodaki)</div>
                    <div className="col-span-3">Miktar</div>
                    <div className="col-span-2 text-right">İşlem</div>
                  </div>
                  <div className="divide-y">
                    {(bulkTransfer.lines || []).map((line, idx) => {
                  const src = inventory.find(x => x.id === line.source_item_id);
                  const dst = resolveBulkDest(src, dstLoc);
                  const totalForSrc = src ? sumBySrc[src.id] || 0 : 0;
                  const insufficient = src && totalForSrc > (src.quantity || 0);
                  const missingDest = src && dstLoc && !dst;
                  return <div key={idx} className="grid grid-cols-12 gap-2 px-3 py-2 items-start">
                          <div className="col-span-7">
                            <select className="w-full border rounded-md p-2 text-sm" value={line.source_item_id} disabled={!srcLoc} onChange={e => updateLine(idx, {
                        source_item_id: e.target.value
                      })}>
                              <option value="">— Kalem seç —</option>
                              {sourceItems.map(it => <option key={it.id} value={it.id}>
                                  {it.name}{it.sku ? ` [${it.sku}]` : ''} — {it.quantity} {it.unit}
                                </option>)}
                            </select>
                            {src && dst && <p className="text-xs text-emerald-600 mt-1">
                                Hedef eşleşme: {dst.name}{dst.sku ? ` [${dst.sku}]` : ''} · {dst.quantity} {dst.unit}
                              </p>}
                            {missingDest && <p className="text-xs text-amber-600 mt-1">
                                Hedef depoda "{src.name}" için eşleşen kalem yok. Aynı SKU/isimle bir kalem oluşturulmalı.
                              </p>}
                          </div>
                          <div className="col-span-3">
                            <Input type="number" min="0.01" step="0.01" value={line.quantity} onChange={e => updateLine(idx, {
                        quantity: e.target.value
                      })} />
                            {insufficient && <p className="text-xs text-red-600 mt-1">
                                Toplam {totalForSrc} {src.unit}, mevcut {src.quantity} {src.unit}.
                              </p>}
                          </div>
                          <div className="col-span-2 flex justify-end">
                            <Button size="sm" variant="ghost" onClick={() => removeLine(idx)} disabled={saving || (bulkTransfer.lines || []).length <= 1} title="Satırı sil">
                              <Trash2 className="w-4 h-4 text-red-500" />
                            </Button>
                          </div>
                        </div>;
                })}
                  </div>
                  <div className="px-3 py-2 border-t">
                    <Button size="sm" variant="outline" onClick={addLine} disabled={saving || !srcLoc || (bulkTransfer.lines || []).length >= 100}>
                      <Plus className="w-3.5 h-3.5 mr-1" /> Satır Ekle
                    </Button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label>Belge Referansı (opsiyonel)</Label>
                    <Input value={bulkTransfer.reference} placeholder="Örn: WT-2026-05-27" onChange={e => setBulkTransfer({
                  ...bulkTransfer,
                  reference: e.target.value
                })} />
                  </div>
                  <div>
                    <Label>Notlar (opsiyonel)</Label>
                    <Input value={bulkTransfer.notes} placeholder="Örn: Restoran deposu için haftalık aktarım" onChange={e => setBulkTransfer({
                  ...bulkTransfer,
                  notes: e.target.value
                })} />
                  </div>
                </div>

                <div className="bg-sky-50 border border-sky-100 rounded-lg p-3 text-xs text-sky-900">
                  Tüm satırlar tek bir <strong>transfer_id</strong> ile yazılır, finans bu hareketi tek belge olarak görür.
                  Herhangi bir satır başarısız olursa daha önce uygulanan satırlar otomatik geri alınır.
                </div>
              </div>
              <div className="border-t p-4 flex items-center justify-end gap-2 bg-gray-50 sticky bottom-0">
                <Button variant="outline" onClick={() => setBulkTransfer(null)} disabled={saving}>Vazgeç</Button>
                <Button className="bg-sky-600 hover:bg-sky-700" onClick={saveBulkTransfer} disabled={saving || !srcLoc || !dstLoc || srcLoc === dstLoc}>
                  {saving ? 'Gönderiliyor…' : 'Belgeyi Gönder'}
                </Button>
              </div>
            </div>
          </div>;
    })()}

      {/* ── Stok Transferi Modal ───────────────────────── */}
      {transfer && (() => {
      const src = inventory.find(x => x.id === transfer.source_item_id);
      const dst = inventory.find(x => x.id === transfer.destination_item_id);
      const candidates = inventory.filter(x => x.id !== transfer.source_item_id);
      const qty = Number(transfer.quantity) || 0;
      const insufficient = src && qty > (src.quantity || 0);
      // Task #75 — unit-mismatch block. Backend will 422 on this anyway,
      // so we hard-disable Confirm and surface a clear explanation.
      const unitMismatch = !!(src && dst && src.unit && dst.unit && src.unit !== dst.unit);
      return <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setTransfer(null)}>
            <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full" onClick={e => e.stopPropagation()}>
              <div className="border-b p-4 bg-sky-50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <ArrowRightLeft className="w-6 h-6 text-sky-600" />
                  <div>
                    <h2 className="font-bold">Depolar Arası Stok Transferi</h2>
                    <p className="text-xs text-gray-600">Bir konumdan diğerine atomik olarak aktarın.</p>
                  </div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setTransfer(null)} disabled={saving}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <div className="p-5 space-y-3">
                <div>
                  <Label>Kaynak Ürün / Depo *</Label>
                  <select className="w-full border rounded-md p-2 text-sm" value={transfer.source_item_id} onChange={e => setTransfer({
                ...transfer,
                source_item_id: e.target.value
              })}>
                    <option value="">— Kaynak seç —</option>
                    {inventory.map(it => <option key={it.id} value={it.id}>
                        {it.name}{it.location ? ` — ${it.location}` : ''} ({it.quantity} {it.unit})
                      </option>)}
                  </select>
                  {src && <p className="text-xs text-gray-500 mt-1">
                      Mevcut: {src.quantity} {src.unit}{src.location ? ` · ${src.location}` : ''}
                    </p>}
                </div>
                <div>
                  <Label>Hedef Ürün / Depo *</Label>
                  <select className="w-full border rounded-md p-2 text-sm" value={transfer.destination_item_id} onChange={e => setTransfer({
                ...transfer,
                destination_item_id: e.target.value
              })}>
                    <option value="">— Hedef seç —</option>
                    {candidates.map(it => <option key={it.id} value={it.id}>
                        {it.name}{it.location ? ` — ${it.location}` : ''} ({it.quantity} {it.unit})
                      </option>)}
                  </select>
                  {unitMismatch && <p className="text-xs text-red-600 mt-1">
                      Birimler uyuşmuyor: kaynak <strong>{src.unit}</strong>, hedef{' '}
                      <strong>{dst.unit}</strong>. Farklı birimler arası transfer
                      stok seviyesini bozar; bu nedenle bloke edildi.
                    </p>}
                </div>
                <div>
                  <Label>Miktar{src ? ` (${src.unit})` : ''} *</Label>
                  <Input type="number" min="0.01" step="0.01" autoFocus value={transfer.quantity} onChange={e => setTransfer({
                ...transfer,
                quantity: e.target.value
              })} />
                  {insufficient && <p className="text-xs text-red-600 mt-1">
                      Kaynakta sadece {src.quantity} {src.unit} var.
                    </p>}
                </div>
                <div>
                  <Label>Referans (opsiyonel)</Label>
                  <Input value={transfer.reference} placeholder="Örn: WT-2026-04-12" onChange={e => setTransfer({
                ...transfer,
                reference: e.target.value
              })} />
                </div>
                <div>
                  <Label>Notlar (opsiyonel)</Label>
                  <Input value={transfer.notes} placeholder="Örn: Restoran deposu için" onChange={e => setTransfer({
                ...transfer,
                notes: e.target.value
              })} />
                </div>
              </div>
              <div className="border-t p-4 flex items-center justify-end gap-2 bg-gray-50">
                <Button variant="outline" onClick={() => setTransfer(null)} disabled={saving}>Vazgeç</Button>
                <Button className="bg-sky-600 hover:bg-sky-700" onClick={saveTransfer} disabled={saving || !transfer.source_item_id || !transfer.destination_item_id || insufficient || unitMismatch}>
                  {saving ? 'Aktarılıyor…' : 'Transferi Onayla'}
                </Button>
              </div>
            </div>
          </div>;
    })()}

      {/* ── Yeni Ürün Modal ────────────────────────────── */}
      {newItem && <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setNewItem(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="border-b p-4 flex items-center justify-between sticky top-0 bg-white">
              <div>
                <h2 className="font-bold text-lg">Yeni Ürün Ekle</h2>
                <p className="text-xs text-gray-500">Stoğunuza yeni bir kalem ekleyin.</p>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setNewItem(null)} disabled={saving}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="md:col-span-2">
                  <Label>Ürün Adı *</Label>
                  <Input value={newItem.name} autoFocus placeholder="Örn: Şampuan, Havlu, Çay…" onChange={e => setNewItem({
                ...newItem,
                name: e.target.value
              })} />
                </div>
                <div>
                  <Label>Kategori</Label>
                  <select className="w-full border rounded-md p-2 text-sm" value={newItem.category} onChange={e => setNewItem({
                ...newItem,
                category: e.target.value
              })}>
                    {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <Label>SKU / Kod</Label>
                  <Input value={newItem.sku} placeholder="İsteğe bağlı" onChange={e => setNewItem({
                ...newItem,
                sku: e.target.value
              })} />
                </div>
                <div>
                  <Label>Birim</Label>
                  <select className="w-full border rounded-md p-2 text-sm" value={newItem.unit} onChange={e => setNewItem({
                ...newItem,
                unit: e.target.value
              })}>
                    {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                  </select>
                </div>
                <div>
                  <Label>Mevcut Miktar</Label>
                  <Input type="number" min="0" value={newItem.quantity} onChange={e => setNewItem({
                ...newItem,
                quantity: e.target.value
              })} />
                </div>
                <div>
                  <Label>Birim Fiyat (₺)</Label>
                  <Input type="number" min="0" step="0.01" value={newItem.unit_cost} onChange={e => setNewItem({
                ...newItem,
                unit_cost: e.target.value
              })} />
                </div>
                <div>
                  <Label>Kritik Seviye (Min. Stok)</Label>
                  <Input type="number" min="0" value={newItem.reorder_level} onChange={e => setNewItem({
                ...newItem,
                reorder_level: e.target.value
              })} />
                </div>
                <div className="md:col-span-2">
                  <Label>Konum</Label>
                  <Input value={newItem.location} placeholder="Örn: Depo A, Raf 3" onChange={e => setNewItem({
                ...newItem,
                location: e.target.value
              })} />
                </div>
                <div className="md:col-span-2">
                  <Label>Notlar</Label>
                  <Input value={newItem.notes} onChange={e => setNewItem({
                ...newItem,
                notes: e.target.value
              })} />
                </div>
                <div className="md:col-span-2">
                  <Label>Ürün Tipi</Label>
                  <div className="flex gap-2 mt-1">
                    <button type="button" className={`flex-1 border rounded-lg p-3 text-left transition ${newItem.is_consumable !== false ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'}`} onClick={() => setNewItem({
                  ...newItem,
                  is_consumable: true
                })}>
                      <div className="font-semibold text-sm">Tek Kullanımlık</div>
                      <div className="text-xs text-gray-600 mt-0.5">Kullanınca tükenir, stoktan düşer (şampuan, sabun, kahve)</div>
                    </button>
                    <button type="button" className={`flex-1 border rounded-lg p-3 text-left transition ${newItem.is_consumable === false ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 hover:border-gray-300'}`} onClick={() => setNewItem({
                  ...newItem,
                  is_consumable: false
                })}>
                      <div className="font-semibold text-sm">Çok Kullanımlık</div>
                      <div className="text-xs text-gray-600 mt-0.5">Tekrar tekrar kullanılır, stoktan düşmez (havlu, nevresim, bornoz)</div>
                    </button>
                  </div>
                </div>
              </div>
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-900">
                <strong>Kritik seviye nedir?</strong> Bu kalemin altına düşünce sistem uyarı verir
                ve "Talep Oluştur" butonu görünür. Sıkça biten ürünleriniz için doğru bir değer girmeniz önemlidir.
              </div>
            </div>
            <div className="border-t p-4 flex items-center justify-end gap-2 bg-gray-50">
              <Button variant="outline" onClick={() => setNewItem(null)} disabled={saving}>Vazgeç</Button>
              <Button className="bg-blue-600 hover:bg-blue-700" onClick={saveNewItem} disabled={saving}>
                {saving ? 'Kaydediliyor…' : 'Ürünü Ekle'}
              </Button>
            </div>
          </div>
        </div>}
    </>;
};
export default HotelInventory;