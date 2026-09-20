import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { permissionLabels } from '@/config/permissionLabels';

const toggle = (values, key, enabled) => enabled ? [...new Set([...values, key])] : values.filter(value => value !== key);

export default function UserAccessDialog({ target, onClose, onSaved }) {
  const [catalog, setCatalog] = useState(null);
  const [scopes, setScopes] = useState([]);
  const [pages, setPages] = useState({});
  const [permissions, setPermissions] = useState([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    axios.get('/admin/user-access-catalog').then(({ data }) => {
      if (!active) return;
      setCatalog(data);
      setScopes(target.module_scopes ?? data.roles.find(role => role.role === target.role)?.modules ?? []);
      setPages(target.page_access || {});
      setPermissions((target.granted_permissions || []).filter(key => data.permissions.includes(key)));
    }).catch(() => { if (active) setError('Yetki kataloğu yüklenemedi. Pencereyi kapatıp tekrar deneyin.'); });
    return () => { active = false; };
  }, [target]);
  const defaults = catalog?.roles.find(role => role.role === target.role)?.permissions || [];
  const save = async (reset = false) => {
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      await axios.patch(`/admin/users/${target.id}/access`, {
        module_scopes: scopes, page_access: pages, granted_permissions: permissions,
        revision: target.access_revision || 0, reset_to_role: reset,
      });
      onSaved();
      onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Yetkiler kaydedilemedi.');
    } finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={open => { if (!open && !saving) onClose(); }}>
    <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
      <DialogHeader><DialogTitle>{target.name || target.email} — Kullanıcı Yetkileri</DialogTitle></DialogHeader>
      <p className="text-sm text-muted-foreground">Rol: {target.role}. Modül kapalıysa alt sayfaları da kapalıdır. Otelin paketinde olmayan özellikler bu izinlerle açılmaz. Yönetici ve platform yetkileri devredilemez.</p>
      {error && <p role="alert" className="text-destructive">{error}</p>}
      {!catalog ? <p role="status">Yetkiler yükleniyor…</p> : <>
        <fieldset disabled={saving} className="space-y-3">
          <legend className="font-semibold">Modüller ve sayfalar</legend>
          {Object.entries(catalog.modules).map(([key, label]) => <section key={key} className="rounded-lg border p-3 space-y-2">
            <label className="flex gap-2 font-medium">
              <input type="checkbox" checked={scopes.includes(key)} onChange={e => setScopes(toggle(scopes, key, e.target.checked))} />{label}
            </label>
            <div className="pl-6 space-y-2">{catalog.pages.filter(page => page.module === key).map(page => {
              const missing = page.permissions.filter(p => !defaults.includes(p) && !permissions.includes(p));
              const missingAlternative = page.any_permissions?.length && !page.any_permissions.some(p => defaults.includes(p) || permissions.includes(p));
              return <div key={page.key}>
                <label className="flex gap-2 text-sm"><input type="checkbox" disabled={!scopes.includes(key)}
                  checked={scopes.includes(key) && pages[page.key] !== false}
                  onChange={e => setPages({ ...pages, [page.key]: e.target.checked })} />{page.label}</label>
                {scopes.includes(key) && pages[page.key] !== false && missing.length > 0 &&
                  <p className="text-xs text-amber-700">Açılması için gereken işlem izinleri: {missing.map(p => permissionLabels[p] || p).join(', ')}</p>}
                {scopes.includes(key) && pages[page.key] !== false && missingAlternative &&
                  <p className="text-xs text-amber-700">Bu izinlerden biri gerekli: {page.any_permissions.map(p => permissionLabels[p] || p).join(' veya ')}</p>}
              </div>;
            })}</div>
          </section>)}
        </fieldset>
        <fieldset disabled={saving} className="space-y-2">
          <legend className="font-semibold">Role ek işlem izinleri</legend>
          <p className="text-xs text-muted-foreground">İşlem izni modül/sayfa yasağını kaldırmaz. Rolün mevcut izinleri işaretli ve kilitlidir; erişimi kaldırmak için yukarıdaki modülü veya sayfayı kapatın.</p>
          <div className="grid sm:grid-cols-2 gap-2">{catalog.permissions.map(key =>
            <label key={key} className="flex gap-2 text-sm"><input type="checkbox" checked={defaults.includes(key) || permissions.includes(key)}
              disabled={defaults.includes(key)} onChange={e => setPermissions(toggle(permissions, key, e.target.checked))} />{permissionLabels[key] || key}</label>
          )}</div>
        </fieldset>
        <details className="rounded border p-3">
          <summary className="cursor-pointer font-medium">Tüm rollerin varsayılan yetki dökümü</summary>
          <p className="my-2 text-xs text-muted-foreground">Sayfa açılması için hem modül hem gereken işlem izni gerekir. Kullanıcıya özel kısıtlar ve otel paketi ayrıca uygulanır.</p>
          {catalog.roles.map(role => <div key={role.role} className="border-t py-2 text-sm">
            <strong>{role.role}</strong>
            <p>Modüller: {role.modules.map(key => catalog.modules[key] || key).join(', ') || 'Yok'}</p>
            <p className="text-muted-foreground">İşlemler: {role.permissions.map(key => permissionLabels[key] || key).join(', ') || 'Otel operasyon yetkisi yok'}</p>
          </div>)}
        </details>
        <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
          <Button variant="outline" disabled={saving} onClick={() => save(true)}>Rol varsayılanlarına dön</Button>
          <Button variant="outline" disabled={saving} onClick={onClose}>Vazgeç</Button>
          <Button disabled={saving} onClick={() => save()}>{saving ? 'Kaydediliyor…' : 'Yetkileri Kaydet'}</Button>
        </div>
      </>}
    </DialogContent>
  </Dialog>;
}
