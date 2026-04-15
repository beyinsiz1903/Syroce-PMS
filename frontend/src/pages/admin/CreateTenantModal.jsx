import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Building2, Home, TreePalm, Bed, Car, Building, Gem, Tent,
  Briefcase, Sun, Snowflake, Droplets, Star, Crown, ChevronRight,
  ChevronLeft, Check, Users, DoorOpen, Sparkles, ArrowRight
} from 'lucide-react';

const ICON_MAP = {
  Home, TreePalm, Bed, Car, Building, Gem, Tent, Building2,
  Briefcase, Sun, Snowflake, Droplets, Star, Crown,
};

const TIER_LABELS = {
  basic: { label: 'Basic', color: 'bg-slate-100 text-slate-700 border-slate-200' },
  professional: { label: 'Professional', color: 'bg-blue-50 text-blue-700 border-blue-200' },
  enterprise: { label: 'Enterprise', color: 'bg-amber-50 text-amber-700 border-amber-200' },
};


const PROPERTY_CATEGORIES = [
  {
    label: 'Küçük Tesisler',
    label_detail: '1-15 oda',
    types: ['pension', 'villa', 'hostel', 'motel', 'camping'],
  },
  {
    label: 'Orta Ölçek',
    label_detail: '15-100 oda',
    types: ['apart_hotel', 'boutique_hotel', 'hotel_3star', 'city_hotel'],
  },
  {
    label: 'Büyük Tesisler',
    label_detail: '100+ oda',
    types: ['business_hotel', 'hotel_4star', 'hotel_5star'],
  },
  {
    label: 'Resortlar',
    label_detail: 'Tatil tesisleri',
    types: ['resort_summer', 'resort_winter', 'resort_thermal'],
  },
];

