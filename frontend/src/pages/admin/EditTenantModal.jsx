import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Pencil, Settings2, Info } from 'lucide-react';
import { MODULE_GROUPS } from './tenantConstants';
import { useTranslation } from 'react-i18next';

const EditTenantModal = ({ open, onOpenChange, tenant, onSuccess }) => {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('info');
  const [form, setForm] = useState({
    property_name: '',
    email: '',
    phone: '',
    address: '',
    location: '',
    description: '',
    total_rooms: '',
  });
  const [modulesMap, setModulesMap] = useState({});

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
      // Initial module map: copy from tenant.modules. For ANY sub-tab key
      // (anything containing a dot, e.g. `pms.frontdesk`, `channels.dashboard`,
      // `reports.excel`) not yet in the map, default to true so existing
      // tenants keep all sub-tabs visible (backward compatible with the
      // hub-side gating which treats missing keys as "enabled").
      const baseModules = { ...(tenant.modules || {}) };
      MODULE_GROUPS.forEach((group) => {
        group.items.forEach((item) => {
          if (item.key in baseModules) return;
          if (item.key.includes('.')) baseModules[item.key] = true;
        });
      });
      setModulesMap(baseModules);
      setError(null);
      setActiveTab('info');
    }
  }, [tenant]);

  const handleChange = (field, value) => setForm((p) => ({ ...p, [field]: value }));
  const toggleModule = (key) => setModulesMap((p) => ({ ...p, [key]: !p[key] }));
  const setGroupAll = (group, value) => {
    setModulesMap((prev) => {
      const next = { ...prev };
      group.items.forEach((item) => { next[item.key] = value; });
      return next;
    });
  };

  const enabledCount = useMemo(() => Object.values(modulesMap).filter(Boolean).length, [modulesMap]);

  const handleSubmitInfo = async () => {
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

  const handleSubmitModules = async () => {
    if (!tenant) return;
    setSaving(true);
    setError(null);
    try {
      await axios.patch(`/admin/tenants/${tenant.id}/modules`, { modules: modulesMap });
      onSuccess?.();
      onOpenChange(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Modül güncelleme hatası');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Pencil className="w-4 h-4 text-indigo-600" />
            {t('cm.pages_admin_EditTenantModal.otel_bilgilerini_duzenle')}
            {tenant?.property_name && (
              <span className="ml-1 text-sm font-normal text-slate-500">— {tenant.property_name}</span>
            )}
          </DialogTitle>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-2">
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="info" className="gap-1.5"><Info className="w-4 h-4" /> Bilgiler</TabsTrigger>
            <TabsTrigger value="modules" className="gap-1.5"><Settings2 className="w-4 h-4" /> {t('cm.pages_admin_EditTenantModal.moduller')}</TabsTrigger>
          </TabsList>

          <TabsContent value="info" className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Label>{t('cm.pages_admin_EditTenantModal.otel_adi')}</Label>
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
                <Label>{t('cm.pages_admin_EditTenantModal.toplam_oda')}</Label>
                <input data-testid="edit-tenant-rooms" type="number" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.total_rooms} onChange={(e) => handleChange('total_rooms', e.target.value)} />
              </div>
              <div className="col-span-2">
                <Label>{t('cm.pages_admin_EditTenantModal.aciklama')}</Label>
                <input data-testid="edit-tenant-description" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.description} onChange={(e) => handleChange('description', e.target.value)} />
              </div>
            </div>
            {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>{t('cm.pages_admin_EditTenantModal.iptal')}</Button>
              <Button data-testid="edit-tenant-submit" onClick={handleSubmitInfo} disabled={saving}>{saving ? 'Kaydediliyor...' : 'Kaydet'}</Button>
            </div>
          </TabsContent>

          <TabsContent value="modules" className="space-y-4 mt-4">
            <div className="bg-sky-50 border border-sky-200 rounded-lg p-3 text-xs text-sky-800">
              <span className="font-semibold">{enabledCount}</span> {t('cm.pages_admin_EditTenantModal.modul_acik_kapattiginiz_moduller_sekmele')}
            </div>

            <div className="space-y-4">
              {MODULE_GROUPS.map((group) => {
                const allOn = group.items.every(it => modulesMap[it.key]);
                const allOff = group.items.every(it => !modulesMap[it.key]);
                return (
                  <div key={group.id} className="border border-slate-200 rounded-lg p-3">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="min-w-0">
                        <h4 className="text-sm font-semibold text-slate-800">{group.title}</h4>
                        {group.description && <p className="text-[11px] text-slate-500 mt-0.5">{group.description}</p>}
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => setGroupAll(group, true)}
                          disabled={allOn}
                          className="text-[11px] px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          Hepsi
                        </button>
                        <button
                          type="button"
                          onClick={() => setGroupAll(group, false)}
                          disabled={allOff}
                          className="text-[11px] px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {t('cm.pages_admin_EditTenantModal.hicbiri')}
                        </button>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                      {group.items.map((item) => {
                        const checked = !!modulesMap[item.key];
                        return (
                          <label
                            key={item.key}
                            className={`flex items-start gap-2 p-2 rounded border cursor-pointer transition-colors ${
                              checked
                                ? 'border-indigo-300 bg-indigo-50/60'
                                : 'border-slate-200 bg-white hover:bg-slate-50'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleModule(item.key)}
                              className="mt-0.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="text-xs font-medium text-slate-800 leading-tight">{item.label}</div>
                              {item.hint && <div className="text-[10px] text-slate-500 mt-0.5">{item.hint}</div>}
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>

            {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}

            <div className="flex justify-end gap-2 pt-2 sticky bottom-0 bg-white border-t -mx-6 px-6 py-3">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>{t('cm.pages_admin_EditTenantModal.iptal_25174')}</Button>
              <Button data-testid="edit-tenant-modules-submit" onClick={handleSubmitModules} disabled={saving}>
                {saving ? 'Kaydediliyor...' : 'Modülleri Kaydet'}
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};

export default EditTenantModal;
