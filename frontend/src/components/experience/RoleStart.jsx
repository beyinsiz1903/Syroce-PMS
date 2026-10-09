import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useEntitlements } from '@/context/EntitlementContext';
import { accessibleNavigationItems } from '@/lib/navigationCatalog';
import { roleStartItems } from '@/lib/productExperience';
import { Button } from '@/components/ui/button';

export default function RoleStart({ user, tenant }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasModule, hasTenantModule = hasModule } = useEntitlements();
  const items = useMemo(() => roleStartItems(user, accessibleNavigationItems({ user, tenant, hasModule: hasTenantModule })), [user, tenant, hasTenantModule]);
  if (!items.length) return null;
  return <section className="rounded-xl border bg-card p-4" aria-label={t('experience.start', 'Çalışma alanınız')}>
    <h2 className="text-base font-semibold">{t('experience.start', 'Çalışma alanınız')}</h2>
    <p className="mt-1 text-sm text-muted-foreground">{t('experience.startHelp', 'Rolünüze ve erişiminize uygun günlük işlemler.')}</p>
    <div className="mt-3 flex flex-wrap gap-2">{items.map(item => <Button key={item.key} variant="outline" onClick={() => navigate(item.path)}>{tenant?.nav_item_labels?.[item.key] || t(`navKeys.${item.key}`, item.label)}</Button>)}</div>
  </section>;
}
