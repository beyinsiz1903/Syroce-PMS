const ROLE_LABELS = {
  super_admin: 'Süper yönetici',
  chain_admin: 'Zincir yöneticisi',
  admin: 'Otel yöneticisi',
  manager: 'Yönetici',
  front_desk: 'Ön büro',
  receptionist: 'Resepsiyon',
  housekeeping: 'Kat hizmetleri',
  accounting: 'Muhasebe',
  agency_admin: 'Acente yöneticisi',
  agency_agent: 'Acente kullanıcısı',
  staff: 'Personel',
};

export function userRoleLabel(role, translate) {
  const normalized = String(role || '').trim().toLowerCase();
  if (!normalized) return 'Tanımsız';
  const fallback = ROLE_LABELS[normalized] || normalized.replaceAll('_', ' ');
  return typeof translate === 'function'
    ? translate(`settings.roles.${normalized}`, { defaultValue: fallback })
    : fallback;
}

export function userIdentityLabel(user = {}) {
  return String(user.name || user.email || 'Kullanıcı').trim();
}

export function userAccessScopeLabel(role) {
  return String(role || '').toLowerCase() === 'super_admin' ? 'Platform geneli' : 'Seçili tesis';
}
