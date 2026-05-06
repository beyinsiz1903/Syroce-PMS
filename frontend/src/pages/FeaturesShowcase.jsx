import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import POSTableManagement from '../components/POSTableManagement';
import POSMenuItems from '../components/POSMenuItems';
import StaffAssignment from '../components/StaffAssignment';
import MessagingTemplates from '../components/MessagingTemplates';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import {
  Users, 
  UtensilsCrossed, 
  MessageSquare,
  Sparkles,
  ArrowLeft,
  Menu
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { alertDialog } from '@/lib/dialogs';

const FeaturesShowcase = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Sparkles className="w-8 h-8 text-indigo-600" />
              {t('featuresShowcase.title')}
            </h1>
            <p className="text-gray-600 mt-1">
              {t('featuresShowcase.subtitle')}
            </p>
          </div>
          <Button onClick={() => navigate('/')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            {t('featuresShowcase.backToDashboard')}
          </Button>
        </div>

        {/* Tabs for Features */}
        <Tabs defaultValue="pos" className="w-full">
          <TabsList className="grid w-full grid-cols-4 max-w-3xl">
            <TabsTrigger value="pos">
              <UtensilsCrossed className="w-4 h-4 mr-2" />
              POS Tables
            </TabsTrigger>
            <TabsTrigger value="menu">
              <Menu className="w-4 h-4 mr-2" />
              Menu Items
            </TabsTrigger>
            <TabsTrigger value="staff">
              <Users className="w-4 h-4 mr-2" />
              Staff
            </TabsTrigger>
            <TabsTrigger value="messaging">
              <MessageSquare className="w-4 h-4 mr-2" />
              Messaging
            </TabsTrigger>
          </TabsList>

          {/* POS Tables Tab */}
          <TabsContent value="pos" className="mt-6">
            <div className="space-y-4">
              <Card className="bg-blue-50 border-blue-200">
                <CardContent className="p-4">
                  <div className="flex items-start space-x-3">
                    <div className="bg-blue-100 p-2 rounded-full">
                      <UtensilsCrossed className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900 mb-1">🍽️ {t('featuresShowcase.tableMgmt')}</h4>
                      <p className="text-sm text-gray-600">
                        {t('featuresShowcase.tableMgmtDesc')}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <POSTableManagement outletId="main_restaurant" />
            </div>
          </TabsContent>

          {/* Menu Items Tab */}
          <TabsContent value="menu" className="mt-6">
            <div className="space-y-4">
              <Card className="bg-amber-50 border-amber-200">
                <CardContent className="p-4">
                  <div className="flex items-start space-x-3">
                    <div className="bg-amber-100 p-2 rounded-full">
                      <Menu className="w-5 h-5 text-amber-600" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900 mb-1">📋 {t('featuresShowcase.menuMgmt')}</h4>
                      <p className="text-sm text-gray-600">
                        {t('featuresShowcase.menuMgmtDesc')}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <POSMenuItems outletId="main_restaurant" />
            </div>
          </TabsContent>

          {/* Staff Assignment Tab */}
          <TabsContent value="staff" className="mt-6">
            <div className="space-y-4">
              <Card className="bg-green-50 border-green-200">
                <CardContent className="p-4">
                  <div className="flex items-start space-x-3">
                    <div className="bg-green-100 p-2 rounded-full">
                      <Users className="w-5 h-5 text-green-600" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900 mb-1">👥 {t('featuresShowcase.staffMgmt')}</h4>
                      <p className="text-sm text-gray-600">
                        {t('featuresShowcase.staffMgmtDesc')}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <StaffAssignment />
            </div>
          </TabsContent>

          {/* Messaging Tab */}
          <TabsContent value="messaging" className="mt-6">
            <div className="space-y-4">
              <Card className="bg-indigo-50 border-indigo-200">
                <CardContent className="p-4">
                  <div className="flex items-start space-x-3">
                    <div className="bg-indigo-100 p-2 rounded-full">
                      <MessageSquare className="w-5 h-5 text-indigo-600" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900 mb-1">💬 {t('featuresShowcase.messagingTitle')}</h4>
                      <p className="text-sm text-gray-600">
                        {t('featuresShowcase.messagingDesc')}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <MessagingTemplates />
            </div>
          </TabsContent>
        </Tabs>

        {/* Quick Links */}
        <Card className="bg-gradient-to-r from-indigo-50 to-pink-50 border-indigo-200">
          <CardHeader>
            <CardTitle>{t('featuresShowcase.otherFeatures')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Button
                variant="outline"
                className="h-24 flex flex-col items-center justify-center"
                onClick={() => navigate('/cost-management')}
              >
                <span className="text-2xl mb-2">💰</span>
                <span className="text-sm">{t('featuresShowcase.costManagement')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-24 flex flex-col items-center justify-center"
                onClick={() => navigate('/rms')}
              >
                <span className="text-2xl mb-2">📊</span>
                <span className="text-sm">{t('featuresShowcase.revenueBreakdown')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-24 flex flex-col items-center justify-center"
                onClick={() => {
                  alertDialog({ message: 'Navigate to any booking and open Upsell Store to see AI products' });
                }}
              >
                <span className="text-2xl mb-2">🛍️</span>
                <span className="text-sm">{t('featuresShowcase.aiUpsellCenter')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-24 flex flex-col items-center justify-center"
                onClick={() => {
                  alertDialog({ message: 'Split Folio: Open any folio and use Split button (to be added to Folio Manager)' });
                }}
              >
                <span className="text-2xl mb-2">📑</span>
                <span className="text-sm">{t('featuresShowcase.splitFolio')}</span>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default FeaturesShowcase;
