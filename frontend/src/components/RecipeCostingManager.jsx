import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { Plus, CookingPot, Flame, Timer, UtensilsCrossed, Percent, DollarSign, TrendingUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const categoryOptions = [
  'appetizer',
  'main',
  'dessert',
  'beverage',
  'room_service',
];

const categoryLabels = {
  'appetizer': 'Başlangıç',
  'main': 'Ana Yemek',
  'dessert': 'Tatlı',
  'beverage': 'İçecek',
  'room_service': 'Oda Servisi'
};

const RecipeCostingManager = () => {
  const { t } = useTranslation();
  const [recipes, setRecipes] = useState([]);
  const [ingredients, setIngredients] = useState([]);
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [form, setForm] = useState({
    dish_name: '',
    category: 'main',
    portion_size: '1 porsiyon',
    preparation_time: 20,
    selling_price: 0,
    notes: '',
    ingredients: [
      {
        tempId: Date.now(),
        ingredient_id: '',
        quantity: 1,
        waste_pct: 0,
      },
    ],
  });

  const fetchData = async () => {
    setLoading(true);
    try {
      const [recipesRes, ingredientsRes] = await Promise.all([
        axios.get('/fnb/recipes'),
        axios.get('/fnb/ingredients'),
      ]);
      setRecipes(recipesRes.data.recipes || []);
      setIngredients(ingredientsRes.data.ingredients || []);
      setSelectedRecipe((recipesRes.data.recipes || [])[0] || null);
    } catch (error) {
      console.error('F&B fetch error', error);
      toast.error('Veriler yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const stats = useMemo(() => {
    if (!recipes.length) {
      return {
        total: 0,
        avg_gp: 0,
        avg_cost: 0,
        best_gp: null,
      };
    }
    const sorted = [...recipes].sort((a, b) => b.gp_percentage - a.gp_percentage);
    return {
      total: recipes.length,
      avg_gp: recipes.reduce((sum, r) => sum + (r.gp_percentage || 0), 0) / recipes.length,
      avg_cost: recipes.reduce((sum, r) => sum + (r.total_cost || 0), 0) / recipes.length,
      best_gp: sorted[0],
    };
  }, [recipes]);

  const resetForm = () => {
    setForm({
      dish_name: '',
      category: 'main',
      portion_size: '1 porsiyon',
      preparation_time: 20,
      selling_price: 0,
      notes: '',
      ingredients: [
        {
          tempId: Date.now(),
          ingredient_id: '',
          quantity: 1,
          waste_pct: 0,
        },
      ],
    });
  };

  const handleIngredientChange = (tempId, field, value) => {
    setForm((prev) => ({
      ...prev,
      ingredients: prev.ingredients.map((row) =>
        row.tempId === tempId ? { ...row, [field]: value } : row
      ),
    }));
  };

  const addIngredientRow = () => {
    setForm((prev) => ({
      ...prev,
      ingredients: [
        ...prev.ingredients,
        { tempId: Date.now(), ingredient_id: '', quantity: 1, waste_pct: 0 },
      ],
    }));
  };

  const removeIngredientRow = (tempId) => {
    setForm((prev) => ({
      ...prev,
      ingredients: prev.ingredients.filter((row) => row.tempId !== tempId),
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.dish_name) {
      toast.error('Reçete adı zorunludur');
      return;
    }
    const payload = {
      dish_name: form.dish_name,
      category: form.category,
      portion_size: form.portion_size,
      preparation_time: Number(form.preparation_time),
      selling_price: Number(form.selling_price),
      notes: form.notes,
      ingredients: form.ingredients
        .filter((row) => row.ingredient_id)
        .map((row) => ({
          ingredient_id: row.ingredient_id,
          quantity: Number(row.quantity || 0),
          waste_pct: Number(row.waste_pct || 0),
        })),
    };

    if (!payload.ingredients.length) {
      toast.error('En az 1 malzeme seçmelisiniz');
      return;
    }

    try {
      setSubmitting(true);
      await axios.post('/fnb/recipes', payload);
      toast.success('Reçete başarıyla kaydedildi');
      setDialogOpen(false);
      resetForm();
      fetchData();
    } catch (error) {
      console.error('Recipe create failed', error);
      toast.error('Reçete kaydedilemedi');
    } finally {
      setSubmitting(false);
    }
  };

  const getIngredientDetails = (ingredientId) =>
    ingredients.find((ing) => ing.id === ingredientId);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="bg-gradient-to-r from-amber-50 to-amber-100 border-amber-200">
          <CardContent className="p-4">
            <p className="text-xs text-amber-600 font-semibold tracking-wide uppercase">Toplam Reçete</p>
            <p className="text-3xl font-bold text-amber-900 mt-1">{stats.total}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-green-50 to-green-100 border-green-200">
          <CardContent className="p-4">
            <p className="text-xs text-green-600 font-semibold tracking-wide uppercase">Ortalama Kâr Marjı</p>
            <p className="text-3xl font-bold text-green-900 mt-1">%{stats.avg_gp.toFixed(1)}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-blue-50 to-blue-100 border-blue-200">
          <CardContent className="p-4">
            <p className="text-xs text-blue-600 font-semibold tracking-wide uppercase">Ortalama Gıda Maliyeti</p>
            <p className="text-3xl font-bold text-blue-900 mt-1">₺{stats.avg_cost.toFixed(2)}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-indigo-50 to-indigo-100 border-indigo-200">
          <CardContent className="p-4">
            <p className="text-xs text-indigo-600 font-semibold tracking-wide uppercase">En Yüksek Kâr Marjı</p>
            <p className="text-lg font-bold text-indigo-900 mt-1 truncate">
              {stats.best_gp ? `${stats.best_gp.dish_name} (%${stats.best_gp.gp_percentage})` : '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-col gap-6 lg:flex-row">
        <Card className="lg:w-1/3 shadow-sm border-gray-200">
          <CardHeader className="flex flex-row items-center justify-between bg-gray-50 border-b border-gray-100 pb-4">
            <CardTitle className="flex items-center gap-2 text-base text-gray-800">
              <CookingPot className="w-5 h-5 text-amber-600" />
              Reçeteler
            </CardTitle>
            <Dialog open={dialogOpen} onOpenChange={(open) => {
              setDialogOpen(open);
              if (!open) resetForm();
            }}>
              <Button size="sm" onClick={() => setDialogOpen(true)} className="bg-amber-500 hover:bg-amber-600 text-white border-0">
                <Plus className="w-4 h-4 mr-1.5" />
                Yeni Reçete
              </Button>
              <DialogContent className="max-w-3xl">
                <DialogHeader>
                  <DialogTitle>Yeni Reçete Oluştur</DialogTitle>
                </DialogHeader>
                <form className="space-y-5" onSubmit={handleSubmit}>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <Label className="font-medium text-gray-700">Yemek Adı <span className="text-red-500">*</span></Label>
                      <Input
                        className="mt-1"
                        value={form.dish_name}
                        onChange={(e) => setForm({ ...form, dish_name: e.target.value })}
                        required
                        placeholder="Örn: Izgara Somon"
                      />
                    </div>
                    <div>
                      <Label className="font-medium text-gray-700">Kategori</Label>
                      <select
                        value={form.category}
                        onChange={(e) => setForm({ ...form, category: e.target.value })}
                        className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                      >
                        {categoryOptions.map((option) => (
                          <option key={option} value={option}>
                            {categoryLabels[option] || option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <Label className="font-medium text-gray-700">Porsiyon</Label>
                      <Input
                        className="mt-1"
                        value={form.portion_size}
                        onChange={(e) => setForm({ ...form, portion_size: e.target.value })}
                        placeholder="Örn: 1 porsiyon"
                      />
                    </div>
                    <div>
                      <Label className="font-medium text-gray-700">Hazırlık Süresi (dk)</Label>
                      <Input
                        className="mt-1"
                        type="number"
                        value={form.preparation_time}
                        onChange={(e) => setForm({ ...form, preparation_time: e.target.value })}
                        min={1}
                      />
                    </div>
                    <div>
                      <Label className="font-medium text-gray-700">Satış Fiyatı (₺)</Label>
                      <Input
                        className="mt-1"
                        type="number"
                        value={form.selling_price}
                        onChange={(e) => setForm({ ...form, selling_price: e.target.value })}
                        min={0}
                        step="0.01"
                      />
                    </div>
                  </div>

                  <div>
                    <Label className="font-medium text-gray-700">Notlar (Plating, servis önerisi vb.)</Label>
                    <Textarea
                      className="mt-1"
                      value={form.notes}
                      onChange={(e) => setForm({ ...form, notes: e.target.value })}
                      rows={2}
                      placeholder="Servis edilirken limon dilimi eklenmeli..."
                    />
                  </div>

                  <div className="space-y-3 bg-gray-50 p-4 rounded-xl border border-gray-100">
                    <div className="flex items-center justify-between mb-2">
                      <Label className="text-base font-semibold text-gray-800 flex items-center gap-2">
                        <UtensilsCrossed className="w-4 h-4 text-gray-500" />
                        Malzemeler
                      </Label>
                      <Button type="button" variant="outline" size="sm" onClick={addIngredientRow} className="text-amber-600 border-amber-200 hover:bg-amber-50">
                        <Plus className="w-4 h-4 mr-1" /> Malzeme Ekle
                      </Button>
                    </div>
                    <div className="space-y-3 max-h-72 overflow-y-auto pr-2 custom-scrollbar">
                      {form.ingredients.map((row) => {
                        const ingredient = getIngredientDetails(row.ingredient_id);
                        const lineCost =
                          row.quantity *
                          (ingredient?.unit_cost || 0) *
                          (1 + (row.waste_pct || 0) / 100);
                        return (
                          <Card key={row.tempId} className="border-gray-200 shadow-sm">
                            <CardContent className="p-4 space-y-3">
                              <div className="grid gap-3 md:grid-cols-2">
                                <div>
                                  <Label className="text-xs text-gray-500 uppercase tracking-wide">Malzeme Seçin</Label>
                                  <select
                                    value={row.ingredient_id}
                                    onChange={(e) =>
                                      handleIngredientChange(row.tempId, 'ingredient_id', e.target.value)
                                    }
                                    className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                                  >
                                    <option value="">Seçiniz...</option>
                                    {ingredients.map((ing) => (
                                      <option key={ing.id} value={ing.id}>
                                        {ing.name} (₺{ing.unit_cost.toFixed(2)} / {ing.unit})
                                      </option>
                                    ))}
                                  </select>
                                </div>
                                <div>
                                  <Label className="text-xs text-gray-500 uppercase tracking-wide">Miktar ({ingredient?.unit || 'birim'})</Label>
                                  <Input
                                    className="mt-1"
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={row.quantity}
                                    onChange={(e) =>
                                      handleIngredientChange(row.tempId, 'quantity', e.target.value)
                                    }
                                  />
                                </div>
                              </div>
                              <div className="grid gap-3 md:grid-cols-2">
                                <div>
                                  <Label className="text-xs text-gray-500 uppercase tracking-wide">Fire Oranı (%)</Label>
                                  <Input
                                    className="mt-1"
                                    type="number"
                                    min="0"
                                    max="100"
                                    value={row.waste_pct}
                                    onChange={(e) =>
                                      handleIngredientChange(row.tempId, 'waste_pct', e.target.value)
                                    }
                                  />
                                </div>
                                <div className="flex items-end justify-between bg-gray-50 px-3 py-2 rounded-lg border border-gray-100">
                                  <div>
                                    <Label className="text-[10px] text-gray-400 uppercase tracking-wide">Satır Maliyeti</Label>
                                    <p className="text-sm font-bold text-gray-900">
                                      ₺{lineCost.toFixed(2)}
                                    </p>
                                  </div>
                                  {form.ingredients.length > 1 && (
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      className="text-red-500 hover:text-red-700 hover:bg-red-50 h-8 px-2"
                                      onClick={() => removeIngredientRow(row.tempId)}
                                    >
                                      Kaldır
                                    </Button>
                                  )}
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  </div>

                  <DialogFooter className="pt-2">
                    <Button variant="outline" type="button" onClick={() => setDialogOpen(false)} disabled={submitting}>
                      İptal
                    </Button>
                    <Button type="submit" disabled={submitting} className="bg-amber-500 hover:bg-amber-600 text-white">
                      {submitting ? 'Kaydediliyor...' : 'Reçeteyi Kaydet'}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent className="p-0 max-h-[600px] overflow-y-auto">
            {loading && <div className="p-6 text-center text-sm text-gray-500">Yükleniyor...</div>}
            {!loading && recipes.length === 0 && (
              <div className="p-8 text-center border-b border-gray-100">
                <CookingPot className="w-10 h-10 mx-auto text-gray-300 mb-2" />
                <p className="text-sm text-gray-500">Henüz reçete yok. Lütfen yeni bir reçete ekleyin.</p>
              </div>
            )}
            <div className="divide-y divide-gray-100">
              {recipes.map((recipe) => (
                <div
                  key={recipe.id}
                  className={`p-4 cursor-pointer transition-colors ${
                    selectedRecipe?.id === recipe.id
                      ? 'bg-amber-50 border-l-4 border-l-amber-500'
                      : 'hover:bg-gray-50 border-l-4 border-l-transparent'
                  }`}
                  onClick={() => setSelectedRecipe(recipe)}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="font-bold text-gray-900">{recipe.dish_name}</p>
                    <Badge variant="outline" className={`text-[10px] ${
                      recipe.category === 'main' ? 'bg-orange-50 text-orange-700 border-orange-200' :
                      recipe.category === 'appetizer' ? 'bg-green-50 text-green-700 border-green-200' :
                      recipe.category === 'dessert' ? 'bg-pink-50 text-pink-700 border-pink-200' :
                      'bg-gray-100 text-gray-700 border-gray-200'
                    }`}>
                      {categoryLabels[recipe.category] || recipe.category}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500 font-medium">Maliyet: <span className="text-gray-800">₺{recipe.total_cost?.toFixed(2) || '0.00'}</span></span>
                    <span className={`font-bold ${recipe.gp_percentage > 60 ? 'text-emerald-600' : recipe.gp_percentage > 40 ? 'text-amber-600' : 'text-red-500'}`}>
                      Marj: %{recipe.gp_percentage || 0}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="flex-1 shadow-sm border-gray-200">
          <CardHeader className="bg-gray-50 border-b border-gray-100 pb-4">
            <CardTitle className="flex items-center gap-2 text-lg text-gray-800">
              <CookingPot className="w-5 h-5 text-indigo-500" />
              {selectedRecipe ? selectedRecipe.dish_name : 'Reçete Detayı'}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            {!selectedRecipe && (
              <div className="flex flex-col items-center justify-center py-20 text-gray-400">
                <UtensilsCrossed className="w-16 h-16 mb-4 text-gray-200" />
                <p>Reçete detaylarını görmek için sol taraftan bir öğe seçin.</p>
              </div>
            )}
            {selectedRecipe && (
              <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="rounded-xl border border-emerald-100 bg-gradient-to-br from-emerald-50 to-green-50 p-4">
                    <p className="text-xs font-semibold text-emerald-600 uppercase tracking-wide flex items-center gap-1.5"><Percent className="w-3.5 h-3.5"/> Kâr Marjı (GP)</p>
                    <p className="text-3xl font-extrabold text-emerald-700 mt-2">
                      %{selectedRecipe.gp_percentage || 0}
                    </p>
                  </div>
                  <div className="rounded-xl border border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-50 p-4">
                    <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide flex items-center gap-1.5"><TrendingUp className="w-3.5 h-3.5"/> Gıda Maliyeti</p>
                    <p className="text-3xl font-extrabold text-blue-700 mt-2">
                      ₺{selectedRecipe.total_cost?.toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-xl border border-amber-100 bg-gradient-to-br from-amber-50 to-orange-50 p-4">
                    <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide flex items-center gap-1.5"><DollarSign className="w-3.5 h-3.5"/> Satış Fiyatı</p>
                    <p className="text-3xl font-extrabold text-amber-700 mt-2">
                      ₺{selectedRecipe.selling_price?.toFixed(2)}
                    </p>
                  </div>
                </div>
                
                <div className="grid gap-4 md:grid-cols-2 bg-gray-50 rounded-xl p-4 border border-gray-100">
                  <div className="flex items-center gap-3 text-sm text-gray-700">
                    <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center shrink-0">
                      <Flame className="w-4 h-4 text-orange-500" />
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 font-medium">Porsiyon</p>
                      <p className="font-semibold">{selectedRecipe.portion_size || '1 porsiyon'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-gray-700">
                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                      <Timer className="w-4 h-4 text-blue-500" />
                    </div>
                    <div>
                      <p className="text-xs text-gray-500 font-medium">Hazırlık Süresi</p>
                      <p className="font-semibold">{selectedRecipe.preparation_time || 0} dakika</p>
                    </div>
                  </div>
                </div>

                {selectedRecipe.notes && (
                  <div className="bg-amber-50/50 border border-amber-100 p-4 rounded-xl">
                    <h4 className="text-xs font-bold text-amber-800 uppercase tracking-wide mb-1">Notlar</h4>
                    <p className="text-sm text-amber-900">{selectedRecipe.notes}</p>
                  </div>
                )}
                
                <Separator className="bg-gray-200" />
                
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-base font-bold text-gray-800 flex items-center gap-2">
                      Malzeme Dağılımı
                      <Badge variant="secondary" className="ml-2 bg-gray-100 text-gray-600 hover:bg-gray-200">{selectedRecipe.ingredient_count || 0} Adet</Badge>
                    </h4>
                  </div>
                  <div className="space-y-2.5">
                    {selectedRecipe.cost_breakdown?.map((line) => (
                      <div
                        key={`${line.ingredient_id}-${line.ingredient_name}`}
                        className="flex flex-col rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm md:flex-row md:items-center md:justify-between shadow-sm hover:border-gray-300 transition-colors"
                      >
                        <div>
                          <p className="font-bold text-gray-900 text-base">{line.ingredient_name}</p>
                          <p className="text-xs text-gray-500 mt-0.5 font-medium">
                            Kullanım: <span className="text-gray-700">{line.quantity} {line.unit}</span> <span className="mx-1 text-gray-300">•</span> Birim Fiyat: <span className="text-gray-700">₺{line.unit_cost} / {line.unit}</span>
                          </p>
                        </div>
                        <div className="text-right mt-2 md:mt-0">
                          <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Maliyet</p>
                          <p className="text-lg font-bold text-gray-900">₺{line.line_cost?.toFixed(2)}</p>
                        </div>
                      </div>
                    ))}
                    {!selectedRecipe.cost_breakdown?.length && (
                      <div className="text-center py-6 border border-dashed border-gray-200 rounded-lg">
                        <p className="text-sm text-gray-500">Bu reçeteye ait malzeme bulunamadı.</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default RecipeCostingManager;
