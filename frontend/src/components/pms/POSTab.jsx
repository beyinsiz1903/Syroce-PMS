import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  UtensilsCrossed, RefreshCw, ShoppingCart, CreditCard, TrendingUp, Clock
} from 'lucide-react';

const fmt = (v, lang) => (v || 0).toLocaleString(lang === 'tr' ? 'tr-TR' : lang === 'de' ? 'de-DE' : lang === 'fr' ? 'fr-FR' : lang === 'es' ? 'es-ES' : lang === 'it' ? 'it-IT' : lang === 'pt' ? 'pt-BR' : lang === 'ru' ? 'ru-RU' : lang === 'ar' ? 'ar-SA' : lang === 'zh' ? 'zh-CN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const POSTab = () => {
  const { t, i18n } = useTranslation();
  const tc = (k) => t(`pmsComponents.pos.${k}`);
  const cur = t('pmsComponents.common.currency');

  const STATUS_MAP = {
    completed: { label: t('pmsComponents.housekeeping.completed'), color: 'bg-green-100 text-green-700' },
    pending: { label: t('pmsComponents.housekeeping.waiting'), color: 'bg-yellow-100 text-yellow-700' },
    cancelled: { label: t('pmsComponents.common.cancel'), color: 'bg-red-100 text-red-700' },
    in_progress: { label: t('pmsComponents.housekeeping.ongoing'), color: 'bg-blue-100 text-blue-700' },
  };

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
      if (anyOk) toast.success(tc('dataRefreshed'));
      else toast.error(tc('dataLoadFailed'));
    } catch {
      toast.error(tc('dataLoadFailed'));
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <UtensilsCrossed className="w-6 h-6" /> {tc('title')}
          </h2>
          <p className="text-sm text-gray-600">{tc('subtitle')}</p>
        </div>
        <Button variant="outline" onClick={loadData} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          {tc('refresh')}
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-emerald-50 border-emerald-200">
          <CardContent className="p-5 text-center">
            <CreditCard className="w-6 h-6 mx-auto mb-1 text-emerald-600" />
            <p className="text-xs text-emerald-600">{tc('totalSales')}</p>
            <p className="text-2xl font-bold text-emerald-700">{fmt(summary.total_sales, i18n.language)} {cur}</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-5 text-center">
            <ShoppingCart className="w-6 h-6 mx-auto mb-1 text-blue-600" />
            <p className="text-xs text-blue-600">{tc('transactionCount')}</p>
            <p className="text-2xl font-bold text-blue-700">{summary.transaction_count || 0}</p>
          </CardContent>
        </Card>
        <Card className="bg-purple-50 border-purple-200">
          <CardContent className="p-5 text-center">
            <TrendingUp className="w-6 h-6 mx-auto mb-1 text-purple-600" />
            <p className="text-xs text-purple-600">{tc('avgTransaction')}</p>
            <p className="text-2xl font-bold text-purple-700">{fmt(summary.average_transaction, i18n.language)} {cur}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Clock className="w-5 h-5" /> {tc('recentOrders')}
          </CardTitle>
          <CardDescription>{tc('dailyTransactions')}</CardDescription>
        </CardHeader>
        <CardContent>
          {orders.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <UtensilsCrossed className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p className="font-medium">{tc('noOrders')}</p>
              <p className="text-sm mt-1">{tc('ordersWillAppear')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {orders.slice(0, 20).map((order) => {
                const st = STATUS_MAP[order.status] || STATUS_MAP.pending;
                return (
                  <div key={order.id} className="flex justify-between items-center p-3 border rounded-lg hover:shadow-sm transition">
                    <div>
                      <div className="font-semibold">{tc('orderNo')} #{order.order_number || order.id}</div>
                      <div className="text-sm text-gray-600">
                        {order.outlet || t('pmsComponents.concierge.restaurant')} {order.room_number ? `• ${t('pmsComponents.common.room')} ${order.room_number}` : ''}
                      </div>
                      <div className="text-xs text-gray-400">
                        {order.created_at ? new Date(order.created_at).toLocaleString(i18n.language) : ''}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold">{fmt(order.total || order.total_amount, i18n.language)} {cur}</div>
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
