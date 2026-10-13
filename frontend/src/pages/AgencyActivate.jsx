import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const rawBase = import.meta.env.VITE_BACKEND_URL || '/api';
const baseURL = rawBase.replace(/\/+$/, '').endsWith('/api') ? rawBase.replace(/\/+$/, '') : `${rawBase.replace(/\/+$/, '')}/api`;
const api = axios.create({ baseURL, timeout: 30000, withCredentials: false });
api.interceptors.request.use((config) => {
  delete config.headers.Authorization;
  return config;
});

export default function AgencyActivate() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { window.history.replaceState(window.history.state, '', window.location.pathname); }, []);
  const submit = async (event) => {
    event.preventDefault(); setError('');
    if (password !== confirmation) { setError('Şifreler eşleşmiyor.'); return; }
    if (password.length < 12 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password) || new TextEncoder().encode(password).length > 72) {
      setError('Şifre 12–72 karakter, büyük/küçük harf ve rakam içermeli; UTF-8 olarak 72 baytı aşmamalıdır.'); return;
    }
    setBusy(true);
    try {
      await api.post('/marketplace/v1/extranet/invitations/accept', { token, password });
      setPassword(''); setConfirmation(''); setDone(true);
    } catch (err) {
      setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Etkinleştirme tamamlanamadı. Bağlantınızı kontrol edin; işlem tamamlanmışsa acente girişini deneyin.');
    } finally { setBusy(false); }
  };
  return <main className="min-h-screen bg-slate-50 p-6 flex items-center justify-center">
    <section className="w-full max-w-md rounded-xl bg-white p-6 shadow space-y-4">
      <h1 className="text-xl font-semibold">Syroce acente hesabını etkinleştir</h1>
      {done ? <p role="status">Şifreniz oluşturuldu. Acente hesabınıza giriş yapabilirsiniz. Satış için tesis sözleşmesi ve müsaitlik ayrıca doğrulanır.</p>
        : !token ? <p role="alert">Davet bağlantısı bulunamadı. E-postanızdaki bağlantıyı yeniden açın veya yöneticinizden yeni davet isteyin.</p>
          : <form onSubmit={submit} className="space-y-3">
            <p>Şifrenizi yalnızca siz belirleyin. En az 12 karakter, büyük/küçük harf ve rakam kullanın.</p>
            <Label htmlFor="new-password">Yeni şifre</Label>
            <Input id="new-password" type="password" autoComplete="new-password" required minLength={12} maxLength={72} value={password} onChange={(e) => setPassword(e.target.value)} />
            <Label htmlFor="confirm-password">Şifre tekrar</Label>
            <Input id="confirm-password" type="password" autoComplete="new-password" required value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
            {error && <p role="alert">{error}</p>}
            <Button type="submit" disabled={busy}>{busy ? 'Etkinleştiriliyor…' : 'Şifremi belirle ve etkinleştir'}</Button>
          </form>}
      <Link to="/acente-girisi" className="block text-blue-700 underline">Acente girişine git</Link>
    </section>
  </main>;
}
