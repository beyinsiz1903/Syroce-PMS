import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Building2, CheckCircle2, Loader2, LockKeyhole, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const rawBackendUrl = import.meta.env.VITE_BACKEND_URL || '/api';
const apiBase = rawBackendUrl.endsWith('/api') ? rawBackendUrl : `${rawBackendUrl.replace(/\/+$/, '')}/api`;
const client = axios.create({ baseURL: apiBase, timeout: 30000, withCredentials: false });

const detail = error => error?.response?.data?.detail || 'İşlem tamamlanamadı. Lütfen tekrar deneyin.';

export default function AgencyConnectAuthorize() {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const request = useMemo(() => ({
    client_id: params.get('client_id') || '',
    redirect_uri: params.get('redirect_uri') || '',
    code_challenge: params.get('code_challenge') || '',
    state: params.get('state') || '',
  }), [params]);
  const [token, setToken] = useState(() => localStorage.getItem('agency_token') || '');
  const [credentials, setCredentials] = useState({ email: '', password: '' });
  const [clientInfo, setClientInfo] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const { data } = await client.get('/marketplace/v1/connect/client', {
          params: { client_id: request.client_id, redirect_uri: request.redirect_uri },
        });
        if (active) setClientInfo(data);
      } catch (err) {
        if (active) setError(detail(err));
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, [request.client_id, request.redirect_uri]);

  useEffect(() => {
    if (!token || !clientInfo) return;
    let active = true;
    client.get('/marketplace/v1/extranet/profile', { headers: { Authorization: `Bearer ${token}` } })
      .then(({ data }) => { if (active) setProfile(data); })
      .catch(() => {
        if (!active) return;
        localStorage.removeItem('agency_token');
        setToken('');
        setProfile(null);
      });
    return () => { active = false; };
  }, [clientInfo, token]);

  const login = async event => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const { data } = await client.post('/marketplace/v1/extranet/auth/login', {
        email: credentials.email.trim().toLowerCase(),
        password: credentials.password,
      });
      localStorage.setItem('agency_token', data.token);
      localStorage.setItem('agency_portal_mode', 'marketplace');
      setToken(data.token);
      setProfile({ agency: data.agency, user: data.user });
    } catch (err) {
      setError(detail(err));
    } finally {
      setSubmitting(false);
    }
  };

  const approve = async () => {
    setSubmitting(true);
    setError('');
    try {
      const { data } = await client.post('/marketplace/v1/connect/authorize', request, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const destination = new URL(request.redirect_uri);
      destination.searchParams.set('code', data.code);
      destination.searchParams.set('state', data.state);
      window.location.assign(destination.toString());
    } catch (err) {
      setError(detail(err));
      setSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100">
      <section className="mx-auto max-w-lg overflow-hidden rounded-3xl border border-slate-800 bg-slate-900 shadow-2xl">
        <div className="border-b border-slate-800 bg-gradient-to-br from-blue-950 to-slate-900 p-7">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-300">
            <ShieldCheck aria-hidden="true" />
          </div>
          <h1 className="text-2xl font-bold">Syroce hesabıyla bağlan</h1>
          <p className="mt-2 text-sm leading-6 text-slate-300">Kalıcı anahtar kopyalamadan acente hesabınızı güvenli biçimde bağlayın.</p>
        </div>

        <div className="space-y-6 p-7">
          {loading ? <div className="flex items-center gap-3 text-slate-300"><Loader2 className="animate-spin" /> Bağlantı doğrulanıyor…</div> : null}
          {clientInfo ? (
            <div className="flex items-center gap-4 rounded-2xl border border-slate-700 bg-slate-800/70 p-4">
              <Building2 className="text-blue-300" aria-hidden="true" />
              <div><p className="font-semibold">{clientInfo.name}</p><p className="text-xs text-slate-400">Syroce Marketplace erişimi istiyor</p></div>
            </div>
          ) : null}

          {error ? <div role="alert" className="rounded-xl border border-red-800 bg-red-950/40 p-3 text-sm text-red-200">{error}</div> : null}

          {!loading && clientInfo && !profile ? (
            <form className="space-y-4" onSubmit={login}>
              <div className="space-y-2"><Label htmlFor="email">Acente e-postası</Label><Input id="email" type="email" autoComplete="username" required value={credentials.email} onChange={event => setCredentials(current => ({ ...current, email: event.target.value }))} /></div>
              <div className="space-y-2"><Label htmlFor="password">Şifre</Label><Input id="password" type="password" autoComplete="current-password" required value={credentials.password} onChange={event => setCredentials(current => ({ ...current, password: event.target.value }))} /></div>
              <Button type="submit" className="w-full" disabled={submitting}>{submitting ? <Loader2 className="animate-spin" /> : <LockKeyhole />} Güvenli giriş yap</Button>
            </form>
          ) : null}

          {profile ? (
            <div className="space-y-5">
              <div className="rounded-2xl border border-emerald-900 bg-emerald-950/25 p-4">
                <div className="flex items-center gap-2 font-semibold text-emerald-300"><CheckCircle2 size={18} /> {profile.agency?.name}</div>
                <p className="mt-2 text-sm text-slate-300">Bu acente hesabının otel keşfi, sözleşme, fiyat, müsaitlik ve rezervasyon erişimi bağlanacak.</p>
              </div>
              <Button className="w-full" onClick={approve} disabled={submitting}>{submitting ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Bağlan ve devam et</Button>
              <Button variant="ghost" className="w-full text-slate-300" onClick={() => window.history.back()} disabled={submitting}>İptal</Button>
              <p className="text-center text-xs leading-5 text-slate-500">Yetkilendirme kodu tek kullanımlıktır ve 5 dakika içinde sona erer. API anahtarı tarayıcıya gönderilmez.</p>
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}
