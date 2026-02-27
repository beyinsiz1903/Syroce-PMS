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
              F&B Management Suite
            </h1>
            <p className="text-gray-600 mt-1">Recipe Costing, BEO, Kitchen Display, Inventory</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => navigate('/pos')}>
              <Monitor className="w-4 h-4 mr-2" />
              POS Restaurant
            </Button>
            <Button onClick={() => navigate('/')}>
              <Home className="w-4 h-4 mr-2" />
              Dashboard
            </Button>
          </div>
        </div>

        {/* Main Tabs */}
        <Tabs defaultValue="outlet-sales" className="w-full mt-4">
          <TabsList className="grid w-full max-w-3xl grid-cols-4 md:grid-cols-5">
            <TabsTrigger value="outlet-sales">
              <ChefHat className="w-4 h-4 mr-2" />Outlet Sales
            </TabsTrigger>
            <TabsTrigger value="recipes">
              <ChefHat className="w-4 h-4 mr-2" />Recipes
            </TabsTrigger>
            <TabsTrigger value="beo">
              <FileText className="w-4 h-4 mr-2" />BEO
            </TabsTrigger>
            <TabsTrigger value="kitchen">
              <Monitor className="w-4 h-4 mr-2" />Kitchen Display
            </TabsTrigger>
            <TabsTrigger value="inventory">
              <Package className="w-4 h-4 mr-2" />Inventory
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
                <CardTitle>BEO Generator</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center py-8">
                  <FileText className="w-16 h-16 text-orange-600 mx-auto mb-4" />
                  <p className="text-gray-700 mb-4">Banquet Event Order otomatik oluşturma</p>
                  <Button
                    className="bg-orange-600"
                    onClick={() => navigate('/fnb/beo-generator')}
                  >
                    BEO Oluştur
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="kitchen" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Kitchen Display System</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col items-center justify-center gap-4 py-8">
                  <p className="text-center text-gray-600 max-w-md">
                    Servis sırasında mutfak için tam ekran, karanlık temalı Kitchen Display ekranını kullanın.
                  </p>
                  <Button
                    className="bg-orange-600 hover:bg-orange-700"
                    onClick={() => navigate('/kitchen-display')}
                  >
                    Tam Ekran Kitchen Display Aç
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
