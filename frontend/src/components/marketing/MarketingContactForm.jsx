import React, { useState } from 'react';
import axios from 'axios';
import { Send } from 'lucide-react';
import { getLeadAttribution, trackDemoLeadSuccess } from '@/lib/marketingAnalytics';

export default function MarketingContactForm() {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const onSubmit = async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setSubmitting(true);
    setResult(null);
    try {
      const response = await axios.post('/leads/contact', {
        full_name: String(fields.get('fullName') || '').trim(),
        company: String(fields.get('company') || '').trim(),
        phone: String(fields.get('phone') || '').trim(),
        email: String(fields.get('email') || '').trim(),
        business_type: String(fields.get('businessType') || '').trim() || undefined,
        message: String(fields.get('message') || '').trim() || undefined,
        metadata: getLeadAttribution(),
      });
      if (!response.data?.deduped) trackDemoLeadSuccess();
      setResult({ ok: true, msg: 'Demo talebiniz alındı. Ekibimiz sizinle iletişime geçecek.' });
      form.reset();
    } catch (error) {
      setResult({
        ok: false,
        msg: error?.response?.status === 422
          ? 'Lütfen ad soyad, işletme, telefon ve geçerli bir e-posta girin.'
          : 'Talebiniz gönderilemedi. Lütfen tekrar deneyin veya bize e-posta yazın.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return <form className="grid grid-cols-1 gap-4 sm:grid-cols-2" onSubmit={onSubmit}>
    {[
      { name: 'fullName', label: 'Ad Soyad', type: 'text', required: true },
      { name: 'company', label: 'İşletme Adı', type: 'text', required: true },
      { name: 'phone', label: 'Telefon', type: 'tel', required: true },
      { name: 'email', label: 'E-posta', type: 'email', required: true },
      { name: 'businessType', label: 'İşletme Türü', type: 'text', required: false },
    ].map(field => <label key={field.name} className={field.name === 'businessType' ? 'block sm:col-span-2' : 'block'}>
      <span className="mb-1.5 block text-xs font-medium text-slate-400">{field.label}{field.required && ' *'}</span>
      <input name={field.name} type={field.type} required={field.required} autoComplete={field.name === 'fullName' ? 'name' : field.name === 'email' ? 'email' : field.name === 'phone' ? 'tel' : 'organization'} className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/40 focus:ring-2 focus:ring-cyan-400/20" />
    </label>)}
    <label className="block sm:col-span-2">
      <span className="mb-1.5 block text-xs font-medium text-slate-400">Kısaca ihtiyacınız (isteğe bağlı)</span>
      <textarea name="message" rows={3} className="w-full resize-none rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/40 focus:ring-2 focus:ring-cyan-400/20" />
    </label>
    {result && <div role="status" className={`rounded-xl px-4 py-3 text-sm sm:col-span-2 ${result.ok ? 'border border-emerald-400/30 bg-emerald-400/10 text-emerald-100' : 'border border-rose-400/30 bg-rose-400/10 text-rose-100'}`}>{result.msg}</div>}
    <div className="flex flex-col gap-4 sm:col-span-2 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs text-slate-400">Talebiniz ve kampanya kaynağı bilgisi gizlilik politikamıza göre işlenir. <a className="underline hover:text-white" href="/privacy-policy">Gizlilik politikası</a></p>
      <button type="submit" disabled={submitting} className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-full bg-gradient-to-r from-cyan-400 to-teal-300 px-6 py-3 text-sm font-semibold text-[#05070f] disabled:opacity-60">{submitting ? 'Gönderiliyor...' : 'Demo Talep Et'}<Send className="h-4 w-4" /></button>
    </div>
  </form>;
}
