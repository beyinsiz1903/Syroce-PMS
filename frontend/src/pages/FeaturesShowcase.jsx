import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import POSTableManagement from '../components/POSTableManagement';
import POSMenuItems       from '../components/POSMenuItems';
import StaffAssignment    from '../components/StaffAssignment';
import MessagingTemplates from '../components/MessagingTemplates';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { alertDialog } from '@/lib/dialogs';
import {
  Users, UtensilsCrossed, MessageSquare, Sparkles,
  ArrowLeft, Menu, ShoppingBag, BarChart2, ScissorsSquare,
  ChevronRight,
} from 'lucide-react';

/* ─── tab config ─────────────────────────────────────────────────── */
const TABS = [
  { value: 'pos',       icon: UtensilsCrossed, label: 'POS Masaları',  colorClass: 'text-blue-600',   bgClass: 'bg-blue-50'   },
  { value: 'menu',      icon: Menu,            label: 'Menü Kalemleri', colorClass: 'text-amber-600', bgClass: 'bg-amber-50'  },
  { value: 'staff',     icon: Users,           label: 'Personel',       colorClass: 'text-green-600', bgClass: 'bg-green-50'  },
  { value: 'messaging', icon: MessageSquare,   label: 'Mesajlaşma',     colorClass: 'text-indigo-600',bgClass: 'bg-indigo-50' },
];

/* ─── feature description card ─────────────────────────────────── */
function FeatureHeader({ icon: Icon, title, description, colorClass, bgClass }) {
  return (
    <div className={`rounded-2xl border border-gray-200 ${bgClass} px-5 py-4 mb-5 flex items-center gap-4`}>
      <div className={`w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center shrink-0`}>
        <Icon className={`w-5 h-5 ${colorClass}`} />
      </div>
      <div>
        <h2 className="font-bold text-gray-900 text-sm">{title}</h2>
        <p className="text-xs text-gray-500 mt-0.5">{description}</p>
      </div>
    </div>
  );
}

/* ─── quick link button ─────────────────────────────────────────── */
function QuickLink({ icon: Icon, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className="group flex flex-col items-center justify-center gap-2 h-24 rounded-2xl border border-gray-200 bg-white hover:border-indigo-200 hover:bg-indigo-50 transition-all p-4"
    >
      <Icon className="w-6 h-6 text-gray-400 group-hover:text-indigo-600 transition-colors" />
      <span className="text-xs font-medium text-gray-600 group-hover:text-indigo-700 text-center leading-tight">{label}</span>
      <ChevronRight className="w-3.5 h-3.5 text-gray-300 group-hover:text-indigo-400 transition-colors" />
    </button>
  );
}

/* ─── main ─────────────────────────────────────────────────────── */
const FeaturesShowcase = () => {
  const { t }    = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 shadow-sm px-6 py-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-indigo-100 flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 leading-tight">
                {t('featuresShowcase.title', 'Özellik Vitrini')}
              </h1>
              <p className="text-sm text-gray-500">
                {t('featuresShowcase.subtitle', 'Yeni masaüstü özellikleri — POS Masalar, Personel Atama, Mesajlaşma')}
              </p>
            </div>
          </div>
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-900 text-white text-sm font-semibold hover:bg-gray-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            {t('featuresShowcase.backToDashboard', "Dashboard'a Dön")}
          </button>
        </div>
      </div>

      <div className="px-6 py-6 space-y-6">
        {/* Tabs */}
        <Tabs defaultValue="pos" className="w-full">
          <TabsList className="inline-flex h-10 items-center rounded-xl bg-white border border-gray-200 shadow-sm p-1 gap-0.5 mb-6">
            {TABS.map(({ value, icon: Icon, label }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium
                  text-gray-500 data-[state=active]:bg-indigo-600 data-[state=active]:text-white
                  data-[state=active]:shadow-sm hover:text-gray-800 transition-all"
              >
                <Icon className="w-4 h-4" />
                {label}
              </TabsTrigger>
            ))}
          </TabsList>

          {/* POS Tables */}
          <TabsContent value="pos">
            <FeatureHeader
              icon={UtensilsCrossed}
              title={t('featuresShowcase.tableMgmt', 'Restoran Masa Yönetimi')}
              description={t('featuresShowcase.tableMgmtDesc', 'Restoran masalarını yönetin, müsaitliği takip edin ve durumları gerçek zamanlı güncelleyin. Kapasite takibi ve hızlı durum güncellemeli 20 masa.')}
              colorClass="text-blue-600"
              bgClass="bg-blue-50"
            />
            <POSTableManagement outletId="main_restaurant" />
          </TabsContent>

          {/* Menu Items */}
          <TabsContent value="menu">
            <FeatureHeader
              icon={Menu}
              title={t('featuresShowcase.menuMgmt', 'Menü Yönetimi')}
              description={t('featuresShowcase.menuMgmtDesc', 'Menü öğelerini oluşturun, düzenleyin ve kategorilere ayırın. Fiyat, KDV ve stok durumu yönetimi.')}
              colorClass="text-amber-600"
              bgClass="bg-amber-50"
            />
            <POSMenuItems outletId="main_restaurant" />
          </TabsContent>

          {/* Staff */}
          <TabsContent value="staff">
            <FeatureHeader
              icon={Users}
              title={t('featuresShowcase.staffMgmt', 'Personel Atama')}
              description={t('featuresShowcase.staffMgmtDesc', 'Personeli masalara ve vardiyalara atayın. Gerçek zamanlı çalışma planı ve yetki yönetimi.')}
              colorClass="text-green-600"
              bgClass="bg-green-50"
            />
            <StaffAssignment />
          </TabsContent>

          {/* Messaging */}
          <TabsContent value="messaging">
            <FeatureHeader
              icon={MessageSquare}
              title={t('featuresShowcase.messagingTitle', 'Mesajlaşma Şablonları')}
              description={t('featuresShowcase.messagingDesc', 'Misafir iletişimi için hazır mesaj şablonları oluşturun. SMS, e-posta ve uygulama içi bildirimler için özelleştirilebilir.')}
              colorClass="text-indigo-600"
              bgClass="bg-indigo-50"
            />
            <MessagingTemplates />
          </TabsContent>
        </Tabs>

        {/* Quick links */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            {t('featuresShowcase.otherFeatures', 'Diğer Yeni Özellikler')}
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <QuickLink
              icon={BarChart2}
              label={t('featuresShowcase.costManagement', 'Gelir Dağılımı')}
              onClick={() => navigate('/cost-management')}
            />
            <QuickLink
              icon={BarChart2}
              label={t('featuresShowcase.revenueBreakdown', 'Gelir Analizi (RMS)')}
              onClick={() => navigate('/rms')}
            />
            <QuickLink
              icon={ShoppingBag}
              label={t('featuresShowcase.aiUpsellCenter', 'AI Satış Merkezi')}
              onClick={() => alertDialog({ message: 'Herhangi bir rezervasyona gidin ve Upsell Store\'u açın' })}
            />
            <QuickLink
              icon={ScissorsSquare}
              label={t('featuresShowcase.splitFolio', 'Folio Böl')}
              onClick={() => alertDialog({ message: 'Herhangi bir folio\'yu açın ve Böl butonunu kullanın' })}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default FeaturesShowcase;
