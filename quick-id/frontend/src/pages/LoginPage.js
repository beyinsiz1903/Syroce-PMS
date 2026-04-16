import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '../lib/AuthContext';
import { api } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Button } from '../components/ui/button';
import { CreditCard, Loader2, LogIn, Lock } from 'lucide-react';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [lockoutInfo, setLockoutInfo] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) { toast.error('E-posta ve şifre gerekli'); return; }
    setLoading(true);
    setLockoutInfo(null);
    try {
      const result = await api.login(email, password);
      login(result.token, result.user);
      toast.success(`Hoş geldiniz, ${result.user.name}!`);
      navigate('/');
    } catch (err) {
      if (err.locked) {
        setLockoutInfo({
          message: err.message,
          remaining_minutes: err.remaining_minutes,
        });
        toast.error(err.message);
      } else {
        toast.error(err.message || 'Giriş başarısız');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[hsl(var(--background))] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-[var(--brand-sky)] flex items-center justify-center mx-auto mb-4">
            <CreditCard className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-semibold text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Quick ID
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Otel Kimlik Okuyucu Sistemi</p>
        </div>

        <Card className="bg-white shadow-lg">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-center">Giriş Yap</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {lockoutInfo && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700">
                  <Lock className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <div className="text-sm">
                    <p className="font-medium">Hesap Kilitlendi</p>
                    <p className="text-xs mt-0.5">{lockoutInfo.message}</p>
                  </div>
                </div>
              )}
              <div className="space-y-1.5">
                <Label className="text-sm">E-posta</Label>
                <Input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="ornek@otel.com"
                  data-testid="login-email-input"
                  autoFocus
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm">Şifre</Label>
                <Input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  data-testid="login-password-input"
                />
              </div>
              <Button
                type="submit"
                disabled={loading}
                className="w-full bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white h-11"
                data-testid="login-submit-button"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Giriş yapılıyor...</>
                ) : (
                  <><LogIn className="w-4 h-4 mr-2" /> Giriş Yap</>
                )}
              </Button>
            </form>

            <div className="mt-6 p-3 rounded-lg bg-[hsl(var(--secondary))] text-xs text-muted-foreground">
              <p className="font-medium mb-1">Yardım:</p>
              <p>Giriş bilgilerinizi sistem yöneticinizden alabilirsiniz.</p>
              <p className="mt-1">Şifrenizi unuttuysanız yöneticinize başvurun.</p>
            </div>
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground mt-6">
          Kimlik verileri KVKK kapsamında korunmaktadır.
        </p>
      </div>
    </div>
  );
}
