export default function AccountingPendingNotice({ runs = [] }) {
  const run = runs.find(row => !row.dry_run && !row.is_dry_run && row.status === 'completed'
    && ['valuation_required', 'failed'].includes(row.gl_bridge_status));
  if (!run) return null;
  return <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-950" role="status" data-testid="night-audit-gl-pending">
    <p className="font-semibold">{run.business_date} günü kapandı; muhasebe aktarımı henüz tamamlanmadı</p>
    <p className="mt-1 text-sm">Kaynak gününe ait döviz değerlemesi ve ikram/indirim hesaplarını Genel Muhasebe bölümünde kontrol edin. Gün kapanışını tekrar çalıştırmayın.</p>
    {run.gl_bridge_error && <p className="mt-1 text-xs">{run.gl_bridge_error}</p>}
  </div>;
}
