import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Layout from '@/components/Layout';
import {
  User as UserIcon, Hotel, Shield, KeyRound, Mail, Phone,
  Smartphone, CheckCircle2, AlertTriangle, Copy, RefreshCw, Pencil,
} from 'lucide-react';

const ProfilePage = ({ user, tenant, onLogout }) => {
  const [me, setMe] = useState(user || null);
  const [tenantInfo] = useState(tenant || null);
  const [loading, setLoading] = useState(false);
  const [pwd, setPwd] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', phone: '' });
  const [savingProfile, setSavingProfile] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get('/auth/me');
        if (!cancelled) setMe(res.data);
      } catch { /* keep */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const startEdit = () => {
    setEditForm({ name: me?.name || '', phone: me?.phone || '' });
    setEditing(true);
  };

  const saveProfile = async (e) => {
    e.preventDefault();
    if (editForm.name.trim().length < 2) {
      toast.error('Ad Soyad en az 2 karakter olmalıdır.');
      return;
    }
    setSavingProfile(true);
    try {
      const res = await axios.put('/auth/me', {
        name: editForm.name.trim(),
        phone: editForm.phone.trim(),
      });
      setMe(res.data);
      setEditing(false);
      toast.success('Profil bilgileriniz güncellendi.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Profil güncellenemedi.');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (pwd.new_password.length < 6) { toast.error('Yeni şifre en az 6 karakter olmalıdır.'); return; }
    if (pwd.new_password !== pwd.confirm_password) { toast.error('Yeni şifreler eşleşmiyor.'); return; }
    if (pwd.new_password === pwd.current_password) { toast.error('Yeni şifre eskisinden farklı olmalıdır.'); return; }
    setLoading(true);
    try {
      await axios.post('/auth/change-password', {
        current_password: pwd.current_password,
        new_password: pwd.new_password,
      });
      toast.success('Şifreniz başarıyla güncellendi.');
      setPwd({ current_password: '', new_password: '', confirm_password: '' });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Şifre değiştirilemedi.');
    } finally { setLoading(false); }
  };

  const Field = ({ icon: Icon, label, value }) => (
    <div className="flex items-start gap-3 py-2">
      <Icon className="w-4 h-4 mt-1 text-gray-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-xs text-gray-500">{label}</div>
        <div className="text-sm font-medium text-gray-900 break-words">{value || '—'}</div>
      </div>
    </div>
  );

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="profile" title="Profilim" subtitle="Hesap bilgilerinizi görüntüleyin, şifrenizi değiştirin ve güvenliğinizi yönetin.">
    <div className="max-w-3xl mx-auto p-4 space-y-4">

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <UserIcon className="w-5 h-5" /> Kullanıcı Bilgileri
            </CardTitle>
            <CardDescription>Sistemdeki kayıtlı bilgileriniz</CardDescription>
          </div>
          {!editing && (
            <Button size="sm" variant="outline" onClick={startEdit}>
              <Pencil className="w-3.5 h-3.5 mr-1" /> Düzenle
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {editing ? (
            <form onSubmit={saveProfile} className="space-y-4 max-w-md">
              <div>
                <Label>Ad Soyad</Label>
                <Input value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  required minLength={2} autoFocus />
              </div>
              <div>
                <Label>Telefon</Label>
                <Input value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                  placeholder="+90 555 123 45 67" />
              </div>
              <div className="flex gap-2">
                <Button type="submit" disabled={savingProfile}>
                  {savingProfile ? 'Kaydediliyor…' : 'Kaydet'}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setEditing(false)} disabled={savingProfile}>
                  İptal
                </Button>
              </div>
              <p className="text-xs text-gray-500">
                E-posta, kullanıcı adı ve rol değiştirilemez. Bu bilgilerin değişmesi gerekiyorsa sistem yöneticinizle iletişime geçin.
              </p>
            </form>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
              <Field icon={UserIcon} label="Ad Soyad" value={me?.name} />
              <Field icon={KeyRound} label="Kullanıcı Adı" value={me?.username} />
              <Field icon={Mail} label="E-posta" value={me?.email} />
              <Field icon={Phone} label="Telefon" value={me?.phone} />
              <Field icon={Shield} label="Rol" value={me?.role} />
              <Field icon={Hotel} label="Otel ID" value={tenantInfo?.hotel_id} />
            </div>
          )}
        </CardContent>
      </Card>

      <TwoFactorSection />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <KeyRound className="w-5 h-5" /> Şifre Değiştir
          </CardTitle>
          <CardDescription>Hesabınızın güvenliği için düzenli olarak şifrenizi yenileyin.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
            <div>
              <Label>Mevcut Şifre</Label>
              <Input type="password" value={pwd.current_password}
                onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })}
                required autoComplete="current-password" />
            </div>
            <div>
              <Label>Yeni Şifre</Label>
              <Input type="password" value={pwd.new_password}
                onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })}
                required minLength={6} autoComplete="new-password" />
              <p className="text-xs text-gray-500 mt-1">En az 6 karakter olmalı.</p>
            </div>
            <div>
              <Label>Yeni Şifre (Tekrar)</Label>
              <Input type="password" value={pwd.confirm_password}
                onChange={(e) => setPwd({ ...pwd, confirm_password: e.target.value })}
                required minLength={6} autoComplete="new-password" />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? 'Güncelleniyor…' : 'Şifremi Güncelle'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
    </Layout>
  );
};

