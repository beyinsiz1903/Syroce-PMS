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
import { Plus, CookingPot, Flame, Timer, UtensilsCrossed } from 'lucide-react';

const categoryOptions = [
  'appetizer',
  'main',
  'dessert',
  'beverage',
  'room_service',
];

const RecipeCostingManager = () => {
  const [recipes, setRecipes] = useState([]);
  const [ingredients, setIngredients] = useState([]);
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [form, setForm] = useState({
    dish_name: '',
    category: 'main',
    portion_size: '1 portion',
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
      toast.error('F&B verileri yüklenemedi');
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
      portion_size: '1 portion',
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
      toast.error('Yemek adı zorunludur');
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
      toast.success('Recipe kaydedildi');
      setDialogOpen(false);
      resetForm();
      fetchData();
    } catch (error) {
      console.error('Recipe create failed', error);
      toast.error('Recipe kaydedilemedi');
    } finally {
      setSubmitting(false);
    }
  };

  const getIngredientDetails = (ingredientId) =>
    ingredients.find((ing) => ing.id === ingredientId);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="bg-gradient-to-r from-orange-50 to-orange-100 border-orange-200">
          <CardContent className="p-4">
            <p className="text-xs text-orange-600 font-semibold">Toplam Recipe</p>
            <p className="text-3xl font-bold">{stats.total}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-green-50 to-green-100 border-green-200">
          <CardContent className="p-4">
            <p className="text-xs text-green-600 font-semibold">Ortalama GP%</p>
            <p className="text-3xl font-bold">{stats.avg_gp.toFixed(1)}%</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-blue-50 to-blue-100 border-blue-200">
          <CardContent className="p-4">
            <p className="text-xs text-blue-600 font-semibold">Ortalama Food Cost</p>
            <p className="text-3xl font-bold">€{stats.avg_cost.toFixed(2)}</p>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-r from-purple-50 to-purple-100 border-purple-200">
          <CardContent className="p-4">
            <p className="text-xs text-purple-600 font-semibold">En Yüksek GP</p>
            <p className="text-sm font-bold">
              {stats.best_gp ? `${stats.best_gp.dish_name} (${stats.best_gp.gp_percentage}%)` : '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row">
        <Card className="lg:w-1/3">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <CookingPot className="w-4 h-4 text-orange-600" />
              Recipes
            </CardTitle>
            <Dialog open={dialogOpen} onOpenChange={(open) => {
              setDialogOpen(open);
              if (!open) resetForm();
            }}>
              <Button size="sm" onClick={() => setDialogOpen(true)}>
                <Plus className="w-4 h-4 mr-1" />
                Yeni Recipe
              </Button>
              <DialogContent className="max-w-3xl">
                <DialogHeader>
                  <DialogTitle>Yeni Recipe Oluştur</DialogTitle>
                </DialogHeader>
                <form className="space-y-4" onSubmit={handleSubmit}>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <Label>Yemek Adı</Label>
                      <Input
                        value={form.dish_name}
                        onChange={(e) => setForm({ ...form, dish_name: e.target.value })}
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
                        {categoryOptions.map((option) => (
                          <option key={option} value={option}>
                            {option.replace('_', ' ')}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <Label>Portion</Label>
                      <Input
                        value={form.portion_size}
                        onChange={(e) => setForm({ ...form, portion_size: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label>Hazırlık Süresi (dk)</Label>
                      <Input
                        type="number"
                        value={form.preparation_time}
                        onChange={(e) => setForm({ ...form, preparation_time: e.target.value })}
                        min={1}
                      />
                    </div>
                    <div>
                      <Label>Satış Fiyatı (€)</Label>
                      <Input
                        type="number"
                        value={form.selling_price}
                        onChange={(e) => setForm({ ...form, selling_price: e.target.value })}
                        min={0}
                        step="0.01"
                      />
                    </div>
                  </div>

                  <div>
                    <Label>Notlar</Label>
                    <Textarea
                      value={form.notes}
                      onChange={(e) => setForm({ ...form, notes: e.target.value })}
                      rows={3}
                      placeholder="Servis önerisi, plating notu..."
                    />
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label>Malzemeler</Label>
                      <Button type="button" variant="outline" size="sm" onClick={addIngredientRow}>
                        + Malzeme
                      </Button>
                    </div>
                    <div className="space-y-3 max-h-72 overflow-y-auto pr-2">
                      {form.ingredients.map((row) => {
                        const ingredient = getIngredientDetails(row.ingredient_id);
                        const lineCost =
                          row.quantity *
                          (ingredient?.unit_cost || 0) *
                          (1 + (row.waste_pct || 0) / 100);
                        return (
                          <Card key={row.tempId}>
                            <CardContent className="p-3 space-y-2">
                              <div className="grid gap-2 md:grid-cols-2">
                                <div>
                                  <Label>Ingredient</Label>
                                  <select
                                    value={row.ingredient_id}
                                    onChange={(e) =>
                                      handleIngredientChange(row.tempId, 'ingredient_id', e.target.value)
                                    }
                                    className="w-full rounded-md border border-input px-3 py-2 text-sm"
                                  >
                                    <option value="">Seçiniz</option>
                                    {ingredients.map((ing) => (
                                      <option key={ing.id} value={ing.id}>
                                        {ing.name} ({ing.unit_cost.toFixed(2)} € / {ing.unit})
                                      </option>
                                    ))}
                                  </select>
                                </div>
                                <div>
                                  <Label>Miktar ({ingredient?.unit || 'unit'})</Label>
                                  <Input
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
                              <div className="grid gap-2 md:grid-cols-2">
                                <div>
                                  <Label>Fire %</Label>
                                  <Input
                                    type="number"
                                    min="0"
                                    max="100"
                                    value={row.waste_pct}
                                    onChange={(e) =>
                                      handleIngredientChange(row.tempId, 'waste_pct', e.target.value)
                                    }
                                  />
                                </div>
                                <div className="flex items-end justify-between">
                                  <div>
                                    <Label>Satır Maliyeti</Label>
                                    <p className="text-sm font-semibold text-gray-800">
                                      €{lineCost.toFixed(2)}
                                    </p>
                                  </div>
                                  {form.ingredients.length > 1 && (
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      className="text-red-500"
                                      onClick={() => removeIngredientRow(row.tempId)}
                                    >
                                      Sil
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

                  <DialogFooter>
                    <Button type="submit" disabled={submitting}>
                      {submitting ? 'Kaydediliyor...' : 'Recipe Kaydet'}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[540px] overflow-y-auto pr-1">
            {loading && <p className="text-sm text-gray-500">Yükleniyor...</p>}
            {!loading && recipes.length === 0 && (
              <p className="text-sm text-gray-500">Henüz recipe yok. Yeni recipe ekleyin.</p>
            )}
            {recipes.map((recipe) => (
              <div
                key={recipe.id}
                className={`p-3 rounded-md border cursor-pointer transition ${
                  selectedRecipe?.id === recipe.id
                    ? 'border-orange-500 bg-orange-50'
                    : 'border-gray-200 hover:border-orange-200'
                }`}
                onClick={() => setSelectedRecipe(recipe)}
              >
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-sm">{recipe.dish_name}</p>
                  <Badge variant="outline" className="text-[11px]">
                    {recipe.category}
                  </Badge>
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
                  <span>Food Cost: €{recipe.total_cost}</span>
                  <span>GP {recipe.gp_percentage}%</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="flex-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UtensilsCrossed className="w-4 h-4 text-orange-600" />
              {selectedRecipe ? selectedRecipe.dish_name : 'Recipe Detay'}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!selectedRecipe && (
              <p className="text-sm text-gray-500">Recipe seçmek için listeden bir öğe seçin.</p>
            )}
            {selectedRecipe && (
              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <Card className="bg-green-50 border-green-200">
                    <CardContent className="p-3">
                      <p className="text-xs text-green-600">GP%</p>
                      <p className="text-2xl font-bold text-green-700">
                        {selectedRecipe.gp_percentage || 0}%
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="bg-blue-50 border-blue-200">
                    <CardContent className="p-3">
                      <p className="text-xs text-blue-600">Food Cost</p>
                      <p className="text-2xl font-bold text-blue-700">
                        €{selectedRecipe.total_cost?.toFixed(2)}
                      </p>
                    </CardContent>
                  </Card>
                  <Card className="bg-orange-50 border-orange-200">
                    <CardContent className="p-3">
                      <p className="text-xs text-orange-600">Satış Fiyatı</p>
                      <p className="text-2xl font-bold text-orange-700">
                        €{selectedRecipe.selling_price?.toFixed(2)}
                      </p>
                    </CardContent>
                  </Card>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <Flame className="w-4 h-4 text-orange-500" />
                    {selectedRecipe.portion_size || '1 portion'}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <Timer className="w-4 h-4 text-blue-500" />
                    {selectedRecipe.preparation_time || 0} dk
                  </div>
                </div>
                <Separator />
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-700">
                    Ingredient Breakdown ({selectedRecipe.ingredient_count || 0})
                  </h4>
                  <div className="space-y-2">
                    {selectedRecipe.cost_breakdown?.map((line) => (
                      <div
                        key={`${line.ingredient_id}-${line.ingredient_name}`}
                        className="flex flex-col rounded border border-gray-100 bg-gray-50 px-3 py-2 text-sm md:flex-row md:items-center md:justify-between"
                      >
                        <div>
                          <p className="font-semibold text-gray-800">{line.ingredient_name}</p>
                          <p className="text-xs text-gray-500">
                            {line.quantity} {line.unit} • €{line.unit_cost} / {line.unit}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-gray-400">Satır Maliyeti</p>
                          <p className="font-semibold text-gray-800">€{line.line_cost}</p>
                        </div>
                      </div>
                    ))}
                    {!selectedRecipe.cost_breakdown?.length && (
                      <p className="text-xs text-gray-500">Malzeme bulunamadı</p>
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
