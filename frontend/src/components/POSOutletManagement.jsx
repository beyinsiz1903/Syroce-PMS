import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { Label } from './ui/label';
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
import { Plus, Pencil, Trash2, RefreshCw, Store, MapPin, Users, Clock } from 'lucide-react';

const OUTLET_TYPES = [
  { value: 'restaurant', label: 'Restoran' },
  { value: 'bar', label: 'Bar' },
  { value: 'cafe', label: 'Kafe' },
  { value: 'spa', label: 'SPA' },
  { value: 'room_service', label: 'Oda Servisi' },
  { value: 'banquet', label: 'Banket' },
];

const TYPE_COLOR = {
  restaurant: 'bg-orange-100 text-orange-700',
  bar: 'bg-purple-100 text-purple-700',
  cafe: 'bg-amber-100 text-amber-700',
  spa: 'bg-emerald-100 text-emerald-700',
  room_service: 'bg-blue-100 text-blue-700',
  banquet: 'bg-pink-100 text-pink-700',
};

const blankForm = {
  outlet_name: '',
  outlet_type: 'restaurant',
  location: '',
  capacity: '',
  opening_hours: '',
};

const POSOutletManagement = ({ onChange }) => {
  const [outlets, setOutlets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blankForm);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await axios.get('/pos/outlets');
      const list = Array.isArray(res.data) ? res.data : (res.data.outlets || []);
      setOutlets(list);
    } catch (err) {
      console.error('Outlets yüklenemedi:', err);
      toast.error('Satış noktalari yüklenemedi');
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
      outlet_name: outlet.outlet_name || outlet.name || '',
      outlet_type: outlet.outlet_type || outlet.type || 'restaurant',
      location: outlet.location || '',
      capacity: outlet.capacity || '',
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
        outlet_name: form.outlet_name.trim(),
        outlet_type: form.outlet_type,
        location: form.location.trim(),
        capacity: form.capacity ? Number(form.capacity) : null,
        opening_hours: form.opening_hours.trim() || null,
      };
      if (editing) {
        await axios.put(`/pos/outlets/${editing.id}`, payload);
        toast.success('Satış noktasi guncellendi');
      } else {
        await axios.post('/pos/outlets', payload);
        toast.success('Satış noktasi oluşturuldu');
      }
      setDialogOpen(false);
      await load();
      onChange?.();
    } catch (err) {
      console.error('Outlet kaydi hatası:', err);
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Kayıt basarisiz');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (outlet) => {
    try {
      await axios.delete(`/pos/outlets/${outlet.id}`);
      toast.success('Satış noktasi pasif duruma alindi');
      await load();
      onChange?.();
    } catch (err) {
      console.error('Outlet silinemedi:', err);
      toast.error('Silme basarisiz');
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="flex items-center gap-2">
            <Store className="w-5 h-5 text-orange-600" />
            Satış Noktalari ({outlets.length})
          </CardTitle>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm" onClick={openNew} data-testid="button-new-outlet">
                  <Plus className="w-4 h-4 mr-2" />
                  Yeni Satış Noktası
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>
                    {editing ? 'Satış Noktasını Düzenle' : 'Yeni Satış Noktası'}
                  </DialogTitle>
                  <DialogDescription>
                    Restoran, bar, spa gibi ayrı kasalar için tanım oluştur.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                  <div>
                    <Label>Ad *</Label>
                    <Input
                      value={form.outlet_name}
                      onChange={(e) => setForm({ ...form, outlet_name: e.target.value })}
                      placeholder="Lobi Bar"
                      data-testid="input-outlet-name"
                    />
                  </div>
                  <div>
                    <Label>Tur *</Label>
                    <Select
                      value={form.outlet_type}
                      onValueChange={(v) => setForm({ ...form, outlet_type: v })}
                    >
                      <SelectTrigger data-testid="select-outlet-type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {OUTLET_TYPES.map(t => (
                          <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Konum *</Label>
                    <Input
                      value={form.location}
                      onChange={(e) => setForm({ ...form, location: e.target.value })}
                      placeholder="Lobi kati / 2. kat"
                      data-testid="input-outlet-location"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Kapasite</Label>
                      <Input
                        type="number"
                        value={form.capacity}
                        onChange={(e) => setForm({ ...form, capacity: e.target.value })}
                        placeholder="40"
                      />
                    </div>
                    <div>
                      <Label>Çalışma Saatleri</Label>
                      <Input
                        value={form.opening_hours}
                        onChange={(e) => setForm({ ...form, opening_hours: e.target.value })}
                        placeholder="10:00-02:00"
                      />
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
                    İptal
                  </Button>
                  <Button onClick={submit} disabled={saving} data-testid="button-save-outlet">
                    {saving ? 'Kaydediliyor...' : (editing ? 'Guncelle' : 'Olustur')}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="text-center py-8">
            <RefreshCw className="w-8 h-8 animate-spin text-orange-600 mx-auto" />
          </div>
        ) : outlets.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Store className="w-16 h-16 mx-auto mb-3 text-gray-300" />
            <p>Henüz satış noktasi yok</p>
            <p className="text-sm mt-2">"Yeni Satış Noktası" ile ilk kasanizi oluşturun</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {outlets.map(outlet => {
              const t = outlet.outlet_type || outlet.type || 'restaurant';
              const typeLabel = OUTLET_TYPES.find(x => x.value === t)?.label || t;
              const isInactive = outlet.status === 'inactive';
              return (
                <Card
                  key={outlet.id}
                  className={`hover:shadow-lg transition ${isInactive ? 'opacity-60' : ''}`}
                  data-testid={`card-outlet-${outlet.id}`}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <h3 className="font-bold text-gray-900">{outlet.outlet_name || outlet.name}</h3>
                        <Badge className={`mt-1 ${TYPE_COLOR[t] || 'bg-gray-100 text-gray-700'}`}>
                          {typeLabel}
                        </Badge>
                        {isInactive && (
                          <Badge variant="destructive" className="ml-1 mt-1">Pasif</Badge>
                        )}
                      </div>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost" size="icon"
                          onClick={() => openEdit(outlet)}
                          data-testid={`button-edit-outlet-${outlet.id}`}
                        >
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
                              <AlertDialogTitle>Satış noktasi pasiflestirilsin mi?</AlertDialogTitle>
                              <AlertDialogDescription>
                                "{outlet.outlet_name || outlet.name}" pasif duruma alinacak.
                                Gecmis satış kayitlari silinmez.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Vazgec</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() => remove(outlet)}
                                className="bg-red-600 hover:bg-red-700"
                              >
                                Pasiflestir
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </div>
                    <div className="space-y-1.5 text-sm text-gray-600 mt-3">
                      <div className="flex items-center gap-2">
                        <MapPin className="w-3.5 h-3.5" />
                        <span>{outlet.location || '—'}</span>
                      </div>
                      {outlet.capacity != null && (
                        <div className="flex items-center gap-2">
                          <Users className="w-3.5 h-3.5" />
                          <span>{outlet.capacity} kisilik</span>
                        </div>
                      )}
                      {outlet.opening_hours && (
                        <div className="flex items-center gap-2">
                          <Clock className="w-3.5 h-3.5" />
                          <span>{outlet.opening_hours}</span>
                        </div>
                      )}
                      {outlet.today_transactions != null && (
                        <div className="text-xs pt-2 border-t">
                          Bugün: <strong>{outlet.today_transactions}</strong> işlem
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

export default POSOutletManagement;
