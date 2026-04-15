import { useTranslation } from 'react-i18next';
import { useCallback } from 'react';
import { AlertTriangle, Building2, Layers3, Route } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';


export function StalePendingTriageCard({ triage }) {
  const { t } = useTranslation();
  const tm = useCallback((key) => t(`migrationObs.${key}`), [t]);

  const formatAge = (value) => (typeof value === 'number' ? `${Math.round(value)} ${tm('minutes')}` : '—');

  const translateAssessment = (key, fallback, params = {}) => {
    if (!key) return fallback || '—';
    const translationKey = `migrationObs.assess_${key}`;
    const translated = t(translationKey, params);
    return translated !== translationKey ? translated : fallback || key;
  };

  if (!triage) return null;

  const topProperty = triage.property_breakdown?.[0];
  const semanticOrigin = triage.origin_breakdown?.find((item) => item.origin === 'semantic');

  return (
    <Card className="border-white/70 bg-white/90" data-testid="migration-stale-triage-card">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-slate-950">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              {tm('staleTriage')}
            </CardTitle>
            <CardDescription>
              {tm('staleTriageDesc')}
            </CardDescription>
          </div>
          <Badge variant="outline" data-testid="migration-stale-triage-backlog-shape">{triage.assessment?.backlog_shape || 'clear'}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-2xl bg-amber-50 p-4" data-testid="migration-stale-triage-total">
            <div className="text-xs uppercase tracking-[0.25em] text-amber-700">{tm('totalStale')}</div>
            <div className="mt-2 text-3xl font-semibold text-slate-950">{triage.total_stale_pending ?? 0}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-stale-triage-oldest-age">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-500">{tm('oldestAge')}</div>
            <div className="mt-2 text-3xl font-semibold text-slate-950">{formatAge(triage.oldest_pending_age_minutes)}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-stale-triage-property-top">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-500">{tm('topProperty')}</div>
            <div className="mt-2 truncate text-sm font-semibold text-slate-950">{topProperty?.property_id || '—'}</div>
            <div className="mt-1 text-xs text-slate-500">{topProperty?.count ?? 0} {tm('event')}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-stale-triage-semantic-share">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-500">{tm('semanticShare')}</div>
            <div className="mt-2 text-3xl font-semibold text-slate-950">%{semanticOrigin?.share_percent ?? 0}</div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-3 rounded-[24px] border border-slate-200 bg-slate-950 p-5 text-white" data-testid="migration-stale-triage-assessment-panel">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <Layers3 className="h-4 w-4 text-teal-300" />
              {tm('assessment')}
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-400">{tm('sourceScope')}</p>
              <p className="mt-2 text-sm text-white" data-testid="migration-stale-triage-source-scope">{translateAssessment(triage.assessment?.source_scope_key, triage.assessment?.source_scope, triage.assessment?.source_scope_params || {})}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-400">{tm('likelyRootCause')}</p>
              <p className="mt-2 text-sm text-white" data-testid="migration-stale-triage-root-cause">{translateAssessment(triage.assessment?.likely_root_cause_key, triage.assessment?.likely_root_cause)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-400">{tm('recommendedAction')}</p>
              <p className="mt-2 text-sm text-white" data-testid="migration-stale-triage-recommended-action">{translateAssessment(triage.assessment?.recommended_action_key, triage.assessment?.recommended_action)}</p>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-5" data-testid="migration-stale-triage-delivery-signals-panel">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <Route className="h-4 w-4 text-sky-600" />
                {tm('deliverySignals')}
              </div>
              <div className="mt-4 space-y-3 text-sm text-slate-700">
                <div className="flex items-center justify-between"><span>{tm('processedCount')}</span><span data-testid="migration-stale-triage-processed-count">{triage.delivery_signals?.processed_count ?? 0}</span></div>
                <div className="flex items-center justify-between"><span>{tm('retryMetadata')}</span><span data-testid="migration-stale-triage-retry-count">{triage.delivery_signals?.retry_metadata_count ?? 0}</span></div>
                <div className="flex items-center justify-between"><span>{tm('lifecycleActive')}</span><span data-testid="migration-stale-triage-lifecycle-active">{triage.delivery_signals?.has_delivery_lifecycle ? tm('yes') : tm('no')}</span></div>
              </div>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-5" data-testid="migration-stale-triage-window-panel">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <Building2 className="h-4 w-4 text-emerald-600" />
                {tm('pendingWindow')}
              </div>
              <div className="mt-4 space-y-3 text-sm text-slate-700">
                <div className="flex items-center justify-between gap-4"><span>{tm('oldestPendingLabel')}</span><span className="text-right">{triage.oldest_pending_at || '—'}</span></div>
                <div className="flex items-center justify-between gap-4"><span>{tm('newestStale')}</span><span className="text-right">{triage.newest_pending_at || '—'}</span></div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div data-testid="migration-stale-triage-event-breakdown-panel">
            <p className="mb-3 text-xs uppercase tracking-[0.25em] text-slate-500">{tm('eventTypeBreakdown')}</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{tm('event')}</TableHead>
                  <TableHead>{tm('count')}</TableHead>
                  <TableHead>{tm('share')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(triage.event_type_breakdown || []).map((item) => (
                  <TableRow key={item.event_type} data-testid={`migration-stale-triage-event-row-${item.event_type.replace(/[^a-z0-9]/gi, '-')}`}>
                    <TableCell className="font-medium">{item.event_type}</TableCell>
                    <TableCell>{item.count}</TableCell>
                    <TableCell>%{item.share_percent}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div data-testid="migration-stale-triage-source-breakdown-panel">
            <p className="mb-3 text-xs uppercase tracking-[0.25em] text-slate-500">{tm('sourceBreakdown')}</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{tm('source')}</TableHead>
                  <TableHead>{tm('origin')}</TableHead>
                  <TableHead>{tm('count')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(triage.source_breakdown || []).map((item) => (
                  <TableRow key={`${item.source}-${item.origin}`} data-testid={`migration-stale-triage-source-row-${item.source.replace(/[^a-z0-9]/gi, '-')}`}>
                    <TableCell className="font-medium">{item.source}</TableCell>
                    <TableCell>{item.origin}</TableCell>
                    <TableCell>{item.count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
