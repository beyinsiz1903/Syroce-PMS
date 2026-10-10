import { useTranslation } from 'react-i18next';

export default function DashboardWelcome({ user, tenant }) {
  const { t } = useTranslation();
  return <header className="mb-4" data-testid="dashboard-welcome">
    <h1 className="dashboard-greeting mb-1 text-foreground">
      <span className="text-muted-foreground">{t('dashboard.welcome')}{user?.name ? ', ' : ''}</span>
      {user?.name && <span className="font-semibold">{user.name}</span>}
    </h1>
    <p className="text-sm md:text-base text-muted-foreground">{tenant?.property_name || 'Hotel Management System'}</p>
  </header>;
}
