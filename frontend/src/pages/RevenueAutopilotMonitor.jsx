import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  Activity, RefreshCw, Clock, Send, Building2, BarChart3, TrendingUp, Loader2,
} from 'lucide-react';

const MODE_LABELS = {
  full_auto: 'Tam Otonom',
  supervised: 'Denetimli',
  advisory: 'Danışma',
};

const MODE_INTENT = {
  full_auto: 'success',
  supervised: 'info',
  advisory: 'neutral',
};

const STATUS_LABELS = {
  completed: 'Tamamlandı',
  dispatched: 'Kuyruğa Alındı',
};

const STATUS_INTENT = {
  completed: 'success',
  dispatched: 'info',
};

function fmtDate(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('tr-TR');
  } catch {
    return value;
  }
}

function fmtMoney(value) {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString('tr-TR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function RevenueAutopilotMonitor() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await axios.get('/autopilot/last-run');
      setData(res.data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const mode = data?.mode;
  const prices = data?.optimal_prices || [];
  const dispatch = data?.dispatch;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <PageHeader
        icon={Activity}
        title="Otonom Fiyat Döngüsü İzleme"
        subtitle="Son otonom Revenue Autopilot çalışması ve üretilen fiyatlar (salt-okunur)"
        actions={(
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Yenile
          </Button>
        )}
      />

      {loading && (
        <div className="flex items-center justify-center h-48 text-slate-400">
          <Loader2 className="w-7 h-7 animate-spin" />
        </div>
      )}

      {!loading && error && (
        <Card>
          <CardContent className="py-10 text-center text-slate-500">
            Durum bilgisi yüklenemedi. Lütfen tekrar deneyin.
          </CardContent>
        </Card>
      )}

      {!loading && !error && data && !data.has_run && (
        <Card>
          <CardContent className="py-10 text-center text-slate-500">
            Henüz otonom bir fiyat döngüsü çalışmadı. Gece çalışması tamamlandığında
            son çalışma ve üretilen fiyatlar burada görünecek.
          </CardContent>
        </Card>
      )}

      {!loading && !error && data && data.has_run && (
        <div className="space-y-6">
          {/* Last run summary */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard
              icon={Clock}
              label="Son Çalışma"
              value={fmtDate(data.last_auto_run_completed_at || data.last_auto_run)}
              sub={(
                <span className="inline-flex items-center gap-1">
                  <StatusBadge intent={STATUS_INTENT[data.last_auto_run_status] || 'neutral'}>
                    {STATUS_LABELS[data.last_auto_run_status] || data.last_auto_run_status || '—'}
                  </StatusBadge>
                </span>
              )}
              intent="info"
            />
            <KpiCard
              icon={Activity}
              label="Mod"
              value={MODE_LABELS[mode] || mode || '—'}
              intent={MODE_INTENT[mode] || 'default'}
            />
            <KpiCard
              icon={BarChart3}
              label="Fiyatlanan Oda Tipi"
              value={data.room_types_priced ?? prices.length}
              sub={`${data.competitors_checked ?? 0} rakip kaydı tarandı`}
              intent="default"
            />
            <KpiCard
              icon={Send}
              label="RATE_UPDATED Olayı"
              value={data.rate_events_emitted ?? 0}
              sub={mode === 'full_auto' ? 'Tam otonom fırlatma' : 'Yalnızca full_auto modunda'}
              intent={mode === 'full_auto' ? 'success' : 'neutral'}
            />
          </div>

          {/* Demand + dispatch */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <KpiCard
              icon={TrendingUp}
              label="Ortalama Doluluk"
              value={data.avg_occupancy === null || data.avg_occupancy === undefined ? '—' : `%${data.avg_occupancy}`}
              sub={data.demand_trend ? `Trend: ${data.demand_trend}` : undefined}
              intent="default"
            />
            <KpiCard
              icon={Building2}
              label="Taranan Kiracı"
              value={dispatch ? dispatch.scanned_tenants : '—'}
              sub={dispatch ? `Son dağıtım: ${fmtDate(dispatch.last_dispatch_at)}` : 'Dağıtım verisi yok'}
              intent="default"
            />
            <KpiCard
              icon={Building2}
              label="Kuyruğa Alınan Kiracı"
              value={dispatch ? dispatch.queued_tenants : '—'}
              intent="default"
            />
          </div>

          {/* Generated prices table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-slate-600" />
                Üretilen Optimal Fiyatlar (Oda Tipi Bazında)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {prices.length === 0 ? (
                <p className="text-sm text-slate-500 py-4">
                  Bu çalışmada fiyat önerisi üretilmedi (geçerli taban fiyatı olan oda tipi yok).
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500 border-b border-slate-200">
                        <th className="py-2 pr-4 font-semibold">Oda Tipi</th>
                        <th className="py-2 pr-4 font-semibold text-right">Mevcut Fiyat</th>
                        <th className="py-2 pr-4 font-semibold text-right">Optimal Fiyat</th>
                        <th className="py-2 pr-4 font-semibold text-right">Değişim</th>
                        <th className="py-2 pr-4 font-semibold">Uygulanan Kural</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prices.map((p, idx) => {
                        const change = p.change_pct;
                        const changeIntent = change > 0 ? 'success' : change < 0 ? 'danger' : 'neutral';
                        return (
                          <tr key={p.room_type || idx} className="border-b border-slate-100 last:border-0">
                            <td className="py-2 pr-4 font-medium text-slate-900">{p.room_type}</td>
                            <td className="py-2 pr-4 text-right tabular-nums">{fmtMoney(p.current_price)}</td>
                            <td className="py-2 pr-4 text-right tabular-nums font-semibold">{fmtMoney(p.optimal_price)}</td>
                            <td className="py-2 pr-4 text-right">
                              {change === null || change === undefined ? '—' : (
                                <StatusBadge intent={changeIntent}>
                                  {change > 0 ? '+' : ''}{change}%
                                </StatusBadge>
                              )}
                            </td>
                            <td className="py-2 pr-4 text-slate-500 text-xs max-w-md">{p.applied_rule || '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
