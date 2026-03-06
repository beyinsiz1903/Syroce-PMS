import { AlertTriangle, Building2, Layers3, Route } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';


const formatAge = (value) => (typeof value === 'number' ? `${Math.round(value)} dk` : '—');


export function StalePendingTriageCard({ triage }) {
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
              Stale pending triage
            </CardTitle>
            <CardDescription>
              Yellow health score’un nedenini event dağılımı ve delivery sinyaliyle açıklayan hızlı kontrol yüzeyi.
            </CardDescription>
          </div>
          <Badge variant="outline" data-testid="migration-stale-triage-backlog-shape">{triage.assessment?.backlog_shape || 'clear'}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="rounded-2xl bg-amber-50 p-4" data-testid="migration-stale-triage-total">
            <div className="text-xs uppercase tracking-[0.25em] text-amber-700">Total stale</div>
            <div className="mt-2 text-3xl font-semibold text-slate-950">{triage.total_stale_pending ?? 0}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-stale-triage-oldest-age">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-500">Oldest age</div>
            <div className="mt-2 text-3xl font-semibold text-slate-950">{formatAge(triage.oldest_pending_age_minutes)}</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-stale-triage-property-top">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-500">Top property</div>
            <div className="mt-2 truncate text-sm font-semibold text-slate-950">{topProperty?.property_id || '—'}</div>
            <div className="mt-1 text-xs text-slate-500">{topProperty?.count ?? 0} event</div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-stale-triage-semantic-share">
            <div className="text-xs uppercase tracking-[0.25em] text-slate-500">Semantic share</div>
            <div className="mt-2 text-3xl font-semibold text-slate-950">%{semanticOrigin?.share_percent ?? 0}</div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-3 rounded-[24px] border border-slate-200 bg-slate-950 p-5 text-white" data-testid="migration-stale-triage-assessment-panel">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <Layers3 className="h-4 w-4 text-teal-300" />
              Assessment
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Source scope</p>
              <p className="mt-2 text-sm text-white" data-testid="migration-stale-triage-source-scope">{triage.assessment?.source_scope || '—'}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Likely root cause</p>
              <p className="mt-2 text-sm text-white" data-testid="migration-stale-triage-root-cause">{triage.assessment?.likely_root_cause || '—'}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Recommended action</p>
              <p className="mt-2 text-sm text-white" data-testid="migration-stale-triage-recommended-action">{triage.assessment?.recommended_action || '—'}</p>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-5" data-testid="migration-stale-triage-delivery-signals-panel">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <Route className="h-4 w-4 text-sky-600" />
                Delivery signals
              </div>
              <div className="mt-4 space-y-3 text-sm text-slate-700">
                <div className="flex items-center justify-between"><span>Processed count</span><span data-testid="migration-stale-triage-processed-count">{triage.delivery_signals?.processed_count ?? 0}</span></div>
                <div className="flex items-center justify-between"><span>Retry metadata</span><span data-testid="migration-stale-triage-retry-count">{triage.delivery_signals?.retry_metadata_count ?? 0}</span></div>
                <div className="flex items-center justify-between"><span>Lifecycle active</span><span data-testid="migration-stale-triage-lifecycle-active">{triage.delivery_signals?.has_delivery_lifecycle ? 'Yes' : 'No'}</span></div>
              </div>
            </div>
            <div className="rounded-[24px] border border-slate-200 bg-slate-50 p-5" data-testid="migration-stale-triage-window-panel">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <Building2 className="h-4 w-4 text-emerald-600" />
                Pending window
              </div>
              <div className="mt-4 space-y-3 text-sm text-slate-700">
                <div className="flex items-center justify-between gap-4"><span>Oldest pending</span><span className="text-right">{triage.oldest_pending_at || '—'}</span></div>
                <div className="flex items-center justify-between gap-4"><span>Newest stale</span><span className="text-right">{triage.newest_pending_at || '—'}</span></div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div data-testid="migration-stale-triage-event-breakdown-panel">
            <p className="mb-3 text-xs uppercase tracking-[0.25em] text-slate-500">Event type breakdown</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Event</TableHead>
                  <TableHead>Count</TableHead>
                  <TableHead>Share</TableHead>
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
            <p className="mb-3 text-xs uppercase tracking-[0.25em] text-slate-500">Source breakdown</p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Origin</TableHead>
                  <TableHead>Count</TableHead>
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