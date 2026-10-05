export const DAYS = [
  { value: 0, label: 'Pazar' },
  { value: 1, label: 'Pazartesi' },
  { value: 2, label: 'Salı' },
  { value: 3, label: 'Çarşamba' },
  { value: 4, label: 'Perşembe' },
  { value: 5, label: 'Cuma' },
  { value: 6, label: 'Cumartesi' },
];

export const UPDATE_FIELDS = [
  { key: 'availability', label: 'Müsaitlik' },
  { key: 'rate', label: 'Fiyat' },
  { key: 'min_stay', label: 'Minimum konaklama' },
  { key: 'min_los_arrival', label: 'Varış tarihine göre min. konaklama', providers: ['exely'] },
  { key: 'max_stay', label: 'Maksimum konaklama' },
  { key: 'cta', label: 'Varışa kapalı (CTA)' },
  { key: 'ctd', label: 'Çıkışa kapalı (CTD)' },
  { key: 'stop_sell', label: 'Satışı durdur' },
];
