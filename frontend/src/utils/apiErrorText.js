// A readable message from an API error. FastAPI validation errors (422)
// carry `detail` as a list of {loc, msg} objects: handing that list to a
// toast crashes React, so it is turned into text.
export default function apiErrorText(err, fallback = 'İşlem tamamlanamadı.') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map(item => (typeof item === 'string' ? item : item?.msg || '')).filter(Boolean).join(' · ') || fallback;
  }
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message;
  return fallback;
}
