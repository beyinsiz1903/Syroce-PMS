import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import Layout from '../components/Layout';
import POSTableManagement from '../components/POSTableManagement';
import POSMenuItems from '../components/POSMenuItems';
import POSOutletManagement from '../components/POSOutletManagement';
import POSReports from '../components/POSReports';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from '../components/ui/tabs';
import {
  UtensilsCrossed, Menu, ArrowLeft, BarChart3, Sparkles,
  Store, LayoutGrid, AlertCircle,
} from 'lucide-react';

const POSDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [outlets, setOutlets] = useState([]);
  const [selectedOutletId, setSelectedOutletId] = useState('all');
  const [stats, setStats] = useState({
    outlet_count: 0,
    menu_count: 0,
    today_orders: 0,
    today_revenue: 0,
  });
  const [loadingStats, setLoadingStats] = useState(true);

  const loadOutlets = useCallback(async () => {
    try {
      const res = await axios.get('/pos/outlets');
      const list = Array.isArray(res.data) ? res.data : (res.data.outlets || []);
      const active = list.filter(o => o.status !== 'inactive');
      setOutlets(active);
      return active;
    } catch (err) {
      console.error('Outlets yüklenemedi:', err);
      return [];
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      setLoadingStats(true);
      const params = selectedOutletId !== 'all' ? { outlet_id: selectedOutletId } : {};
      const [outletList, menuRes, zRes] = await Promise.all([
        loadOutlets(),
        axios.get('/pos/menu-items', { params }).catch(() => ({ data: [] })),
        axios.get('/pos/z-report', { params }).catch(() => ({ data: { transaction_count: 0, gross_sales: 0 } })),
      ]);
      const menuList = Array.isArray(menuRes.data) ? menuRes.data : (menuRes.data.menu_items || []);
      setStats({
        outlet_count: outletList.length,
        menu_count: menuList.length,
        today_orders: zRes.data.transaction_count || 0,
        today_revenue: zRes.data.gross_sales || 0,
      });
    } catch (err) {
      console.error('Istatistikler yüklenemedi:', err);
    } finally {
      setLoadingStats(false);
    }
  }, [selectedOutletId, loadOutlets]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const currentOutletId = selectedOutletId === 'all' ? null : selectedOutletId;
  const selectedOutlet = outlets.find(o => o.id === selectedOutletId);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pos">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <UtensilsCrossed className="w-8 h-8 text-orange-600" />
              {t('posDashboard.title')}
            </h1>
            <p className="text-gray-600 mt-1">{t('posDashboard.subtitle')}</p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <Button variant="outline" onClick={() => navigate('/fnb-complete')}
              data-testid="nav-fnb-complete">
              <UtensilsCrossed className="w-4 h-4 mr-2" />
              {t('posDashboard.fnbSuite')}
            </Button>
            <Button variant="outline" onClick={() => navigate('/admin/features')}>
              <Sparkles className="w-4 h-4 mr-2" />
              {t('posDashboard.allFeatures')}
            </Button>
            <Button onClick={() => navigate('/')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('nav.dashboard')}
            </Button>
          </div>
        </div>

        {/* Outlet Selector + Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <Card className="md:col-span-2 bg-gradient-to-br from-orange-50 to-amber-50 border-orange-200">
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Store className="w-4 h-4 text-orange-600" />
                <span className="text-sm font-semibold">{t('posDashboard.activeOutlet')}</span>
              </div>
              <Select value={selectedOutletId} onValueChange={setSelectedOutletId}>
                <SelectTrigger data-testid="select-outlet" className="bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('posDashboard.allOutlets')}</SelectItem>
                  {outlets.map(o => (
                    <SelectItem key={o.id} value={o.id}>
                      {o.outlet_name || o.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedOutlet && (
                <div className="mt-2 flex items-center gap-2 text-xs text-gray-600">
                  <Badge variant="outline">{selectedOutlet.outlet_type}</Badge>
                  {selectedOutlet.location && <span>{selectedOutlet.location}</span>}
                </div>
              )}
              {outlets.length === 0 && !loadingStats && (
                <div className="mt-2 flex items-start gap-2 text-xs text-amber-700 bg-amber-50 p-2 rounded">
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  <span>{t('posDashboard.noOutletsHint')}</span>
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-sm text-gray-600 mb-1">{t('posDashboard.outletCount')}</p>
              <p className="text-3xl font-bold text-orange-600" data-testid="stat-outlets">
                {stats.outlet_count}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-sm text-gray-600 mb-1">{t('posDashboard.menuCount')}</p>
              <p className="text-3xl font-bold text-green-600" data-testid="stat-menu">
                {stats.menu_count}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-sm text-gray-600 mb-1">{t('posDashboard.todaysRevenue')}</p>
              <p className="text-2xl font-bold text-blue-600" data-testid="stat-revenue">
                {Number(stats.today_revenue).toLocaleString('tr-TR', {
                  maximumFractionDigits: 0,
                })}
                <span className="text-sm ml-1">TL</span>
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {stats.today_orders} {t('posDashboard.transactions')}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="outlets" className="w-full">
          <TabsList className="grid w-full grid-cols-2 md:grid-cols-4 max-w-2xl">
            <TabsTrigger value="outlets" data-testid="tab-outlets">
              <Store className="w-4 h-4 mr-2" />
              {t('posDashboard.outlets')}
            </TabsTrigger>
            <TabsTrigger value="menu" data-testid="tab-menu">
              <Menu className="w-4 h-4 mr-2" />
              {t('posDashboard.menuItems')}
            </TabsTrigger>
            <TabsTrigger value="tables" data-testid="tab-tables">
              <LayoutGrid className="w-4 h-4 mr-2" />
              {t('posDashboard.tables')}
            </TabsTrigger>
            <TabsTrigger value="reports" data-testid="tab-reports">
              <BarChart3 className="w-4 h-4 mr-2" />
              {t('posDashboard.reports')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="outlets" className="mt-6">
            <POSOutletManagement onChange={loadStats} />
          </TabsContent>

          <TabsContent value="menu" className="mt-6">
            <POSMenuItems
              outletId={currentOutletId}
              onItemSelect={() => { /* hook for cart add — implemented in POSOrderEntry */ }}
            />
          </TabsContent>

          <TabsContent value="tables" className="mt-6">
            {currentOutletId ? (
              <POSTableManagement outletId={currentOutletId} />
            ) : outlets.length > 0 ? (
              <POSTableManagement outletId={outlets[0].id} />
            ) : (
              <Card>
                <CardContent className="p-8 text-center text-gray-500">
                  <LayoutGrid className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                  <p>{t('posDashboard.createOutletFirst')}</p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="reports" className="mt-6">
            <POSReports outletId={currentOutletId} />
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default POSDashboard;
