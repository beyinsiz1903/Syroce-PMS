import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ChefHat, FileText, Package, Monitor, TrendingUp,
  ArrowLeft, BookOpen, UtensilsCrossed, ExternalLink,
} from 'lucide-react';
import FnBOutletDashboard       from '@/components/FnBOutletDashboard';
import RecipeCostingManager     from '@/components/RecipeCostingManager';
import IngredientInventoryPanel from '@/components/IngredientInventoryPanel';

/* ─── nav tab config ─────────────────────────────────────────────── */
const TABS = [
  { value: 'outlet-sales', icon: TrendingUp,  labelKey: 'fnb.outletSales',     label: 'Outlet Satışları' },
  { value: 'recipes',      icon: BookOpen,    labelKey: 'fnb.recipes',          label: 'Reçeteler'        },
  { value: 'beo',          icon: FileText,    labelKey: 'fnb.beo',              label: 'BEO'              },
  { value: 'kitchen',      icon: Monitor,     labelKey: 'fnb.kitchenDisplay',   label: 'Mutfak Ekranı'   },
  { value: 'inventory',    icon: Package,     labelKey: 'fnb.inventory',        label: 'Stok'             },
];

/* ─── link card (BEO / Kitchen) ─────────────────────────────────── */
function LinkCard({ icon: Icon, title, description, buttonLabel, onClick, color = 'amber' }) {
  const c = {
    amber:  { bg: 'from-amber-50  to-orange-50',  icon: 'bg-amber-100  text-amber-600',  btn: 'bg-amber-500 hover:bg-amber-600'  },
    slate:  { bg: 'from-slate-50  to-gray-50',    icon: 'bg-slate-100  text-slate-600',  btn: 'bg-slate-700 hover:bg-slate-800'  },
  }[color] || {};
  return (
    <div className={`rounded-2xl border border-gray-200 bg-gradient-to-br ${c.bg} p-8 flex flex-col items-center text-center gap-5 shadow-sm`}>
      <div className={`w-16 h-16 rounded-2xl flex items-center justify-center ${c.icon}`}>
        <Icon className="w-8 h-8" />
      </div>
      <div>
        <h3 className="text-lg font-bold text-gray-900">{title}</h3>
        <p className="text-sm text-gray-500 mt-1 max-w-sm">{description}</p>
      </div>
      <button
        onClick={onClick}
        className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-white font-semibold text-sm ${c.btn} transition-colors shadow-sm`}
      >
        <ExternalLink className="w-4 h-4" />
        {buttonLabel}
      </button>
    </div>
  );
}

/* ─── main ── */
const FnBComplete = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ── Header ── */}
      <div className="bg-white border-b border-gray-200 shadow-sm px-6 py-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-amber-100 flex items-center justify-center">
              <ChefHat className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 leading-tight">
                {t('fnb.suiteTitle', 'Yiyecek-İçecek Yönetim Paketi')}
              </h1>
              <p className="text-sm text-gray-500">
                {t('fnb.suiteSubtitle', 'Reçete Maliyetlendirme, BEO, Mutfak Ekranı, Stok')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('/admin/pos')}
              className="flex items-center gap-2 px-4 py-2 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <UtensilsCrossed className="w-4 h-4" />
              {t('fnb.posRestaurant', 'POS Restoran')}
            </button>
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-900 text-white text-sm font-semibold hover:bg-gray-800 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              {t('nav.dashboard', 'Kontrol Paneli')}
            </button>
          </div>
        </div>
      </div>

      {/* ── Tabs body ── */}
      <div className="px-6 py-6">
        <Tabs defaultValue="outlet-sales" className="w-full">
          {/* Tab bar */}
          <TabsList className="inline-flex h-10 items-center rounded-xl bg-white border border-gray-200 shadow-sm p-1 gap-0.5 mb-6 overflow-x-auto max-w-full">
            {TABS.map(({ value, icon: Icon, labelKey, label }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap
                  text-gray-500 data-[state=active]:bg-amber-500 data-[state=active]:text-white
                  data-[state=active]:shadow-sm hover:text-gray-800 transition-all"
              >
                <Icon className="w-4 h-4" />
                {t(labelKey, label)}
              </TabsTrigger>
            ))}
          </TabsList>

          {/* Outlet Sales */}
          <TabsContent value="outlet-sales">
            <FnBOutletDashboard />
          </TabsContent>

          {/* Recipes */}
          <TabsContent value="recipes">
            <RecipeCostingManager />
          </TabsContent>

          {/* BEO */}
          <TabsContent value="beo">
            <div className="max-w-lg mx-auto mt-8">
              <LinkCard
                icon={FileText}
                title={t('fnb.beoGenerator', 'BEO Oluşturucu')}
                description={t('fnb.beoAutoCreate', 'Banket Etkinlik Siparişlerini otomatik oluşturun ve yazdırın.')}
                buttonLabel={t('fnb.createBeo', 'BEO Oluştur')}
                onClick={() => navigate('/fnb/beo-generator')}
                color="amber"
              />
            </div>
          </TabsContent>

          {/* Kitchen Display */}
          <TabsContent value="kitchen">
            <div className="max-w-lg mx-auto mt-8">
              <LinkCard
                icon={Monitor}
                title={t('fnb.kitchenDisplaySystem', 'Mutfak Ekranı (KDS)')}
                description={t('fnb.kitchenDisplayDesc', 'Siparişleri gerçek zamanlı takip edin. Tam ekran modda TV\'ye bağlanabilir.')}
                buttonLabel={t('fnb.openFullScreen', 'Tam Ekran Aç')}
                onClick={() => navigate('/kitchen-display')}
                color="slate"
              />
            </div>
          </TabsContent>

          {/* Inventory */}
          <TabsContent value="inventory">
            <IngredientInventoryPanel />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default FnBComplete;
