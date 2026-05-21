// HR v2 Foundation (Task #262) — Türkçe etiket sözlüğü.
//
// Backend `department` / `position` / `employment_type` alanlarını UI'da
// kullanıcı-dostu Türkçe metne çevirir. Eski (technical code) ve yeni
// (free-form) iki kaynağı da destekler — eşleşme yoksa orijinal değer
// döner, böylece yeni eklenen serbest kayıtlar bozulmaz.

const DEPT_LABELS = {
  front_desk: 'Resepsiyon',
  housekeeping: 'Kat Hizmetleri',
  finance: 'Finans',
  management: 'Yönetim',
  sales: 'Satış & Pazarlama',
  marketing: 'Pazarlama',
  fb: 'Yiyecek-İçecek',
  food_beverage: 'Yiyecek-İçecek',
  spa: 'Spa & Wellness',
  maintenance: 'Teknik Servis',
  technical: 'Teknik Servis',
  security: 'Güvenlik',
  hr: 'İnsan Kaynakları',
  it: 'Bilgi İşlem',
  procurement: 'Satınalma',
  other: 'Diğer',
};

const EMPLOYMENT_TYPE_LABELS = {
  full_time: 'Tam Zamanlı',
  part_time: 'Yarı Zamanlı',
  seasonal: 'Sezonluk',
  contract: 'Sözleşmeli',
  intern: 'Stajyer',
};

const POSITION_LABELS = {
  front_desk: 'Resepsiyonist',
  housekeeping: 'Kat Görevlisi',
  supervisor: 'Süpervizör',
  finance: 'Finans Uzmanı',
  sales: 'Satış Temsilcisi',
  admin: 'Yönetici',
  staff: 'Personel',
};

const SOURCE_LABELS = {
  hr: 'Personel',
  users: 'Sistem Kullanıcısı',
  all: 'Tümü',
};

export function deptLabel(code) {
  if (!code) return '—';
  const key = String(code).toLowerCase().trim();
  return DEPT_LABELS[key] || code;
}

export function positionLabel(code) {
  if (!code) return '—';
  const key = String(code).toLowerCase().trim();
  return POSITION_LABELS[key] || code;
}

export function employmentTypeLabel(code) {
  if (!code) return '—';
  return EMPLOYMENT_TYPE_LABELS[code] || code;
}

export function sourceLabel(code) {
  if (!code) return '—';
  return SOURCE_LABELS[code] || code;
}

export const DEPT_LABEL_MAP = DEPT_LABELS;
export const EMPLOYMENT_TYPE_OPTIONS = Object.entries(EMPLOYMENT_TYPE_LABELS).map(
  ([value, label]) => ({ value, label }),
);