const CreateTenantModal = ({ open, onOpenChange, onSuccess }) => {
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [propertyTypes, setPropertyTypes] = useState([]);
  const [selectedType, setSelectedType] = useState(null);
  const [form, setForm] = useState({
    property_name: '',
    property_type: '',
    email: '',
    password: '',
    name: '',
    phone: '',
    address: '',
    location: '',
    total_rooms: '',
    description: '',
    subscription_tier: 'basic',
    subscription_days: 30,
  });

  useEffect(() => {
    if (open) {
      axios.get('/admin/property-types').then(r => {
        setPropertyTypes(r.data.property_types || []);
      }).catch(() => {});
    }
  }, [open]);

  const handleChange = (field, value) => setForm((p) => ({ ...p, [field]: value }));

  const selectPropertyType = (typeKey) => {
    const pt = propertyTypes.find(p => p.key === typeKey);
    if (!pt) return;
    setSelectedType(pt);
    setForm(prev => ({
      ...prev,
      property_type: typeKey,
      subscription_tier: pt.recommended_tier || 'basic',
      total_rooms: prev.total_rooms || pt.room_range?.min || '',
    }));
  };

  const goToStep2 = () => {
    if (!selectedType) {
      setError('Lütfen bir tesis tipi seçin');
      return;
    }
    setError(null);
    setStep(2);
  };

  const handleSubmit = async () => {
    if (!form.property_name || !form.email || !form.password || !form.name || !form.phone || !form.address) {
      setError('Lütfen zorunlu alanları doldurun');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form };
      if (payload.total_rooms) payload.total_rooms = parseInt(payload.total_rooms);
      else delete payload.total_rooms;
      await axios.post('/admin/tenants', payload);
      onSuccess?.();
      onOpenChange(false);
      resetForm();
    } catch (err) {
      setError(err.response?.data?.detail || 'Tesis oluşturulurken hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setStep(1);
    setSelectedType(null);
    setError(null);
    setForm({
      property_name: '', property_type: '', email: '', password: '', name: '', phone: '',
      address: '', location: '', total_rooms: '', description: '', subscription_tier: 'basic', subscription_days: 30,
    });
  };

  const getTypesByCategory = (categoryTypes) => {
    return propertyTypes.filter(pt => categoryTypes.includes(pt.key));
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) resetForm(); }}>
      <DialogContent className={`${step === 1 ? 'max-w-3xl' : 'max-w-lg'} max-h-[90vh] overflow-y-auto p-0`}>
        <div className="sticky top-0 z-10 bg-white border-b px-6 py-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-indigo-600" />
              Yeni Tesis Ekle
              {step === 2 && selectedType && (
                <span className="ml-2 text-sm font-normal text-slate-500">
                  — {selectedType.name_tr}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex items-center gap-3 mt-3">
            <div className={`flex items-center gap-1.5 text-xs font-medium ${step === 1 ? 'text-indigo-600' : 'text-slate-400'}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${step === 1 ? 'bg-indigo-600 text-white' : 'bg-indigo-100 text-indigo-600'}`}>1</div>
              Tesis Tipi
            </div>
            <ChevronRight size={14} className="text-slate-300" />
            <div className={`flex items-center gap-1.5 text-xs font-medium ${step === 2 ? 'text-indigo-600' : 'text-slate-400'}`}>
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${step === 2 ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'}`}>2</div>
              Tesis Bilgileri
            </div>
          </div>
        </div>

        <div className="px-6 pb-6 pt-4">
          {step === 1 && (
            <div className="space-y-5">
              <p className="text-sm text-slate-500">
                Tesisinizin tipini seçin. Seçtiğiniz tipe göre PMS otomatik olarak sizin için en uygun modülleri, dashboard düzenini ve ayarları yapılandıracak.
              </p>

              {PROPERTY_CATEGORIES.map((cat, ci) => (
                <div key={ci}>
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-sm font-semibold text-slate-700">{cat.label}</h3>
                    <span className="text-xs text-slate-400">{cat.label_detail}</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {getTypesByCategory(cat.types).map(pt => {
                      const IconComp = ICON_MAP[pt.icon] || Building2;
                      const isSelected = selectedType?.key === pt.key;
                      const tierInfo = TIER_LABELS[pt.recommended_tier] || TIER_LABELS.basic;
                      return (
                        <button
                          key={pt.key}
                          onClick={() => selectPropertyType(pt.key)}
                          className={`relative text-left p-3 rounded-xl border-2 transition-all duration-150 hover:shadow-md ${
                            isSelected
                              ? 'border-indigo-500 bg-indigo-50 shadow-md ring-2 ring-indigo-200'
                              : 'border-slate-200 bg-white hover:border-slate-300'
                          }`}
                        >
                          {isSelected && (
                            <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center">
                              <Check size={12} className="text-white" />
                            </div>
                          )}
                          <IconComp size={20} className={isSelected ? 'text-indigo-600' : 'text-slate-400'} />
                          <div className="mt-1.5">
                            <div className="text-sm font-medium text-slate-800 leading-tight">{pt.name_tr}</div>
                            <div className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1.5">
                              <span className="flex items-center gap-0.5"><DoorOpen size={10} />{pt.room_range.min}-{pt.room_range.max}</span>
                              <span className="flex items-center gap-0.5"><Users size={10} />{pt.typical_staff}</span>
                            </div>
                          </div>
                          <div className="mt-1.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${tierInfo.color}`}>
                              {tierInfo.label}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}

              {selectedType && (
                <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 mt-4">
                  <div className="flex items-start gap-3">
                    <Sparkles size={18} className="text-indigo-600 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-semibold text-indigo-900">{selectedType.name_tr}</h4>
                      <p className="text-xs text-indigo-700 mt-0.5">{selectedType.description_tr}</p>
                      <div className="flex flex-wrap gap-3 mt-2 text-xs text-indigo-600">
                        <span className="flex items-center gap-1"><DoorOpen size={12} /> {selectedType.room_range.min}–{selectedType.room_range.max} oda</span>
                        <span className="flex items-center gap-1"><Users size={12} /> ~{selectedType.typical_staff} personel</span>
                        <span className="flex items-center gap-1">
                          Dashboard: <span className="font-medium capitalize">{selectedType.dashboard_layout}</span>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}

              <div className="flex justify-end pt-2">
                <Button onClick={goToStep2} disabled={!selectedType} className="gap-1.5">
                  Devam <ArrowRight size={15} />
                </Button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <Label>Tesis Adı *</Label>
                  <input data-testid="create-tenant-property-name" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.property_name} onChange={(e) => handleChange('property_name', e.target.value)} placeholder={selectedType?.name_tr === 'Pansiyon' ? 'Deniz Pansiyonu' : 'Grand Hotel'} />
                </div>
                <div>
                  <Label>Yönetici Adı *</Label>
                  <input data-testid="create-tenant-admin-name" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.name} onChange={(e) => handleChange('name', e.target.value)} placeholder="Ahmet Yılmaz" />
                </div>
                <div>
                  <Label>E-posta *</Label>
                  <input data-testid="create-tenant-email" type="email" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.email} onChange={(e) => handleChange('email', e.target.value)} placeholder="admin@hotel.com" />
                </div>
                <div>
                  <Label>Şifre *</Label>
                  <input data-testid="create-tenant-password" type="password" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.password} onChange={(e) => handleChange('password', e.target.value)} placeholder="En az 6 karakter" />
                </div>
                <div>
                  <Label>Telefon *</Label>
                  <input data-testid="create-tenant-phone" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.phone} onChange={(e) => handleChange('phone', e.target.value)} placeholder="+90 555 123 4567" />
                </div>
                <div className="col-span-2">
                  <Label>Adres *</Label>
                  <input data-testid="create-tenant-address" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.address} onChange={(e) => handleChange('address', e.target.value)} placeholder="Caddesi No:1, İlçe" />
                </div>
                <div>
                  <Label>Konum</Label>
                  <input className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.location} onChange={(e) => handleChange('location', e.target.value)} placeholder="İstanbul" />
                </div>
                <div>
                  <Label>Oda Sayısı</Label>
                  <input type="number" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.total_rooms} onChange={(e) => handleChange('total_rooms', e.target.value)} placeholder={selectedType ? `${selectedType.room_range.min}` : '50'} min="1" max="2000" />
                </div>
                <div>
                  <Label>Açıklama</Label>
                  <input className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.description} onChange={(e) => handleChange('description', e.target.value)} placeholder={selectedType?.name_tr || 'Tesis açıklaması'} />
                </div>
                <div>
                  <Label>Plan</Label>
                  <select data-testid="create-tenant-tier" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.subscription_tier} onChange={(e) => handleChange('subscription_tier', e.target.value)}>
                    <option value="basic">Basic</option>
                    <option value="professional">Professional</option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                  {selectedType && form.subscription_tier !== selectedType.recommended_tier && (
                    <p className="text-[11px] text-amber-600 mt-1">
                      Bu tesis tipi için önerilen plan: <span className="font-semibold">{TIER_LABELS[selectedType.recommended_tier]?.label}</span>
                    </p>
                  )}
                </div>
                <div>
                  <Label>Üyelik Süresi</Label>
                  <select className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.subscription_days || ''} onChange={(e) => handleChange('subscription_days', e.target.value ? parseInt(e.target.value) : null)}>
                    <option value="30">30 Gün</option>
                    <option value="90">90 Gün</option>
                    <option value="365">1 Yıl</option>
                    <option value="">Sınırsız</option>
                  </select>
                </div>
              </div>

              {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}

              <div className="flex justify-between pt-2">
                <Button variant="outline" onClick={() => { setStep(1); setError(null); }} className="gap-1.5">
                  <ChevronLeft size={15} /> Geri
                </Button>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>İptal</Button>
                  <Button data-testid="create-tenant-submit" onClick={handleSubmit} disabled={saving}>
                    {saving ? 'Oluşturuluyor...' : 'Tesis Oluştur'}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default CreateTenantModal;
