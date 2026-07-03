import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Package, AlertTriangle, DollarSign, Boxes, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const categoryLabels = {
  produce: 'Sebze/Meyve',
  meat: 'Et',
  dairy: 'Süt Ürünleri',
  dry: 'Kuru Gıda',
  beverage: 'İçecek',
  other: 'Diğer'
};

const IngredientInventoryPanel = () => {
  const { t } = useTranslation();
  const [ingredients, setIngredients] = useState([]);
  const [summary, setSummary] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    category: 'produce',
    unit: 'kg',
    current_stock: 0,
    par_level: 0,
    reorder_point: 0,
    unit_cost: 0,
    supplier: '',
  });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchIngredients = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/fnb/ingredients');
      setIngredients(res.data.ingredients || []);
      setSummary(res.data.summary || null);
    } catch (error) {
      console.error('Ingredient fetch failed', error);
      toast.error('Malzeme listesi yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIngredients();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await axios.post('/fnb/ingredients', {
        ...form,
        current_stock: Number(form.current_stock),
        par_level: Number(form.par_level),
        reorder_point: Number(form.reorder_point),
        unit_cost: Number(form.unit_cost),
      });
      toast.success('Malzeme başarıyla eklendi');
      setDialogOpen(false);
      setForm({
        name: '',
        category: 'produce',
        unit: 'kg',
        current_stock: 0,
        par_level: 0,
        reorder_point: 0,
        unit_cost: 0,
        supplier: '',
      });
      fetchIngredients();
    } catch (error) {
      console.error('Ingredient create failed', error);
      toast.error('Malzeme eklenirken hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Summary Cards ── */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="bg-gradient-to-r from-amber-50 to-amber-100 border-amber-200">
          <CardContent className="p-4">
            <p className="text-xs text-amber-700 font-semibold flex items-center gap-2 uppercase tracking-wide">
              <Package className="w-4 h-4" />
              {t('cm.components_IngredientInventoryPanel.toplam_kalem', 'Toplam Kalem')}
            </p>
            <p className="text-3xl font-bold text-amber-900 mt-1">{summary?.total_items ?? ingredients.length}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-red-50 to-red-100 border-red-200">
          <CardContent className="p-4">
            <p className="text-xs text-red-700 font-semibold flex items-center gap-2 uppercase tracking-wide">
              <AlertTriangle className="w-4 h-4" />
              {t('cm.components_IngredientInventoryPanel.dusuk_stok', 'Düşük Stok Uyarıları')}
            </p>
            <p className="text-3xl font-bold text-red-900 mt-1">{summary?.low_stock ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-emerald-50 to-emerald-100 border-emerald-200">
          <CardContent className="p-4">
            <p className="text-xs text-emerald-700 font-semibold flex items-center gap-2 uppercase tracking-wide">
              <DollarSign className="w-4 h-4" />
              {t('cm.components_IngredientInventoryPanel.envanter_degeri', 'Envanter Değeri')}
            </p>
            <p className="text-3xl font-bold text-emerald-900 mt-1">
              ₺{summary?.inventory_value?.toFixed(2) ?? '0.00'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* ── Main Panel ── */}
      <Card className="shadow-sm border-gray-200">
        <CardHeader className="flex flex-row items-center justify-between bg-gray-50 border-b border-gray-100 pb-4">
          <CardTitle className="flex items-center gap-2 text-base text-gray-800">
            <Boxes className="w-5 h-5 text-indigo-600" />
            Stok & Envanter Listesi
          </CardTitle>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <Button size="sm" onClick={() => setDialogOpen(true)} className="bg-indigo-600 hover:bg-indigo-700 text-white border-0">
              <Plus className="w-4 h-4 mr-1.5" />
              Yeni Malzeme
            </Button>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Yeni Malzeme Ekle</DialogTitle>
              </DialogHeader>
              <form className="space-y-5" onSubmit={handleSubmit}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <Label className="font-medium text-gray-700">Malzeme Adı <span className="text-red-500">*</span></Label>
                    <Input
                      className="mt-1"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      required
                      placeholder="Örn: Un"
                    />
                  </div>
                  <div>
                    <Label className="font-medium text-gray-700">Kategori</Label>
                    <select
                      value={form.category}
                      onChange={(e) => setForm({ ...form, category: e.target.value })}
                      className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      {Object.entries(categoryLabels).map(([val, label]) => (
                        <option key={val} value={val}>{label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <Label className="font-medium text-gray-700">Birim</Label>
                    <Input
                      className="mt-1"
                      value={form.unit}
                      onChange={(e) => setForm({ ...form, unit: e.target.value })}
                      placeholder="kg, litre, adet vb."
                    />
                  </div>
                  <div>
                    <Label className="font-medium text-gray-700">{t('cm.components_IngredientInventoryPanel.tedarikci', 'Tedarikçi (Opsiyonel)')}</Label>
                    <Input
                      className="mt-1"
                      value={form.supplier}
                      onChange={(e) => setForm({ ...form, supplier: e.target.value })}
                      placeholder="Firma Adı"
                    />
                  </div>
                </div>
                
                <div className="bg-gray-50 p-4 rounded-xl border border-gray-100 space-y-4">
                  <h4 className="text-sm font-bold text-gray-700 uppercase tracking-wide">Stok ve Maliyet Bilgileri</h4>
                  <div className="grid gap-4 md:grid-cols-3">
                    <div>
                      <Label className="text-gray-600">Mevcut Stok</Label>
                      <Input
                        className="mt-1"
                        type="number"
                        min="0"
                        step="0.01"
                        value={form.current_stock}
                        onChange={(e) => setForm({ ...form, current_stock: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label className="text-gray-600" title="Hedeflenen ideal stok seviyesi">Hedef Stok (Par)</Label>
                      <Input
                        className="mt-1"
                        type="number"
                        min="0"
                        step="0.01"
                        value={form.par_level}
                        onChange={(e) => setForm({ ...form, par_level: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label className="text-gray-600" title="Bu seviyeye düşünce uyarı ver">Kritik Eşik (Sipariş)</Label>
                      <Input
                        className="mt-1"
                        type="number"
                        min="0"
                        step="0.01"
                        value={form.reorder_point}
                        onChange={(e) => setForm({ ...form, reorder_point: e.target.value })}
                      />
                    </div>
                  </div>
                  <div>
                    <Label className="text-gray-600">Birim Maliyet (₺)</Label>
                    <Input
                      className="mt-1 max-w-[200px]"
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.unit_cost}
                      onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
                    />
                  </div>
                </div>

                <DialogFooter className="pt-2">
                  <Button variant="outline" type="button" onClick={() => setDialogOpen(false)} disabled={saving}>
                    İptal
                  </Button>
                  <Button type="submit" disabled={saving} className="bg-indigo-600 hover:bg-indigo-700 text-white">
                    {saving ? 'Kaydediliyor...' : 'Malzemeyi Kaydet'}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </CardHeader>
        
        <CardContent className="p-0">
          {loading && <div className="p-8 text-center text-sm text-gray-500">Yükleniyor...</div>}
          
          {!loading && ingredients.length === 0 && (
            <div className="p-12 text-center border-b border-gray-100">
              <Boxes className="w-12 h-12 mx-auto text-gray-300 mb-3" />
              <p className="font-medium text-gray-700">Henüz malzeme kaydı yok.</p>
              <p className="text-sm text-gray-500 mt-1">Stok takibi yapmak için "Yeni Malzeme" ekleyin.</p>
            </div>
          )}

          {!loading && ingredients.length > 0 && (
            <div className="divide-y divide-gray-100">
              {ingredients.map((ingredient) => {
                const isLow = ingredient.current_stock <= ingredient.reorder_point;
                return (
                  <div
                    key={ingredient.id}
                    className={`grid gap-4 px-6 py-4 text-sm md:grid-cols-5 items-center transition-colors hover:bg-gray-50 ${
                      isLow ? 'bg-red-50/50 hover:bg-red-50' : 'bg-white'
                    }`}
                  >
                    <div className="md:col-span-1">
                      <p className="font-bold text-gray-900 text-base">{ingredient.name}</p>
                      <p className="text-xs text-gray-500 font-medium mt-0.5">{ingredient.supplier || 'Tedarikçi yok'}</p>
                    </div>
                    
                    <div>
                      <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-0.5">Stok Durumu</p>
                      <p className={`font-bold text-lg ${isLow ? 'text-red-600' : 'text-gray-900'}`}>
                        {ingredient.current_stock} <span className="text-sm font-normal text-gray-500">{ingredient.unit}</span>
                      </p>
                    </div>
                    
                    <div>
                      <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-0.5">Hedef / Kritik</p>
                      <p className="font-medium text-gray-700">
                        {ingredient.par_level} / <span className="text-red-500 font-semibold">{ingredient.reorder_point}</span>
                      </p>
                    </div>
                    
                    <div>
                      <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-0.5">Birim Maliyeti</p>
                      <p className="font-semibold text-gray-800">₺{ingredient.unit_cost?.toFixed(2) || '0.00'}</p>
                    </div>
                    
                    <div className="flex items-center md:justify-end gap-2">
                      <Badge variant="outline" className={`text-[10px] ${
                        ingredient.category === 'produce' ? 'bg-green-50 text-green-700 border-green-200' :
                        ingredient.category === 'meat' ? 'bg-red-50 text-red-700 border-red-200' :
                        ingredient.category === 'dairy' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                        'bg-gray-100 text-gray-700 border-gray-200'
                      }`}>
                        {categoryLabels[ingredient.category] || ingredient.category}
                      </Badge>
                      
                      {isLow && (
                        <Badge variant="destructive" className="bg-red-500 hover:bg-red-600">
                          Sipariş Ver
                        </Badge>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default IngredientInventoryPanel;
