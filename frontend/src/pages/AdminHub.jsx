import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Shield,
  Users,
  ShieldAlert,
  Gavel,
  Building2,
  Truck,
  Package,
  Compass,
  FileBarChart,
  Sparkles,
  Brush,
  Utensils,
  Bell,
  KeyRound,
  Webhook,
  Smartphone,
  QrCode,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

const SECTIONS = [
  {
    id: 'access',
    titleKey: 'adminHub.sections.access.title',
    titleFallback: 'Yetki ve Erişim',
    descKey: 'adminHub.sections.access.desc',
    descFallback: 'Roller, izinler, yönetişim',
    items: [
      { to: '/admin/user-roles',          icon: Users,        labelKey: 'adminHub.items.userRoles',          labelFallback: 'Kullanıcı Rolleri' },
      { to: '/admin/urgent-permissions',  icon: ShieldAlert,  labelKey: 'adminHub.items.urgentPermissions',  labelFallback: 'Acil İzinler' },
      { to: '/admin/governance',          icon: Gavel,        labelKey: 'adminHub.items.governance',         labelFallback: 'Yönetişim' },
    ],
  },
  {
    id: 'tenants',
    titleKey: 'adminHub.sections.tenants.title',
    titleFallback: 'Tenant ve Tedarikçi',
    descKey: 'adminHub.sections.tenants.desc',
    descFallback: 'Çoklu tenant ve vendor yönetimi',
    items: [
      { to: '/admin/tenants', icon: Building2, labelKey: 'adminHub.items.tenants', labelFallback: 'Tenantlar' },
      { to: '/admin/vendors', icon: Truck,     labelKey: 'adminHub.items.vendors', labelFallback: 'Tedarikçiler' },
    ],
  },
  {
    id: 'modules',
    titleKey: 'adminHub.sections.modules.title',
    titleFallback: 'Modüller',
    descKey: 'adminHub.sections.modules.desc',
    descFallback: 'Özellik bayrakları, keşif, raporlar',
    items: [
      { to: '/admin/features',         icon: Sparkles,      labelKey: 'adminHub.items.features',         labelFallback: 'Özellik Vitrini' },
      { to: '/admin/module-discovery', icon: Compass,       labelKey: 'adminHub.items.moduleDiscovery',  labelFallback: 'Modül Keşfi' },
      { to: '/admin/module-report',    icon: FileBarChart,  labelKey: 'adminHub.items.moduleReport',     labelFallback: 'Modül Raporu' },
    ],
  },
  {
    id: 'ops',
    titleKey: 'adminHub.sections.ops.title',
    titleFallback: 'Operasyon İzleme',
    descKey: 'adminHub.sections.ops.desc',
    descFallback: 'Kat hizmetleri, POS, erken uyarı',
    items: [
      { to: '/admin/housekeeping',   icon: Brush,    labelKey: 'adminHub.items.housekeeping',   labelFallback: 'Kat Hizmetleri' },
      { to: '/admin/pos',            icon: Utensils, labelKey: 'adminHub.items.pos',            labelFallback: 'POS' },
      { to: '/admin/early-warning',  icon: Bell,     labelKey: 'adminHub.items.earlyWarning',   labelFallback: 'Erken Uyarı' },
    ],
  },
  {
    id: 'integrations',
    titleKey: 'adminHub.sections.integrations.title',
    titleFallback: 'Entegrasyonlar',
    descKey: 'adminHub.sections.integrations.desc',
    descFallback: 'Kimlik bilgileri ve webhook',
    items: [
      { to: '/admin/integration-credentials', icon: KeyRound, labelKey: 'adminHub.items.integrationCredentials', labelFallback: 'Entegrasyon Anahtarları' },
      { to: '/admin/capx-integration',        icon: KeyRound, labelKey: 'adminHub.items.capxIntegration',        labelFallback: 'CapX Entegrasyonu' },
      { to: '/admin/webhook-outbox',          icon: Webhook,  labelKey: 'adminHub.items.webhookOutbox',          labelFallback: 'Webhook Outbox' },
    ],
  },
  {
    id: 'devices',
    titleKey: 'adminHub.sections.devices.title',
    titleFallback: 'Cihazlar',
    descKey: 'adminHub.sections.devices.desc',
    descFallback: 'Quick-ID kioskları ve oda QR kodları',
    items: [
      { to: '/admin/quick-id',       icon: Smartphone, labelKey: 'adminHub.items.quickId',     labelFallback: 'Quick-ID Ayarları' },
      { to: '/admin/room-qr-codes',  icon: QrCode,     labelKey: 'adminHub.items.roomQrCodes', labelFallback: 'Oda QR Kodları' },
    ],
  },
];

export default function AdminHub({ user, tenant, onLogout }) {
  const { t } = useTranslation();

  const sections = useMemo(() => SECTIONS, []);

  return (
    <>
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" data-testid="admin-hub">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
            <Shield className="w-5 h-5 text-slate-700" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {t('adminHub.title', 'Yönetim Merkezi')}
            </h1>
            <p className="text-sm text-gray-500">
              {t('adminHub.subtitle', 'Tüm yönetim ve admin sayfaları kategoriler altında')}
            </p>
          </div>
        </div>

        <div className="space-y-8">
          {sections.map((section) => (
            <section key={section.id} data-testid={`admin-section-${section.id}`}>
              <div className="mb-3">
                <h2 className="text-lg font-semibold text-gray-900">
                  {t(section.titleKey, section.titleFallback)}
                </h2>
                <p className="text-xs text-gray-500">
                  {t(section.descKey, section.descFallback)}
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {section.items.map(({ to, icon: Icon, labelKey, labelFallback }) => (
                  <Link
                    key={to}
                    to={to}
                    data-testid={`admin-card-${to.replace(/\//g, '-').replace(/^-/, '')}`}
                    className="group"
                  >
                    <Card className="hover:border-slate-400 hover:shadow-sm transition cursor-pointer">
                      <CardContent className="flex items-center gap-3 p-4">
                        <div className="w-10 h-10 rounded-md bg-slate-50 flex items-center justify-center shrink-0">
                          <Icon className="w-5 h-5 text-slate-600" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {t(labelKey, labelFallback)}
                          </p>
                          <p className="text-xs text-gray-500 truncate">{to}</p>
                        </div>
                        <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-slate-600" />
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </>
  );
}
