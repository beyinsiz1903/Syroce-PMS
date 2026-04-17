import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { User as UserIcon, Hotel, Shield, KeyRound, Mail, Phone } from 'lucide-react';

const ProfilePage = ({ user, tenant }) => {
  const [me, setMe] = useState(user || null);
  const [tenantInfo, setTenantInfo] = useState(tenant || null);
  const [loading, setLoading] = useState(false);
  const [pwd, setPwd] = useState({ current_password: '', new_password: '', confirm_password: '' });

  useEffect(() => {
    // Refresh /auth/me to ensure we have latest fields (username, hotel_id, etc.)
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get('/auth/me');
        if (!cancelled) setMe(res.data);
      } catch {
        // keep existing
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (pwd.new_password.length < 6) {
      toast.error('Yeni şifre en az 6 karakter olmalıdır.');
      return;
    }
    if (pwd.new_password !== pwd.confirm_password) {
      toast.error('Yeni şifreler eşleşmiyor.');
      return;
    }
    if (pwd.new_password === pwd.current_password) {
      toast.error('Yeni şifre eskisinden farklı olmalıdır.');
      return;
    }
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
    } finally {
      setLoading(false);
    }
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
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Profilim</h1>
        <p className="text-sm text-gray-500">Hesap bilgilerinizi görüntüleyin ve şifrenizi değiştirin.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <UserIcon className="w-5 h-5" /> Kullanıcı Bilgileri
          </CardTitle>
          <CardDescription>Sistemdeki kayıtlı bilgileriniz</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
          <Field icon={UserIcon} label="Ad Soyad" value={me?.name} />
          <Field icon={KeyRound} label="Kullanıcı Adı" value={me?.username} />
          <Field icon={Mail} label="E-posta" value={me?.email} />
          <Field icon={Phone} label="Telefon" value={me?.phone} />
          <Field icon={Shield} label="Rol" value={me?.role} />
          <Field icon={Hotel} label="Otel ID" value={tenantInfo?.hotel_id} />
        </CardContent>
      </Card>

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
              <Input
                type="password"
                value={pwd.current_password}
                onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })}
                required
                autoComplete="current-password"
              />
            </div>
            <div>
              <Label>Yeni Şifre</Label>
              <Input
                type="password"
                value={pwd.new_password}
                onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })}
                required
                minLength={6}
                autoComplete="new-password"
              />
              <p className="text-xs text-gray-500 mt-1">En az 6 karakter olmalı.</p>
            </div>
            <div>
              <Label>Yeni Şifre (Tekrar)</Label>
              <Input
                type="password"
                value={pwd.confirm_password}
                onChange={(e) => setPwd({ ...pwd, confirm_password: e.target.value })}
                required
                minLength={6}
                autoComplete="new-password"
              />
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

export default ProfilePage;
