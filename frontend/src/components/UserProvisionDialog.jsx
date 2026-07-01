import React, { useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { UserPlus, Copy, Check, Mail, KeyRound } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';

const EMPTY = {
  name: '', email: '', role: '', department: '', position: '', phone: '', mode: 'invite',
};

/**
 * Tek merkezi "Kullanici Ekle" akisi: atomik olarak giris hesabi + ozluk kaydi
 * olusturur. Davet (magic-link) varsayilan; gecici sifre yedek. Rol listesi
 * sunucudan (paket-duyarli, enum-gecerli) gelir.
 */
export default function UserProvisionDialog({ departments = [], onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [roles, setRoles] = useState([]);
  const [tier, setTier] = useState('');
  const [loadingRoles, setLoadingRoles] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const loadRoles = useCallback(async () => {
    setLoadingRoles(true);
    try {
      const { data } = await axios.get('/admin/assignable-roles');
      setRoles(data.roles || []);
      setTier(data.tier || '');
    } catch (e) {
      const msg = e?.response?.data?.detail;
      toast.error(typeof msg === 'string' ? msg : 'Roller yuklenemedi');
    } finally {
      setLoadingRoles(false);
    }
  }, []);

  const openDialog = () => {
    setForm(EMPTY);
    setResult(null);
    setCopied(false);
    setOpen(true);
    loadRoles();
  };

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error('Ad Soyad zorunludur'); return; }
    if (!form.email.trim()) { toast.error('E-posta zorunludur'); return; }
    if (!form.role) { toast.error('Rol secin'); return; }
    setSaving(true);
    try {
      const { data } = await axios.post('/admin/users', {
        name: form.name.trim(),
        email: form.email.trim(),
        role: form.role,
        department: form.department || null,
        position: form.position || null,
        phone: form.phone || null,
        mode: form.mode,
      });
      if (data.mode === 'temp' && data.temp_password) {
        setResult({ temp_password: data.temp_password, email: form.email.trim() });
        toast.success('Kullanici olusturuldu — gecici sifreyi guvenli iletin');
      } else {
        if (data.email_sent) {
          toast.success('Kullanici olusturuldu — davet e-postasi gonderildi');
        } else {
          toast.warning('Kullanici olusturuldu ancak davet e-postasi gonderilemedi. Gecici sifre yontemini kullanin veya e-posta ayarlarini kontrol edin.');
        }
        setOpen(false);
      }
      onCreated?.();
    } catch (e2) {
      const msg = e2?.response?.data?.detail;
      toast.error(typeof msg === 'string' ? msg : 'Kullanici olusturulamadi');
    } finally {
      setSaving(false);
    }
  };

  const copyTemp = async () => {
    try {
      await navigator.clipboard.writeText(result.temp_password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Kopyalanamadi');
    }
  };

  return (
    <>
      <Button size="sm" onClick={openDialog} data-testid="btn-provision-user">
        <UserPlus className="w-4 h-4 mr-1.5" />Kullanici Ekle
      </Button>

      <Dialog open={open} onOpenChange={(o) => { if (!o) { setOpen(false); setResult(null); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{result ? 'Gecici Sifre' : 'Kullanici Ekle (Giris Hesabi)'}</DialogTitle>
          </DialogHeader>

          {result ? (
            <div className="space-y-3">
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Bu sifre yalnizca bir kez gosterilir. <b>{result.email}</b> kullanicisina guvenli
                bir kanaldan iletin. Kullanici ilk giriste sifresini degistirmek zorundadir.
              </div>
              <div className="flex items-center gap-2">
                <Input readOnly value={result.temp_password} className="font-mono" />
                <Button type="button" variant="outline" size="sm" onClick={copyTemp}>
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>
              <DialogFooter>
                <Button type="button" onClick={() => { setOpen(false); setResult(null); }}>Tamam</Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
              <div className="md:col-span-2">
                <Label className="text-xs">Ad Soyad *</Label>
                <Input required value={form.name} onChange={(e) => set('name', e.target.value)} />
              </div>
              <div>
                <Label className="text-xs">E-posta *</Label>
                <Input type="email" required value={form.email} onChange={(e) => set('email', e.target.value)} />
              </div>
              <div>
                <Label className="text-xs">Telefon</Label>
                <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} />
              </div>
              <div>
                <Label className="text-xs">Departman</Label>
                <select
                  value={form.department}
                  onChange={(e) => set('department', e.target.value)}
                  className="w-full rounded-md border border-input px-3 py-2 text-sm"
                >
                  <option value="">— Secin —</option>
                  {departments.map((d) => <option key={d.id} value={d.code || d.name}>{d.name}</option>)}
                </select>
              </div>
              <div>
                <Label className="text-xs">Pozisyon</Label>
                <Input value={form.position} onChange={(e) => set('position', e.target.value)} />
              </div>
              <div className="md:col-span-2">
                <Label className="text-xs">Rol (yetki seviyesi) *{tier ? ` — paket: ${tier}` : ''}</Label>
                <select
                  required
                  value={form.role}
                  onChange={(e) => set('role', e.target.value)}
                  className="w-full rounded-md border border-input px-3 py-2 text-sm"
                  disabled={loadingRoles}
                >
                  <option value="">{loadingRoles ? 'Yukleniyor…' : '— Secin —'}</option>
                  {roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Departman organizasyoneldir (or. Spa); rol erisim yetkisini belirler.
                  Hat calisanlari icin <b>Personel</b> secin.
                </p>
              </div>
              <div className="md:col-span-2">
                <Label className="text-xs">Hesap Acma Yontemi</Label>
                <div className="mt-1 grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => set('mode', 'invite')}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${form.mode === 'invite' ? 'border-black bg-gray-50' : 'border-input'}`}>
                    <Mail className="w-4 h-4" /> Davet e-postasi
                  </button>
                  <button type="button" onClick={() => set('mode', 'temp')}
                    className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${form.mode === 'temp' ? 'border-black bg-gray-50' : 'border-input'}`}>
                    <KeyRound className="w-4 h-4" /> Gecici sifre
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {form.mode === 'invite'
                    ? 'Kullanici e-postadaki baglantidan kendi sifresini belirler.'
                    : 'Gecici sifre ekranda bir kez gosterilir; kullanici ilk giriste degistirir.'}
                </p>
              </div>
              <DialogFooter className="md:col-span-2">
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>Vazgec</Button>
                <Button type="submit" disabled={saving} data-testid="btn-submit-provision">
                  {saving ? 'Olusturuluyor…' : 'Olustur'}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
