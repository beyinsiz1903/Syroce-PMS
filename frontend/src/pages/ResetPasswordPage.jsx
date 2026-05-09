import { useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { KeyRound } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const ResetPasswordPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = useMemo(() => params.get('token') || '', [params]);
  const [pwd, setPwd] = useState({ new_password: '', confirm: '' });
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pwd.new_password.length < 6) {
      toast.error('Şifre en az 6 karakter olmalı.');
      return;
    }
    if (pwd.new_password !== pwd.confirm) {
      toast.error('Şifreler eşleşmiyor.');
      return;
    }
    setLoading(true);
    try {
      await axios.post('/auth/reset-password-by-token', {
        token,
        new_password: pwd.new_password,
      });
      toast.success('Şifreniz güncellendi. Lütfen giriş yapın.');
      setDone(true);
      setTimeout(() => navigate('/auth', { replace: true }), 1200);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Şifre sıfırlanamadı.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', padding: 20 }}>
      <Card style={{ width: '100%', maxWidth: 440 }}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><KeyRound className="w-5 h-5" /> {t('cm.pages_ResetPasswordPage.sifre_sifirlama')}</CardTitle>
          <CardDescription>{t('cm.pages_ResetPasswordPage.yeni_bir_sifre_belirleyin')}</CardDescription>
        </CardHeader>
        <CardContent>
          {!token ? (
            <div className="text-sm text-red-600">
              {t('cm.pages_ResetPasswordPage.gecersiz_veya_eksik_baglanti_lutfen_e_po')}
            </div>
          ) : done ? (
            <div className="text-sm text-green-700">
              {t('cm.pages_ResetPasswordPage.sifreniz_guncellendi_giris_ekranina_yonl')}
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div>
                <Label>{t('cm.pages_ResetPasswordPage.yeni_sifre')}</Label>
                <Input
                  type="password"
                  value={pwd.new_password}
                  onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })}
                  required
                  minLength={6}
                  autoComplete="new-password"
                />
                <p className="text-xs text-gray-500 mt-1">En az 6 karakter.</p>
              </div>
              <div>
                <Label>{t('cm.pages_ResetPasswordPage.yeni_sifre_tekrar')}</Label>
                <Input
                  type="password"
                  value={pwd.confirm}
                  onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })}
                  required
                  minLength={6}
                  autoComplete="new-password"
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Güncelleniyor…' : 'Şifremi Güncelle'}
              </Button>
              <button
                type="button"
                onClick={() => navigate('/auth')}
                className="text-sm text-blue-600 hover:text-blue-800 w-full text-center"
              >
                {t('cm.pages_ResetPasswordPage.giris_ekranina_don')}
              </button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ResetPasswordPage;
