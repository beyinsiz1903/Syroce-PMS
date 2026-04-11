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
import { Package, AlertTriangle, DollarSign, Boxes } from 'lucide-react';

const IngredientInventoryPanel = () => {
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

  const fetchIngredients = async () => {
    try {
      const res = await axios.get('/fnb/ingredients');
      setIngredients(res.data.ingredients || []);
      setSummary(res.data.summary || null);
    } catch (error) {
      console.error('Ingredient fetch failed', error);
      toast.error('Ingredient listesi yüklenemedi');
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
      toast.success('Ingredient eklendi');
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
      toast.error('Ingredient eklenemedi');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="bg-gradient-to-r from-amber-50 to-amber-100 border-amber-200">
          <CardContent className="p-4">
            <p className="text-xs text-amber-700 font-semibold flex items-center gap-2">
              <Package className="w-4 h-4" />
              Toplam Kalem
            </p>
            <p className="text-3xl font-bold">{summary?.total_items ?? ingredients.length}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-red-50 to-red-100 border-red-200">
          <CardContent className="p-4">
            <p className="text-xs text-red-700 font-semibold flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              Düşük Stok
            </p>
            <p className="text-3xl font-bold">{summary?.low_stock ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-emerald-50 to-emerald-100 border-emerald-200">
          <CardContent className="p-4">
            <p className="text-xs text-emerald-700 font-semibold flex items-center gap-2">
              <DollarSign className="w-4 h-4" />
              Envanter Değeri
            </p>
            <p className="text-3xl font-bold">
              €{summary?.inventory_value?.toFixed(2) ?? '0.00'}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Boxes className="w-4 h-4 text-blue-600" />
            Ingredient Inventory
          </CardTitle>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <Button size="sm" onClick={() => setDialogOpen(true)}>
              + Ingredient
            </Button>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Yeni Ingredient</DialogTitle>
              </DialogHeader>
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <Label>Ad</Label>
                    <Input
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <Label>Kategori</Label>
                    <select
                      value={form.category}
                      onChange={(e) => setForm({ ...form, category: e.target.value })}
                      className="w-full rounded-md border border-input px-3 py-2 text-sm"
                    >
                      <option value="produce">Produce</option>
                      <option value="meat">Meat</option>
                      <option value="dairy">Dairy</option>
                      <option value="dry">Dry Goods</option>
                      <option value="beverage">Beverage</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div>
                    <Label>Birim</Label>
                    <Input
                      value={form.unit}
                      onChange={(e) => setForm({ ...form, unit: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label>Tedarikçi</Label>
                    <Input
                      value={form.supplier}
                      onChange={(e) => setForm({ ...form, supplier: e.target.value })}
                    />
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  <div>
                    <Label>Stok</Label>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.current_stock}
                      onChange={(e) => setForm({ ...form, current_stock: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label>Par Level</Label>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.par_level}
                      onChange={(e) => setForm({ ...form, par_level: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label>Reorder Point</Label>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.reorder_point}
                      onChange={(e) => setForm({ ...form, reorder_point: e.target.value })}
                    />
                  </div>
                </div>
                <div>
                  <Label>Birim Maliyet (€)</Label>
                  <Input
                    type="number"
                    min="0"
                    step="0.01"
                    value={form.unit_cost}
                    onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
                  />
                </div>
                <DialogFooter>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Kaydediliyor...' : 'Ingredient Kaydet'}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent className="space-y-3">
          {ingredients.length === 0 && (
            <p className="text-sm text-gray-500">Henüz ingredient kaydı yok.</p>
          )}
          {ingredients.map((ingredient) => {
            const isLow = ingredient.current_stock <= ingredient.reorder_point;
            return (
              <div
                key={ingredient.id}
                className={`grid gap-2 rounded-md border px-3 py-3 text-sm md:grid-cols-5 ${
                  isLow ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'
                }`}
              >
                <div>
                  <p className="font-semibold text-gray-800">{ingredient.name}</p>
                  <p className="text-xs text-gray-500">{ingredient.supplier || 'Supplier yok'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Stok</p>
                  <p className="font-semibold text-gray-800">
                    {ingredient.current_stock} {ingredient.unit}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Par / Reorder</p>
                  <p className="font-semibold text-gray-800">
                    {ingredient.par_level} / {ingredient.reorder_point}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Birim Maliyeti</p>
                  <p className="font-semibold text-gray-800">€{ingredient.unit_cost}</p>
                </div>
                <div className="flex items-center justify-end">
                  <Badge variant={isLow ? 'destructive' : 'outline'}>
                    {isLow ? 'Reorder' : ingredient.category}
                  </Badge>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
};

export default IngredientInventoryPanel;
