import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { REC_STYLES, LoadingState, EmptyState, ErrorState } from './shared';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
const HistoryTab = ({
  user,
  tenant,
  onLogout
} = {}) => {
  const {
    t
  } = useTranslation();
  const fallbackCurrency = tenant?.currency || cachedTenantCurrency();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await axios.get('/displacement/history?limit=20');
      setData(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      console.error('History error:', e);
      setData([]);
      setError(t('displacement.historyLoadError', 'Geçmiş analizler yüklenemedi. Lütfen yeniden deneyin.'));
    } finally {
      setLoading(false);
    }
  }, [t]);
  useEffect(() => { load(); }, [load]);
  if (loading) return <LoadingState text={t('displacement.loadingHistory', 'Loading history...')} />;
  if (error) return <ErrorState text={error} onRetry={load} />;
  if (!data.length) {
    return <EmptyState text={t('displacement.noHistory', 'No saved analyses yet. Run an analysis and save it to see history here.')} />;
  }
  return <div className="space-y-3">
      {data.map((item, i) => {
      const rec = item.recommendation?.action;
      const recS = REC_STYLES[rec] || REC_STYLES.conditional;
      const RecI = recS.icon;
      return <Card key={item.id || i}>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <RecI className={`w-6 h-6 ${recS.color}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-sm truncate">{item.scenario?.group_name || t('displacement.unnamedGroup', 'Adsız grup')}</h4>
                    <Badge className={recS.bg + ' ' + recS.color + ' text-[10px]'}>
                      {rec?.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500">
                    {item.scenario?.check_in} → {item.scenario?.check_out} · {item.scenario?.rooms_requested} {t('displacement.rooms', 'rooms')} · {formatCurrency(item.scenario?.proposed_rate, item.currency || fallbackCurrency)}/{t('displacement.night', 'night')}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`font-bold ${item.summary?.net_displacement >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    {formatCurrency(item.summary?.net_displacement, item.currency || fallbackCurrency)}
                  </p>
                  <p className="text-[10px] text-gray-400">{item.created_at?.slice(0, 10)}</p>
                </div>
              </div>
            </CardContent>
          </Card>;
    })}
    </div>;
};
export default HistoryTab;
