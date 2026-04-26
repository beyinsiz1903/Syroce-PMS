import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Switch } from './ui/switch';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from './ui/select';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from './ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from './ui/alert-dialog';
import {
  UtensilsCrossed, RefreshCw, Search, Plus, Pencil, Trash2,
} from 'lucide-react';

const DEFAULT_CATEGORIES = ['Ana Yemek', 'Baslangic', 'Tatli', 'Icecek', 'Alkollu', 'Atistirmalik'];

const blankForm = {
  name: '',
  category: 'Ana Yemek',
  price: '',
  cost: '',
  tax_rate: '0.10',
  description: '',
  available: true,
  image_url: '',
};

const POSMenuItems = ({ outletId, onItemSelect, allowEdit = true }) => {
  const [menuItems, setMenuItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blankForm);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params = outletId ? { outlet_id: outletId } : {};
      const res = await axios.get('/pos/menu-items', { params });
      const list = Array.isArray(res.data) ? res.data : (res.data.menu_items || []);
      setMenuItems(list);
    } catch (err) {
      console.error('Menu yuklenemedi:', err);
      toast.error('Menu yuklenemedi');
    } finally {
      setLoading(false);
    }
  }, [outletId]);

  useEffect(() => { load(); }, [load]);

  const openNew = () => {
    setEditing(null);
    setForm(blankForm);
    setDialogOpen(true);
  };

  const openEdit = (item) => {
    setEditing(item);
    setForm({
      name: item.name || '',
      category: item.category || 'Ana Yemek',
      price: String(item.price ?? ''),
      cost: String(item.cost ?? ''),
      tax_rate: String(item.tax_rate ?? '0.10'),
      description: item.description || '',
      available: item.available !== false,
      image_url: item.image_url || '',
    });
    setDialogOpen(true);
  };

  const submit = async () => {
    if (!form.name.trim() || !form.price) {
      toast.error('Ad ve fiyat zorunlu');
      return;
    }
    try {
      setSaving(true);
      const payload = {
        name: form.name.trim(),
        category: form.category,
        price: Number(form.price),
        cost: form.cost ? Number(form.cost) : null,
        tax_rate: Number(form.tax_rate || 0.10),
        description: form.description.trim() || null,
        available: form.available,
        image_url: form.image_url.trim() || null,
        outlet_id: outletId || null,
      };
      if (editing) {
        await axios.put(`/pos/menu-item/${editing.id}`, payload);
        toast.success('Urun guncellendi');
      } else {
        await axios.post('/pos/menu-item', payload);
        toast.success('Urun eklendi');
      }
      setDialogOpen(false);
      await load();
    } catch (err) {
      console.error('Menu kaydi hatasi:', err);
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Kayit basarisiz');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item) => {
    try {
      await axios.delete(`/pos/menu-item/${item.id}`);
      toast.success('Urun silindi');
      await load();
    } catch (err) {
      console.error('Urun silinemedi:', err);
      toast.error('Silme basarisiz');
    }
  };

  const categories = useMemo(() => {
    const set = new Set(DEFAULT_CATEGORIES);
    menuItems.forEach(i => i.category && set.add(i.category));
    return ['all', ...Array.from(set)];
  }, [menuItems]);

  const filteredItems = useMemo(() => menuItems.filter(item => {
    const matchesSearch = (item.name || '').toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || item.category === selectedCategory;
    return matchesSearch && matchesCategory;
  }), [menuItems, searchTerm, selectedCategory]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="flex items-center">
            <UtensilsCrossed className="w-5 h-5 mr-2 text-orange-600" />
            Menu ({filteredItems.length})
          </CardTitle>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Yenile
            </Button>
            {allowEdit && (
              <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogTrigger asChild>
                  <Button size="sm" onClick={openNew} data-testid="button-new-menu-item">
                    <Plus className="w-4 h-4 mr-2" />
                    Yeni Urun
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-lg">
                  <DialogHeader>
                    <DialogTitle>
                      {editing ? 'Urunu Duzenle' : 'Yeni Menu Urunu'}
                    </DialogTitle>
                    <DialogDescription>
                      Fiyat, KDV, kategori ve durum bilgisi.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="col-span-2">
                        <Label>Urun Adi *</Label>
                        <Input
                          value={form.name}
                          onChange={(e) => setForm({ ...form, name: e.target.value })}
                          placeholder="Cesar Salata"
                          data-testid="input-menu-name"
                        />
                      </div>
                      <div>
                        <Label>Kategori</Label>
                        <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {DEFAULT_CATEGORIES.map(c => (
                              <SelectItem key={c} value={c}>{c}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>KDV Orani</Label>
                        <Select value={form.tax_rate} onValueChange={(v) => setForm({ ...form, tax_rate: v })}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="0.01">%1</SelectItem>
                            <SelectItem value="0.08">%8</SelectItem>
                            <SelectItem value="0.10">%10</SelectItem>
                            <SelectItem value="0.18">%18</SelectItem>
                            <SelectItem value="0.20">%20</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Satis Fiyati (TL) *</Label>
                        <Input
                          type="number" step="0.01"
                          value={form.price}
                          onChange={(e) => setForm({ ...form, price: e.target.value })}
                          data-testid="input-menu-price"
                        />
                      </div>
                      <div>
                        <Label>Maliyet (TL)</Label>
                        <Input
                          type="number" step="0.01"
                          value={form.cost}
                          onChange={(e) => setForm({ ...form, cost: e.target.value })}
                        />
                      </div>
                      <div className="col-span-2">
                        <Label>Aciklama</Label>
                        <Textarea
                          rows={2}
                          value={form.description}
                          onChange={(e) => setForm({ ...form, description: e.target.value })}
                        />
                      </div>
                      <div className="col-span-2">
                        <Label>Gorsel URL (opsiyonel)</Label>
                        <Input
                          value={form.image_url}
                          onChange={(e) => setForm({ ...form, image_url: e.target.value })}
                          placeholder="https://..."
                        />
                      </div>
                      <div className="col-span-2 flex items-center justify-between">
                        <Label htmlFor="available-switch">Satista</Label>
                        <Switch
                          id="available-switch"
                          checked={form.available}
                          onCheckedChange={(v) => setForm({ ...form, available: v })}
                        />
                      </div>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
                      Iptal
                    </Button>
                    <Button onClick={submit} disabled={saving} data-testid="button-save-menu-item">
                      {saving ? 'Kaydediliyor...' : (editing ? 'Guncelle' : 'Ekle')}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Search */}
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Urun ara..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        {/* Category Filter */}
        <div className="flex flex-wrap gap-2 mb-4">
          {categories.map((cat) => (
            <Badge
              key={cat}
              variant={selectedCategory === cat ? 'default' : 'outline'}
              className="cursor-pointer"
              onClick={() => setSelectedCategory(cat)}
            >
              {cat === 'all' ? 'Tumu' : cat}
            </Badge>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-8">
            <RefreshCw className="w-8 h-8 animate-spin text-orange-600 mx-auto" />
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <UtensilsCrossed className="w-16 h-16 mx-auto mb-3 text-gray-300" />
            <p>Urun yok</p>
            {allowEdit && (
              <p className="text-sm mt-2">"Yeni Urun" ile menunuze ekleme yapin</p>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredItems.map((item) => {
              const price = Number(item.price || 0);
              const cost = Number(item.cost || 0);
              const margin = price > 0 ? ((price - cost) / price * 100) : 0;
              const taxPct = Math.round(Number(item.tax_rate || 0.10) * 100);
              return (
                <Card
                  key={item.id}
                  className={`hover:shadow-lg transition ${!item.available ? 'opacity-50' : ''}`}
                  data-testid={`card-menu-${item.id}`}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-gray-900 truncate cursor-pointer"
                          onClick={() => onItemSelect && onItemSelect(item)}>
                          {item.name}
                        </h3>
                        <div className="flex items-center gap-1 mt-1 flex-wrap">
                          <Badge variant="outline">{item.category}</Badge>
                          <Badge variant="outline" className="text-xs">KDV %{taxPct}</Badge>
                          {!item.available && (
                            <Badge variant="destructive" className="text-xs">Tukendi</Badge>
                          )}
                        </div>
                      </div>
                      {allowEdit && (
                        <div className="flex gap-1 ml-2">
                          <Button variant="ghost" size="icon" onClick={() => openEdit(item)}
                            data-testid={`button-edit-menu-${item.id}`}>
                            <Pencil className="w-4 h-4" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button variant="ghost" size="icon" className="text-red-600">
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Urun silinsin mi?</AlertDialogTitle>
                                <AlertDialogDescription>
                                  "{item.name}" menuden kaldirilacak.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Vazgec</AlertDialogCancel>
                                <AlertDialogAction onClick={() => remove(item)}
                                  className="bg-red-600 hover:bg-red-700">
                                  Sil
                                </AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </div>
                      )}
                    </div>
                    {item.description && (
                      <p className="text-sm text-gray-500 mt-1 line-clamp-2">{item.description}</p>
                    )}
                    <div className="flex items-center justify-between mt-3 pt-3 border-t">
                      <div>
                        <p className="text-2xl font-bold text-green-600">
                          {price.toFixed(2)}<span className="text-sm ml-1">TL</span>
                        </p>
                        {cost > 0 && (
                          <p className="text-xs text-gray-500">
                            Maliyet: {cost.toFixed(2)} TL
                          </p>
                        )}
                      </div>
                      {cost > 0 && price > 0 && (
                        <div className="text-right">
                          <p className="text-xs font-medium text-gray-600">Marj</p>
                          <p className="text-lg font-bold text-blue-600">
                            %{margin.toFixed(0)}
                          </p>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default POSMenuItems;
