export const MODULE_SALES_PATH = '/admin/module-requests';
export const SALES_STAGES = {
  new: 'Yeni', assigned: 'Atandı', in_progress: 'Görüşülüyor', quote_sent: 'Teklif verildi', won: 'Kazanıldı', lost: 'Kaybedildi',
};

export const followUpTimestamp = value => {
  if (!value) return null;
  // Legacy form values were Turkish local wall times without an offset.
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}+03:00`;
  const result = new Date(normalized);
  return Number.isFinite(result.getTime()) ? result : null;
};

export const followUpLocalInput = value => {
  const date = followUpTimestamp(value);
  if (!date) return '';
  const two = number => String(number).padStart(2, '0');
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}T${two(date.getHours())}:${two(date.getMinutes())}`;
};
