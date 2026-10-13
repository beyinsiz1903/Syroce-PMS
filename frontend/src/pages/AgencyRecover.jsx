import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const rawBase = (import.meta.env.VITE_BACKEND_URL || '/api').replace(/\/+$/, '');
const api = axios.create({ baseURL: rawBase.endsWith('/api') ? rawBase : `${rawBase}/api`, timeout: 30000, withCredentials: false });
api.interceptors.request.use(config => { delete config.headers.Authorization; return config; });

export default function AgencyRecover() {
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  useEffect(() => { window.history.replaceState(window.history.state, '', window.location.pathname); }, []);
  const submit = async event => {
    event.preventDefault(); setError(''); setMessage('');
    if (token && (password !== confirmation || password.length < 12 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password) || new TextEncoder().encode(password).length > 72)) {
      setError('Şifreler eşleşmeli; en az 12 karakter, büyük/küçük harf ve rakam içermeli, 72 baytı aşmamalıdır.'); return;
    }
    setBusy(true);
    try {
      if (token) {
        await api.post('/marketplace/v1/extranet/auth/reset', { token, password });
        setPassword(''); setConfirmation(''); setDone(true); setMessage('Şifreniz yenilendi. Yeni şifrenizle acente girişini kullanın.');
      } else {
        const { data } = await api.post('/marketplace/v1/extranet/auth/recover', { email: email.trim().toLowerCase() });
        setMessage(data.message);
      }
    } catch (err) {
      setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'İşlem tamamlanamadı. Lütfen tekrar deneyin.');
    } finally { setBusy(false); }
  };
  return <main className="min-h-screen bg-slate-50 p-6 flex items-center justify-center">
    <section className="w-full max-w-md rounded-xl bg-white p-6 shadow space-y-4">
      <h1 className="text-xl font-semibold">Acente hesabı — Şifremi unuttum</h1>
      {!done && <form onSubmit={submit} className="space-y-3">
        {token ? <>
          <Label htmlFor="recovery-password">Yeni şifre</Label>
          <Input id="recovery-password" type="password" required autoComplete="new-password" minLength={12} value={password} onChange={e => setPassword(e.target.value)} />
          <Label htmlFor="recovery-confirm">Yeni şifre tekrar</Label>
          <Input id="recovery-confirm" type="password" required autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} />
          <p className="text-sm">En az 12 karakter, büyük/küçük harf ve rakam kullanın.</p>
        </> : <>
          <Label htmlFor="recovery-email">Acente hesabı e-posta adresi</Label>
          <Input id="recovery-email" type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} />
          <p className="text-sm">Global ve otele bağlı acente hesapları için kullanabilirsiniz. Henüz etkinleşmemiş hesaplar için davet e-postasındaki bağlantıyı açın.</p>
        </>}
        <Button type="submit" disabled={busy}>{busy ? 'İşleniyor…' : token ? 'Şifreyi yenile' : 'Yenileme bağlantısı gönder'}</Button>
      </form>}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {token && !done && <Button variant="outline" disabled={busy} onClick={() => { setToken(''); setError(''); setPassword(''); setConfirmation(''); }}>Yeni bağlantı iste</Button>}
      <Link to="/acente-girisi" className="block text-blue-700 underline">Acente girişine dön</Link>
    </section>
  </main>;
}
