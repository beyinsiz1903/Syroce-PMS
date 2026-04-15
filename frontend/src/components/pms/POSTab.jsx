import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  UtensilsCrossed, RefreshCw, ShoppingCart, CreditCard, TrendingUp, Clock
} from 'lucide-react';

const fmt = (v) => (v || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const STATUS_MAP = {
  completed: { label: 'Tamamlandı', color: 'bg-green-100 text-green-700' },
  pending: { label: 'Bekliyor', color: 'bg-yellow-100 text-yellow-700' },
  cancelled: { label: 'İptal', color: 'bg-red-100 text-red-700' },
  in_progress: { label: 'Hazırlanıyor', color: 'bg-blue-100 text-blue-700' },
};

const POSTab = () => {
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState({ total_sales: 0, transaction_count: 0, average_transaction: 0 });
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [ordersRes, summaryRes] = await Promise.allSettled([
        axios.get('/pos/orders'),
        axios.get('/pos/daily-summary'),
      ]);
      if (ordersRes.status === 'fulfilled') {
        setOrders(ordersRes.value.data?.orders || ordersRes.value.data || []);
      }
      if (summaryRes.status === 'fulfilled') {
        setSummary(summaryRes.value.data || {});
      }
      const anyOk = ordersRes.status === 'fulfilled' || summaryRes.status === 'fulfilled';
      if (anyOk) toast.success('POS verileri yenilendi');
      else toast.error('POS verileri yüklenemedi');
    } catch {
      toast.error('POS verileri yüklenemedi');
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <UtensilsCrossed className="w-6 h-6" /> POS Entegrasyonu
          </h2>
          <p className="text-sm text-gray-600">Satış noktası sipariş ve gelir takibi</p>
        </div>
        <Button variant="outline" onClick={loadData} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Yenile
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-emerald-50 border-emerald-200">
          <CardContent className="p-5 text-center">
            <CreditCard className="w-6 h-6 mx-auto mb-1 text-emerald-600" />
            <p className="text-xs text-emerald-600">Toplam Satış</p>
            <p className="text-2xl font-bold text-emerald-700">{fmt(summary.total_sales)} ₺</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-5 text-center">
            <ShoppingCart className="w-6 h-6 mx-auto mb-1 text-blue-600" />
            <p className="text-xs text-blue-600">İşlem Sayısı</p>
            <p className="text-2xl font-bold text-blue-700">{summary.transaction_count || 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-purple-50 border-purple-200">
          <CardContent className="p-5 text-center">
            <TrendingUp className="w-6 h-6 mx-auto mb-1 text-purple-600" />
            <p className="text-xs text-purple-600">Ortalama İşlem</p>
            <p className="text-2xl font-bold text-purple-700">{fmt(summary.average_transaction)} ₺</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Clock className="w-5 h-5" /> Son Siparişler
          </CardTitle>
          <CardDescription>Günün POS işlemleri</CardDescription>
        </CardHeader>
        <CardContent>
          {orders.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <UtensilsCrossed className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p className="font-medium">Henüz sipariş yok</p>
              <p className="text-sm mt-1">POS siparişleri burada görünecek</p>
            </div>
          ) : (
            <div className="space-y-3">
              {orders.slice(0, 20).map((order) => {
                const st = STATUS_MAP[order.status] || STATUS_MAP.pending;
                return (
                  <div key={order.id} className="flex justify-between items-center p-3 border rounded-lg hover:shadow-sm transition">
                    <div>
                      <div className="font-semibold">Sipariş #{order.order_number || order.id}</div>
                      <div className="text-sm text-gray-600">
                        {order.outlet || 'Restoran'} {order.room_number ? `• Oda ${order.room_number}` : ''}
                      </div>
                      <div className="text-xs text-gray-400">
                        {order.created_at ? new Date(order.created_at).toLocaleString('tr-TR') : ''}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold">{fmt(order.total || order.total_amount)} ₺</div>
                      <Badge className={st.color}>{st.label}</Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default POSTab;
