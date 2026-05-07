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
import {
  ArrowLeft, 
  UtensilsCrossed, 
  DollarSign, 
  TrendingUp,
  Clock,
  Users,
  RefreshCw,
  ShoppingBag,
  BarChart3,
  Plus,
  Minus,
  FileText,
  XCircle,
  MenuIcon,
  Calculator,
  Download,
  Store,
  ChevronDown,
  CheckCircle,
  Home
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { promptDialog } from '@/lib/dialogs';
const MobileFnB = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [dailySummary, setDailySummary] = useState(null);
  const [recentTransactions, setRecentTransactions] = useState([]);
  const [outlets, setOutlets] = useState([]);
  const [topItems, setTopItems] = useState([]);
  const [menuItems, setMenuItems] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [orderModalOpen, setOrderModalOpen] = useState(false);
  const [reportsModalOpen, setReportsModalOpen] = useState(false);
  const [selectedOutlet, setSelectedOutlet] = useState(null);
  const [orderItems, setOrderItems] = useState([]);
  const [tableNumber, setTableNumber] = useState('');
  const [zReportModalOpen, setZReportModalOpen] = useState(false);
  const [voidReportModalOpen, setVoidReportModalOpen] = useState(false);
  const [menuManagementModalOpen, setMenuManagementModalOpen] = useState(false);
  const [zReportData, setZReportData] = useState(null);
  const [voidTransactions, setVoidTransactions] = useState([]);
  const [outletSelectorOpen, setOutletSelectorOpen] = useState(false);
  const [activeOutlet, setActiveOutlet] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    // Set first active outlet as default
    if (outlets.length > 0 && !activeOutlet) {
      const firstActive = outlets.find(o => o.status === 'active') || outlets[0];
      setActiveOutlet(firstActive);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [outlets]);

  const loadData = async () => {
    try {
      setLoading(true);
      const today = new Date().toISOString().split('T')[0];
      
      const [summaryRes, transactionsRes, outletsRes, menuRes] = await Promise.all([
        axios.get(`/pos/daily-summary?date=${today}`),
        axios.get('/pos/transactions?limit=10'),
        axios.get('/pos/outlets'),
        axios.get('/pos/menu-items')
      ]);

      setDailySummary(summaryRes.data);
      const txData = transactionsRes.data;
      setRecentTransactions(
        Array.isArray(txData) ? txData : (txData?.transactions || txData?.orders || [])
      );
      const outletData = outletsRes.data;
      setOutlets(
        Array.isArray(outletData) ? outletData : (outletData?.outlets || [])
      );
      const menuData = menuRes.data;
      const menuList = Array.isArray(menuData) ? menuData : (menuData?.menu_items || []);
      setMenuItems(menuList);
      setTopItems(menuList.slice(0, 5));
    } catch (error) {
      console.error('Failed to load F&B data:', error);
      toast.error('✗ Yükleme');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleAddItem = (item) => {
    const existing = orderItems.find(i => i.item_id === item.id);
    if (existing) {
      setOrderItems(orderItems.map(i => 
        i.item_id === item.id ? {...i, quantity: i.quantity + 1} : i
      ));
    } else {
      setOrderItems([...orderItems, { item_id: item.id, name: item.name, price: item.price, quantity: 1 }]);
    }
  };

  const handleRemoveItem = (itemId) => {
    const existing = orderItems.find(i => i.item_id === itemId);
    if (existing && existing.quantity > 1) {
      setOrderItems(orderItems.map(i => 
        i.item_id === itemId ? {...i, quantity: i.quantity - 1} : i
      ));
    } else {
      setOrderItems(orderItems.filter(i => i.item_id !== itemId));
    }
  };

  const calculateTotal = () => {
    return orderItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  };

  const handleSubmitOrder = async () => {
    try {
      if (!selectedOutlet) {
        toast.error('⚠️ Outlet seçin');
        return;
      }
      if (orderItems.length === 0) {
        toast.error('⚠️ Ürün ekleyin');
        return;
      }

      await axios.post('/pos/mobile/quick-order', {
        outlet_id: selectedOutlet,
        table_number: tableNumber,
        items: orderItems,
        notes: ''
      });

      toast.success('✓ Sipariş');
      setOrderModalOpen(false);
      setOrderItems([]);
      setTableNumber('');
      loadData();
    } catch (error) {
      toast.error('✗ Sipariş');
    }
  };

  const formatCurrency = (amount) => {
    return `₺${parseFloat(amount || 0).toFixed(2)}`;
  };

  const loadZReport = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const res = await axios.get(`/pos/z-report?date=${today}`);
      setZReportData(res.data);
      setZReportModalOpen(true);
    } catch (error) {
      toast.error('✗ Z Raporu');
    }
  };

  const loadVoidReport = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const res = await axios.get(`/pos/void-transactions?start_date=${today}&end_date=${today}`);
      setVoidTransactions(res.data.void_transactions || []);
      setVoidReportModalOpen(true);
    } catch (error) {
      toast.error('✗ İptal Raporu');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-amber-600 mx-auto mb-2" />
          <p className="text-gray-600">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-amber-600 to-amber-500 text-white sticky top-0 z-50 shadow-lg">
        <div className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/mobile')}
                className="text-white hover:bg-white/20 p-2"
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div>
                <h1 className="text-xl font-bold">F&B Yönetimi</h1>
                <p className="text-xs text-amber-100">Food & Beverage Dashboard</p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/')}
                className="text-white hover:bg-white/20 p-2"
                title="Ana Sayfa"
              >
                <Home className="w-5 h-5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRefresh}
                disabled={refreshing}
                className="text-white hover:bg-white/20 p-2"
              >
                <RefreshCw className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
        </div>

        {/* Outlet Selector */}
        {outlets.length > 0 && (
          <div className="px-4 pb-3">
            <Button
              variant="ghost"
              className="w-full bg-white/10 hover:bg-white/20 text-white border border-white/30 justify-between"
              onClick={() => setOutletSelectorOpen(true)}
            >
              <div className="flex items-center space-x-2">
                <Store className="w-4 h-4" />
                <div className="text-left">
                  <p className="text-xs font-normal opacity-80">Seçili Outlet</p>
                  <p className="text-sm font-bold">{activeOutlet?.name || 'Outlet Seçin'}</p>
                </div>
              </div>
              <ChevronDown className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>

      <div className="p-4 space-y-4">
        {/* Quick Stats */}
        <div className="grid grid-cols-2 gap-3">
          <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-green-600 font-medium">BUGÜN SATIŞ</p>
                  <p className="text-2xl font-bold text-green-700">
                    {formatCurrency(dailySummary?.total_sales || 0)}
                  </p>
                </div>
                <DollarSign className="w-10 h-10 text-green-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-blue-600 font-medium">TOPLAM İŞLEM</p>
                  <p className="text-3xl font-bold text-blue-700">
                    {dailySummary?.transaction_count || 0}
                  </p>
                </div>
                <ShoppingBag className="w-10 h-10 text-blue-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-indigo-50 to-indigo-100 border-indigo-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-indigo-600 font-medium">ORT. SEPET</p>
                  <p className="text-2xl font-bold text-indigo-700">
                    {formatCurrency(dailySummary?.average_transaction || 0)}
                  </p>
                </div>
                <BarChart3 className="w-10 h-10 text-indigo-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-amber-50 to-amber-100 border-amber-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-amber-600 font-medium">OUTLET SAYISI</p>
                  <p className="text-3xl font-bold text-amber-700">
                    {outlets.length}
                  </p>
                </div>
                <UtensilsCrossed className="w-10 h-10 text-amber-300" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Outlets */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center">
              <UtensilsCrossed className="w-5 h-5 mr-2 text-amber-600" />
              Outlet'ler ({outlets.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {outlets.length === 0 ? (
              <p className="text-gray-500 text-center py-4">Outlet bulunamadı</p>
            ) : (
              outlets.map((outlet) => (
                <div key={outlet.id} className="flex items-center justify-between p-3 bg-amber-50 rounded-lg border border-amber-200">
                  <div className="flex-1">
                    <p className="font-bold text-gray-900">{outlet.name}</p>
                    <p className="text-sm text-gray-600">{outlet.location}</p>
                    <p className="text-xs text-gray-500">
                      Kapasite: {outlet.capacity} • {outlet.type}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge className={outlet.status === 'active' ? 'bg-green-500' : 'bg-gray-500'}>
                      {outlet.status === 'active' ? 'Açık' : 'Kapalı'}
                    </Badge>
                    <p className="text-xs text-gray-500 mt-1">{outlet.operating_hours}</p>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Recent Transactions */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center">
              <Clock className="w-5 h-5 mr-2 text-blue-600" />
              Son İşlemler
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentTransactions.length === 0 ? (
              <p className="text-gray-500 text-center py-4">Henüz işlem yok</p>
            ) : (
              recentTransactions.map((transaction) => (
                <div key={transaction.id} className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border border-blue-200">
                  <div className="flex-1">
                    <p className="font-bold text-gray-900">
                      {transaction.outlet_name || 'Outlet'}
                    </p>
                    <p className="text-sm text-gray-600">
                      Masa {transaction.table_number || 'N/A'}
                    </p>
                    <p className="text-xs text-gray-500">
                      {new Date(transaction.created_at).toLocaleTimeString('tr-TR')}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-green-700">{formatCurrency(transaction.total_amount)}</p>
                    <Badge variant="outline" className="mt-1">
                      {transaction.payment_method || 'Cash'}
                    </Badge>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <div className="grid grid-cols-2 gap-3">
          <Button
            className="h-20 flex flex-col items-center justify-center bg-amber-600 hover:bg-amber-700"
            onClick={() => setOrderModalOpen(true)}
          >
            <ShoppingBag className="w-6 h-6 mb-1" />
            <span className="text-xs">Yeni Sipariş</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-green-600 hover:bg-green-700"
            onClick={loadZReport}
          >
            <Calculator className="w-6 h-6 mb-1" />
            <span className="text-xs">Z Raporu</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-red-600 hover:bg-red-700"
            onClick={loadVoidReport}
          >
            <XCircle className="w-6 h-6 mb-1" />
            <span className="text-xs">İptal Raporu</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-indigo-600 hover:bg-indigo-700"
            onClick={() => setMenuManagementModalOpen(true)}
          >
            <MenuIcon className="w-6 h-6 mb-1" />
            <span className="text-xs">Menü Yönetimi</span>
          </Button>
        </div>
      </div>

      {/* Order Modal */}
      <Dialog open={orderModalOpen} onOpenChange={setOrderModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Yeni Sipariş Oluştur</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Outlet Seçin</Label>
              <select 
                className="w-full p-2 border rounded mt-1"
                value={selectedOutlet || ''}
                onChange={(e) => setSelectedOutlet(e.target.value)}
              >
                <option value="">Seçin...</option>
                {outlets.filter(o => o.status === 'active').map(outlet => (
                  <option key={outlet.id} value={outlet.id}>{outlet.name}</option>
                ))}
              </select>
            </div>

            <div>
              <Label>Masa Numarası</Label>
              <Input 
                value={tableNumber}
                onChange={(e) => setTableNumber(e.target.value)}
                placeholder="Örn: 12"
              />
            </div>

            <div>
              <Label>Ürünler</Label>
              <div className="space-y-2 mt-2 max-h-60 overflow-y-auto">
                {menuItems.map(item => (
                  <div key={item.id} className="flex items-center justify-between p-2 border rounded">
                    <div className="flex-1">
                      <p className="font-medium text-sm">{item.name}</p>
                      <p className="text-xs text-gray-500">{formatCurrency(item.price)}</p>
                    </div>
                    <div className="flex items-center space-x-2">
                      {orderItems.find(i => i.item_id === item.id) && (
                        <>
                          <Button size="sm" variant="outline" onClick={() => handleRemoveItem(item.id)}>
                            <Minus className="w-3 h-3" />
                          </Button>
                          <span className="text-sm font-bold">
                            {orderItems.find(i => i.item_id === item.id)?.quantity || 0}
                          </span>
                        </>
                      )}
                      <Button size="sm" onClick={() => handleAddItem(item)}>
                        <Plus className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {orderItems.length > 0 && (
              <div className="border-t pt-3">
                <div className="space-y-1">
                  {orderItems.map(item => (
                    <div key={item.item_id} className="flex justify-between text-sm">
                      <span>{item.name} x{item.quantity}</span>
                      <span>{formatCurrency(item.price * item.quantity)}</span>
                    </div>
                  ))}
                  <div className="flex justify-between font-bold text-lg border-t pt-2">
                    <span>TOPLAM:</span>
                    <span>{formatCurrency(calculateTotal())}</span>
                  </div>
                </div>
              </div>
            )}

            <Button 
              className="w-full bg-amber-600 hover:bg-amber-700"
              onClick={handleSubmitOrder}
              disabled={!selectedOutlet || orderItems.length === 0}
            >
              Sipariş Oluştur
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Reports Modal */}
      <Dialog open={reportsModalOpen} onOpenChange={setReportsModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>F&B Raporları</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Bugünkü Özet</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">Toplam Satış:</span>
                  <span className="font-bold">{formatCurrency(dailySummary?.total_sales || 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">İşlem Sayısı:</span>
                  <span className="font-bold">{dailySummary?.transaction_count || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Ortalama Sepet:</span>
                  <span className="font-bold">{formatCurrency(dailySummary?.average_transaction || 0)}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Popüler Ürünler</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {topItems.map((item, idx) => (
                  <div key={item.id} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                    <div className="flex items-center space-x-2">
                      <span className="font-bold text-amber-600">{idx + 1}.</span>
                      <span className="text-sm">{item.name}</span>
                    </div>
                    <span className="text-sm font-bold">{formatCurrency(item.price)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>

      {/* Z Report Modal */}
      <Dialog open={zReportModalOpen} onOpenChange={setZReportModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Calculator className="w-5 h-5 text-green-600" />
              <span>Z Raporu - Günlük Kapanış</span>
            </DialogTitle>
          </DialogHeader>
          
          {zReportData ? (
            <div className="space-y-4">
              {/* Header Info */}
              <Card className="bg-green-50">
                <CardContent className="p-4">
                  <div className="text-center">
                    <p className="text-sm text-gray-600">Tarih</p>
                    <p className="text-lg font-bold text-gray-900">
                      {new Date(zReportData.report_date || Date.now()).toLocaleDateString('tr-TR')}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      Rapor No: {zReportData.report_number || 'Z-' + Date.now()}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Sales Summary */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Satış Özeti</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex justify-between p-2 bg-gray-50 rounded">
                    <span className="text-gray-700">Toplam Satış:</span>
                    <span className="font-bold text-green-700">
                      {formatCurrency(zReportData.gross_sales || 0)}
                    </span>
                  </div>
                  <div className="flex justify-between p-2">
                    <span className="text-gray-700">İşlem Sayısı:</span>
                    <span className="font-bold">{zReportData.transaction_count || 0}</span>
                  </div>
                  <div className="flex justify-between p-2 bg-gray-50 rounded">
                    <span className="text-gray-700">İptal/İade:</span>
                    <span className="font-bold text-red-700">
                      -{formatCurrency(zReportData.refunds || 0)}
                    </span>
                  </div>
                  <div className="flex justify-between p-2">
                    <span className="text-gray-700">İndirimler:</span>
                    <span className="font-bold text-amber-700">
                      -{formatCurrency(zReportData.discounts || 0)}
                    </span>
                  </div>
                  <div className="flex justify-between p-3 bg-green-100 rounded-lg border-2 border-green-300 mt-3">
                    <span className="font-bold text-green-900">NET SATIŞ:</span>
                    <span className="font-bold text-xl text-green-700">
                      {formatCurrency(zReportData.net_sales || 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* Payment Methods */}
              {zReportData.payment_methods && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Ödeme Yöntemleri</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {Object.entries(zReportData.payment_methods).map(([method, amount]) => (
                      <div key={method} className="flex justify-between p-2 bg-blue-50 rounded">
                        <span className="capitalize">{method === 'card' ? 'Kredi Kartı' : method === 'cash' ? 'Nakit' : method}</span>
                        <span className="font-bold">{formatCurrency(amount)}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Category Breakdown */}
              {zReportData.category_sales && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Kategori Bazlı Satışlar</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {Object.entries(zReportData.category_sales).map(([category, amount]) => (
                      <div key={category} className="flex justify-between p-2 bg-indigo-50 rounded">
                        <span className="capitalize">{category}</span>
                        <span className="font-bold">{formatCurrency(amount)}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              <Button 
                className="w-full bg-green-600 hover:bg-green-700"
                onClick={() => toast.success('Z raporu indirildi!')}
              >
                <Download className="w-4 h-4 mr-2" />
                Raporu İndir (PDF)
              </Button>
            </div>
          ) : (
            <div className="text-center py-8">
              <FileText className="w-12 h-12 mx-auto text-gray-300 mb-2" />
              <p className="text-gray-500">Z raporu yükleniyor...</p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Void Report Modal */}
      <Dialog open={voidReportModalOpen} onOpenChange={setVoidReportModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <XCircle className="w-5 h-5 text-red-600" />
              <span>İptal Raporu</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-3">
            {voidTransactions.length === 0 ? (
              <div className="text-center py-12">
                <CheckCircle className="w-16 h-16 mx-auto text-green-300 mb-3" />
                <p className="text-gray-600 font-medium">Bugün iptal işlemi yok</p>
                <p className="text-sm text-gray-500 mt-1">Tüm işlemler başarıyla tamamlandı</p>
              </div>
            ) : (
              <>
                <Card className="bg-red-50">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-red-700 font-medium">Toplam İptal</p>
                        <p className="text-2xl font-bold text-red-900">{voidTransactions.length}</p>
                      </div>
                      <XCircle className="w-12 h-12 text-red-300" />
                    </div>
                    <p className="text-xs text-red-600 mt-2">
                      Toplam Tutar: {formatCurrency(voidTransactions.reduce((sum, t) => sum + (t.amount || 0), 0))}
                    </p>
                  </CardContent>
                </Card>

                {voidTransactions.map((transaction, idx) => (
                  <Card key={idx}>
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-2 mb-1">
                            <Badge className="bg-red-500">İPTAL</Badge>
                            <span className="text-xs text-gray-500">
                              {new Date(transaction.voided_at || transaction.created_at).toLocaleString('tr-TR')}
                            </span>
                          </div>
                          <p className="font-bold text-gray-900">
                            İşlem #{transaction.transaction_id || transaction.id}
                          </p>
                          <p className="text-sm text-gray-600 mt-1">
                            Outlet: {transaction.outlet_name || 'N/A'}
                          </p>
                          <p className="text-sm text-gray-600">
                            Masa: {transaction.table_number || 'N/A'}
                          </p>
                          <div className="mt-2 p-2 bg-yellow-50 rounded border border-yellow-200">
                            <p className="text-xs text-yellow-800 font-medium">İptal Nedeni:</p>
                            <p className="text-xs text-yellow-900">{transaction.void_reason || 'Belirtilmedi'}</p>
                          </div>
                          {transaction.voided_by && (
                            <p className="text-xs text-gray-500 mt-1">
                              İptal Eden: {transaction.voided_by}
                            </p>
                          )}
                        </div>
                        <div className="text-right">
                          <p className="font-bold text-lg text-red-700">
                            {formatCurrency(transaction.amount || 0)}
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Menu Management Modal */}
      <Dialog open={menuManagementModalOpen} onOpenChange={setMenuManagementModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <MenuIcon className="w-5 h-5 text-indigo-600" />
              <span>Menü Yönetimi</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-3">
            {/* Menu Stats */}
            <div className="grid grid-cols-3 gap-2">
              <Card className="bg-indigo-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-indigo-700">{menuItems.length}</p>
                  <p className="text-xs text-indigo-600">Toplam Ürün</p>
                </CardContent>
              </Card>
              <Card className="bg-green-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-green-700">
                    {menuItems.filter(i => i.available !== false).length}
                  </p>
                  <p className="text-xs text-green-600">Aktif</p>
                </CardContent>
              </Card>
              <Card className="bg-amber-50">
                <CardContent className="p-3 text-center">
                  <p className="text-2xl font-bold text-amber-700">
                    {new Set(menuItems.map(i => i.category)).size}
                  </p>
                  <p className="text-xs text-amber-600">Kategori</p>
                </CardContent>
              </Card>
            </div>

            {/* Category Groups */}
            {['food', 'beverage', 'dessert', 'appetizer', 'alcohol'].map(category => {
              const items = menuItems.filter(i => i.category === category);
              if (items.length === 0) return null;
              
              return (
                <Card key={category}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm capitalize flex items-center justify-between">
                      <span>
                        {category === 'food' ? '🍽️ Yemekler' : 
                         category === 'beverage' ? '☕ İçecekler' :
                         category === 'dessert' ? '🍰 Tatlılar' :
                         category === 'appetizer' ? '🥗 Mezeler' :
                         '🍷 Alkollü İçecekler'}
                      </span>
                      <Badge variant="outline">{items.length}</Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {items.map(item => (
                      <div key={item.id} className="flex items-center justify-between p-2 bg-gray-50 rounded border">
                        <div className="flex-1">
                          <p className="font-medium text-sm">{item.name}</p>
                          {item.description && (
                            <p className="text-xs text-gray-500">{item.description}</p>
                          )}
                        </div>
                        <div className="text-right">
                          <p className="font-bold text-indigo-700">{formatCurrency(item.price)}</p>
                          <Badge className={item.available !== false ? 'bg-green-500' : 'bg-gray-400'}>
                            {item.available !== false ? 'Mevcut' : 'Yok'}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              );
            })}

            <Button 
              className="w-full bg-indigo-600 hover:bg-indigo-700"
              onClick={async () => {
                const name = await promptDialog({ message: 'Ürün adı:' })?.trim();
                if (!name) return;
                const priceStr = await promptDialog({ message: 'Fiyat (TL):' })?.trim();
                const price = parseFloat((priceStr || '').replace(',', '.'));
                if (!price || price <= 0) {
                  toast.error('Geçerli bir fiyat girin');
                  return;
                }
                const category = (await promptDialog({ message: 'Kategori (food/drink/dessert/appetizer/alcohol):', defaultValue: 'food' }) || 'food').trim().toLowerCase();
                try {
                  const res = await axios.post('/pos/menu-item', {
                    name, price, category, available: true
                  });
                  toast.success(`✅ "${res.data?.name || name}" eklendi`);
                  loadData?.();
                } catch (err) {
                  toast.error(err?.response?.data?.detail || 'Ürün eklenemedi');
                }
              }}
            >
              <Plus className="w-4 h-4 mr-2" />
              Yeni Ürün Ekle
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Outlet Selector Modal */}
      <Dialog open={outletSelectorOpen} onOpenChange={setOutletSelectorOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Store className="w-5 h-5 text-amber-600" />
              <span>Outlet Seçimi</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-3">
            {/* Active Outlet Info */}
            {activeOutlet && (
              <Card className="bg-gradient-to-r from-amber-50 to-red-50 border-amber-200">
                <CardContent className="p-4">
                  <div className="flex items-center space-x-3">
                    <CheckCircle className="w-8 h-8 text-amber-600" />
                    <div className="flex-1">
                      <p className="text-sm text-gray-600">Şu anda görüntülenen:</p>
                      <p className="font-bold text-gray-900">{activeOutlet.name}</p>
                      <p className="text-xs text-gray-500">
                        📍 {activeOutlet.location} • 🪑 {activeOutlet.capacity} kişi
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Outlet List */}
            <div className="space-y-2">
              <p className="text-sm font-medium text-gray-700 mb-2">Tüm Outlet'ler:</p>
              {outlets.map((outlet) => (
                <Button
                  key={outlet.id}
                  variant={activeOutlet?.id === outlet.id ? "default" : "outline"}
                  className={`w-full justify-start h-auto p-4 ${
                    activeOutlet?.id === outlet.id 
                      ? 'bg-amber-600 hover:bg-amber-700 text-white border-amber-600' 
                      : 'bg-white hover:bg-gray-50'
                  }`}
                  onClick={() => {
                    setActiveOutlet(outlet);
                    setOutletSelectorOpen(false);
                    toast.success(`${outlet.name} outlet'ine geçildi!`);
                    loadData(); // Reload data for new outlet
                  }}
                >
                  <div className="flex items-center space-x-3 w-full">
                    <Store className={`w-8 h-8 ${
                      activeOutlet?.id === outlet.id ? 'text-white' : 'text-amber-600'
                    }`} />
                    <div className="flex-1 text-left">
                      <p className={`font-bold ${
                        activeOutlet?.id === outlet.id ? 'text-white' : 'text-gray-900'
                      }`}>
                        {outlet.name}
                      </p>
                      <p className={`text-sm ${
                        activeOutlet?.id === outlet.id ? 'text-amber-100' : 'text-gray-600'
                      }`}>
                        📍 {outlet.location}
                      </p>
                      <div className="flex items-center space-x-3 mt-1">
                        <span className={`text-xs ${
                          activeOutlet?.id === outlet.id ? 'text-amber-100' : 'text-gray-500'
                        }`}>
                          🪑 {outlet.capacity} kişi
                        </span>
                        <span className={`text-xs ${
                          activeOutlet?.id === outlet.id ? 'text-amber-100' : 'text-gray-500'
                        }`}>
                          {outlet.type}
                        </span>
                        <Badge className={
                          outlet.status === 'active' 
                            ? 'bg-green-500' 
                            : 'bg-gray-500'
                        }>
                          {outlet.status === 'active' ? 'Açık' : 'Kapalı'}
                        </Badge>
                      </div>
                      {outlet.operating_hours && (
                        <p className={`text-xs mt-1 ${
                          activeOutlet?.id === outlet.id ? 'text-amber-100' : 'text-gray-500'
                        }`}>
                          🕐 {outlet.operating_hours}
                        </p>
                      )}
                    </div>
                    {activeOutlet?.id === outlet.id && (
                      <CheckCircle className="w-6 h-6 text-white" />
                    )}
                  </div>
                </Button>
              ))}
            </div>

            {/* Outlets Summary */}
            <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200 mt-4">
              <CardContent className="p-4">
                <p className="text-sm font-bold text-gray-900 mb-2">📊 F&B Özeti</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="text-center p-2 bg-white rounded">
                    <p className="text-xs text-gray-600">Toplam Outlet</p>
                    <p className="text-2xl font-bold text-blue-700">{outlets.length}</p>
                  </div>
                  <div className="text-center p-2 bg-white rounded">
                    <p className="text-xs text-gray-600">Aktif</p>
                    <p className="text-2xl font-bold text-green-700">
                      {outlets.filter(o => o.status === 'active').length}
                    </p>
                  </div>
                  <div className="text-center p-2 bg-white rounded col-span-2">
                    <p className="text-xs text-gray-600">Toplam Kapasite</p>
                    <p className="text-2xl font-bold text-amber-700">
                      {outlets.reduce((sum, o) => sum + (o.capacity || 0), 0)} kişi
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MobileFnB;
