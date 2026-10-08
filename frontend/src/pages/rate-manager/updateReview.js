const DAY_MS = 24 * 60 * 60 * 1000;

const parseDate = (value) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
  if (!match) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return Number.isNaN(date.getTime()) ? null : date;
};

const hasValue = (value) => value !== null && value !== undefined && value !== '';

export const countTargetNights = ({ dateFrom, dateTo, allDays, selectedDays }) => {
  const start = parseDate(dateFrom);
  const end = parseDate(dateTo);
  if (!start || !end || end < start) return 0;
  const allowedDays = allDays ? null : new Set(selectedDays || []);
  let count = 0;
  for (let timestamp = start.getTime(); timestamp <= end.getTime(); timestamp += DAY_MS) {
    if (!allowedDays || allowedDays.has(new Date(timestamp).getUTCDay())) count += 1;
  }
  return count;
};

export const buildRateUpdateReview = ({
  dateFrom,
  dateTo,
  allDays,
  selectedDays,
  selections = {},
  enabledFields = new Set(),
  roomValues = {},
  selectedChannelCodes = new Set(),
  activeChannelsStale = false,
}) => {
  const errors = [];
  const warnings = [];
  const roomCodes = Object.keys(selections).filter(code => (selections[code]?.size ?? selections[code]?.length ?? 0) > 0);
  const planCount = roomCodes.reduce((total, code) => total + (selections[code]?.size ?? selections[code]?.length ?? 0), 0);
  const dateCount = countTargetNights({ dateFrom, dateTo, allDays, selectedDays });

  if (!dateFrom || !dateTo) errors.push('Başlangıç ve bitiş tarihi seçilmelidir.');
  else if (parseDate(dateTo) < parseDate(dateFrom)) errors.push('Bitiş tarihi başlangıç tarihinden önce olamaz.');
  if (!allDays && (selectedDays?.size ?? 0) === 0) errors.push('En az bir gün seçilmelidir.');
  if (enabledFields.size === 0) errors.push('Güncellenecek en az bir alan seçilmelidir.');
  if (roomCodes.length === 0 || planCount === 0) errors.push('En az bir oda tipi ve fiyat planı seçilmelidir.');

  roomCodes.forEach((roomCode) => {
    const values = roomValues[roomCode] || {};
    const label = roomCode;
    if (enabledFields.has('rate') && (!hasValue(values.rate) || Number(values.rate) <= 0)) {
      errors.push(`${label} için fiyat sıfırdan büyük olmalıdır.`);
    }
    if (enabledFields.has('availability') && (!hasValue(values.availability) || !Number.isInteger(Number(values.availability)) || Number(values.availability) < 0)) {
      errors.push(`${label} için müsaitlik sıfır veya pozitif tam sayı olmalıdır.`);
    }
    ['min_stay', 'min_los_arrival', 'max_stay'].forEach((field) => {
      if (enabledFields.has(field) && (!hasValue(values[field]) || !Number.isInteger(Number(values[field])) || Number(values[field]) < 1)) {
        errors.push(`${label} için konaklama kısıtları pozitif tam sayı olmalıdır.`);
      }
    });
    if (enabledFields.has('min_stay') && enabledFields.has('max_stay')
      && hasValue(values.min_stay) && hasValue(values.max_stay)
      && Number(values.max_stay) < Number(values.min_stay)) {
      errors.push(`${label} için maksimum konaklama minimumdan kısa olamaz.`);
    }
    if (enabledFields.has('stop_sell') && values.stop_sell === true) warnings.push(`${label} satışa kapatılacak.`);
    if (enabledFields.has('cta') && values.cta === true) warnings.push(`${label} varışa kapatılacak (CTA).`);
    if (enabledFields.has('ctd') && values.ctd === true) warnings.push(`${label} çıkışa kapatılacak (CTD).`);
  });

  if (activeChannelsStale) warnings.push('Kanal listesi güncel değil; yayın öncesinde bağlantıları yenileyin.');
  if ((selectedChannelCodes?.size ?? 0) === 0) warnings.push('OTA kanalı seçilmedi; değişiklik yalnızca PMS ve seçili acente kapsamına uygulanır.');

  return {
    errors: [...new Set(errors)],
    warnings: [...new Set(warnings)],
    dateCount,
    roomCount: roomCodes.length,
    planCount,
    fieldCount: enabledFields.size,
    channelCount: selectedChannelCodes?.size ?? 0,
    cellCount: dateCount * planCount,
  };
};