// ── 2FA Management ─────────────────────────────────────────────────
function TwoFactorSection() {
  const [status, setStatus] = useState(null);
  const [setup, setSetup] = useState(null); // {secret, qr_code, otpauth_uri}
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [backupCodes, setBackupCodes] = useState(null);
  const [disableForm, setDisableForm] = useState({ open: false, password: '', code: '' });

  const loadStatus = async () => {
    try {
      const r = await axios.get('/2fa/status');
      setStatus(r.data);
    } catch { /* ignore */ }
  };
  useEffect(() => { loadStatus(); }, []);

  const startSetup = async () => {
    setBusy(true);
    try {
      const r = await axios.post('/2fa/setup');
      setSetup(r.data);
      setCode('');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Başlatılamadı');
    } finally { setBusy(false); }
  };

  const confirmSetup = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await axios.post('/2fa/setup/confirm', { code: code.trim() });
      setBackupCodes(r.data.backup_codes);
      setSetup(null);
      setCode('');
      await loadStatus();
      toast.success('2FA etkinleştirildi');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Doğrulama hatası');
    } finally { setBusy(false); }
  };

  const disable = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await axios.post('/2fa/disable', {
        password: disableForm.password,
        code: disableForm.code.trim(),
      });
      toast.success('2FA devre dışı bırakıldı');
      setDisableForm({ open: false, password: '', code: '' });
      await loadStatus();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Devre dışı bırakılamadı');
    } finally { setBusy(false); }
  };

  const regen = async () => {
    const c = window.prompt('Yedek kodları yenilemek için 6 haneli mevcut TOTP kodunu girin:');
    if (!c) return;
    setBusy(true);
    try {
      const r = await axios.post('/2fa/regenerate-backup-codes', { code: c.trim() });
      setBackupCodes(r.data.backup_codes);
      await loadStatus();
      toast.success('Yedek kodlar yenilendi');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Yenilenemedi');
    } finally { setBusy(false); }
  };

  const copyCodes = () => {
    if (!backupCodes) return;
    navigator.clipboard.writeText(backupCodes.join('\n')).then(
      () => toast.success('Yedek kodlar panoya kopyalandı'),
      () => toast.error('Kopyalanamadı')
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Smartphone className="w-5 h-5" /> İki Adımlı Doğrulama (2FA)
          {status?.enabled && (
            <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Etkin
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Google/Microsoft Authenticator gibi bir uygulama ile hesabınıza ek bir güvenlik katmanı ekleyin.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Backup codes display (one-time) */}
        {backupCodes && (
          <div className="rounded-lg border-2 border-amber-300 bg-amber-50 p-4 space-y-2">
            <div className="flex items-center gap-2 text-amber-900 font-semibold">
              <AlertTriangle className="w-4 h-4" /> Yedek Kodlarınız
            </div>
            <p className="text-xs text-amber-800">
              Telefonunuzu kaybederseniz bu kodlardan birini kullanarak giriş yapabilirsiniz.
              <strong> Bu kodlar bir daha gösterilmeyecek</strong> — güvenli bir yere kaydedin.
            </p>
            <div className="grid grid-cols-2 gap-2 font-mono text-sm bg-white rounded p-2">
              {backupCodes.map((c) => <div key={c}>{c}</div>)}
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={copyCodes}>
                <Copy className="w-3 h-3 mr-1" /> Kopyala
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setBackupCodes(null)}>
                Kaydettim, kapat
              </Button>
            </div>
          </div>
        )}

        {/* Setup flow */}
        {setup && (
          <div className="rounded-lg border bg-slate-50 p-4 space-y-3">
            <p className="text-sm">1) Authenticator uygulamanızla bu QR kodu tarayın:</p>
            <div className="flex justify-center">
              <img src={setup.qr_code} alt="2FA QR" className="w-48 h-48 bg-white p-2 rounded" />
            </div>
            <details className="text-xs text-gray-600">
              <summary className="cursor-pointer">Manuel kod (QR taranamıyorsa)</summary>
              <div className="mt-1 font-mono break-all bg-white p-2 rounded">{setup.secret}</div>
            </details>
            <form onSubmit={confirmSetup} className="space-y-2">
              <Label>2) Uygulamadan gelen 6 haneli kodu girin:</Label>
              <Input
                autoFocus
                inputMode="numeric"
                placeholder="123 456"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                style={{ textAlign: 'center', letterSpacing: '0.3em' }}
              />
              <div className="flex gap-2">
                <Button type="submit" disabled={busy || code.trim().length < 6}>
                  {busy ? 'Doğrulanıyor…' : 'Etkinleştir'}
                </Button>
                <Button type="button" variant="ghost" onClick={() => { setSetup(null); setCode(''); }}>
                  İptal
                </Button>
              </div>
            </form>
          </div>
        )}

        {/* Default state controls */}
        {!setup && !status?.enabled && (
          <div className="space-y-3">
            <p className="text-sm text-gray-600">2FA şu anda kapalı.</p>
            <Button onClick={startSetup} disabled={busy}>
              <Smartphone className="w-4 h-4 mr-2" />
              {busy ? 'Hazırlanıyor…' : '2FA Etkinleştir'}
            </Button>
          </div>
        )}

        {!setup && status?.enabled && (
          <div className="space-y-3">
            <div className="text-sm text-gray-700 space-y-1">
              <div>Etkinleştirilme: <span className="font-mono text-xs">{status.enabled_at?.slice(0, 19)}</span></div>
              <div>Son kullanım: <span className="font-mono text-xs">{status.last_used_at?.slice(0, 19) || 'Henüz yok'}</span></div>
              <div>Kalan yedek kod: <strong>{status.backup_codes_remaining}</strong> / 10</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={regen} disabled={busy}>
                <RefreshCw className="w-4 h-4 mr-2" /> Yedek Kodları Yenile
              </Button>
              <Button
                variant="outline"
                className="text-red-600 border-red-200 hover:bg-red-50"
                onClick={() => setDisableForm({ open: true, password: '', code: '' })}
              >
                2FA'yı Kapat
              </Button>
            </div>

            {disableForm.open && (
              <form onSubmit={disable} className="space-y-2 border-t pt-3">
                <p className="text-xs text-gray-500">
                  Devre dışı bırakmak için parolanızı ve mevcut bir 2FA kodunu girin.
                </p>
                <div>
                  <Label>Parola</Label>
                  <Input type="password" value={disableForm.password}
                    onChange={(e) => setDisableForm((f) => ({ ...f, password: e.target.value }))}
                    required autoComplete="current-password" />
                </div>
                <div>
                  <Label>2FA Kodu (TOTP veya yedek kod)</Label>
                  <Input value={disableForm.code} inputMode="numeric"
                    onChange={(e) => setDisableForm((f) => ({ ...f, code: e.target.value }))}
                    required />
                </div>
                <div className="flex gap-2">
                  <Button type="submit" variant="destructive" disabled={busy}>
                    {busy ? 'İşleniyor…' : 'Onayla ve Kapat'}
                  </Button>
                  <Button type="button" variant="ghost"
                    onClick={() => setDisableForm({ open: false, password: '', code: '' })}>
                    İptal
                  </Button>
                </div>
              </form>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ProfilePage;
