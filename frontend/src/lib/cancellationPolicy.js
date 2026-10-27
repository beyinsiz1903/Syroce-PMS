const LABELS = {
  flexible: 'Esnek', standard: 'Standart', refundable: 'İade Edilebilir',
  'non-refundable': 'İade Edilemez', non_refundable: 'İade Edilemez', nonrefundable: 'İade Edilemez',
};

// Presentation only: never invent missing contract terms or alter the policy.
export function formatCancellationPolicy(policy) {
  if (typeof policy === 'string' && policy.trim()) return LABELS[policy.trim().toLowerCase()] || policy.trim();
  if (!policy || typeof policy !== 'object' || Array.isArray(policy)) return 'Belirtilmemiş';
  const number = value => (typeof value === 'number' || (typeof value === 'string' && value.trim())) && Number.isFinite(Number(value)) ? Number(value) : null;
  const days = number(policy.free_until_days_before);
  const penalty = number(policy.penalty_pct);
  const noShow = number(policy.no_show_penalty_pct);
  const parts = [];
  if (Number.isInteger(days) && days >= 0) parts.push(`Girişten ${days} gün öncesine kadar ücretsiz iptal`);
  if (penalty !== null && penalty >= 0 && penalty <= 100) parts.push(`İptal kesintisi: %${penalty}`);
  if (noShow !== null && noShow >= 0 && noShow <= 100) parts.push(`Gelmeme kesintisi: %${noShow}`);
  return parts.join(' · ') || 'Politika ayrıntıları doğrulanamadı';
}
