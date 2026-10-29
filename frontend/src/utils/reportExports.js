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

export const validateReportDate = reportDate;

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

// A download owns its browser API and timer, rather than looking up `window`
// again after its page (or test DOM) has gone away. The owner can release it
// early on unmount; the delayed callback is safe even if it was already queued.
export function saveReportFile(blob, filename, browser = window, onRelease) {
  const urlApi = browser.URL;
  const revoke = urlApi.revokeObjectURL.bind(urlApi);
  const schedule = browser.setTimeout.bind(browser);
  const cancel = browser.clearTimeout.bind(browser);
  const document = browser.document;
  const url = urlApi.createObjectURL(blob);
  let timer;
  let released = false;
  let link;
  const release = () => {
    if (released) return;
    released = true;
    if (timer !== undefined) cancel(timer);
    try { revoke(url); } finally { onRelease?.(release); }
  };
  try {
    link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    timer = schedule(release, 1000);
    return release;
  } catch (error) {
    release();
    throw error;
  } finally {
    link?.remove();
  }
}
