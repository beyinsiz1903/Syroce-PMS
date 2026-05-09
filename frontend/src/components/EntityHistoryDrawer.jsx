import { useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { History, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const ACTION_COLORS = {
  create: 'bg-emerald-100 text-emerald-800',
  update: 'bg-sky-100 text-sky-800',
  delete: 'bg-red-100 text-red-800',
};

const actionBadge = (a) => {
  const key = (a || '').split(':')[0];
  return ACTION_COLORS[key] || 'bg-amber-100 text-amber-800';
};

const fmt = (ts) => {
  if (!ts) return '';
  try { return new Date(ts).toLocaleString('tr-TR'); }
  catch { return ts; }
};

const Diff = ({ before, after, changed }) => {
  const { t } = useTranslation();
  if (changed && Object.keys(changed).length) {
    return (
      <div className="mt-2 space-y-1">
        {Object.entries(changed).slice(0, 8).map(([k, v]) => (
          <div key={k} className="text-xs flex gap-2">
            <span className="font-mono text-slate-600 min-w-[120px]">{k}</span>
            <span className="text-red-600 line-through max-w-[180px] truncate">
              {JSON.stringify(v.before)}
            </span>
            <span className="text-emerald-700 max-w-[180px] truncate">
              → {JSON.stringify(v.after)}
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (after && !before) {
    return <div className="text-xs text-emerald-700 mt-1">{t('cm.components_EntityHistoryDrawer.yeni_kayit_olusturuldu')}</div>;
  }
  if (!after && before) {
    return <div className="text-xs text-red-700 mt-1">{t('cm.components_EntityHistoryDrawer.kayit_silindi')}</div>;
  }
  return null;
};

const EntityHistoryDrawer = ({ entityType, entityId, title, onClose }) => {
  const [trail, setTrail] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    axios.get(`/audit/timeline/${entityType}/${entityId}?limit=100`)
      .then((r) => { if (alive) setTrail(r.data?.trail || []); })
      .catch(() => { if (alive) setTrail([]); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [entityType, entityId]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30"
         onClick={onClose}>
      <div className="bg-white w-full max-w-xl h-full overflow-y-auto shadow-xl"
           onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-slate-700" />
            <div>
              <div className="font-semibold">{t('cm.components_EntityHistoryDrawer.degisiklik_gecmisi')}</div>
              {title && <div className="text-xs text-slate-500">{title}</div>}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="p-4">
          {loading && <div className="text-sm text-slate-500">{t('cm.components_EntityHistoryDrawer.yukleniyor')}</div>}
          {!loading && trail.length === 0 && (
            <div className="text-sm text-slate-500">{t('cm.components_EntityHistoryDrawer.bu_kayit_icin_gecmis_bulunmuyor')}</div>
          )}
          <ol className="relative border-l-2 border-slate-200 ml-2">
            {trail.map((entry) => (
              <li key={entry.id} className="ml-4 mb-5">
                <div className="absolute -left-[7px] mt-1 w-3 h-3 rounded-full bg-slate-400" />
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge className={`${actionBadge(entry.operation)} border-0 text-[10px]`}>
                    {entry.operation || '—'}
                  </Badge>
                  <span className="text-xs text-slate-600">{fmt(entry.timestamp)}</span>
                  {entry.actor_id && (
                    <span className="text-xs text-slate-500">· {entry.actor_id}</span>
                  )}
                </div>
                {entry.override_reason && (
                  <div className="text-xs text-amber-700 mt-1">
                    Sebep: {entry.override_reason}
                  </div>
                )}
                <Diff before={entry.before_snapshot}
                      after={entry.after_snapshot}
                      changed={entry.changed_fields} />
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
};

export default EntityHistoryDrawer;
