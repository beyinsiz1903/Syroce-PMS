import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Pencil } from 'lucide-react';

const EditTenantModal = ({ open, onOpenChange, tenant, onSuccess }) => {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({
    property_name: '',
    email: '',
    phone: '',
    address: '',
    location: '',
    description: '',
    total_rooms: '',
  });

  useEffect(() => {
    if (tenant) {
      setForm({
        property_name: tenant.property_name || '',
        email: tenant.email || tenant.contact_email || '',
        phone: tenant.phone || tenant.contact_phone || '',
        address: tenant.address || '',
        location: tenant.location || '',
        description: tenant.description || '',
        total_rooms: tenant.total_rooms || '',
      });
      setError(null);
    }
  }, [tenant]);

  const handleChange = (field, value) => setForm((p) => ({ ...p, [field]: value }));

  const handleSubmit = async () => {
    if (!tenant) return;
    setSaving(true);
    setError(null);
    try {
      const payload = {};
      Object.entries(form).forEach(([k, v]) => {
        if (v !== '' && v !== null && v !== undefined) {
          payload[k] = k === 'total_rooms' ? parseInt(v) : v;
        }
      });
      await axios.patch(`/admin/tenants/${tenant.id}/info`, payload);
      onSuccess?.();
      onOpenChange(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Güncelleme hatası');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Pencil className="w-4 h-4 text-indigo-600" />
            Otel Bilgilerini Düzenle
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Otel Adı</Label>
              <input data-testid="edit-tenant-property-name" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.property_name} onChange={(e) => handleChange('property_name', e.target.value)} />
            </div>
            <div>
              <Label>E-posta</Label>
              <input data-testid="edit-tenant-email" type="email" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.email} onChange={(e) => handleChange('email', e.target.value)} />
            </div>
            <div>
              <Label>Telefon</Label>
              <input data-testid="edit-tenant-phone" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.phone} onChange={(e) => handleChange('phone', e.target.value)} />
            </div>
            <div className="col-span-2">
              <Label>Adres</Label>
              <input data-testid="edit-tenant-address" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.address} onChange={(e) => handleChange('address', e.target.value)} />
            </div>
            <div>
              <Label>Konum</Label>
              <input data-testid="edit-tenant-location" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.location} onChange={(e) => handleChange('location', e.target.value)} />
            </div>
            <div>
              <Label>Toplam Oda</Label>
              <input data-testid="edit-tenant-rooms" type="number" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.total_rooms} onChange={(e) => handleChange('total_rooms', e.target.value)} />
            </div>
            <div className="col-span-2">
              <Label>Açıklama</Label>
              <input data-testid="edit-tenant-description" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.description} onChange={(e) => handleChange('description', e.target.value)} />
            </div>
          </div>
          {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>İptal</Button>
            <Button data-testid="edit-tenant-submit" onClick={handleSubmit} disabled={saving}>{saving ? 'Kaydediliyor...' : 'Kaydet'}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default EditTenantModal;
