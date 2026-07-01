import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fmt } from './helpers';
import { REC_STYLES, LoadingState, EmptyState } from './shared';

const HistoryTab = ({ user, tenant, onLogout } = {}) => {  
  const { t } = useTranslation();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get('/displacement/history?limit=20');
        setData(Array.isArray(res.data) ? res.data : []);
      } catch (e) {
        console.error('History error:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <LoadingState text={t('displacement.loadingHistory', 'Loading history...')} />;

  if (!data.length) {
    return (
      <EmptyState text={t('displacement.noHistory', 'No saved analyses yet. Run an analysis and save it to see history here.')} />
    );
  }

  return (
    <div className="space-y-3">
      {data.map((item, i) => {
        const rec = item.recommendation?.action;
        const recS = REC_STYLES[rec] || REC_STYLES.conditional;
        const RecI = recS.icon;
        return (
          <Card key={i}>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <RecI className={`w-6 h-6 ${recS.color}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-sm truncate">{item.scenario?.group_name || 'Unnamed'}</h4>
                    <Badge className={recS.bg + ' ' + recS.color + ' text-[10px]'}>
                      {rec?.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500">
                    {item.scenario?.check_in} → {item.scenario?.check_out} · {item.scenario?.rooms_requested} {t('displacement.rooms', 'rooms')} · ₺{item.scenario?.proposed_rate}/{t('displacement.night', 'night')}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`font-bold ${item.summary?.net_displacement >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    ₺{fmt(item.summary?.net_displacement)}
                  </p>
                  <p className="text-[10px] text-gray-400">{item.created_at?.slice(0, 10)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};

export default HistoryTab;
