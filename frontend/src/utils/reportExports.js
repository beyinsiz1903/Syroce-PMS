function reportDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) throw new Error('Geçerli bir rapor tarihi seçin.');
  const date = new Date(`${value}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
    throw new Error('Geçerli bir rapor tarihi seçin.');
  }
  return date;
}

function shiftDate(value, days) {
  const date = reportDate(value);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function defaultReportDates(report, businessDate) {
  return {
    startDate: report.id === 'forecast-detail' ? businessDate : shiftDate(businessDate, -29),
    endDate: report.id === 'forecast-detail' ? shiftDate(businessDate, 29) : businessDate,
    reportDate: businessDate,
  };
}

export function reportDownloadUrl(report) {
  const params = new URLSearchParams();
  if (report.needsDateRange) {
    reportDate(report.startDate);
    reportDate(report.endDate);
    if (report.startDate > report.endDate) throw new Error('Başlangıç tarihi bitiş tarihinden sonra olamaz.');
    params.set('start_date', report.startDate);
    params.set('end_date', report.endDate);
  } else if (report.singleDateParam) {
    reportDate(report.reportDate);
    params.set(report.singleDateParam, report.reportDate);
  }
  return report.endpoint + (params.size ? `?${params}` : '');
}

export async function reportDownloadError(error) {
  let data = error?.response?.data;
  if (data && typeof data.text === 'function') {
    try { data = JSON.parse(await data.text()); } catch { data = null; }
  }
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map(item => item.msg).filter(Boolean).join(' · ');
  return 'Rapor indirilemedi. Lütfen tekrar deneyin.';
}
