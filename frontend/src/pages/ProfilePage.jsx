import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { StatusBadge } from '@/components/ui/status-badge';

import { promptDialog } from '@/lib/dialogs';
import {
  User as UserIcon, Hotel, Shield, KeyRound, Mail, Phone,
  Smartphone, CheckCircle2, AlertTriangle, Copy, RefreshCw, Pencil,
  Download, ShieldCheck,
} from 'lucide-react';

const ROLE_LABELS = {
  super_admin: 'Süper Admin',
  admin: 'Yönetici',
  manager: 'Müdür',
  front_desk: 'Resepsiyon',
  housekeeping: 'Kat Hizmetleri',
  maintenance: 'Teknik Servis',
  accounting: 'Muhasebe',
  fnb: 'Yiyecek & İçecek',
  spa: 'Spa',
  guest: 'Misafir',
};

const ROLE_INTENT = {
  super_admin: 'danger',
  admin: 'info',
  manager: 'info',
};

const formatDateTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('tr-TR', {
      day: '2-digit', month: 'long', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso.slice(0, 19);
  }
};

const copyToClipboard = async (text) => {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fallthrough */ }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    return true;
  } catch {
    return false;
  }
};

const ProfilePage = ({ user, tenant }) => {
  const [me, setMe] = useState(user || null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [pwd, setPwd] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', phone: '' });
  const [savingProfile, setSavingProfile] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const loadMe = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setRefreshing(true);
    try {
      const res = await axios.get('/auth/me');
      setMe(res.data);
      return res.data;
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Profil bilgileri alınamadı.');
      return null;
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get('/auth/me');
        if (!cancelled) setMe(res.data);
      } catch (err) {
        if (!cancelled) {
          toast.error(err.response?.data?.detail || 'Profil bilgileri alınamadı.');
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleRefresh = async () => {
    await loadMe();
    setReloadKey((k) => k + 1);
  };

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

  const validatePassword = (p) => {
    if (p.length < 8) return 'Yeni şifre en az 8 karakter olmalıdır.';
    if (!/[A-Za-zğüşöçıİĞÜŞÖÇ]/.test(p)) return 'Şifre en az bir harf içermelidir.';
    if (!/\d/.test(p)) return 'Şifre en az bir rakam içermelidir.';
    return null;
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    const err = validatePassword(pwd.new_password);
    if (err) { toast.error(err); return; }
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

  const Field = ({ icon: Icon, label, value, valueNode }) => (
    <div className="flex items-start gap-3 py-2">
      <Icon className="w-4 h-4 mt-1 text-slate-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-xs text-slate-500">{label}</div>
        <div className="text-sm font-medium text-slate-900 break-words">
          {valueNode ?? (value || '—')}
        </div>
      </div>
    </div>
  );

  const roleKey = me?.role || '';
  const roleLabel = ROLE_LABELS[roleKey] || roleKey || '—';
  const roleIntent = ROLE_INTENT[roleKey] || 'neutral';

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      <PageHeader
        icon={UserIcon}
        title="Profilim"
        subtitle="Hesap bilgileriniz, iki adımlı doğrulama ve şifre yönetimi"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        }
      />

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
                  placeholder="+90 555 123 45 67"
                  inputMode="tel"
                  pattern="[+0-9 ()-]{6,20}"
                  title="Geçerli bir telefon numarası girin (örn. +90 555 123 45 67)" />
              </div>
              <div className="flex gap-2">
                <Button type="submit" disabled={savingProfile}>
                  {savingProfile ? 'Kaydediliyor…' : 'Kaydet'}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setEditing(false)} disabled={savingProfile}>
                  İptal
                </Button>
              </div>
              <p className="text-xs text-slate-500">
                E-posta, kullanıcı adı ve rol değiştirilemez. Bu bilgilerin değişmesi gerekiyorsa sistem yöneticinizle iletişime geçin.
              </p>
            </form>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
              <Field icon={UserIcon} label="Ad Soyad" value={me?.name} />
              {me?.username ? (
                <Field icon={KeyRound} label="Kullanıcı Adı" value={me.username} />
              ) : null}
              <Field icon={Mail} label="E-posta" value={me?.email} />
              <Field icon={Phone} label="Telefon" value={me?.phone} />
              <Field
                icon={Shield}
                label="Rol"
                valueNode={<StatusBadge intent={roleIntent}>{roleLabel}</StatusBadge>}
              />
              <Field icon={Hotel} label="Otel ID" value={tenant?.hotel_id} />
            </div>
          )}
        </CardContent>
      </Card>

      <TwoFactorSection key={reloadKey} />

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
                required minLength={8} autoComplete="new-password" />
              <p className="text-xs text-slate-500 mt-1">
                En az 8 karakter, en az bir harf ve bir rakam içermeli.
              </p>
            </div>
            <div>
              <Label>Yeni Şifre (Tekrar)</Label>
              <Input type="password" value={pwd.confirm_password}
                onChange={(e) => setPwd({ ...pwd, confirm_password: e.target.value })}
                required minLength={8} autoComplete="new-password" />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? 'Güncelleniyor…' : 'Şifremi Güncelle'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

// ── 2FA Management ─────────────────────────────────────────────────
function TwoFactorSection() {
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState(false);
  const [setup, setSetup] = useState(null); // {secret, qr_code, otpauth_uri}
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [backupCodes, setBackupCodes] = useState(null);
  const [disableForm, setDisableForm] = useState({ open: false, password: '', code: '' });

  const loadStatus = async () => {
    try {
      const r = await axios.get('/2fa/status');
      setStatus(r.data);
      setStatusError(false);
    } catch (err) {
      setStatusError(true);
      toast.error(err.response?.data?.detail || '2FA durumu alınamadı.');
    }
  };
  useEffect(() => { loadStatus(); }, []);

  // Warn before unloading the page while one-time backup codes are visible
  useEffect(() => {
    if (!backupCodes) return undefined;
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = '';
      return '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [backupCodes]);

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
    const c = await promptDialog({ message: 'Yedek kodları yenilemek için 6 haneli mevcut TOTP kodunu girin:' });
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

  const copyCodes = async () => {
    if (!backupCodes) return;
    const ok = await copyToClipboard(backupCodes.join('\n'));
    if (ok) toast.success('Yedek kodlar panoya kopyalandı');
    else toast.error('Kopyalanamadı');
  };

  const downloadCodes = () => {
    if (!backupCodes) return;
    const header = `Syroce PMS — 2FA Yedek Kodları\nOluşturma: ${new Date().toLocaleString('tr-TR')}\n\n`;
    const blob = new Blob([header + backupCodes.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `syroce-2fa-backup-codes-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copySecret = async () => {
    if (!setup?.secret) return;
    const ok = await copyToClipboard(setup.secret);
    if (ok) toast.success('Gizli anahtar kopyalandı');
    else toast.error('Kopyalanamadı');
  };

  const totalBackup = (status?.backup_codes_total) || 10;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Smartphone className="w-5 h-5" /> İki Adımlı Doğrulama (2FA)
          {status?.enabled && (
            <StatusBadge intent="success" icon={CheckCircle2}>Etkin</StatusBadge>
          )}
          {statusError && (
            <StatusBadge intent="danger" icon={AlertTriangle}>Durum alınamadı</StatusBadge>
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
              <strong> Bu kodlar bir daha gösterilmeyecek</strong> — güvenli bir yere kaydedin veya indirin.
            </p>
            <div className="grid grid-cols-2 gap-2 font-mono text-sm bg-white rounded p-2">
              {backupCodes.map((c) => <div key={c}>{c}</div>)}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={downloadCodes}>
                <Download className="w-3 h-3 mr-1" /> İndir (.txt)
              </Button>
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
              <img src={setup.qr_code} alt="2FA QR" className="w-48 h-48 bg-white p-2 rounded border border-slate-200" />
            </div>
            <details className="text-xs text-slate-600">
              <summary className="cursor-pointer">Manuel kod (QR taranamıyorsa)</summary>
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 font-mono break-all bg-white p-2 rounded border border-slate-200">
                  {setup.secret}
                </div>
                <Button type="button" size="sm" variant="outline" onClick={copySecret}>
                  <Copy className="w-3 h-3 mr-1" /> Kopyala
                </Button>
              </div>
            </details>
            <form onSubmit={confirmSetup} className="space-y-2">
              <Label>2) Uygulamadan gelen 6 haneli kodu girin:</Label>
              <Input
                autoFocus
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="\d{6}"
                maxLength={6}
                placeholder="123456"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
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
        {!setup && !status?.enabled && !statusError && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">2FA şu anda kapalı.</p>
            <Button onClick={startSetup} disabled={busy}>
              <Smartphone className="w-4 h-4 mr-2" />
              {busy ? 'Hazırlanıyor…' : '2FA Etkinleştir'}
            </Button>
          </div>
        )}

        {!setup && status?.enabled && (
          <div className="space-y-3">
            <div className="text-sm text-slate-700 space-y-1">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>Etkinleştirilme: <strong>{formatDateTime(status.enabled_at)}</strong></span>
              </div>
              <div>Son kullanım: <strong>{status.last_used_at ? formatDateTime(status.last_used_at) : 'Henüz yok'}</strong></div>
              <div>
                Kalan yedek kod:{' '}
                <strong>{status.backup_codes_remaining}</strong> / {totalBackup}
                {status.backup_codes_remaining <= 2 && (
                  <span className="ml-2">
                    <StatusBadge intent="warning" icon={AlertTriangle}>Az kaldı</StatusBadge>
                  </span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={regen} disabled={busy}>
                <RefreshCw className="w-4 h-4 mr-2" /> Yedek Kodları Yenile
              </Button>
              <Button
                variant="outline"
                className="text-rose-600 border-rose-200 hover:bg-rose-50"
                onClick={() => setDisableForm({ open: true, password: '', code: '' })}
              >
                2FA'yı Kapat
              </Button>
            </div>

            {disableForm.open && (
              <form onSubmit={disable} className="space-y-2 border-t pt-3">
                <p className="text-xs text-slate-500">
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
                  <Input value={disableForm.code}
                    autoComplete="one-time-code"
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

        {!setup && statusError && (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="font-semibold">2FA durumu yüklenemedi.</div>
              <div className="text-xs mt-0.5">Lütfen daha sonra tekrar deneyin veya sayfayı yenileyin.</div>
            </div>
            <Button size="sm" variant="outline" onClick={loadStatus}>
              <RefreshCw className="w-3.5 h-3.5 mr-1" /> Tekrar dene
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ProfilePage;
