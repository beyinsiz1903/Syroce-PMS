import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import PropertySwitcher from '@/components/PropertySwitcher';
import {
  ArrowLeft, 
  Clock, 
  AlertTriangle,
  CheckCircle,
  ChefHat,
  UtensilsCrossed,
  Filter,
  RefreshCw,
  Eye,
  TrendingUp,
  Calendar,
  User,
  Store
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MobileOrderTracking = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeOrders, setActiveOrders] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [filterModalOpen, setFilterModalOpen] = useState(false);
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  
  // Filters
  const [statusFilter, setStatusFilter] = useState('all');
  const [outletFilter, setOutletFilter] = useState('all');
  const [orderHistory, setOrderHistory] = useState([]);

  useEffect(() => {
    loadActiveOrders();
  }, [statusFilter, outletFilter]);

  const loadActiveOrders = async () => {
    try {
      setLoading(true);
      
      const params = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      if (outletFilter !== 'all') params.outlet_id = outletFilter;
      
      const response = await axios.get('/pos/mobile/active-orders', { params });
      setActiveOrders(response.data.orders || []);
    } catch (error) {
      console.error('Failed to load orders:', error);
      toast.error('Siparişler yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadOrderDetails = async (orderId) => {
    try {
      const response = await axios.get(`/pos/mobile/order/${orderId}`);
      setSelectedOrder(response.data);
      setDetailModalOpen(true);
    } catch (error) {
      console.error('Failed to load order details:', error);
      toast.error('Sipariş detayları yüklenemedi');
    }
  };

  const updateOrderStatus = async (orderId, newStatus) => {
    try {
      await axios.put(`/pos/mobile/order/${orderId}/status`, {
        status: newStatus,
        notes: `Status updated to ${newStatus}`
      });
      
      toast.success(`Sipariş durumu: ${getStatusLabel(newStatus)}`);
      loadActiveOrders();
      
      // Reload details if modal is open
      if (detailModalOpen && selectedOrder?.id === orderId) {
        loadOrderDetails(orderId);
      }
    } catch (error) {
      console.error('Failed to update status:', error);
      toast.error('Durum güncellenemedi');
    }
  };

  const loadOrderHistory = async () => {
    try {
      const today = new Date();
      const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
      
      const response = await axios.get('/pos/mobile/order-history', {
        params: {
          start_date: weekAgo.toISOString().split('T')[0],
          end_date: today.toISOString().split('T')[0],
          limit: 50
        }
      });
      
      setOrderHistory(response.data.orders || []);
      setHistoryModalOpen(true);
    } catch (error) {
      console.error('Failed to load order history:', error);
      toast.error('Sipariş geçmişi yüklenemedi');
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadActiveOrders();
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      pending: { label: 'Bekliyor', color: 'bg-yellow-500', icon: Clock },
      preparing: { label: 'Hazırlanıyor', color: 'bg-blue-500', icon: ChefHat },
      ready: { label: 'Hazır', color: 'bg-green-500', icon: CheckCircle },
      served: { label: 'Servis Edildi', color: 'bg-gray-500', icon: UtensilsCrossed }
    };
    
    const config = statusConfig[status] || statusConfig.pending;
    const Icon = config.icon;
    
    return (
      <Badge className={`${config.color} text-white flex items-center gap-1`}>
        <Icon className="h-3 w-3" />
        {config.label}
      </Badge>
    );
  };

  const getStatusLabel = (status) => {
    const labels = {
      pending: 'Bekliyor',
      preparing: 'Hazırlanıyor',
      ready: 'Hazır',
      served: 'Servis Edildi'
    };
    return labels[status] || status;
  };

  const getNextStatus = (currentStatus) => {
    const statusFlow = {
      pending: 'preparing',
      preparing: 'ready',
      ready: 'served'
    };
    return statusFlow[currentStatus];
  };

  const getNextStatusLabel = (currentStatus) => {
    const nextStatus = getNextStatus(currentStatus);
    return nextStatus ? getStatusLabel(nextStatus) : null;
  };

  const canUpdateStatus = (order) => {
    // Kitchen staff can move from pending to preparing to ready
    // Service staff can move from ready to served
    const userRole = user?.role || '';
    
    if (userRole === 'kitchen_staff' || userRole === 'fnb_supervisor' || userRole === 'fnb_manager' || userRole === 'admin') {
      return ['pending', 'preparing', 'ready'].includes(order.status);
    }
    
    if (userRole === 'service' || userRole === 'fnb_supervisor' || userRole === 'fnb_manager' || userRole === 'admin') {
      return order.status === 'ready';
    }
    
    return false;
  };

  // Stats
  const stats = {
    total: activeOrders.length,
    pending: activeOrders.filter(o => o.status === 'pending').length,
    preparing: activeOrders.filter(o => o.status === 'preparing').length,
    ready: activeOrders.filter(o => o.status === 'ready').length,
    delayed: activeOrders.filter(o => o.is_delayed).length
  };

  if (loading && !refreshing) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-orange-50 to-red-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="h-12 w-12 animate-spin text-orange-600 mx-auto mb-4" />
          <p className="text-gray-600">Siparişler yükleniyor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-red-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-orange-600 to-red-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg transition">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold">Sipariş Takibi</h1>
              <p className="text-orange-100 text-sm">F&B Mobil</p>
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
              onClick={() => setFilterModalOpen(true)}
              className="p-2 hover:bg-white/20 rounded-lg transition"
            >
              <Filter className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-4 gap-2">
          <div className="bg-white/20 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.total}</div>
            <div className="text-xs">Toplam</div>
          </div>
          <div className="bg-yellow-500/80 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.pending}</div>
            <div className="text-xs">Bekliyor</div>
          </div>
          <div className="bg-blue-500/80 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.preparing}</div>
            <div className="text-xs">Hazırlanıyor</div>
          </div>
          <div className="bg-green-500/80 rounded-lg p-2 text-center">
            <div className="text-2xl font-bold">{stats.ready}</div>
            <div className="text-xs">Hazır</div>
          </div>
        </div>
      </div>

      {/* Delayed Orders Alert */}
      {stats.delayed > 0 && (
        <div className="mx-4 mt-4">
          <div className="bg-red-500 text-white p-3 rounded-lg flex items-center gap-2 animate-pulse">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-semibold">{stats.delayed} geciken sipariş!</span>
          </div>
        </div>
      )}

      {/* Orders List */}
      <div className="p-4 space-y-3">
        {activeOrders.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-center">
              <UtensilsCrossed className="h-16 w-16 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">Aktif sipariş bulunmuyor</p>
              <Button 
                onClick={loadOrderHistory}
                variant="outline" 
                className="mt-4"
              >
                <Calendar className="h-4 w-4 mr-2" />
                Geçmiş Siparişler
              </Button>
            </CardContent>
          </Card>
        ) : (
          activeOrders.map((order) => (
            <Card 
              key={order.id} 
              className={`${order.is_delayed ? 'border-2 border-red-400 shadow-lg' : ''} hover:shadow-xl transition cursor-pointer`}
              onClick={() => loadOrderDetails(order.id)}
            >
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-bold text-lg">#{order.order_number}</span>
                      {order.is_delayed && (
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                      )}
                    </div>
                    <div className="text-sm text-gray-500 space-y-1">
                      <div className="flex items-center gap-1">
                        <Store className="h-3 w-3" />
                        {order.outlet_name}
                      </div>
                      <div className="flex items-center gap-1">
                        <User className="h-3 w-3" />
                        {order.guest_name}
                      </div>
                    </div>
                  </div>
                  {getStatusBadge(order.status)}
                </div>

                <div className="flex justify-between items-center text-sm">
                  <div>
                    <span className="text-gray-600">Masa: </span>
                    <span className="font-semibold">{order.table_number}</span>
                    <span className="mx-2">•</span>
                    <span className="text-gray-600">{order.items_count} ürün</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className={`h-4 w-4 ${order.is_delayed ? 'text-red-500' : 'text-gray-500'}`} />
                    <span className={`font-semibold ${order.is_delayed ? 'text-red-500' : ''}`}>
                      {order.time_elapsed_minutes} dk
                    </span>
                  </div>
                </div>

                <div className="flex justify-between items-center mt-3 pt-3 border-t">
                  <div className="text-lg font-bold text-orange-600">
                    ₺{order.total_amount.toFixed(2)}
                  </div>
                  
                  {canUpdateStatus(order) && getNextStatus(order.status) && (
                    <Button
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        updateOrderStatus(order.id, getNextStatus(order.status));
                      }}
                      className="bg-orange-600 hover:bg-orange-700"
                    >
                      {getNextStatusLabel(order.status)}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Order Detail Modal */}
      <Dialog open={detailModalOpen} onOpenChange={setDetailModalOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Sipariş Detayı</DialogTitle>
          </DialogHeader>
          
          {selectedOrder && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <div>
                  <div className="text-2xl font-bold">#{selectedOrder.order_number}</div>
                  <div className="text-sm text-gray-500">{selectedOrder.outlet_name}</div>
                </div>
                {getStatusBadge(selectedOrder.status)}
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-gray-500">Masa</div>
                  <div className="font-semibold">{selectedOrder.table_number}</div>
                </div>
                <div>
                  <div className="text-gray-500">Misafir</div>
                  <div className="font-semibold">{selectedOrder.guest_name}</div>
                </div>
                <div>
                  <div className="text-gray-500">Süre</div>
                  <div className="font-semibold">{selectedOrder.time_elapsed_minutes} dakika</div>
                </div>
                <div>
                  <div className="text-gray-500">Garson</div>
                  <div className="font-semibold">{selectedOrder.server_name || 'N/A'}</div>
                </div>
              </div>

              {/* Order Items */}
              <div>
                <h3 className="font-semibold mb-2">Sipariş Kalemleri</h3>
                <div className="space-y-2">
                  {selectedOrder.order_items?.map((item, idx) => (
                    <div key={idx} className="flex justify-between items-center bg-gray-50 p-2 rounded">
                      <div>
                        <div className="font-medium">{item.item_name}</div>
                        <div className="text-sm text-gray-500">
                          {item.quantity} x ₺{item.unit_price.toFixed(2)}
                        </div>
                        {item.special_instructions && (
                          <div className="text-xs text-orange-600 mt-1">
                            Not: {item.special_instructions}
                          </div>
                        )}
                      </div>
                      <div className="font-semibold">₺{item.total_price.toFixed(2)}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Notes */}
              {selectedOrder.notes && (
                <div className="bg-yellow-50 p-3 rounded">
                  <div className="font-semibold text-sm mb-1">Notlar</div>
                  <div className="text-sm">{selectedOrder.notes}</div>
                </div>
              )}

              {/* Totals */}
              <div className="space-y-1 border-t pt-2">
                <div className="flex justify-between text-sm">
                  <span>Ara Toplam</span>
                  <span>₺{selectedOrder.subtotal?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span>KDV</span>
                  <span>₺{selectedOrder.tax_amount?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between font-bold text-lg">
                  <span>Toplam</span>
                  <span className="text-orange-600">₺{selectedOrder.total_amount.toFixed(2)}</span>
                </div>
              </div>

              {/* Status Update Buttons */}
              {canUpdateStatus(selectedOrder) && getNextStatus(selectedOrder.status) && (
                <Button
                  className="w-full bg-orange-600 hover:bg-orange-700"
                  onClick={() => {
                    updateOrderStatus(selectedOrder.id, getNextStatus(selectedOrder.status));
                  }}
                >
                  {getNextStatusLabel(selectedOrder.status)}
                </Button>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Filter Modal */}
      <Dialog open={filterModalOpen} onOpenChange={setFilterModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("common.filter")}</DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Durum</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full p-2 border rounded"
              >
                <option value="all">{t("common.all")}</option>
                <option value="pending">Bekliyor</option>
                <option value="preparing">Hazırlanıyor</option>
                <option value="ready">Hazır</option>
              </select>
            </div>

            <div className="flex gap-2">
              <Button
                onClick={() => {
                  setStatusFilter('all');
                  setOutletFilter('all');
                }}
                variant="outline"
                className="flex-1"
              >
                Sıfırla
              </Button>
              <Button
                onClick={() => {
                  setFilterModalOpen(false);
                  loadActiveOrders();
                }}
                className="flex-1 bg-orange-600 hover:bg-orange-700"
              >
                Uygula
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Order History Modal */}
      <Dialog open={historyModalOpen} onOpenChange={setHistoryModalOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Sipariş Geçmişi (Son 7 Gün)</DialogTitle>
          </DialogHeader>
          
          <div className="space-y-2">
            {orderHistory.map((order) => (
              <div key={order.id} className="bg-gray-50 p-3 rounded space-y-2">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-semibold">#{order.order_number}</div>
                    <div className="text-sm text-gray-500">{order.guest_name}</div>
                  </div>
                  {getStatusBadge(order.status)}
                </div>
                <div className="flex justify-between text-sm">
                  <span>{order.items_count} ürün</span>
                  <span className="font-semibold">₺{order.total_amount.toFixed(2)}</span>
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Quick Access Button */}
      <div className="fixed bottom-4 right-4">
        <Button
          onClick={loadOrderHistory}
          className="rounded-full w-14 h-14 shadow-lg bg-orange-600 hover:bg-orange-700"
        >
          <TrendingUp className="h-6 w-6" />
        </Button>
      </div>

      {/* Property Switcher */}
      <PropertySwitcher onPropertyChange={() => loadActiveOrders()} />
    </div>
  );
};

export default MobileOrderTracking;
