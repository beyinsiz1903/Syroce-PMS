import React from 'react';

const formatDate = value => value
  ? new Date(`${value}T12:00:00`).toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
  : '-';

const ReportFrame = ({ children, reportName, reportDate, periodLabel, tenant, user }) => {
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
      {children}
      <footer className="report-print-footer hidden print:flex">
        <span>{hotelName} · {reportName}</span>
        <span>Syroce PMS tarafından oluşturuldu</span>
      </footer>
    </section>
  );
};

export default ReportFrame;
