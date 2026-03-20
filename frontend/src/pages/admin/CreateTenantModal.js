import React, { useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Building2 } from 'lucide-react';

const CreateTenantModal = ({ open, onOpenChange, onSuccess }) => {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({
    property_name: '',
    email: '',
    password: '',
    name: '',
    phone: '',
    address: '',
    location: '',
    description: '',
    subscription_tier: 'basic',
    subscription_days: 30,
  });

  const handleChange = (field, value) => setForm((p) => ({ ...p, [field]: value }));

  const handleSubmit = async () => {
    if (!form.property_name || !form.email || !form.password || !form.name || !form.phone || !form.address) {
      setError('Lütfen zorunlu alanları doldurun');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await axios.post('/admin/tenants', form);
      onSuccess?.();
      onOpenChange(false);
      setForm({
        property_name: '', email: '', password: '', name: '', phone: '',
        address: '', location: '', description: '', subscription_tier: 'basic', subscription_days: 30,
      });
    } catch (err) {
      setError(err.response?.data?.detail || 'Otel oluşturulurken hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-indigo-600" />
            Yeni Otel Ekle
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label data-testid="create-tenant-property-label">Otel Adı *</Label>
              <input data-testid="create-tenant-property-name" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.property_name} onChange={(e) => handleChange('property_name', e.target.value)} placeholder="Grand Hotel" />
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
              <input data-testid="create-tenant-location" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.location} onChange={(e) => handleChange('location', e.target.value)} placeholder="İstanbul" />
            </div>
            <div>
              <Label>Açıklama</Label>
              <input data-testid="create-tenant-description" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.description} onChange={(e) => handleChange('description', e.target.value)} placeholder="Boutique otel" />
            </div>
            <div>
              <Label>Plan</Label>
              <select data-testid="create-tenant-tier" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.subscription_tier} onChange={(e) => handleChange('subscription_tier', e.target.value)}>
                <option value="basic">Basic</option>
                <option value="professional">Professional</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            <div>
              <Label>Üyelik Süresi</Label>
              <select data-testid="create-tenant-days" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.subscription_days || ''} onChange={(e) => handleChange('subscription_days', e.target.value ? parseInt(e.target.value) : null)}>
                <option value="30">30 Gün</option>
                <option value="90">90 Gün</option>
                <option value="365">1 Yıl</option>
                <option value="">Sınırsız</option>
              </select>
            </div>
          </div>
          {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>İptal</Button>
            <Button data-testid="create-tenant-submit" onClick={handleSubmit} disabled={saving}>{saving ? 'Oluşturuluyor...' : 'Otel Oluştur'}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default CreateTenantModal;
