import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Package, AlertTriangle, TrendingDown, ShoppingCart,
  RefreshCw, FileText, BarChart3, CheckCircle, Plus, BookOpen, X,
  ArrowDownCircle, ArrowUpCircle, Edit3,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslation } from 'react-i18next';

const EMPTY_ITEM = {
  name: '', sku: '', category: 'Oda Ürünleri', unit: 'adet',
  quantity: 0, unit_cost: 0, reorder_level: 0, location: '', notes: '',
};

const CATEGORIES = ['Oda Ürünleri', 'Banyo Ürünleri', 'Yatak Ürünleri', 'Temizlik', 'F&B', 'Kırtasiye', 'Diğer'];
const UNITS = ['adet', 'kg', 'gr', 'lt', 'ml', 'paket', 'kutu', 'metre'];

const HotelInventory = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [newItem, setNewItem] = useState(null);
  const [saving, setSaving] = useState(false);
  const [movement, setMovement] = useState(null); // { item, type, quantity, reference, notes }

  const openMovement = (item, type) => {
    setMovement({
      item,
      type,
      quantity: type === 'adjustment' ? (item.quantity || 0) : 1,
      reference: '',
      notes: '',
    });
  };

  const saveMovement = async () => {
    const qty = Number(movement.quantity);
    if (!qty || qty < 0) { toast.error('Geçerli bir miktar girin'); return; }
    if (movement.type === 'out' && qty > (movement.item.quantity || 0)) {
      toast.error(`Stokta sadece ${movement.item.quantity} ${movement.item.unit} var`); return;
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
          notes: movement.notes || undefined,
        },
      });
      const labels = { in: 'eklendi', out: 'düşürüldü', adjustment: 'güncellendi' };
      toast.success(`${movement.item.name} stoğu ${labels[movement.type]}`);
      setMovement(null);
      loadInventory();
      loadAlerts();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Stok hareketi kaydedilemedi');
    } finally { setSaving(false); }
  };

  const saveNewItem = async () => {
    if (!newItem.name?.trim() || newItem.name.trim().length < 2) {
      toast.error('Ürün adı en az 2 karakter olmalı'); return;
    }
    setSaving(true);
    try {
      await axios.post('/accounting/inventory', null, {
        params: {
          name: newItem.name.trim(),
          category: newItem.category,
          unit: newItem.unit,
          quantity: Number(newItem.quantity) || 0,
          unit_cost: Number(newItem.unit_cost) || 0,
          reorder_level: Number(newItem.reorder_level) || 0,
          sku: newItem.sku || undefined,
          location: newItem.location || undefined,
          notes: newItem.notes || undefined,
        },
      });
      toast.success(`${newItem.name} eklendi`);
      setNewItem(null);
      loadInventory();
      loadAlerts();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Ürün eklenemedi');
    } finally { setSaving(false); }
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
          department: item.category || '',
        },
      },
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
    loadInventory();
    loadAlerts();
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
    if (quantity === 0) return { label: 'Tükendi', color: 'bg-red-500', textColor: 'text-red-700' };
    if (quantity <= reorderLevel / 2) return { label: 'Kritik', color: 'bg-orange-500', textColor: 'text-orange-700' };
    if (quantity <= reorderLevel) return { label: 'Düşük', color: 'bg-yellow-500', textColor: 'text-yellow-700' };
    return { label: 'Normal', color: 'bg-green-500', textColor: 'text-green-700' };
  };

  const getCategoryIcon = (category) => {
    const icons = {
      'Banyo Ürünleri': '🛁',
      'Oda Ürünleri': '🏠',
      'Yatak Ürünleri': '🛏️',
      'Temizlik': '🧹'
    };
    return icons[category] || '📦';
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout}>
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
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
            <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => setNewItem({ ...EMPTY_ITEM })}>
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
                  <p className="text-2xl font-bold text-orange-500">{stats.lowStockCount}</p>
                </div>
                <AlertTriangle className="w-10 h-10 text-orange-500" />
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
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="inventory">
              <Package className="w-4 h-4 mr-2" />
              Stok Durumu
            </TabsTrigger>
            <TabsTrigger value="alerts">
              <AlertTriangle className="w-4 h-4 mr-2" />
              Uyarılar ({alerts.length})
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
                  {Object.entries(
                    inventory.reduce((acc, item) => {
                      if (!acc[item.category]) acc[item.category] = [];
                      acc[item.category].push(item);
                      return acc;
                    }, {})
                  ).map(([category, items]) => (
                    <div key={category} className="border rounded-lg p-4">
                      <h3 className="font-semibold text-lg mb-3 flex items-center">
                        <span className="mr-2">{getCategoryIcon(category)}</span>
                        {category} ({items.length})
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {items.map((item) => {
                          const status = getStockStatus(item.quantity, item.reorder_level);
                          return (
                            <Card key={item.id} className="hover:shadow-md transition-shadow">
                              <CardContent className="p-4">
                                <div className="flex justify-between items-start mb-2">
                                  <div>
                                    <p className="font-semibold">{item.name}</p>
                                    <p className="text-sm text-gray-600">{item.sku}</p>
                                  </div>
                                  <Badge className={status.color}>{status.label}</Badge>
                                </div>
                                <div className="space-y-1 text-sm">
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
                                  <Button
                                    size="sm" variant="outline"
                                    className="flex-1 text-xs px-2 border-orange-300 text-orange-700 hover:bg-orange-50"
                                    onClick={() => openMovement(item, 'out')}
                                    title="Stoktan düş (kullanım/tüketim)"
                                  >
                                    <ArrowDownCircle className="w-3.5 h-3.5 mr-1" /> Düş
                                  </Button>
                                  <Button
                                    size="sm" variant="outline"
                                    className="flex-1 text-xs px-2 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                                    onClick={() => openMovement(item, 'in')}
                                    title="Stoğa ekle (manuel giriş)"
                                  >
                                    <ArrowUpCircle className="w-3.5 h-3.5 mr-1" /> Ekle
                                  </Button>
                                  <Button
                                    size="sm" variant="outline"
                                    className="text-xs px-2"
                                    onClick={() => openMovement(item, 'adjustment')}
                                    title="Sayım sonucu düzeltme"
                                  >
                                    <Edit3 className="w-3.5 h-3.5" />
                                  </Button>
                                </div>
                                {item.quantity <= item.reorder_level && (
                                  <Button
                                    size="sm"
                                    className="w-full mt-2 bg-blue-600 hover:bg-blue-700"
                                    onClick={() => createPRForItem(item, Math.max(1, item.reorder_level * 2 - item.quantity))}
                                  >
                                    <Plus className="w-3.5 h-3.5 mr-1" />
                                    Talep Oluştur
                                  </Button>
                                )}
                              </CardContent>
                            </Card>
                          );
                        })}
                      </div>
                    </div>
                  ))}
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
                {alerts.length === 0 ? (
                  <div className="text-center py-8">
                    <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-3" />
                    <p className="text-lg font-semibold">Tüm stoklar normal seviyede</p>
                    <p className="text-gray-600">Herhangi bir uyarı bulunmamaktadır</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {alerts.map((alert, idx) => (
                      <Card 
                        key={idx} 
                        className={`border-l-4 ${
                          alert.priority === 'URGENT' ? 'border-red-500' : 
                          alert.priority === 'HIGH' ? 'border-orange-500' : 'border-yellow-500'
                        }`}
                      >
                        <CardContent className="p-4">
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <AlertTriangle className={`w-5 h-5 ${
                                  alert.priority === 'URGENT' ? 'text-red-500' : 
                                  alert.priority === 'HIGH' ? 'text-orange-500' : 'text-yellow-500'
                                }`} />
                                <p className="font-semibold">{alert.item_name}</p>
                                <Badge variant={
                                  alert.priority === 'URGENT' ? 'destructive' : 'default'
                                }>
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
                            <Button
                              size="sm"
                              className="ml-4 bg-blue-600 hover:bg-blue-700"
                              onClick={() => createPRForItem(
                                {
                                  id: alert.item_id || alert.id,
                                  name: alert.item_name,
                                  sku: alert.sku,
                                  unit: alert.unit || 'adet',
                                  unit_cost: alert.unit_cost || (alert.estimated_cost && alert.suggested_order_quantity
                                    ? alert.estimated_cost / alert.suggested_order_quantity : 0),
                                  quantity: alert.current_stock,
                                  reorder_level: alert.critical_level,
                                },
                                alert.suggested_order_quantity,
                              )}
                            >
                              <Plus className="w-4 h-4 mr-1" />
                              Talep Oluştur
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
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
                {alerts.length > 0 ? (
                  <div className="space-y-2">
                    <div className="bg-blue-50 p-4 rounded-lg mb-4">
                      <p className="font-semibold mb-2">📦 Toplu Sipariş Özeti</p>
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
                          <p className="font-bold text-lg text-orange-600">
                            {alerts.filter(a => a.priority === 'HIGH').length}
                          </p>
                        </div>
                      </div>
                    </div>
                    <Button
                      className="w-full bg-blue-600 hover:bg-blue-700"
                      size="lg"
                      onClick={() => navigate('/app/procurement')}
                    >
                      <ShoppingCart className="w-5 h-5 mr-2" />
                      Satın Alma Ekranına Git
                    </Button>
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-3" />
                    <p className="text-lg font-semibold">Sipariş gerekmiyor</p>
                    <p className="text-gray-600">Tüm stoklar yeterli seviyede</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      {/* ── Stok Hareketi Modal ────────────────────────── */}
      {movement && (() => {
        const cfg = {
          out:        { title: 'Stoktan Düş',     desc: 'Tüketim, kullanım veya kayıp girişi.', headerCls: 'bg-orange-50',  iconCls: 'text-orange-600',  icon: ArrowDownCircle },
          in:         { title: 'Stoğa Ekle',      desc: 'Manuel giriş (mal kabul dışında).',    headerCls: 'bg-emerald-50', iconCls: 'text-emerald-600', icon: ArrowUpCircle },
          adjustment: { title: 'Sayım Düzeltmesi', desc: 'Fiziksel sayım sonucu yeni miktarı girin.', headerCls: 'bg-slate-50',  iconCls: 'text-slate-600',   icon: Edit3 },
        }[movement.type];
        const Ic = cfg.icon;
        return (
          <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
               onClick={() => !saving && setMovement(null)}>
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full"
                 onClick={(e) => e.stopPropagation()}>
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
                  <Input type="number" min="0" autoFocus value={movement.quantity}
                    onChange={(e) => setMovement({ ...movement, quantity: e.target.value })} />
                  {movement.type === 'out' && (
                    <p className="text-xs text-gray-500 mt-1">
                      Kalan: {Math.max(0, (movement.item.quantity || 0) - (Number(movement.quantity) || 0))} {movement.item.unit}
                    </p>
                  )}
                </div>
                <div>
                  <Label>Neden / Referans</Label>
                  <select className="w-full border rounded-md p-2 text-sm"
                    value={movement.reference}
                    onChange={(e) => setMovement({ ...movement, reference: e.target.value })}>
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
                  <Input value={movement.notes} placeholder="Örn: 5 oda hazırlığı için"
                    onChange={(e) => setMovement({ ...movement, notes: e.target.value })} />
                </div>
              </div>
              <div className="border-t p-4 flex items-center justify-end gap-2 bg-gray-50">
                <Button variant="outline" onClick={() => setMovement(null)} disabled={saving}>Vazgeç</Button>
                <Button
                  className={
                    movement.type === 'out' ? 'bg-orange-600 hover:bg-orange-700' :
                    movement.type === 'in'  ? 'bg-emerald-600 hover:bg-emerald-700' :
                                              'bg-blue-600 hover:bg-blue-700'
                  }
                  onClick={saveMovement} disabled={saving}>
                  {saving ? 'Kaydediliyor…' : 'Onayla'}
                </Button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── Yeni Ürün Modal ────────────────────────────── */}
      {newItem && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
             onClick={() => !saving && setNewItem(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
               onClick={(e) => e.stopPropagation()}>
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
                  <Input value={newItem.name} autoFocus
                    placeholder="Örn: Şampuan, Havlu, Çay…"
                    onChange={(e) => setNewItem({ ...newItem, name: e.target.value })} />
                </div>
                <div>
                  <Label>Kategori</Label>
                  <select className="w-full border rounded-md p-2 text-sm"
                    value={newItem.category}
                    onChange={(e) => setNewItem({ ...newItem, category: e.target.value })}>
                    {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <Label>SKU / Kod</Label>
                  <Input value={newItem.sku} placeholder="İsteğe bağlı"
                    onChange={(e) => setNewItem({ ...newItem, sku: e.target.value })} />
                </div>
                <div>
                  <Label>Birim</Label>
                  <select className="w-full border rounded-md p-2 text-sm"
                    value={newItem.unit}
                    onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })}>
                    {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                  </select>
                </div>
                <div>
                  <Label>Mevcut Miktar</Label>
                  <Input type="number" min="0" value={newItem.quantity}
                    onChange={(e) => setNewItem({ ...newItem, quantity: e.target.value })} />
                </div>
                <div>
                  <Label>Birim Fiyat (₺)</Label>
                  <Input type="number" min="0" step="0.01" value={newItem.unit_cost}
                    onChange={(e) => setNewItem({ ...newItem, unit_cost: e.target.value })} />
                </div>
                <div>
                  <Label>Kritik Seviye (Min. Stok)</Label>
                  <Input type="number" min="0" value={newItem.reorder_level}
                    onChange={(e) => setNewItem({ ...newItem, reorder_level: e.target.value })} />
                </div>
                <div className="md:col-span-2">
                  <Label>Konum</Label>
                  <Input value={newItem.location} placeholder="Örn: Depo A, Raf 3"
                    onChange={(e) => setNewItem({ ...newItem, location: e.target.value })} />
                </div>
                <div className="md:col-span-2">
                  <Label>Notlar</Label>
                  <Input value={newItem.notes}
                    onChange={(e) => setNewItem({ ...newItem, notes: e.target.value })} />
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
        </div>
      )}
    </Layout>
  );
};

export default HotelInventory;
