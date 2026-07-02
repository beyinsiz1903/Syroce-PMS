import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button }   from './ui/button';
import { Badge }    from './ui/badge';
import { Input }    from './ui/input';
import { Label }    from './ui/label';
import { Textarea } from './ui/textarea';
import { Switch }   from './ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from './ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from './ui/alert-dialog';
import { UtensilsCrossed, RefreshCw, Search, Plus, Pencil, Trash2, Loader2, TrendingUp, Tag } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/* ── constants ── */
const DEFAULT_CATEGORIES = ['Ana Yemek', 'Başlangıç', 'Tatlı', 'İçecek', 'Alkollü', 'Atıştırmalık'];

const CATEGORY_COLORS = {
  'Ana Yemek':    'bg-orange-50 border-orange-200 text-orange-700',
  'Başlangıç':   'bg-green-50  border-green-200  text-green-700',
  'Tatlı':        'bg-pink-50   border-pink-200   text-pink-700',
  'İçecek':      'bg-blue-50   border-blue-200   text-blue-700',
  'Alkollü':     'bg-purple-50 border-purple-200 text-purple-700',
  'Atıştırmalık':'bg-amber-50  border-amber-200  text-amber-700',
};

const blankForm = {
  name:        '',
  category:    'Ana Yemek',
  price:       '',
  cost:        '',
  tax_rate:    '0.10',
  description: '',
  available:   true,
  image_url:   '',
};

