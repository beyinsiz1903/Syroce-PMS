import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { KpiCard } from '@/components/ui/kpi-card';
import {
  UtensilsCrossed, RefreshCw, ShoppingCart, CreditCard, TrendingUp, Clock,
  Plus, Monitor, AlertCircle, ExternalLink,
} from 'lucide-react';

const fmt = (v, lang) => (v || 0).toLocaleString(
  lang === 'tr' ? 'tr-TR' : lang === 'de' ? 'de-DE' : lang === 'fr' ? 'fr-FR' : lang === 'es' ? 'es-ES' : lang === 'it' ? 'it-IT' : lang === 'pt' ? 'pt-BR' : lang === 'ru' ? 'ru-RU' : lang === 'ar' ? 'ar-SA' : lang === 'zh' ? 'zh-CN' : 'en-US',
  { minimumFractionDigits: 2, maximumFractionDigits: 2 },
);

const todayIso = () => new Date().toISOString().slice(0, 10);

const POSTab = () => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const tc = (k) => t(`pmsComponents.pos.${k}`);
  const cur = t('pmsComponents.common.currency');

  const STATUS_MAP = {
    completed: { label: t('pmsComponents.housekeeping.completed'), color: 'bg-green-100 text-green-700' },
    pending:   { label: t('pmsComponents.housekeeping.waiting'),   color: 'bg-yellow-100 text-yellow-700' },
    preparing: { label: tc('preparing'),                            color: 'bg-amber-100 text-amber-700' },
    ready:     { label: tc('ready'),                                color: 'bg-blue-100 text-blue-700' },
    served:    { label: tc('served'),                               color: 'bg-emerald-100 text-emerald-700' },
    cancelled: { label: t('pmsComponents.common.cancel'),           color: 'bg-red-100 text-red-700' },
    in_progress: { label: t('pmsComponents.housekeeping.ongoing'),  color: 'bg-blue-100 text-blue-700' },
  };

  const [orders, setOrders] = useState([]);
  const [activeOrders, setActiveOrders] = useState([]);
  const [delayedCount, setDelayedCount] = useState(0);
  const [summary, setSummary] = useState({ total_sales: 0, transaction_count: 0, average_transaction: 0 });
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    const today = todayIso();
    try {
      const [breakdownRes, historyRes, activeRes] = await Promise.allSettled([
        axios.get(`/pos/outlet-sales-breakdown?start_date=${today}&end_date=${today}`),
        axios.get(`/pos/mobile/order-history?start_date=${today}&end_date=${today}&limit=20`),
        axios.get('/pos/mobile/active-orders'),
      ]);

      // Daily summary'yi outlet breakdown'dan türet
      if (breakdownRes.status === 'fulfilled') {
        const data = breakdownRes.value.data || {};
        const outlets = data.outlets || {};
        const totalSales = data.total_sales || 0;
        const totalOrders = Object.values(outlets).reduce((acc, o) => acc + (o.orders || 0), 0);
        setSummary({
          total_sales: totalSales,
          transaction_count: totalOrders,
          average_transaction: totalOrders > 0 ? totalSales / totalOrders : 0,
        });
      }

      if (historyRes.status === 'fulfilled') {
        setOrders(historyRes.value.data?.orders || []);
      }

      if (activeRes.status === 'fulfilled') {
        const ad = activeRes.value.data || {};
        setActiveOrders(ad.orders || []);
        setDelayedCount(ad.delayed_count || 0);
      }

      const anyOk = [breakdownRes, historyRes, activeRes].some(r => r.status === 'fulfilled');
      if (!anyOk) toast.error(tc('dataLoadFailed'));
    } catch {
      toast.error(tc('dataLoadFailed'));
    }
    setLoading(false);
  }, [tc]);

  useEffect(() => { loadData(); }, [loadData, i18n.language]);

  const activeCount = activeOrders.length;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <UtensilsCrossed className="w-6 h-6" /> {tc('title')}
          </h2>
          <p className="text-sm text-gray-600">{tc('subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate('/kitchen-display')} data-testid="btn-pos-kitchen">
            <Monitor className="w-4 h-4 mr-1.5" /> {tc('kitchenDisplay')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate('/fnb-complete')} data-testid="btn-pos-fnb">
            <ExternalLink className="w-4 h-4 mr-1.5" /> {tc('openFnB')}
          </Button>
          <Button size="sm" onClick={() => navigate('/fnb-complete')} data-testid="btn-pos-new-order">
            <Plus className="w-4 h-4 mr-1.5" /> {tc('newOrder')}
          </Button>
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            {tc('refresh')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KpiCard
          icon={CreditCard}
          intent="success"
          label={tc('totalSales')}
          value={`${fmt(summary.total_sales, i18n.language)} ${cur}`}
          sub={tc('today')}
        />
        <KpiCard
          icon={ShoppingCart}
          intent="info"
          label={tc('transactionCount')}
          value={summary.transaction_count || 0}
          sub={tc('today')}
        />
        <KpiCard
          icon={TrendingUp}
          intent="default"
          label={tc('avgTransaction')}
          value={`${fmt(summary.average_transaction, i18n.language)} ${cur}`}
          sub={tc('perOrder')}
        />
        <KpiCard
          icon={Clock}
          intent={delayedCount > 0 ? 'danger' : (activeCount > 0 ? 'warning' : 'neutral')}
          label={tc('activeOrders')}
          value={activeCount}
          sub={delayedCount > 0 ? tc('delayedCount').replace('{n}', delayedCount) : tc('inProgress')}
          onClick={() => navigate('/kitchen-display')}
        />
      </div>

      {delayedCount > 0 && (
        <Card className="border-rose-200 bg-rose-50">
          <CardContent className="p-3 flex items-center gap-2 text-sm text-rose-700">
            <AlertCircle className="w-4 h-4" />
            <span>{tc('delayedWarning').replace('{n}', delayedCount)}</span>
            <Button variant="link" size="sm" className="ml-auto text-rose-700" onClick={() => navigate('/kitchen-display')}>
              {tc('viewKitchen')}
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Clock className="w-5 h-5" /> {tc('recentOrders')}
            {orders.length > 0 && <Badge variant="secondary">{orders.length}</Badge>}
          </CardTitle>
          <CardDescription>{tc('dailyTransactions')}</CardDescription>
        </CardHeader>
        <CardContent>
          {orders.length === 0 ? (
            <div className="text-center py-10 text-gray-500">
              <UtensilsCrossed className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p className="font-medium">{tc('noOrders')}</p>
              <p className="text-sm mt-1 mb-4">{tc('ordersWillAppear')}</p>
              <Button onClick={() => navigate('/fnb-complete')} data-testid="btn-pos-empty-new-order">
                <Plus className="w-4 h-4 mr-1.5" /> {tc('newOrder')}
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              {orders.slice(0, 20).map((order) => {
                const st = STATUS_MAP[order.status] || STATUS_MAP.pending;
                return (
                  <div key={order.id} className="flex justify-between items-center p-3 border rounded-lg hover:shadow-sm transition">
                    <div className="min-w-0">
                      <div className="font-semibold">{tc('orderNo')} #{order.order_number || (order.id || '').slice(0, 8)}</div>
                      <div className="text-sm text-gray-600 truncate">
                        {order.outlet_name || t('pmsComponents.concierge.restaurant')}
                        {order.table_number && order.table_number !== 'N/A' ? ` • ${tc('table')} ${order.table_number}` : ''}
                        {order.guest_name ? ` • ${order.guest_name}` : ''}
                      </div>
                      <div className="text-xs text-gray-400">
                        {order.created_at ? new Date(order.created_at).toLocaleString(i18n.language) : ''}
                        {order.items_count != null ? ` • ${order.items_count} ${tc('items')}` : ''}
                      </div>
                    </div>
                    <div className="text-right ml-3 flex-shrink-0">
                      <div className="font-bold">{fmt(order.total_amount, i18n.language)} {cur}</div>
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
