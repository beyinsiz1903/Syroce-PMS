import { useTranslation } from 'react-i18next';
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ArrowLeft, Wrench, AlertTriangle, CheckCircle, Clock, TrendingUp, RefreshCw, Settings, History, FileText, BarChart3, Eye, Calendar, Package, ShoppingCart, Camera, Upload, Filter, X, Plus, Minus, QrCode, Activity, Home, Snowflake, Zap, Droplet, Hammer, Sofa } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function MobileMaintenancePartsInventoryModal({ partsInventoryModalOpen, setPartsInventoryModalOpen, partsInventory, toast }) {
    const { t } = useTranslation();
    return (
        <Dialog open={partsInventoryModalOpen} onOpenChange={setPartsInventoryModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Package className="w-5 h-5 text-green-600" />
              <span>Parça & Malzeme Stok Kartı</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-3">
            {/* Stock Summary */}
            <div className="grid grid-cols-3 gap-2">
              <Card className="bg-blue-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-blue-900">{partsInventory.length}</p>
                  <p className="text-xs text-blue-600">Toplam Kalem</p>
                </CardContent>
              </Card>
              <Card className="bg-red-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-red-900">
                    {partsInventory.filter(p => p.stock < p.min_stock).length}
                  </p>
                  <p className="text-xs text-red-600">Düşük Stok</p>
                </CardContent>
              </Card>
              <Card className="bg-green-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-green-900">
                    {partsInventory.filter(p => p.stock >= p.min_stock).length}
                  </p>
                  <p className="text-xs text-green-600">Yeterli Stok</p>
                </CardContent>
              </Card>
            </div>

            {/* Low Stock Alert */}
            {partsInventory.filter(p => p.stock < p.min_stock).length > 0 && <Card className="bg-red-50 border-red-200">
                <CardContent className="p-3">
                  <div className="flex items-center space-x-2">
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                    <p className="text-sm font-bold text-red-900">
                      {partsInventory.filter(p => p.stock < p.min_stock).length} kalem kritik seviyede!
                    </p>
                  </div>
                </CardContent>
              </Card>}

            {/* Parts List by Category */}
            {['HVAC', 'Elektrik', 'Tesisat', 'Yapısal', 'Mobilya', 'Genel'].map(category => {
        const categoryParts = partsInventory.filter(p => p.category === category);
        if (categoryParts.length === 0) return null;
        return <Card key={category}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center justify-between">
                      <span className="flex items-center gap-1.5">
                        {category === 'HVAC' ? <><Snowflake className="w-3.5 h-3.5 text-sky-600" /> HVAC</> : category === 'Elektrik' ? <><Zap className="w-3.5 h-3.5 text-amber-600" /> Elektrik</> : category === 'Tesisat' ? <><Droplet className="w-3.5 h-3.5 text-sky-500" /> Tesisat</> : category === 'Yapısal' ? <><Hammer className="w-3.5 h-3.5 text-slate-600" /> Yapısal</> : category === 'Mobilya' ? <><Sofa className="w-3.5 h-3.5 text-amber-700" /> Mobilya</> : <><Wrench className="w-3.5 h-3.5 text-slate-600" /> Genel Malzeme</>}
                      </span>
                      <Badge variant="outline">{categoryParts.length}</Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {categoryParts.map(part => {
              const isLowStock = part.stock < part.min_stock;
              const stockPercentage = part.stock / part.min_stock * 100;
              return <div key={part.id} className={`p-3 rounded-lg border ${isLowStock ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'}`}>
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex-1">
                              <div className="flex items-center space-x-2">
                                <p className="font-bold text-gray-900">{part.name}</p>
                                {isLowStock && <Badge className="bg-red-500 text-xs">DİKKAT</Badge>}
                              </div>
                              <p className="text-xs text-gray-500 mt-1">{part.location}</p>
                            </div>
                            <div className="text-right">
                              <p className="font-bold text-lg text-indigo-700">{part.unit_price} ₺</p>
                              <p className="text-xs text-gray-500">/{part.unit}</p>
                            </div>
                          </div>
                          
                          {/* Stock Bar */}
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className="text-gray-600">Stok Durumu:</span>
                              <span className={`font-bold ${isLowStock ? 'text-red-700' : 'text-green-700'}`}>
                                {part.stock} / {part.min_stock} {part.unit}
                              </span>
                            </div>
                            <div className="w-full bg-gray-200 rounded-full h-2">
                              <div className={`h-2 rounded-full transition-all ${stockPercentage < 50 ? 'bg-red-500' : stockPercentage < 100 ? 'bg-yellow-500' : 'bg-green-500'}`} style={{
                      width: `${Math.min(stockPercentage, 100)}%`
                    }} />
                            </div>
                          </div>

                          {isLowStock && <div className="mt-2 flex items-center justify-between p-2 bg-red-100 rounded">
                              <span className="text-xs text-red-900 flex items-center gap-1">
                                <AlertTriangle className="w-3 h-3" />
                                {part.min_stock - part.stock} {part.unit} sipariş gerekli
                              </span>
                              <Button size="sm" className="bg-red-600 hover:bg-red-700 h-6 text-xs" onClick={() => toast.success(`${part.name} sipariş listesine eklendi`)}>
                                <ShoppingCart className="w-3 h-3 mr-1" />
                                Sipariş
                              </Button>
                            </div>}
                        </div>;
            })}
                  </CardContent>
                </Card>;
      })}

            {/* Total Value */}
            <Card className="bg-gradient-to-r from-indigo-50 to-indigo-50 border-indigo-200">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-indigo-700 font-medium">Toplam Stok Değeri</p>
                    <p className="text-xs text-indigo-600 mt-1">Tüm malzemeler</p>
                  </div>
                  <p className="text-3xl font-bold text-indigo-700">
                    {partsInventory.reduce((sum, p) => sum + p.stock * p.unit_price, 0).toLocaleString('tr-TR')} ₺
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>
    );
}
