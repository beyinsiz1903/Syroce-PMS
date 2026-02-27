import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Home, ChefHat, FileText, Package, Monitor } from 'lucide-react';
import { toast } from 'sonner';
import FnBOutletDashboard from '@/components/FnBOutletDashboard';
import RecipeCostingManager from '@/components/RecipeCostingManager';
import IngredientInventoryPanel from '@/components/IngredientInventoryPanel';
import { useTranslation } from 'react-i18next';

const FnBComplete = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="fnb">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <ChefHat className="w-8 h-8 text-orange-600" />
              {t('fnb.suiteTitle')}
            </h1>
            <p className="text-gray-600 mt-1">{t('fnb.suiteSubtitle')}</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => navigate('/pos')}>
              <Monitor className="w-4 h-4 mr-2" />
              {t('fnb.posRestaurant')}
            </Button>
            <Button onClick={() => navigate('/')}>
              <Home className="w-4 h-4 mr-2" />
              {t('nav.dashboard')}
            </Button>
          </div>
        </div>

        {/* Main Tabs */}
        <Tabs defaultValue="outlet-sales" className="w-full mt-4">
          <TabsList className="grid w-full max-w-3xl grid-cols-4 md:grid-cols-5">
            <TabsTrigger value="outlet-sales">
              <ChefHat className="w-4 h-4 mr-2" />{t('fnb.outletSales')}
            </TabsTrigger>
            <TabsTrigger value="recipes">
              <ChefHat className="w-4 h-4 mr-2" />{t('fnb.recipes')}
            </TabsTrigger>
            <TabsTrigger value="beo">
              <FileText className="w-4 h-4 mr-2" />{t('fnb.beo')}
            </TabsTrigger>
            <TabsTrigger value="kitchen">
              <Monitor className="w-4 h-4 mr-2" />{t('fnb.kitchenDisplay')}
            </TabsTrigger>
            <TabsTrigger value="inventory">
              <Package className="w-4 h-4 mr-2" />{t('fnb.inventory')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="outlet-sales" className="mt-6">
            <FnBOutletDashboard />
          </TabsContent>

          <TabsContent value="recipes" className="mt-6">
            <RecipeCostingManager />
          </TabsContent>

          <TabsContent value="beo" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('fnb.beoGenerator')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center py-8">
                  <FileText className="w-16 h-16 text-orange-600 mx-auto mb-4" />
                  <p className="text-gray-700 mb-4">{t('fnb.beoAutoCreate')}</p>
                  <Button
                    className="bg-orange-600"
                    onClick={() => navigate('/fnb/beo-generator')}
                  >
                    {t('fnb.createBeo')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="kitchen" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>{t('fnb.kitchenDisplaySystem')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col items-center justify-center gap-4 py-8">
                  <p className="text-center text-gray-600 max-w-md">
                    {t('fnb.kitchenDisplayDesc')}
                  </p>
                  <Button
                    className="bg-orange-600 hover:bg-orange-700"
                    onClick={() => navigate('/kitchen-display')}
                  >
                    {t('fnb.openFullScreen')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="inventory" className="mt-6">
            <IngredientInventoryPanel />
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default FnBComplete;
