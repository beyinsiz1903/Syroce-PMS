import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Loader2, RefreshCw, ShieldAlert, CheckCircle2, AlertTriangle,
  PlayCircle, Database,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const BASE = '/api/admin/db/room-night-lock-duplicates';

const RECO_TONE = {
  auto_safe: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  auto_safe_all_inactive: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  manual_required: 'bg-red-500/15 text-red-400 border-red-500/30',
};

const OWNER_TONE = {
  active: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  block: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30',
  terminal: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  missing: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  unknown: 'bg-red-500/15 text-red-400 border-red-500/30',
};

const RnlDuplicatesTab = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState(false);
  const [plan, setPlan] = useState(null);
  const [lastApply, setLastApply] = useState(null);

  const fetchPlan = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(BASE, { params: { limit: 200 } });
      setPlan(data);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('rnlDuplicates.fetchError'));
      setPlan(null);
    }
    setLoading(false);
  }, [t]);

  useEffect(() => { fetchPlan(); }, [fetchPlan]);

  const handleResolve = useCallback(async () => {
    if (!plan || (plan.auto_resolvable || 0) === 0) {
      toast.info(t('rnlDuplicates.nothingAuto'));
      return;
    }
    const msg = t('rnlDuplicates.confirmResolve', { count: plan.auto_resolvable });
    if (typeof window !== 'undefined' && !window.confirm(msg)) return;
    setResolving(true);
    try {
      const { data } = await axios.post(
        `${BASE}/resolve`,
        { confirm: true, limit: 200 },
        { params: { dry_run: false, rebuild_index: true } }
      );
      setLastApply(data);
      toast.success(
        t('rnlDuplicates.resolveDone', {
          resolved: data.resolved_count,
          skipped: data.skipped_count,
        })
      );
      await fetchPlan();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('rnlDuplicates.resolveError'));
    }
    setResolving(false);
  }, [plan, fetchPlan, t]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const groups = plan?.groups || [];
  const manualGroups = groups.filter((g) => g.recommendation === 'manual_required');
  const manualFromApply = (lastApply?.skipped || []).filter(
    (g) => g.recommendation === 'manual_required'
  );

  return (
    <div className="space-y-4" data-testid="rnl-duplicates-tab">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-slate-300 flex items-center gap-2">
            <Database className="w-4 h-4 text-amber-400" />
            {t('rnlDuplicates.title')}
          </h3>
          <p className="text-xs text-slate-500 mt-1">{t('rnlDuplicates.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="border-slate-700 text-slate-300"
            onClick={fetchPlan}
            data-testid="rnl-refresh"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
            {t('rnlDuplicates.refresh')}
          </Button>
          <Button
            size="sm"
            variant="default"
            className="bg-black text-white hover:bg-black/90"
            onClick={handleResolve}
            disabled={resolving || !(plan?.auto_resolvable > 0)}
            data-testid="rnl-resolve-safe"
          >
            {resolving ? (
              <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
            ) : (
              <PlayCircle className="w-3.5 h-3.5 mr-1" />
            )}
            {t('rnlDuplicates.resolveSafe', { count: plan?.auto_resolvable || 0 })}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">{t('rnlDuplicates.kpiTotal')}</div>
            <div className="text-2xl font-semibold text-white mt-1">
              {plan?.total ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">
              {t('rnlDuplicates.kpiAutoResolvable')}
            </div>
            <div className="text-2xl font-semibold text-emerald-400 mt-1">
              {plan?.auto_resolvable ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="text-xs text-slate-500">
              {t('rnlDuplicates.kpiManual')}
            </div>
            <div className="text-2xl font-semibold text-red-400 mt-1">
              {plan?.manual_required ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {lastApply && (
        <Card
          className="bg-slate-800/50 border-slate-700"
          data-testid="rnl-last-apply"
        >
          <CardContent className="p-4">
            <div className="text-xs text-slate-400 mb-2 flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              {t('rnlDuplicates.lastApply', {
                resolved: lastApply.resolved_count,
                skipped: lastApply.skipped_count,
                scanned: lastApply.scanned,
              })}
            </div>
            {lastApply.index_rebuild && (
              <div className="text-[11px] text-slate-500">
                {t('rnlDuplicates.indexRebuild')}:{' '}
                {lastApply.index_rebuild.ran
                  ? t('rnlDuplicates.indexOk')
                  : `${t('rnlDuplicates.indexFailed')}: ${lastApply.index_rebuild.error || '-'}`}
              </div>
            )}
            {manualFromApply.length > 0 && (
              <div className="mt-3 text-xs text-amber-300 flex items-start gap-2">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                <span>
                  {t('rnlDuplicates.manualFollowUp', {
                    count: manualFromApply.length,
                  })}
                </span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {groups.length === 0 ? (
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="py-12 text-center text-slate-400">
            <CheckCircle2 className="w-6 h-6 text-emerald-400 mx-auto mb-2" />
            {t('rnlDuplicates.empty')}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {groups.map((g) => {
            const key = `${g.tenant_id}-${g.room_id}-${g.night_date}`;
            const isManual = g.recommendation === 'manual_required';
            return (
              <Card
                key={key}
                className="bg-slate-800/50 border-slate-700"
                data-testid={`rnl-group-${key}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap mb-2">
                        {isManual ? (
                          <ShieldAlert className="w-4 h-4 text-red-400" />
                        ) : (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        )}
                        <Badge
                          className={`border text-[11px] ${RECO_TONE[g.recommendation] || OWNER_TONE.unknown}`}
                        >
                          {g.recommendation}
                        </Badge>
                        <span className="text-[11px] text-slate-500">
                          {t('rnlDuplicates.rowsLabel')}: {g.count}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                        <div>
                          <span className="text-slate-500">tenant_id:</span>{' '}
                          <span className="text-white font-mono">
                            {g.tenant_id || '-'}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500">room_id:</span>{' '}
                          <span className="text-white font-mono">
                            {g.room_id || '-'}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500">night_date:</span>{' '}
                          <span className="text-white font-mono">
                            {g.night_date || '-'}
                          </span>
                        </div>
                      </div>
                      <div className="mt-2 text-[11px] text-slate-400">
                        {g.reason}
                      </div>
                      <div className="mt-3 space-y-1">
                        {(g.owners || []).map((o, idx) => (
                          <div
                            key={`${key}-${idx}`}
                            className="flex items-center gap-2 text-[11px]"
                          >
                            <Badge
                              className={`border ${OWNER_TONE[o.kind] || OWNER_TONE.unknown}`}
                            >
                              {o.kind}
                            </Badge>
                            <span className="font-mono text-slate-300 truncate">
                              {o.booking_id || '(no booking_id)'}
                            </span>
                            {o.status && (
                              <span className="text-slate-500">
                                · {o.status}
                              </span>
                            )}
                            {o.lock_type && (
                              <span className="text-slate-500">
                                · {o.lock_type}
                              </span>
                            )}
                            {g.keep_booking_id === o.booking_id && (
                              <Badge className="border bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
                                {t('rnlDuplicates.keeper')}
                              </Badge>
                            )}
                            {(g.retire_booking_ids || []).includes(o.booking_id) && (
                              <Badge className="border bg-amber-500/15 text-amber-400 border-amber-500/30">
                                {t('rnlDuplicates.retire')}
                              </Badge>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {manualGroups.length > 0 && (
        <Card className="bg-amber-500/5 border-amber-500/30">
          <CardContent className="p-4 text-xs text-amber-300 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>
              {t('rnlDuplicates.manualWarning', { count: manualGroups.length })}
            </span>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default RnlDuplicatesTab;
