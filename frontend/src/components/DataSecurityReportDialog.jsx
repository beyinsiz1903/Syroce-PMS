import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { FileText, LockKeyhole, Printer, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const MODE_LABELS = { full: 'Tam', masked: 'Maskeli', hidden: 'Gizli' };
const MODE_STYLES = {
  full: 'bg-emerald-50 text-emerald-800',
  masked: 'bg-amber-50 text-amber-800',
  hidden: 'bg-slate-100 text-slate-700',
};

export default function DataSecurityReportDialog({ open, onClose }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const fieldLabel = (key) => report?.field_catalog?.find((field) => field.key === key)?.label || key;

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    setReport(null);
    setError('');
    axios.get('/admin/data-security-report', { signal: controller.signal })
      .then(({ data }) => setReport(data))
      .catch((requestError) => {
        if (requestError?.code !== 'ERR_CANCELED') {
          setError(requestError?.response?.data?.detail || 'Veri güvenliği raporu yüklenemedi.');
        }
      });
    return () => controller.abort();
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="max-w-6xl max-h-[92vh] overflow-y-auto print:max-h-none print:max-w-none print:overflow-visible">
        <DialogHeader className="print:hidden"><DialogTitle>Misafir Verisi Güvenliği Raporu</DialogTitle></DialogHeader>
        {error && <p role="alert" className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
        {!report && !error && <p role="status">Rapor hazırlanıyor…</p>}
        {report && <article aria-label="Misafir verisi güvenliği raporu" className="space-y-5">
          <header className="flex flex-wrap items-start justify-between gap-3 border-b pb-4">
            <div>
              <div className="flex items-center gap-2"><ShieldCheck className="h-6 w-6 text-emerald-700" /><h2 className="text-xl font-bold">{report.property_name}</h2></div>
              <p className="mt-1 text-sm text-slate-600">Misafir verisi maskeleme ve erişim kontrolü kanıt raporu</p>
              <p className="mt-1 text-xs text-slate-500">Üretim: {new Date(report.generated_at).toLocaleString('tr-TR')} · Hazırlayan: {report.generated_by?.name}</p>
            </div>
            <Button variant="outline" onClick={() => window.print()} className="print:hidden"><Printer className="mr-2 h-4 w-4" />Yazdır / PDF</Button>
          </header>

          <section className="grid gap-3 md:grid-cols-4">
            <div className="rounded-lg border p-3"><p className="text-xs text-slate-500">Kullanıcı</p><p className="text-2xl font-bold">{report.coverage.total_users}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-slate-500">Özel veri profili</p><p className="text-2xl font-bold text-emerald-700">{report.coverage.explicit_user_policies}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-slate-500">Eski profil</p><p className="text-2xl font-bold text-amber-700">{report.coverage.legacy_user_policies}</p></div>
            <div className="rounded-lg border p-3"><p className="text-xs text-slate-500">Şifreli misafir kaydı</p><p className="text-2xl font-bold">{report.coverage.encrypted_guest_records} / {report.coverage.guest_records}</p></div>
          </section>

          <section className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4">
            <h3 className="flex items-center gap-2 font-semibold"><LockKeyhole className="h-4 w-4" />Uygulanan kontroller</h3>
            <ul className="mt-2 grid gap-1 text-sm text-slate-700 md:grid-cols-2">
              <li>• Maskeleme API yanıtında sunucu tarafında uygulanır.</li>
              <li>• Ekran ve dışa aktarımlar aynı korumalı veriyi kullanır.</li>
              <li>• Üç seviye: tam, maskeli veya tamamen gizli.</li>
              <li>• Saklama şifrelemesi: {report.controls.encryption_at_rest}.</li>
            </ul>
          </section>

          <section>
            <h3 className="mb-2 flex items-center gap-2 font-semibold"><FileText className="h-4 w-4" />Kullanıcı bazlı görünürlük matrisi</h3>
            <div className="overflow-x-auto rounded-lg border">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-100 text-left"><tr>
                  <th className="p-2">Kullanıcı</th><th className="p-2">Rol</th><th className="p-2">Profil</th>
                  {Object.keys(report.users[0]?.policy || {}).map((key) => <th key={key} className="p-2 whitespace-nowrap">{fieldLabel(key)}</th>)}
                </tr></thead>
                <tbody>{report.users.map((user) => <tr key={user.id} className="border-t">
                  <td className="p-2"><div className="font-medium">{user.name}</div><div className="text-slate-500">{user.email}</div></td>
                  <td className="p-2">{user.role}</td>
                  <td className="p-2">{user.policy_source === 'user' ? 'Kullanıcıya özel' : 'Eski/varsayılan'}</td>
                  {Object.entries(user.policy).map(([key, mode]) => <td key={key} className="p-2"><span className={`rounded px-1.5 py-1 font-medium ${MODE_STYLES[mode]}`}>{MODE_LABELS[mode]}</span></td>)}
                </tr>)}</tbody>
              </table>
            </div>
          </section>

          <footer className="border-t pt-3 text-[11px] leading-5 text-slate-500">
            Bu rapor yapılandırılmış erişim kontrollerinin anlık görüntüsüdür; misafir kişisel verisi içermez.
            “Eski/varsayılan” görünen hesaplar kullanıcı bazlı profile geçirilmelidir.
          </footer>
        </article>}
      </DialogContent>
    </Dialog>
  );
}
