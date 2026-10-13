import { useEffect } from 'react';

export default function WhatsAppConsent({ phone, identity, open = true, value, onChange, selfService = false }) {
  // An approval for one recipient must never follow a guest/phone change.
  useEffect(() => { onChange(false); }, [phone, identity, open]); // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="rounded-lg border p-3 text-sm space-y-1">
    <label className="flex items-start gap-2">
      <input type="checkbox" checked={value === true} disabled={!phone || !open}
        onChange={e => onChange(e.target.checked)} className="mt-1" />
      <span>{selfService
        ? 'Rezervasyon ve konaklama bildirimlerinin WhatsApp üzerinden gönderilmesine izin veriyorum.'
        : 'Misafir, rezervasyon ve konaklama bildirimlerinin WhatsApp üzerinden gönderilmesine izin verdi.'}</span>
    </label>
    <p className="text-xs text-slate-500">İsteğe bağlıdır; pazarlama izni değildir. {phone ? `Numara: ${phone}` : 'İzin kaydı için ülke koduyla telefon numarası girin.'}</p>
  </div>;
}
