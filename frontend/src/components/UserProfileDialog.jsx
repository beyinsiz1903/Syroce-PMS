import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function UserProfileDialog({ target, onClose, onSaved }) {
  const [name, setName] = useState(target.name || '');
  const [email, setEmail] = useState(target.email || '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(target.name || '');
    setEmail(target.email || '');
  }, [target]);

  const save = async event => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError('');
    try {
      await axios.patch(`/admin/users/${target.id}/profile`, {
        name: name.trim(),
        email: email.trim().toLowerCase(),
      });
      onSaved();
      onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Kullanıcı bilgileri kaydedilemedi.');
    } finally {
      setSaving(false);
    }
  };

  return <Dialog open onOpenChange={open => { if (!open && !saving) onClose(); }}>
    <DialogContent className="max-w-lg">
      <DialogHeader><DialogTitle>Kullanıcı Bilgilerini Düzenle</DialogTitle></DialogHeader>
      <form onSubmit={save} className="space-y-4">
        <p className="text-sm text-muted-foreground">E-posta adresi kullanıcının sisteme giriş adresidir. Değişiklikten sonra yeni adres kullanılmalıdır.</p>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <div className="space-y-1.5">
          <Label htmlFor="tenant-user-name">Ad Soyad</Label>
          <Input id="tenant-user-name" required value={name} onChange={event => setName(event.target.value)} disabled={saving} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tenant-user-email">E-posta</Label>
          <Input id="tenant-user-email" type="email" required value={email} onChange={event => setEmail(event.target.value)} disabled={saving} />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={saving}>Vazgeç</Button>
          <Button type="submit" disabled={saving}>{saving ? 'Kaydediliyor…' : 'Bilgileri Kaydet'}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}
