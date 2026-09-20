// Role options per subscription tier
// Basic: Admin plus explicitly authorized staff
// Professional: Department-level roles
// Enterprise: Full granular roles

export const ROLES_BY_TIER = {
  basic: [
    { value: "admin", label: "Yönetici", description: "Tüm yetkilere sahip otel sahibi/yöneticisi" },
    { value: "staff", label: "Personel", description: "Yönetici tarafından verilen modül ve sayfa izinleri" },
  ],
  professional: [
    { value: "admin", label: "Yönetici", description: "Tam yetki - otel yöneticisi" },
    { value: "supervisor", label: "Süpervizör", description: "Departman yönetimi, operasyonel kararlar" },
    { value: "front_desk", label: "Resepsiyon", description: "Rezervasyon, check-in/out, misafir işlemleri" },
    { value: "housekeeping", label: "Kat Hizmetleri", description: "Oda durumları, temizlik görevleri" },
    { value: "finance", label: "Muhasebe", description: "Fatura, ödeme, finansal raporlar" },
    { value: "procurement", label: "Satınalma", description: "Tedarikçi, satınalma talebi/siparişi, mal kabul" },
    { value: "staff", label: "Personel", description: "Kullanıcıya özel erişim" },
  ],
  enterprise: [
    { value: "admin", label: "Yönetici", description: "Tam yetki - genel müdür" },
    { value: "supervisor", label: "Süpervizör", description: "Departman yönetimi" },
    { value: "front_desk", label: "Resepsiyon", description: "Rezervasyon, check-in/out" },
    { value: "housekeeping", label: "Kat Hizmetleri", description: "Oda durumları, temizlik" },
    { value: "finance", label: "Muhasebe", description: "Fatura, ödeme, raporlar" },
    { value: "procurement", label: "Satınalma", description: "Tedarikçi, satınalma talebi/siparişi, mal kabul" },
    { value: "sales", label: "Satış", description: "Kurumsal satış, grup rezervasyon" },
    { value: "staff", label: "Personel", description: "Teknik, restoran, spa vb. departmanlar için kullanıcıya özel erişim" },
  ],
};

// Get available roles for a given tier
export function getRolesForTier(tier) {
  const normalizedTier = (tier || 'basic').toLowerCase();
  if (normalizedTier === 'pro') return ROLES_BY_TIER.professional;
  if (normalizedTier === 'ultra') return ROLES_BY_TIER.enterprise;
  return ROLES_BY_TIER[normalizedTier] || ROLES_BY_TIER.basic;
}

// Check if a role is valid for a tier
export function isRoleValidForTier(role, tier) {
  const roles = getRolesForTier(tier);
  return roles.some(r => r.value === role);
}

// Legacy compatibility
export const LITE_ROLE_OPTIONS = ROLES_BY_TIER.basic;
