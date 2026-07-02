import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Building2, DollarSign, Percent, BarChart3 } from 'lucide-react';
import { RISK_COLORS, fmt } from './helpers';
import { LoadingState, EmptyState, MetricCard } from './shared';
const MarketOverviewTab = ({
  user,
  tenant,
  onLogout
} = {}) => {
  const {
    t
  } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(14);
  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/displacement/market-overview?days=${days}`);
      setData(res.data);
    } catch (e) {
      console.error('Market overview error:', e);
    } finally {
      setLoading(false);
    }
  }, [days]);
  useEffect(() => {
    fetch();
  }, [fetch]);
  if (loading) return <LoadingState text={t('displacement.loadingMarket', 'Loading market data...')} />;
  if (!data) return <EmptyState text={t('displacement.noData', 'No data available')} />;
  return <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard icon={Building2} label={t('displacement.totalRooms', 'Total Rooms')} value={data.total_rooms} />
        <MetricCard icon={DollarSign} label={t('displacement.historicalAdr', 'Historical ADR')} value={fmt(data.historical_adr)} prefix="₺" />
        <MetricCard icon={Percent} label={t('displacement.cancelRate', 'Cancel Rate')} value={`${data.cancellation_rate_pct}%`} />
        <MetricCard icon={BarChart3} label={t('displacement.channels', 'Channels')} value={data.channel_mix?.length || 0} />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold">{t('displacement.occupancyForecast', 'Occupancy & Displacement Risk')}</CardTitle>
            <div className="flex items-center gap-2">
              {[7, 14, 30].map(d => <Button key={d} size="sm" variant={days === d ? 'default' : 'outline'} onClick={() => setDays(d)}>
                  {d} {t('displacement.days', 'days')}
                </Button>)}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-1.5">
            {(data.forecast || []).map((f, i) => <div key={f.id || i} className="flex items-center gap-3 text-sm">
                <span className="w-20 text-gray-500 font-mono text-xs">{f.date?.slice(5)}</span>
                <span className="w-12 text-gray-400 text-xs">{f.day_of_week?.slice(0, 3)}</span>
                <div className="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden relative">
                  <div className={`h-full rounded-full transition-all ${f.occupancy_pct >= 85 ? 'bg-red-500' : f.occupancy_pct >= 65 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{
                width: `${Math.min(f.occupancy_pct, 100)}%`
              }} />
                  <span className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold text-gray-800">
                    {f.occupancy_pct}%
                  </span>
                </div>
                <span className="w-16 text-right text-xs text-gray-500">{f.available} {t('displacement.avail', 'avail')}</span>
                <Badge className={`text-[10px] px-1.5 ${RISK_COLORS[f.displacement_risk]}`}>
                  {f.displacement_risk === 'high' ? t('displacement.highRisk', 'High Risk') : f.displacement_risk === 'medium' ? t('displacement.medRisk', 'Medium') : t('displacement.lowRisk', 'Low')}
                </Badge>
              </div>)}
          </div>
        </CardContent>
      </Card>

      {data.channel_mix?.length > 0 && <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">{t('displacement.channelMix', 'Channel Mix')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {(data.channel_mix || []).map((ch, i) => <div key={ch.id || i} className="flex items-center gap-3 p-3 rounded-lg border bg-white">
                  <div className="w-2 h-10 rounded-full bg-blue-500" style={{
              opacity: 0.3 + ch.share_pct / 100 * 0.7
            }} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate capitalize">{ch.channel}</p>
                    <p className="text-xs text-gray-500">{ch.bookings} {t('displacement.bookings', 'bookings')} · {ch.share_pct}%</p>
                  </div>
                  <p className="text-sm font-semibold">₺{fmt(ch.avg_rate)}</p>
                </div>)}
            </div>
          </CardContent>
        </Card>}
    </div>;
};
export default MarketOverviewTab;