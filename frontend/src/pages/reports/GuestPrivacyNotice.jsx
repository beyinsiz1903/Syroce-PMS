import React from 'react';
import { Shield } from 'lucide-react';

const GuestPrivacyNotice = ({ privacy, compact = false }) => {
  if (!privacy?.server_side_enforced) return null;
  const masked = privacy.masked_fields?.length || 0;
  const hidden = privacy.hidden_fields?.length || 0;
  const full = privacy.full_fields?.length || 0;
  return <div className="rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid="guest-privacy-notice">
    <div className="flex items-start gap-2.5">
      <Shield className="mt-0.5 h-4 w-4 flex-shrink-0 text-slate-600" />
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-900">Veri koruması bu rapora uygulandı</p>
        {!compact && <p className="mt-1 text-xs leading-5 text-slate-600">Ekran ve dışa aktarılan içerik kullanıcıya özel görünürlük profiliyle hazırlanır; gizli alanlar tarayıcıya gönderilmez.</p>}
        <p className="mt-1 text-xs text-slate-600">Tam görünen: {full} · Maskeli: {masked} · Gizli: {hidden}</p>
      </div>
    </div>
  </div>;
};

export default GuestPrivacyNotice;
