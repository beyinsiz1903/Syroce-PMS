import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  ShieldCheck, ShieldX, Loader2, GraduationCap, Search,
} from 'lucide-react';

const apiBase = (import.meta.env.VITE_BACKEND_URL || '').replace(/\/$/, '');
const publicAxios = axios.create({ baseURL: apiBase ? `${apiBase}/api` : '/api' });

const CODE_RE = /^SYR-ACAD-[0-9A-F]{10}$/;

const CertificateVerifyPage = () => {
  const { code: codeParam } = useParams();
  const navigate = useNavigate();
  const [code, setCode] = useState((codeParam || '').toUpperCase());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const runVerify = async (raw) => {
    const value = (raw || '').trim().toUpperCase();
    if (!value) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await publicAxios.get(`/academy/verify/${encodeURIComponent(value)}`);
      setResult(res.data);
    } catch (err) {
      if (err?.response?.status === 429) {
        setError('Çok fazla deneme yapıldı. Lütfen birazdan tekrar deneyin.');
      } else {
        setError('Doğrulama sırasında bir hata oluştu. Lütfen tekrar deneyin.');
      }
    }
    setLoading(false);
  };

  useEffect(() => {
    if (codeParam) {
      setCode(codeParam.toUpperCase());
      runVerify(codeParam);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeParam]);

  const onSubmit = (e) => {
    e.preventDefault();
    const value = code.trim().toUpperCase();
    if (!value) return;
    navigate(`/sertifika-dogrula/${encodeURIComponent(value)}`);
    runVerify(value);
  };

  const formatHint = !CODE_RE.test(code.trim().toUpperCase()) && code.trim().length > 0;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:bg-none dark:bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900">
            <GraduationCap className="h-6 w-6" />
          </div>
          <CardTitle className="text-xl">Sertifika Doğrulama</CardTitle>
          <p className="text-sm text-muted-foreground">
            Syroce Academy sertifikasının gerçekliğini doğrulama kodu ile teyit edin.
          </p>
        </CardHeader>
        <CardContent className="space-y-5">
          <form onSubmit={onSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="cert-code">Doğrulama Kodu</Label>
              <Input
                id="cert-code"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="SYR-ACAD-XXXXXXXXXX"
                autoComplete="off"
                spellCheck={false}
                className="font-mono tracking-wide"
              />
              {formatHint && (
                <p className="text-xs text-amber-600">
                  Kod biçimi: SYR-ACAD- ardından 10 karakter.
                </p>
              )}
            </div>
            <Button type="submit" className="w-full" disabled={loading || !code.trim()}>
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-2 h-4 w-4" />
              )}
              Doğrula
            </Button>
          </form>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
              {error}
            </div>
          )}

          {result && result.valid && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900/50 dark:bg-emerald-950/30">
              <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
                <ShieldCheck className="h-5 w-5" />
                <span className="font-semibold">Geçerli sertifika</span>
              </div>
              <dl className="mt-3 space-y-2 text-sm">
                {result.recipient_name && (
                  <div className="flex justify-between gap-4">
                    <dt className="text-muted-foreground">Sertifika sahibi</dt>
                    <dd className="font-medium text-right">{result.recipient_name}</dd>
                  </div>
                )}
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Eğitim</dt>
                  <dd className="font-medium text-right">{result.course_title || '—'}</dd>
                </div>
                {result.department_label && (
                  <div className="flex justify-between gap-4">
                    <dt className="text-muted-foreground">Departman</dt>
                    <dd className="font-medium text-right">{result.department_label}</dd>
                  </div>
                )}
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Veriliş tarihi</dt>
                  <dd className="font-medium text-right">{result.issued_at || '—'}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Doğrulama kodu</dt>
                  <dd className="font-mono text-right">{result.verification_code}</dd>
                </div>
              </dl>
            </div>
          )}

          {result && !result.valid && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900/50 dark:bg-red-950/30">
              <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
                <ShieldX className="h-5 w-5" />
                <span className="font-semibold">Sertifika bulunamadı</span>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                Bu doğrulama koduna ait geçerli bir sertifika bulunamadı. Lütfen kodu
                kontrol edip tekrar deneyin.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default CertificateVerifyPage;
