import React from 'react';
import { Info } from 'lucide-react';

const formatDate = value => value
  ? new Date(`${value}T12:00:00`).toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
  : '-';

const ReportFrame = ({ children, reportName, reportDate, periodLabel, tenant, user, contract, refreshedAt }) => {
  const hotelName = tenant?.property_name || tenant?.hotel_name || tenant?.name || 'Otel';
  const preparedBy = user?.full_name || user?.name || user?.email || 'Sistem kullanıcısı';
  const generatedAt = new Date().toLocaleString('tr-TR');

  return (
    <section className="report-document" aria-label={`${reportName} raporu`}>
      <header className="report-print-header hidden print:block">
        <div className="flex items-start justify-between gap-6 border-b-2 border-slate-800 pb-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Syroce PMS · Rapor Merkezi</p>
            <h1 className="mt-1 text-2xl font-bold text-slate-950">{reportName}</h1>
            <p className="mt-1 text-sm text-slate-600">{hotelName}</p>
          </div>
          <dl className="grid grid-cols-[auto_auto] gap-x-3 gap-y-1 text-right text-xs text-slate-600">
            <dt className="font-semibold">Rapor tarihi</dt><dd>{formatDate(reportDate)}</dd>
            <dt className="font-semibold">Dönem</dt><dd>{periodLabel}</dd>
            <dt className="font-semibold">Hazırlayan</dt><dd>{preparedBy}</dd>
            <dt className="font-semibold">Oluşturulma</dt><dd>{generatedAt}</dd>
          </dl>
        </div>
      </header>
      {contract && <details className="mb-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm print:hidden" data-testid="report-data-contract">
        <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-slate-800">
          <Info className="h-4 w-4 text-sky-700" aria-hidden="true" />
          Bu rapor nasıl hesaplanır?
        </summary>
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-xs text-slate-600 sm:grid-cols-2">
          <div><dt className="font-semibold text-slate-700">Veri kaynağı</dt><dd>{contract.dataSource}</dd></div>
          <div><dt className="font-semibold text-slate-700">Tarih kapsamı</dt><dd>{contract.dateScope}</dd></div>
          <div><dt className="font-semibold text-slate-700">Finansal kapsam</dt><dd>{contract.financialScope}</dd></div>
          <div><dt className="font-semibold text-slate-700">Para birimi kuralı</dt><dd>{contract.currencyRule}</dd></div>
          <div><dt className="font-semibold text-slate-700">Rapor tarihi</dt><dd>{formatDate(reportDate)}</dd></div>
          {refreshedAt && <div><dt className="font-semibold text-slate-700">Son yenileme</dt><dd>{refreshedAt}</dd></div>}
        </dl>
      </details>}
      {children}
      <footer className="report-print-footer hidden print:flex">
        <span>{hotelName} · {reportName}</span>
        <span>Syroce PMS tarafından oluşturuldu</span>
      </footer>
    </section>
  );
};

export default ReportFrame;
