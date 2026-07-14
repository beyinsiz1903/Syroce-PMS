import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';

import POSTableManagement   from '../components/POSTableManagement';
import POSMenuItems         from '../components/POSMenuItems';
import POSOutletManagement  from '../components/POSOutletManagement';
import POSReports           from '../components/POSReports';
import POSPrinterSettings   from '../components/POSPrinterSettings';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  UtensilsCrossed, BarChart3, Sparkles, Store, LayoutGrid,
  AlertCircle, Coffee, Tablet, Printer, Menu as MenuIcon,
  TrendingUp, ShoppingBag, ArrowLeft, ChevronRight, Monitor,
} from 'lucide-react';
import { useEntitlements } from '@/context/EntitlementContext';

/* ── helper ── */
const fmt = (n, digits = 0) =>
  Number(n || 0).toLocaleString('tr-TR', { maximumFractionDigits: digits });

/* ── stat card ── */
function StatCard({ icon: Icon, label, value, sub, color = 'amber', loading, testId }) {
  const ring = {
    amber:   'from-amber-50  to-amber-50  border-amber-200  text-amber-600',
    green:   'from-emerald-50 to-green-50  border-emerald-200 text-emerald-600',
    blue:    'from-blue-50   to-indigo-50  border-blue-200   text-blue-600',
    purple:  'from-indigo-50 to-violet-50  border-indigo-200 text-indigo-600',
  }[color];
  return (
    <div className={`rounded-2xl border bg-gradient-to-br p-5 flex items-center gap-4 shadow-sm ${ring}`}>
      <div className={`w-12 h-12 rounded-xl bg-white/80 shadow-sm flex items-center justify-center shrink-0`}>
        <Icon className="w-6 h-6" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-0.5">{label}</p>
        {loading ? (
          <div className="h-7 w-16 bg-gray-200 rounded animate-pulse" />
        ) : (
          <p className="text-2xl font-extrabold text-gray-900 leading-none" data-testid={testId}>
            {value}
          </p>
        )}
        {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
      </div>
    </div>
  );
}

/* ── quick-action button ── */
function QuickBtn({ icon: Icon, label, onClick, testId, accent = false }) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      className={`group flex items-center gap-2.5 px-4 py-2.5 rounded-xl font-semibold text-sm
        border transition-all duration-150
        ${accent
          ? 'bg-amber-500 hover:bg-amber-600 border-amber-500 text-white shadow-md shadow-amber-200'
          : 'bg-white hover:bg-gray-50 border-gray-200 text-gray-700 hover:border-gray-300'
        }`}
    >
      <Icon className="w-4 h-4" />
      {label}
      <ChevronRight className="w-3.5 h-3.5 opacity-40 group-hover:opacity-80 transition-opacity" />
    </button>
  );
}

