import React from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import POSTableManagement from '../components/POSTableManagement';
import POSMenuItems from '../components/POSMenuItems';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { UtensilsCrossed, Menu, ArrowLeft, BarChart3, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const POSDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pos">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <UtensilsCrossed className="w-8 h-8 text-orange-600" />
              {t('posDashboard.title')}
            </h1>
            <p className="text-gray-600 mt-1">
              {t('posDashboard.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-3">
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

        {/* Info Banner */}
        <Card className="bg-gradient-to-r from-orange-50 to-red-50 border-orange-200">
          <CardContent className="p-4">
            <div className="flex items-start space-x-3">
              <div className="bg-orange-100 p-2 rounded-full">
                <UtensilsCrossed className="w-5 h-5 text-orange-600" />
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 mb-1">{t('posDashboard.restaurantMgmt')}</h4>
                <p className="text-sm text-gray-600">
                  {t('posDashboard.restaurantMgmtDesc')}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Tabs defaultValue="tables" className="w-full">
          <TabsList className="grid w-full grid-cols-3 max-w-2xl">
            <TabsTrigger value="tables">
              <UtensilsCrossed className="w-4 h-4 mr-2" />
              {t('posDashboard.tables')}
            </TabsTrigger>
            <TabsTrigger value="menu">
              <Menu className="w-4 h-4 mr-2" />
              {t('posDashboard.menuItems')}
            </TabsTrigger>
            <TabsTrigger value="reports">
              <BarChart3 className="w-4 h-4 mr-2" />
              {t('posDashboard.reports')}
            </TabsTrigger>
          </TabsList>

          {/* Tables Tab */}
          <TabsContent value="tables" className="mt-6">
            <POSTableManagement outletId="main_restaurant" />
          </TabsContent>

          {/* Menu Tab */}
          <TabsContent value="menu" className="mt-6">
            <POSMenuItems 
              outletId="main_restaurant"
              onItemSelect={(item) => console.log('Selected:', item)}
            />
          </TabsContent>

          {/* Reports Tab */}
          <TabsContent value="reports" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('posDashboard.salesReports')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center py-12 text-gray-500">
                  <BarChart3 className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                  <p>{t('posDashboard.comingSoon')}</p>
                  <p className="text-sm mt-2">
                    {t('posDashboard.comingSoonDesc')}
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Quick Stats (Placeholder) */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <p className="text-sm text-gray-600 mb-1">{t('posDashboard.tables')}</p>
                <p className="text-3xl font-bold text-blue-600">20</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <p className="text-sm text-gray-600 mb-1">{t('posDashboard.menuItems')}</p>
                <p className="text-3xl font-bold text-green-600">13</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <p className="text-sm text-gray-600 mb-1">{t('posDashboard.todaysOrders')}</p>
                <p className="text-3xl font-bold text-purple-600">--</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-center">
                <p className="text-sm text-gray-600 mb-1">{t('posDashboard.revenue')}</p>
                <p className="text-3xl font-bold text-orange-600">--</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
};

export default POSDashboard;
