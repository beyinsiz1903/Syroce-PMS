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
import PropertySwitcher from '@/components/PropertySwitcher';
import {
  ArrowLeft, 
  Package,
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  Filter,
  RefreshCw,
  History,
  Edit,
  CheckCircle,
  XCircle,
  BarChart3,
  Plus,
  Minus,
  Activity
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MobileInventory = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [stockItems, setStockItems] = useState([]);
  const [lowStockAlerts, setLowStockAlerts] = useState([]);
  const [movements, setMovements] = useState([]);
  
  // Modals
  const [alertsModalOpen, setAlertsModalOpen] = useState(false);
  const [movementsModalOpen, setMovementsModalOpen] = useState(false);
  const [adjustModalOpen, setAdjustModalOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState(null);
  
  // Filters
  const [showLowStockOnly, setShowLowStockOnly] = useState(false);
  
  // Adjust form
  const [adjustType, setAdjustType] = useState('in');
  const [adjustQuantity, setAdjustQuantity] = useState('');
  const [adjustReason, setAdjustReason] = useState('');
  const [adjustNotes, setAdjustNotes] = useState('');

  useEffect(() => {
    loadData();
  }, [showLowStockOnly]);

  const loadData = async () => {
    try {
      setLoading(true);
      
      const [stockRes, alertsRes] = await Promise.all([
        axios.get('/pos/mobile/stock-levels', {
          params: { low_stock_only: showLowStockOnly }
        }),
        axios.get('/pos/mobile/low-stock-alerts')
      ]);
      
      setStockItems(stockRes.data.stock_items || []);
      setLowStockAlerts(alertsRes.data.alerts || []);
    } catch (error) {
      console.error('Failed to load inventory data:', error);
      toast.error(t('mobileInventory.errors.loadFailed'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadMovements = async () => {
    try {
      const today = new Date();
      const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
      
      const response = await axios.get('/pos/mobile/inventory-movements', {
        params: {
          start_date: weekAgo.toISOString().split('T')[0],
          end_date: today.toISOString().split('T')[0],
          limit: 100
        }
      });
      
      setMovements(response.data.movements || []);
      setMovementsModalOpen(true);
    } catch (error) {
      console.error('Failed to load movements:', error);
      toast.error(t('mobileInventory.errors.movementsFailed'));
    }
  };

  const handleAdjustStock = async () => {
    if (!selectedItem || !adjustQuantity || !adjustReason) {
      toast.error(t('mobileInventory.errors.fillAllFields'));
      return;
    }

    try {
      await axios.post('/pos/mobile/stock-adjust', {
        product_id: selectedItem.product_id || selectedItem.id,
        adjustment_type: adjustType,
        quantity: parseInt(adjustQuantity),
        reason: adjustReason,
        notes: adjustNotes
      });
      
      toast.success(t('mobileInventory.success.adjusted'));
      setAdjustModalOpen(false);
      resetAdjustForm();
      loadData();
    } catch (error) {
      console.error('Failed to adjust stock:', error);
      const errorMsg = error.response?.data?.detail || t('mobileInventory.errors.updateFailed');
      toast.error(errorMsg);
    }
  };

  const resetAdjustForm = () => {
    setSelectedItem(null);
    setAdjustType('in');
    setAdjustQuantity('');
    setAdjustReason('');
    setAdjustNotes('');
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const openAdjustModal = (item) => {
    setSelectedItem(item);
    setAdjustModalOpen(true);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'good':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'medium':
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case 'low':
        return <TrendingDown className="h-5 w-5 text-amber-500" />;
      case 'out_of_stock':
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Package className="h-5 w-5 text-gray-500" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'good':
        return 'border-green-200 bg-green-50';
      case 'medium':
        return 'border-yellow-200 bg-yellow-50';
      case 'low':
        return 'border-amber-200 bg-amber-50';
      case 'out_of_stock':
        return 'border-red-200 bg-red-50';
      default:
        return 'border-gray-200 bg-gray-50';
    }
  };

  const getMovementIcon = (type) => {
    switch (type) {
      case 'in':
        return <TrendingUp className="h-4 w-4 text-green-500" />;
      case 'out':
        return <TrendingDown className="h-4 w-4 text-red-500" />;
      default:
        return <Activity className="h-4 w-4 text-blue-500" />;
    }
  };

  const canAdjustStock = () => {
    const allowedRoles = ['admin', 'warehouse', 'fnb_manager', 'supervisor'];
    if (user?.role === 'super_admin') return true;
    if (Array.isArray(user?.roles) && user.roles.includes('super_admin')) return true;
    if (allowedRoles.includes(user?.role)) return true;
    if (Array.isArray(user?.roles) && user.roles.some((r) => allowedRoles.includes(r))) return true;
    return false;
  };

  // Stats
  const stats = {
    total: stockItems.length,
    good: stockItems.filter(i => i.stock_status === 'good').length,
    low: stockItems.filter(i => i.is_low_stock).length,
    outOfStock: stockItems.filter(i => i.stock_status === 'out_of_stock').length
  };

  if (loading && !refreshing) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="h-12 w-12 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">{t('mobileInventory.loading')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg transition">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold">{t('mobileInventory.title')}</h1>
              <p className="text-blue-100 text-sm">{t('mobileInventory.subtitle')}</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              className="p-2 hover:bg-white/20 rounded-lg transition"
              disabled={refreshing}
            >
              <RefreshCw className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={loadMovements}
              className="p-2 hover:bg-white/20 rounded-lg transition"
            >
              <History className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-4 gap-2">
          <div className="bg-white/20 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.total}</div>
            <div className="text-xs">{t('mobileInventory.stats.total')}</div>
          </div>
          <div className="bg-green-500/80 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.good}</div>
            <div className="text-xs">{t('mobileInventory.stats.good')}</div>
          </div>
          <div className="bg-amber-500/80 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.low}</div>
            <div className="text-xs">{t('mobileInventory.stats.low')}</div>
          </div>
          <div className="bg-red-500/80 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.outOfStock}</div>
            <div className="text-xs">{t('mobileInventory.stats.outOfStock')}</div>
          </div>
        </div>
      </div>

      {/* Low Stock Alerts Banner */}
      {lowStockAlerts.length > 0 && (
        <div className="mx-4 mt-4">
          <button
            onClick={() => setAlertsModalOpen(true)}
            className="w-full bg-gradient-to-r from-amber-500 to-red-500 text-white p-3 rounded-lg flex items-center justify-between shadow-lg hover:shadow-xl transition"
          >
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 animate-pulse" />
              <span className="font-semibold">{t('mobileInventory.alertsBanner', { count: lowStockAlerts.length })}</span>
            </div>
            <span className="text-sm">{t('mobileInventory.details')} →</span>
          </button>
        </div>
      )}

      {/* Filter Toggle */}
      <div className="mx-4 mt-4 flex items-center justify-between">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showLowStockOnly}
            onChange={(e) => setShowLowStockOnly(e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-sm font-medium">{t('mobileInventory.showLowOnly')}</span>
        </label>
      </div>

      {/* Stock Items List */}
      <div className="p-4 space-y-3">
        {stockItems.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-center">
              <Package className="h-16 w-16 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">{t('mobileInventory.empty')}</p>
            </CardContent>
          </Card>
        ) : (
          stockItems.map((item) => (
            <Card 
              key={item.id || item.product_id} 
              className={`border-2 ${getStatusColor(item.stock_status)} hover:shadow-xl transition`}
            >
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-3">
                  <div className="flex items-start gap-3 flex-1">
                    {getStatusIcon(item.stock_status)}
                    <div className="flex-1">
                      <div className="font-bold text-lg">{item.product_name}</div>
                      <Badge variant="outline" className="text-xs mt-1">
                        {item.category}
                      </Badge>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 mb-3">
                  <div>
                    <div className="text-sm text-gray-500">{t('mobileInventory.current')}</div>
                    <div className="text-2xl font-bold text-blue-600">
                      {item.current_quantity}
                      <span className="text-sm text-gray-500 ml-1">{item.unit_of_measure}</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-500">{t('mobileInventory.minimum')}</div>
                    <div className="text-2xl font-bold text-gray-400">
                      {item.minimum_quantity}
                      <span className="text-sm text-gray-500 ml-1">{item.unit_of_measure}</span>
                    </div>
                  </div>
                </div>

                {/* Low Stock Warning */}
                {item.is_low_stock && (
                  <div className="bg-amber-100 border border-amber-200 rounded p-2 mb-3">
                    <div className="flex items-center gap-2 text-amber-700 text-sm">
                      <AlertTriangle className="h-4 w-4" />
                      <span className="font-semibold">{t('mobileInventory.lowStockWarning')}</span>
                    </div>
                  </div>
                )}

                {/* Adjust Stock Button (only for authorized roles) */}
                {canAdjustStock() && (
                  <Button
                    size="sm"
                    onClick={() => openAdjustModal(item)}
                    className="w-full bg-blue-600 hover:bg-blue-700"
                  >
                    <Edit className="h-4 w-4 mr-2" />
                    {t('mobileInventory.adjust')}
                  </Button>
                )}
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Low Stock Alerts Modal */}
      <Dialog open={alertsModalOpen} onOpenChange={setAlertsModalOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              {t('mobileInventory.alertsModal.title')}
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-2">
            {lowStockAlerts.map((alert) => (
              <div 
                key={alert.id} 
                className={`p-3 rounded border-l-4 ${
                  alert.urgency === 'critical' 
                    ? 'bg-red-50 border-red-500' 
                    : alert.urgency === 'high'
                    ? 'bg-amber-50 border-amber-500'
                    : 'bg-yellow-50 border-yellow-500'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="font-semibold">{alert.product_name}</div>
                  <Badge variant={alert.urgency === 'critical' ? 'destructive' : 'default'}>
                    {alert.urgency === 'critical'
                      ? t('mobileInventory.alertsModal.urgency.critical')
                      : alert.urgency === 'high'
                      ? t('mobileInventory.alertsModal.urgency.high')
                      : t('mobileInventory.alertsModal.urgency.medium')}
                  </Badge>
                </div>
                <div className="text-sm space-y-1">
                  <div>{alert.alert_message}</div>
                  <div className="text-gray-600">
                    {t('mobileInventory.alertsModal.shortage')}: {alert.shortage} {alert.unit_of_measure}
                  </div>
                  <div className="text-blue-600 font-semibold">
                    {t('mobileInventory.alertsModal.recommendedOrder')}: {alert.recommended_order} {alert.unit_of_measure}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Movements History Modal */}
      <Dialog open={movementsModalOpen} onOpenChange={setMovementsModalOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="h-5 w-5" />
              {t('mobileInventory.movementsModal.title')}
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-2">
            {movements.map((movement) => (
              <div key={movement.id} className="bg-gray-50 p-3 rounded space-y-2">
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-2">
                    {getMovementIcon(movement.movement_type)}
                    <div>
                      <div className="font-semibold">{movement.product_name}</div>
                      <div className="text-xs text-gray-500">{movement.reason}</div>
                    </div>
                  </div>
                  <div className={`font-bold ${movement.quantity > 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {movement.quantity > 0 ? '+' : ''}{movement.quantity}
                  </div>
                </div>
                {movement.notes && (
                  <div className="text-xs text-gray-600">{movement.notes}</div>
                )}
                <div className="text-xs text-gray-400">
                  {new Date(movement.timestamp).toLocaleString('tr-TR')}
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Adjust Stock Modal */}
      <Dialog open={adjustModalOpen} onOpenChange={(open) => {
        setAdjustModalOpen(open);
        if (!open) resetAdjustForm();
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('mobileInventory.adjustModal.title')}</DialogTitle>
          </DialogHeader>
          
          {selectedItem && (
            <div className="space-y-4">
              <div className="bg-blue-50 p-3 rounded">
                <div className="font-semibold">{selectedItem.product_name}</div>
                <div className="text-sm text-gray-600">
                  {t('mobileInventory.adjustModal.currentLabel')}: {selectedItem.current_quantity} {selectedItem.unit_of_measure}
                </div>
              </div>

              <div>
                <Label>{t('mobileInventory.adjustModal.type')}</Label>
                <select
                  value={adjustType}
                  onChange={(e) => setAdjustType(e.target.value)}
                  className="w-full p-2 border rounded mt-1"
                >
                  <option value="in">{t('mobileInventory.adjustModal.typeIn')}</option>
                  <option value="out">{t('mobileInventory.adjustModal.typeOut')}</option>
                  <option value="adjustment">{t('mobileInventory.adjustModal.typeAdjustment')}</option>
                </select>
              </div>

              <div>
                <Label>{t('mobileInventory.adjustModal.quantity')}</Label>
                <Input
                  type="number"
                  value={adjustQuantity}
                  onChange={(e) => setAdjustQuantity(e.target.value)}
                  placeholder={t('mobileInventory.adjustModal.quantityPlaceholder')}
                  min="1"
                />
              </div>

              <div>
                <Label>{t('mobileInventory.adjustModal.reason')}</Label>
                <select
                  value={adjustReason}
                  onChange={(e) => setAdjustReason(e.target.value)}
                  className="w-full p-2 border rounded mt-1"
                >
                  <option value="">{t('mobileInventory.adjustModal.reasonSelect')}</option>
                  <option value="Tedarikçi teslimatı">{t('mobileInventory.adjustModal.reasons.supplier')}</option>
                  <option value="F&B satışı">{t('mobileInventory.adjustModal.reasons.fbSale')}</option>
                  <option value="Fire">{t('mobileInventory.adjustModal.reasons.waste')}</option>
                  <option value="İade">{t('mobileInventory.adjustModal.reasons.return')}</option>
                  <option value="Sayım düzeltmesi">{t('mobileInventory.adjustModal.reasons.count')}</option>
                  <option value="Diğer">{t('mobileInventory.adjustModal.reasons.other')}</option>
                </select>
              </div>

              <div>
                <Label>{t('mobileInventory.adjustModal.notes')}</Label>
                <Textarea
                  value={adjustNotes}
                  onChange={(e) => setAdjustNotes(e.target.value)}
                  placeholder={t('mobileInventory.adjustModal.notesPlaceholder')}
                  rows={3}
                />
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setAdjustModalOpen(false);
                    resetAdjustForm();
                  }}
                  className="flex-1"
                >
                  {t('mobileInventory.adjustModal.cancel')}
                </Button>
                <Button
                  onClick={handleAdjustStock}
                  className="flex-1 bg-blue-600 hover:bg-blue-700"
                >
                  {t('mobileInventory.adjustModal.save')}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Quick Access Buttons */}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2">
        <Button
          onClick={() => setAlertsModalOpen(true)}
          className="rounded-full w-14 h-14 shadow-lg bg-amber-600 hover:bg-amber-700 relative"
        >
          <AlertTriangle className="h-6 w-6" />
          {lowStockAlerts.length > 0 && (
            <Badge className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full h-6 w-6 flex items-center justify-center p-0">
              {lowStockAlerts.length}
            </Badge>
          )}
        </Button>
        <Button
          onClick={loadMovements}
          className="rounded-full w-14 h-14 shadow-lg bg-blue-600 hover:bg-blue-700"
        >
          <History className="h-6 w-6" />
        </Button>
      </div>

      {/* Property Switcher */}
      <PropertySwitcher onPropertyChange={() => loadData()} />
    </div>
  );
};

export default MobileInventory;