/* ── main component ── */
const POSMenuItems = ({ outletId, onItemSelect, allowEdit = true }) => {
  const { t } = useTranslation();
  const [menuItems,        setMenuItems]        = useState([]);
  const [loading,          setLoading]          = useState(true);
  const [searchTerm,       setSearchTerm]       = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [dialogOpen,       setDialogOpen]       = useState(false);
  const [editing,          setEditing]          = useState(null);
  const [form,             setForm]             = useState(blankForm);
  const [saving,           setSaving]           = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params = outletId ? { outlet_id: outletId } : {};
      const res    = await axios.get('/pos/menu-items', { params });
      const list   = Array.isArray(res.data) ? res.data : (res.data.menu_items || []);
      setMenuItems(list);
    } catch {
      toast.error('Menü yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [outletId]);

  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditing(null); setForm(blankForm); setDialogOpen(true); };

  const openEdit = (item) => {
    setEditing(item);
    setForm({
      name:        item.name        || '',
      category:    item.category    || 'Ana Yemek',
      price:       String(item.price  ?? ''),
      cost:        String(item.cost   ?? ''),
      tax_rate:    String(item.tax_rate ?? '0.10'),
      description: item.description || '',
      available:   item.available   !== false,
      image_url:   item.image_url   || '',
    });
    setDialogOpen(true);
  };

  const submit = async () => {
    if (!form.name.trim() || !form.price) {
      toast.error('Ürün adı ve fiyat zorunludur');
      return;
    }
    try {
      setSaving(true);
      const payload = {
        name:        form.name.trim(),
        category:    form.category,
        price:       Number(form.price),
        cost:        form.cost ? Number(form.cost) : null,
        tax_rate:    Number(form.tax_rate || 0.10),
        description: form.description.trim() || null,
        available:   form.available,
        image_url:   form.image_url.trim() || null,
        outlet_id:   outletId || null,
      };
      if (editing) {
        await axios.put(`/pos/menu-item/${editing.id}`, payload);
        toast.success('Ürün güncellendi');
      } else {
        await axios.post('/pos/menu-item', payload);
        toast.success('Ürün eklendi');
      }
      setDialogOpen(false);
      await load();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Kayıt başarısız');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (item) => {
    try {
      await axios.delete(`/pos/menu-item/${item.id}`);
      toast.success('Ürün silindi');
      await load();
    } catch {
      toast.error('Silme başarısız');
    }
  };

  const categories = useMemo(() => {
    const set = new Set(DEFAULT_CATEGORIES);
    menuItems.forEach(i => i.category && set.add(i.category));
    return ['all', ...Array.from(set)];
  }, [menuItems]);

  const filteredItems = useMemo(() => menuItems.filter(item => {
    const matchSearch   = (item.name || '').toLowerCase().includes(searchTerm.toLowerCase());
    const matchCategory = selectedCategory === 'all' || item.category === selectedCategory;
    return matchSearch && matchCategory;
  }), [menuItems, searchTerm, selectedCategory]);

  /* category pill counts */
  const catCounts = useMemo(() => {
    const m = { all: menuItems.length };
    menuItems.forEach(i => { m[i.category] = (m[i.category] || 0) + 1; });
    return m;
  }, [menuItems]);

  /* ── dialog form ── */
  const itemForm = (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <Label className="text-sm font-medium">Ürün Adı <span className="text-red-500">*</span></Label>
          <Input
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
            placeholder="Sezar Salata"
            data-testid="input-menu-name"
            className="mt-1"
          />
        </div>
        <div>
          <Label className="text-sm font-medium">Kategori</Label>
          <Select value={form.category} onValueChange={v => setForm({ ...form, category: v })}>
            <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DEFAULT_CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-sm font-medium">KDV Oranı</Label>
          <Select value={form.tax_rate} onValueChange={v => setForm({ ...form, tax_rate: v })}>
            <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[['0.01','%1'],['0.08','%8'],['0.10','%10'],['0.18','%18'],['0.20','%20']].map(([v,l]) => (
                <SelectItem key={v} value={v}>{l}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-sm font-medium">Satış Fiyatı (₺) <span className="text-red-500">*</span></Label>
          <Input
            type="number" step="0.01"
            value={form.price}
            onChange={e => setForm({ ...form, price: e.target.value })}
            data-testid="input-menu-price"
            className="mt-1"
          />
        </div>
        <div>
          <Label className="text-sm font-medium">Maliyet (₺)</Label>
          <Input
            type="number" step="0.01"
            value={form.cost}
            onChange={e => setForm({ ...form, cost: e.target.value })}
            className="mt-1"
          />
        </div>
        <div className="col-span-2">
          <Label className="text-sm font-medium">Açıklama</Label>
          <Textarea
            rows={2}
            value={form.description}
            onChange={e => setForm({ ...form, description: e.target.value })}
            className="mt-1"
          />
        </div>
        <div className="col-span-2">
          <Label className="text-sm font-medium">Görsel URL (opsiyonel)</Label>
          <Input
            value={form.image_url}
            onChange={e => setForm({ ...form, image_url: e.target.value })}
            placeholder="https://..."
            className="mt-1"
          />
        </div>
        <div className="col-span-2 flex items-center justify-between py-1">
          <div>
            <Label htmlFor="available-switch" className="text-sm font-medium cursor-pointer">Satışta</Label>
            <p className="text-xs text-gray-400 mt-0.5">Kapalı ise menüde "Tükendi" görünür</p>
          </div>
          <Switch
            id="available-switch"
            checked={form.available}
            onCheckedChange={v => setForm({ ...form, available: v })}
          />
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
            <UtensilsCrossed className="w-5 h-5 text-amber-600" />
            Menü Kalemleri
            <span className="text-sm font-normal text-gray-400">({filteredItems.length})</span>
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">Fiyat, KDV, kategori ve stok yönetimi</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
            Yenile
          </Button>
          {allowEdit && (
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm" onClick={openNew} data-testid="button-new-menu-item"
                  className="bg-amber-500 hover:bg-amber-600 text-white border-0">
                  <Plus className="w-4 h-4 mr-1.5" />
                  Yeni Ürün
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg">
                <DialogHeader>
                  <DialogTitle>{editing ? 'Ürünü Düzenle' : 'Yeni Menü Ürünü'}</DialogTitle>
                  <DialogDescription>Fiyat, KDV, kategori ve stok durumu bilgileri.</DialogDescription>
                </DialogHeader>
                {itemForm}
                <DialogFooter>
                  <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>İptal</Button>
                  <Button onClick={submit} disabled={saving} data-testid="button-save-menu-item"
                    className="bg-amber-500 hover:bg-amber-600 text-white border-0">
                    {saving ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />Kaydediliyor…</> : editing ? 'Güncelle' : 'Ekle'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>

      {/* Search + category filter */}
      <div className="space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            placeholder="Ürün ara…"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {categories.map(cat => {
            const isActive = selectedCategory === cat;
            const colorCls = cat !== 'all' ? (CATEGORY_COLORS[cat] || 'bg-gray-50 border-gray-200 text-gray-700') : '';
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-medium transition-all
                  ${isActive
                    ? cat === 'all'
                      ? 'bg-gray-900 border-gray-900 text-white'
                      : `${colorCls} ring-2 ring-offset-1 ring-current`
                    : cat === 'all'
                      ? 'bg-white border-gray-200 text-gray-600 hover:border-gray-400'
                      : `${colorCls} opacity-60 hover:opacity-100`
                  }`}
              >
                {cat === 'all' ? 'Tümü' : cat}
                <span className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold
                  ${isActive ? 'bg-white/20' : 'bg-black/10'}`}>
                  {catCounts[cat] || 0}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white py-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <UtensilsCrossed className="w-8 h-8 text-gray-400" />
          </div>
          <p className="font-semibold text-gray-700">
            {searchTerm ? 'Aramanızla eşleşen ürün yok' : 'Bu kategoride ürün yok'}
          </p>
          {allowEdit && !searchTerm && (
            <p className="text-sm text-gray-400 mt-1">"Yeni Ürün" ile menünüze ekleme yapın</p>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredItems.map(item => {
            const price   = Number(item.price || 0);
            const cost    = Number(item.cost  || 0);
            const margin  = price > 0 ? ((price - cost) / price * 100) : 0;
            const taxPct  = Math.round(Number(item.tax_rate || 0.10) * 100);
            const catCls  = CATEGORY_COLORS[item.category] || 'bg-gray-50 border-gray-200 text-gray-600';

            return (
              <div
                key={item.id}
                data-testid={`card-menu-${item.id}`}
                className={`group relative bg-white rounded-2xl border border-gray-200 shadow-sm
                  hover:shadow-md hover:-translate-y-0.5 transition-all duration-200
                  ${!item.available ? 'opacity-60' : ''}`}
              >
                {/* Unavailable ribbon */}
                {!item.available && (
                  <div className="absolute top-3 right-3 z-10">
                    <span className="text-xs font-bold bg-red-100 border border-red-300 text-red-600 px-2 py-0.5 rounded-full">
                      Tükendi
                    </span>
                  </div>
                )}

                <div className="p-4">
                  {/* Title row */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex-1 min-w-0">
                      <h3
                        className={`font-bold text-gray-900 leading-tight ${onItemSelect ? 'cursor-pointer hover:text-amber-600' : ''}`}
                        onClick={() => onItemSelect && onItemSelect(item)}
                      >
                        {item.name}
                      </h3>
                      {item.description && (
                        <p className="text-xs text-gray-400 mt-0.5 line-clamp-1">{item.description}</p>
                      )}
                    </div>
                    {/* Edit / Delete — shown on hover */}
                    {allowEdit && (
                      <div className="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => openEdit(item)}
                          data-testid={`button-edit-menu-${item.id}`}
                          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-700"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <button className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Ürün silinsin mi?</AlertDialogTitle>
                              <AlertDialogDescription>
                                <strong>"{item.name}"</strong> menüden kaldırılacak.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Vazgeç</AlertDialogCancel>
                              <AlertDialogAction onClick={() => remove(item)} className="bg-red-600 hover:bg-red-700">
                                Sil
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    )}
                  </div>

                  {/* Tags */}
                  <div className="flex items-center gap-1.5 mb-3 flex-wrap">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${catCls}`}>
                      {item.category}
                    </span>
                    <span className="text-xs text-gray-400 flex items-center gap-0.5">
                      <Tag className="w-3 h-3" /> KDV %{taxPct}
                    </span>
                  </div>

                  {/* Price + margin */}
                  <div className="flex items-end justify-between pt-3 border-t border-gray-100">
                    <div>
                      <p className="text-xl font-extrabold text-gray-900">
                        {price.toFixed(2)}
                        <span className="text-sm font-normal text-gray-400 ml-1">₺</span>
                      </p>
                      {cost > 0 && (
                        <p className="text-xs text-gray-400 mt-0.5">
                          Maliyet: {cost.toFixed(2)} ₺
                        </p>
                      )}
                    </div>
                    {cost > 0 && price > 0 && (
                      <div className="text-right">
                        <p className="text-xs text-gray-400 mb-1 flex items-center gap-1 justify-end">
                          <TrendingUp className="w-3 h-3" /> Marj
                        </p>
                        {/* Margin bar */}
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${margin > 60 ? 'bg-emerald-500' : margin > 40 ? 'bg-amber-400' : 'bg-red-400'}`}
                              style={{ width: `${Math.min(margin, 100)}%` }}
                            />
                          </div>
                          <span className={`text-sm font-bold ${margin > 60 ? 'text-emerald-600' : margin > 40 ? 'text-amber-600' : 'text-red-500'}`}>
                            %{margin.toFixed(0)}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default POSMenuItems;
