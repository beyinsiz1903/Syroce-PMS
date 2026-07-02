import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button }   from './ui/button';
import { Badge }    from './ui/badge';
import { Input }    from './ui/input';
import { Label }    from './ui/label';
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
import {
  Plus, Pencil, Trash2, RefreshCw, Store, MapPin, Users, Clock,
  ChefHat, GlassWater, Coffee as CafeIcon, Sparkles, Bed, UtensilsCrossed,
  Loader2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

/* ── constants ── */
const OUTLET_TYPES = [
  { value: 'restaurant', label: 'Restoran',     icon: UtensilsCrossed, color: 'amber'  },
  { value: 'bar',        label: 'Bar',           icon: GlassWater,      color: 'indigo' },
  { value: 'cafe',       label: 'Kafe',          icon: CafeIcon,        color: 'yellow' },
  { value: 'spa',        label: 'SPA',           icon: Sparkles,        color: 'emerald'},
  { value: 'room_service',label:'Oda Servisi',   icon: Bed,             color: 'blue'   },
  { value: 'banquet',    label: 'Banket',        icon: ChefHat,         color: 'pink'   },
];

const TYPE_STYLE = {
  restaurant: { bg: 'bg-amber-50  border-amber-200  text-amber-700',  dot: 'bg-amber-400'  },
  bar:        { bg: 'bg-indigo-50 border-indigo-200 text-indigo-700', dot: 'bg-indigo-400' },
  cafe:       { bg: 'bg-yellow-50 border-yellow-200 text-yellow-700', dot: 'bg-yellow-400' },
  spa:        { bg: 'bg-emerald-50 border-emerald-200 text-emerald-700', dot: 'bg-emerald-400' },
  room_service:{ bg:'bg-blue-50   border-blue-200   text-blue-700',   dot: 'bg-blue-400'  },
  banquet:    { bg: 'bg-pink-50   border-pink-200   text-pink-700',   dot: 'bg-pink-400'  },
};

const blankForm = {
  outlet_name:   '',
  outlet_type:   'restaurant',
  location:      '',
  capacity:      '',
  opening_hours: '',
};

/* ── component ── */
const POSOutletManagement = ({ onChange }) => {
  const { t } = useTranslation();
  const [outlets,     setOutlets]    = useState([]);
  const [loading,     setLoading]    = useState(true);
  const [dialogOpen,  setDialogOpen] = useState(false);
  const [editing,     setEditing]    = useState(null);
  const [form,        setForm]       = useState(blankForm);
  const [saving,      setSaving]     = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res  = await axios.get('/pos/outlets');
      const list = Array.isArray(res.data) ? res.data : (res.data.outlets || []);
      setOutlets(list);
    } catch {
      toast.error('Satış noktaları yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openNew = () => {
    setEditing(null);
    setForm(blankForm);
    setDialogOpen(true);
  };

  const openEdit = (outlet) => {
    setEditing(outlet);
    setForm({
      outlet_name:   outlet.outlet_name || outlet.name || '',
      outlet_type:   outlet.outlet_type || outlet.type || 'restaurant',
      location:      outlet.location      || '',
      capacity:      outlet.capacity      || '',
      opening_hours: outlet.opening_hours || '',
    });
    setDialogOpen(true);
  };

  const submit = async () => {
    if (!form.outlet_name.trim() || !form.location.trim()) {
      toast.error('Ad ve konum zorunlu');
      return;
    }
    try {
      setSaving(true);
      const payload = {
        outlet_name:   form.outlet_name.trim(),
        outlet_type:   form.outlet_type,
        location:      form.location.trim(),
        capacity:      form.capacity ? Number(form.capacity) : null,
        opening_hours: form.opening_hours.trim() || null,
      };
      if (editing) {
        await axios.put(`/pos/outlets/${editing.id}`, payload);
        toast.success('Satış noktası güncellendi');
      } else {
        await axios.post('/pos/outlets', payload);
        toast.success('Satış noktası oluşturuldu');
      }
      setDialogOpen(false);
      await load();
      onChange?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Kayıt başarısız');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (outlet) => {
    try {
      await axios.delete(`/pos/outlets/${outlet.id}`);
      toast.success('Satış noktası pasif duruma alındı');
      await load();
      onChange?.();
    } catch {
      toast.error('Silme başarısız');
    }
  };

  const outletForm = (
    <div className="space-y-4">
      <div>
        <Label className="text-sm font-medium">Ad <span className="text-red-500">*</span></Label>
        <Input
          value={form.outlet_name}
          onChange={(e) => setForm({ ...form, outlet_name: e.target.value })}
          placeholder="Lobi Bar"
          data-testid="input-outlet-name"
          className="mt-1"
        />
      </div>
      <div>
        <Label className="text-sm font-medium">Tür <span className="text-red-500">*</span></Label>
        <Select value={form.outlet_type} onValueChange={(v) => setForm({ ...form, outlet_type: v })}>
          <SelectTrigger data-testid="select-outlet-type" className="mt-1">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OUTLET_TYPES.map(({ value, label, icon: Icon }) => (
              <SelectItem key={value} value={value}>
                <span className="flex items-center gap-2">
                  <Icon className="w-4 h-4" /> {label}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="text-sm font-medium">Konum <span className="text-red-500">*</span></Label>
        <Input
          value={form.location}
          onChange={(e) => setForm({ ...form, location: e.target.value })}
          placeholder="Lobi katı / 2. kat"
          data-testid="input-outlet-location"
          className="mt-1"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-sm font-medium">Kapasite (kişi)</Label>
          <Input
            type="number"
            value={form.capacity}
            onChange={(e) => setForm({ ...form, capacity: e.target.value })}
            placeholder="40"
            className="mt-1"
          />
        </div>
        <div>
          <Label className="text-sm font-medium">Çalışma Saatleri</Label>
          <Input
            value={form.opening_hours}
            onChange={(e) => setForm({ ...form, opening_hours: e.target.value })}
            placeholder="10:00–02:00"
            className="mt-1"
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
            <Store className="w-5 h-5 text-amber-600" />
            Satış Noktaları
            <span className="text-sm font-normal text-gray-400">({outlets.length})</span>
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">Restoran, bar, SPA ve diğer satış kanalları</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
            Yenile
          </Button>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" onClick={openNew} data-testid="button-new-outlet"
                className="bg-amber-500 hover:bg-amber-600 text-white border-0">
                <Plus className="w-4 h-4 mr-1.5" />
                Yeni Satış Noktası
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>{editing ? 'Satış Noktasını Düzenle' : 'Yeni Satış Noktası'}</DialogTitle>
                <DialogDescription>
                  Restoran, bar, SPA gibi ayrı kasalar için ayrı satış noktası tanımlayın.
                </DialogDescription>
              </DialogHeader>
              {outletForm}
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>İptal</Button>
                <Button onClick={submit} disabled={saving} data-testid="button-save-outlet"
                  className="bg-amber-500 hover:bg-amber-600 text-white border-0">
                  {saving ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />Kaydediliyor…</> : editing ? 'Güncelle' : 'Oluştur'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
        </div>
      ) : outlets.length === 0 ? (
        <div className="rounded-2xl border-2 border-dashed border-gray-200 bg-white py-16 text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <Store className="w-8 h-8 text-gray-400" />
          </div>
          <p className="font-semibold text-gray-700">Henüz satış noktası yok</p>
          <p className="text-sm text-gray-400 mt-1">
            "Yeni Satış Noktası" ile ilk kasanizi oluşturun
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {outlets.map((outlet) => {
            /* FIX: renamed from 't' to avoid shadowing the i18n translate fn */
            const outletType  = outlet.outlet_type || outlet.type || 'restaurant';
            const typeDef     = OUTLET_TYPES.find(x => x.value === outletType);
            const typeLabel   = typeDef?.label  || outletType;
            const TypeIcon    = typeDef?.icon   || Store;
            const style       = TYPE_STYLE[outletType] || { bg: 'bg-gray-50 border-gray-200 text-gray-700', dot: 'bg-gray-400' };
            const isInactive  = outlet.status === 'inactive';

            return (
              <div
                key={outlet.id}
                data-testid={`card-outlet-${outlet.id}`}
                className={`group relative bg-white rounded-2xl border border-gray-200 shadow-sm
                  hover:shadow-md hover:-translate-y-0.5 transition-all duration-200
                  ${isInactive ? 'opacity-60' : ''}`}
              >
                {/* Top accent strip */}
                <div className={`absolute inset-x-0 top-0 h-1 rounded-t-2xl ${style.dot}`} />

                <div className="p-5 pt-6">
                  {/* Header row */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-xl border flex items-center justify-center ${style.bg}`}>
                        <TypeIcon className="w-5 h-5" />
                      </div>
                      <div>
                        <h3 className="font-bold text-gray-900 leading-tight">
                          {outlet.outlet_name || outlet.name}
                        </h3>
                        <div className="flex items-center gap-1.5 mt-1">
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${style.bg}`}>
                            {typeLabel}
                          </span>
                          {isInactive && (
                            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 border border-red-200 text-red-600">
                              Pasif
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    {/* Actions */}
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => openEdit(outlet)}
                        data-testid={`button-edit-outlet-${outlet.id}`}
                        className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-800 transition-colors"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <button className="p-1.5 rounded-lg hover:bg-red-50 text-gray-500 hover:text-red-600 transition-colors">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Satış noktası pasifleştirilsin mi?</AlertDialogTitle>
                            <AlertDialogDescription>
                              <strong>{outlet.outlet_name || outlet.name}</strong> pasif duruma alınacak.
                              Geçmiş satış kayıtları korunur.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Vazgeç</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => remove(outlet)}
                              className="bg-red-600 hover:bg-red-700"
                            >
                              Pasifleştir
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>

                  {/* Meta */}
                  <div className="space-y-1.5 text-sm text-gray-500 border-t border-gray-100 pt-3">
                    {outlet.location && (
                      <div className="flex items-center gap-2">
                        <MapPin className="w-3.5 h-3.5 shrink-0" />
                        <span className="truncate">{outlet.location}</span>
                      </div>
                    )}
                    {outlet.capacity != null && (
                      <div className="flex items-center gap-2">
                        <Users className="w-3.5 h-3.5 shrink-0" />
                        <span>{outlet.capacity} kişilik</span>
                      </div>
                    )}
                    {outlet.opening_hours && (
                      <div className="flex items-center gap-2">
                        <Clock className="w-3.5 h-3.5 shrink-0" />
                        <span>{outlet.opening_hours}</span>
                      </div>
                    )}
                    {outlet.today_transactions != null && (
                      <div className="flex items-center justify-between pt-2 mt-2 border-t border-gray-100">
                        <span className="text-xs text-gray-400">Bugün</span>
                        <span className="text-xs font-semibold text-gray-700">
                          {outlet.today_transactions} işlem
                        </span>
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

export default POSOutletManagement;