/* ── main ── */
const POSDashboard = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [outlets,         setOutlets]         = useState([]);
  const [selectedOutletId, setSelectedOutletId] = useState('all');
  const [stats,           setStats]           = useState({ outlet_count: 0, menu_count: 0, today_orders: 0, today_revenue: 0 });
  const [loadingStats,    setLoadingStats]    = useState(true);
  const { hasFeature } = useEntitlements();

  /* ── data ── */
  const loadOutlets = useCallback(async () => {
    try {
      const res  = await axios.get('/pos/outlets');
      const list = Array.isArray(res.data) ? res.data : (res.data.outlets || []);
      const active = list.filter(o => o.status !== 'inactive');
      setOutlets(active);
      return active;
    } catch { return []; }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      setLoadingStats(true);
      const params = selectedOutletId !== 'all' ? { outlet_id: selectedOutletId } : {};
      const [menuRes, zRes] = await Promise.all([
        axios.get('/pos/menu-items', { params }).catch(() => ({ data: [] })),
        axios.get('/pos/z-report',   { params }).catch(() => ({ data: { transaction_count: 0, gross_sales: 0 } })),
      ]);
      const menuList = Array.isArray(menuRes.data) ? menuRes.data : (menuRes.data.menu_items || []);
      setStats(prev => ({
        ...prev,
        menu_count:    menuList.length,
        today_orders:  zRes.data.transaction_count || 0,
        today_revenue: zRes.data.gross_sales       || 0,
      }));
    } catch { /* silent */ } finally {
      setLoadingStats(false);
    }
  }, [selectedOutletId]);

  useEffect(() => { loadOutlets(); }, [loadOutlets]);
  useEffect(() => { setStats(prev => ({ ...prev, outlet_count: outlets.length })); }, [outlets.length]);
  useEffect(() => { loadStats(); }, [loadStats]);

  const handleOutletsChanged = useCallback(async () => {
    await loadOutlets();
    await loadStats();
  }, [loadOutlets, loadStats]);

  const currentOutletId = selectedOutletId === 'all' ? null : selectedOutletId;

  /* ── render ── */
  return (
    <div className="min-h-screen bg-gray-50">
      {/* ── Page header ── */}
      <div className="bg-white border-b border-gray-200 shadow-sm">
        <div className="px-6 py-5">
          {/* top row */}
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl bg-amber-100 flex items-center justify-center">
                <UtensilsCrossed className="w-6 h-6 text-amber-600" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900 leading-tight">
                  {t('posDashboard.title', 'Satış Noktası Paneli')}
                </h1>
                <p className="text-sm text-gray-500">
                  {t('posDashboard.subtitle', 'Satış Noktası · Masa, Menü ve Sipariş Yönetimi')}
                </p>
              </div>
            </div>

            {/* quick actions */}
            <div className="flex items-center gap-2 flex-wrap">
              <QuickBtn accent icon={Tablet}          label="Garson Terminali"   onClick={() => navigate('/pos/terminal')}      testId="nav-waiter-terminal" />
              {hasFeature('pos_fnb', 'kds') && (
                <QuickBtn        icon={Monitor}         label={t('fnb.kitchenDisplay', 'Mutfak Ekranı')} onClick={() => navigate('/kitchen-display')} testId="nav-kitchen-display" />
              )}
              <QuickBtn        icon={Coffee}          label={t('staffRoomService.title', 'Oda Servisi Siparişleri')} onClick={() => navigate('/staff/room-service')} testId="nav-staff-room-service" />
              <QuickBtn        icon={UtensilsCrossed} label={t('posDashboard.fnbSuite', 'F&B Paketi')}    onClick={() => navigate('/fnb-complete')}       testId="nav-fnb-complete" />
              <QuickBtn        icon={Sparkles}        label={t('posDashboard.allFeatures', 'Tüm Özellikler')} onClick={() => navigate('/admin/features')} />
              <QuickBtn        icon={ArrowLeft}       label={t('nav.dashboard', 'Kontrol Paneli')}        onClick={() => navigate('/')} />
            </div>
          </div>
        </div>

        {/* ── Stat bar ── */}
        <div className="px-6 pb-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              icon={Store}       label={t('posDashboard.outletCount', 'Satış Noktası')}
              value={stats.outlet_count} color="amber" loading={loadingStats} testId="stat-outlets"
            />
            <StatCard
              icon={MenuIcon}    label={t('posDashboard.menuCount', 'Menü Ürünü')}
              value={stats.menu_count}   color="green" loading={loadingStats} testId="stat-menu"
            />
            <StatCard
              icon={ShoppingBag} label={t('posDashboard.todaysOrders', 'Bugün Sipariş')}
              value={stats.today_orders} color="purple" loading={loadingStats}
            />
            <StatCard
              icon={TrendingUp}  label={t('posDashboard.todaysRevenue', 'Bugün Ciro')}
              value={`${fmt(stats.today_revenue)} ₺`}
              sub={`${stats.today_orders} ${t('posDashboard.transactions', 'işlem')}`}
              color="blue" loading={loadingStats} testId="stat-revenue"
            />
          </div>
        </div>

        {/* Outlet selector strip */}
        <div className="px-6 pb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              <Store className="w-3.5 h-3.5 inline mr-1" />
              Filtre:
            </span>
            <div className="flex items-center gap-1.5 flex-wrap">
              <OutletPill
                label="Tümü (toplam)"
                active={selectedOutletId === 'all'}
                onClick={() => setSelectedOutletId('all')}
                testId="select-outlet-all"
              />
              {outlets.map(o => (
                <OutletPill
                  key={o.id}
                  label={o.outlet_name || o.name}
                  active={selectedOutletId === o.id}
                  onClick={() => setSelectedOutletId(o.id)}
                  testId={`select-outlet-${o.id}`}
                />
              ))}
            </div>
            {outlets.length === 0 && !loadingStats && (
              <div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {t('posDashboard.noOutletsHint', 'Henüz satış noktası yok — "Satış Noktaları" sekmesinden ekleyin')}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Tabs body ── */}
      <div className="px-6 py-6">
        <Tabs defaultValue="outlets" className="w-full">
          <TabsList className="inline-flex h-10 items-center rounded-xl bg-white border border-gray-200 shadow-sm p-1 gap-0.5 mb-6">
            {[
              { value: 'outlets',  icon: Store,       label: t('posDashboard.outlets',   'Satış Noktaları'), testId: 'tab-outlets' },
              { value: 'menu',     icon: MenuIcon,    label: t('posDashboard.menuItems', 'Menü Kalemleri'), testId: 'tab-menu' },
              { value: 'tables',   icon: LayoutGrid,  label: t('posDashboard.tables',    'Masalar'),         testId: 'tab-tables' },
              { value: 'reports',  icon: BarChart3,   label: t('posDashboard.reports',   'Raporlar'),        testId: 'tab-reports' },
              { value: 'printers', icon: Printer,     label: 'Yazıcılar',                                   testId: 'tab-printers' },
            ].map(({ value, icon: Icon, label, testId }) => (
              <TabsTrigger
                key={value}
                value={value}
                data-testid={testId}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium
                  text-gray-500 data-[state=active]:bg-amber-500 data-[state=active]:text-white
                  data-[state=active]:shadow-sm hover:text-gray-800 transition-all"
              >
                <Icon className="w-4 h-4" />
                {label}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="outlets">
            <POSOutletManagement onChange={handleOutletsChanged} />
          </TabsContent>

          <TabsContent value="menu">
            <POSMenuItems outletId={currentOutletId} onItemSelect={() => {}} />
          </TabsContent>

          <TabsContent value="tables">
            {currentOutletId ? (
              <POSTableManagement outletId={currentOutletId} />
            ) : outlets.length > 0 ? (
              <POSTableManagement outletId={outlets[0].id} />
            ) : (
              <EmptyTabState
                icon={LayoutGrid}
                text={t('posDashboard.createOutletFirst', 'Önce bir satış noktası oluşturun')}
              />
            )}
          </TabsContent>

          <TabsContent value="reports">
            <POSReports outletId={currentOutletId} />
          </TabsContent>

          <TabsContent value="printers">
            <POSPrinterSettings />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

/* ── tiny helpers ── */
function OutletPill({ label, active, onClick, testId }) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
        active
          ? 'bg-amber-500 border-amber-500 text-white shadow-sm'
          : 'bg-white border-gray-200 text-gray-600 hover:border-amber-300 hover:text-amber-700'
      }`}
    >
      {label}
    </button>
  );
}

function EmptyTabState({ icon: Icon, text }) {
  return (
    <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-12 text-center">
      <Icon className="w-12 h-12 mx-auto mb-3 text-gray-300" />
      <p className="text-gray-500 text-sm">{text}</p>
    </div>
  );
}

export default POSDashboard;
