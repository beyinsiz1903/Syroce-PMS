export const STATUS = {
  lead: { label: 'Aday', cls: 'bg-slate-100 text-slate-700' },
  tentative: { label: 'Beklemede', cls: 'bg-amber-100 text-amber-800' },
  definite: { label: 'Kesinleşmiş', cls: 'bg-sky-100 text-sky-800' },
  confirmed: { label: 'Onaylı', cls: 'bg-emerald-100 text-emerald-800' },
  completed: { label: 'Tamamlandı', cls: 'bg-indigo-100 text-indigo-800' },
  cancelled: { label: 'İptal', cls: 'bg-red-100 text-red-800' },
};

export const SETUPS = ['theatre', 'classroom', 'banquet', 'cocktail', 'u_shape', 'boardroom'];
export const EVENT_TYPES = ['meeting', 'conference', 'wedding', 'gala', 'training', 'other'];
export const EVENT_TYPE_LABELS = {
  meeting: 'Toplantı',
  conference: 'Konferans',
  wedding: 'Düğün',
  gala: 'Gala',
  training: 'Eğitim',
  other: 'Diğer',
};
export const AGENDA_KINDS = ['session', 'meal', 'break', 'av', 'logistics', 'other'];
