const DAY_MS = 24 * 60 * 60 * 1000;
import { compileExelyGuestPrices } from './exelyPlacements';

const parseDate = (value) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
  if (!match) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return Number.isNaN(date.getTime()) ? null : date;
};

const hasValue = (value) => value !== null && value !== undefined && value !== '';

export const exelyPriceOccupancy = rule => rule?.policy_invalid !== true
  && rule?.base_occupancy_explicit !== false
  && Number.isInteger(rule?.base_occupancy) && rule.base_occupancy >= 1 && rule.base_occupancy <= 20
  ? rule.base_occupancy : null;

export const isExelyPricePlanWritable = (plan, roomCode) => plan?.price_upload_is_allowed !== false
  && plan?.price_sync_by_room?.[roomCode] !== false;

// Blank explicitly selects automatic stock; 0 is an explicit manual closure.
export const isValidExelyAvailability = value => !hasValue(value)
  || typeof value !== 'boolean' && String(value).trim() !== '' && Number.isInteger(Number(value)) && Number(value) >= 0 && Number(value) <= 999;

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
  channelProvider,
  agenciesOnly = false,
  ratePlans = [],
  roomTypes = [],
  occupancyPricingRules = {},
  currency,
  exelyPlacementsSupported = true,
}) => {
  const errors = [];
  const warnings = [];
  const notes = [];
  const priceSummaries = [];
  const roomCodes = Object.keys(selections).filter(code => (selections[code]?.size ?? selections[code]?.length ?? 0) > 0);
  const roomLabel = code => {
    const name = roomTypes.find(room => room.code === code)?.name?.trim();
    return name && name !== code ? name : `Oda tipi ${roomCodes.indexOf(code) + 1}`;
  };
  const addPriceSummary = (code, prices, baseOnly = false) => {
    const plans = Array.from(selections[code]);
    const planNames = plans.map(code => ratePlans.find(plan => plan.code === code)?.name).filter(name => name && !plans.includes(name));
    priceSummaries.push({ roomCode: code, roomName: roomLabel(code), prices, baseOnly, currency,
      planNames: planNames.length === plans.length ? planNames : [], planCount: plans.length });
  };
  const planCount = roomCodes.reduce((total, code) => total + (selections[code]?.size ?? selections[code]?.length ?? 0), 0);
  const dateCount = countTargetNights({ dateFrom, dateTo, allDays, selectedDays });

  if (!dateFrom || !dateTo) errors.push('Başlangıç ve bitiş tarihi seçilmelidir.');
  else if (parseDate(dateTo) < parseDate(dateFrom)) errors.push('Bitiş tarihi başlangıç tarihinden önce olamaz.');
  if (!allDays && (selectedDays?.size ?? 0) === 0) errors.push('En az bir gün seçilmelidir.');
  if (enabledFields.size === 0) errors.push('Güncellenecek en az bir alan seçilmelidir.');
  if (roomCodes.length === 0 || planCount === 0) errors.push('En az bir oda tipi ve fiyat planı seçilmelidir.');

  roomCodes.forEach((roomCode) => {
    const values = roomValues[roomCode] || {};
    const label = roomLabel(roomCode);
    if (enabledFields.has('rate') && (!hasValue(values.rate) || Number(values.rate) <= 0)) {
      errors.push(`${label} için fiyat sıfırdan büyük olmalıdır.`);
    }
    if (enabledFields.has('rate') && channelProvider === 'exely' && !agenciesOnly) {
      const rule = occupancyPricingRules[roomCode];
      const guests = exelyPriceOccupancy(rule);
      // The backend already rejects this base-only person-pricing case before
      // writing. Show the missing operator review in the preview as well.
      if (rule?.pricing_type === 'per_person' && !rule.exely_price_placements?.length && rule.provider_pricing_verified !== true) {
        errors.push(`${label}: Kişi bazlı fiyatlar kontrol edilmemiş. “Kuralı düzenle” bölümünde Exely ile eşleşmesini kontrol edip kaydedin.`);
      }
      if (!exelyPlacementsSupported && occupancyPricingRules[roomCode]?.pricing_type === 'per_person' && occupancyPricingRules[roomCode]?.exely_price_placements?.length) {
        errors.push('Exely yerleşim tarife servisi bu sunucuda henüz hazır değil; deployu tamamlayıp ekranı yenileyin.');
      }
      if (!guests) errors.push(`${label}: Fiyat kuralında fiyata dahil ana yatak yetişkin sayısını kaydedin; 1 veya 2 kişi varsayılmaz.`);
      else {
        try {
          const prices = compileExelyGuestPrices(occupancyPricingRules[roomCode], values.rate, currency);
          addPriceSummary(roomCode, prices, prices.length === 1);
        } catch (error) { errors.push(`${label}: ${error.message}`); }
      }
    } else if (enabledFields.has('rate') && hasValue(values.rate) && Number(values.rate) > 0) {
      addPriceSummary(roomCode, [{ kind: 'room', amount: Number(values.rate) }]);
    }
    if (enabledFields.has('availability')) {
      if (channelProvider === 'exely' && !agenciesOnly) {
        if (!isValidExelyAvailability(values.availability)) errors.push(`${label} için müsaitliği boş bırakın veya 0–999 arasında tam sayı girin.`);
        else if (!hasValue(values.availability)) warnings.push(`${label}: Müsaitlik otomatik hesaba dönecek; mevcut manuel kontenjan seçili günlerde kaldırılacak.`);
        else if (Number(values.availability) === 0) warnings.push(`${label}: Satışa sunulacak oda sayısı 0 olacak.`);
        else warnings.push(`${label}: Elle girdiğiniz ${Number(values.availability)} oda satışa sunulacak. Bu sayı mevcut doluluktan bağımsızdır; fazla rezervasyona yol açabilir.`);
      } else if (!hasValue(values.availability) || !Number.isInteger(Number(values.availability)) || Number(values.availability) < 0) {
        errors.push(`${label} için müsaitlik sıfır veya pozitif tam sayı olmalıdır.`);
      }
    }
    ['min_stay', 'min_los_arrival', 'max_stay'].forEach((field) => {
      const canRemove = channelProvider === 'exely' && !agenciesOnly;
      if (enabledFields.has(field) && (!hasValue(values[field]) || !Number.isInteger(Number(values[field])) || Number(values[field]) < (canRemove ? 0 : 1))) {
        errors.push(`${label} için konaklama kısıtları pozitif tam sayı olmalıdır.`);
      }
      if (enabledFields.has(field) && canRemove && hasValue(values[field]) && Number(values[field]) === 0) {
        warnings.push(`${label}: ${field === 'max_stay' ? 'Maksimum konaklama' : field === 'min_los_arrival' ? 'Varış bazlı minimum konaklama' : 'Minimum konaklama'} kısıtı kaldırılacak.`);
      }
    });
    if (enabledFields.has('min_stay') && enabledFields.has('max_stay')
      && hasValue(values.min_stay) && hasValue(values.max_stay)
      && Number(values.min_stay) > 0 && Number(values.max_stay) > 0
      && Number(values.max_stay) < Number(values.min_stay)) {
      errors.push(`${label} için maksimum konaklama minimumdan kısa olamaz.`);
    }
    if (enabledFields.has('stop_sell') && values.stop_sell === true) warnings.push(`${label} satışa kapatılacak.`);
    if (enabledFields.has('cta') && values.cta === true) warnings.push(`${label} için bu tarihlerde yeni giriş kabul edilmeyecek.`);
    if (enabledFields.has('ctd') && values.ctd === true) warnings.push(`${label} için bu tarihlerde çıkışa izin verilmeyecek.`);
  });

  if (activeChannelsStale) warnings.push('Kanal listesi güncel değil; yayın öncesinde bağlantıları yenileyin.');
  if (agenciesOnly || channelProvider === 'agency') {
    notes.push('Değişiklikler yalnız seçili anlaşmalı acentelere uygulanır. Otel takvimi ve satış kanalları değişmez.');
  } else if (channelProvider === 'exely') {
    const baseOnlyRooms = priceSummaries.filter(room => room.baseOnly);
    if (baseOnlyRooms.length) notes.push(`${baseOnlyRooms.length === priceSummaries.length ? '' : `${baseOnlyRooms.map(room => room.roomName).join(', ')}: `}Diğer kişi, çocuk ve ek yatak tarifeleri bu işlemde güncellenmez.`);
    if (enabledFields.has('availability')) {
      if (dateCount > 731) errors.push('Net müsaitlik için tek gönderimde en fazla 731 gece seçin.');
    }
    const restrictionCount = ['stop_sell', 'min_stay', 'min_los_arrival', 'max_stay', 'cta', 'ctd']
      .filter(field => enabledFields.has(field)).length;
    roomCodes.forEach(roomCode => {
      const selectedPlans = Array.from(selections[roomCode]);
      if (enabledFields.has('rate')) {
        const writable = selectedPlans.filter(code => isExelyPricePlanWritable(ratePlans.find(plan => plan.code === code), roomCode));
        if (writable.length !== selectedPlans.length) {
          errors.push(`${roomLabel(roomCode)}: Exely'de doğrudan fiyat yüklemesi kapalı plan seçili. Oda altındaki fiyat planlarından bu seçimi kaldırın.`);
        }
        // The server preflights the exact mapped prices and groups a larger
        // selection by plan. A per-envelope budget is not a selection limit.
        // Placement validation above and authoritative provider quotas remain.
      }
      const restrictionChanges = dateCount * selectedPlans.length * restrictionCount;
      if (restrictionChanges > 1460) errors.push(`${roomLabel(roomCode)}: Seçili konaklama/satış kısıtları ${restrictionChanges} değişiklik içeriyor; tek Exely isteğinde oda başına en fazla 1460. Plan, alan veya tarih seçimini düzenleyin.`);
    });
  } else if ((selectedChannelCodes?.size ?? 0) === 0) {
    warnings.push('Satış kanalı seçilmedi; değişiklik yalnız otel takvimine ve seçili acentelere uygulanacak.');
  }

  return {
    errors: [...new Set(errors)],
    warnings: [...new Set(warnings)],
    notes: [...new Set(notes)],
    priceSummaries,
    dateFrom,
    dateTo,
    targetLabel: agenciesOnly || channelProvider === 'agency' ? 'Seçili acenteler'
      : channelProvider === 'exely' ? 'Exely' : selectedChannelCodes?.size ? `${selectedChannelCodes.size} satış kanalı` : 'Otel takvimi',
    dateCount,
    roomCount: roomCodes.length,
    planCount,
    fieldCount: enabledFields.size,
    channelCount: selectedChannelCodes?.size ?? 0,
    cellCount: dateCount * planCount,
  };
};
