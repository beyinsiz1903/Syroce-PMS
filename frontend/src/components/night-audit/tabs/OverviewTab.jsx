import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { TabsContent } from '@/components/ui/tabs';
import { Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Calendar, FileText, ChevronDown, ChevronUp, DollarSign, Users, Building2, BarChart3, Eye, Loader2, Shield, Info, Timer, Settings2, Zap, RotateCcw, TrendingUp, CreditCard, ShieldCheck, Scale, Receipt, PieChart, ArrowUpDown, Banknote, AlertOctagon, Search } from 'lucide-react';

export default function OverviewTab(props) {
  const { SeverityBadge, StatusBadge, exceptions, expandedRun, handleQuickToggleSchedule, history, historyTotal, lastRun, loading, schedule, scheduleStatus, setShowScheduleDialog, t, toggleExpand } = props;
  return (
    <TabsContent value="overview" className="space-y-4 mt-4">
      {/* Automatic Scheduling Card */}
      <Card data-testid="schedule-card">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Timer className="w-4 h-4 text-indigo-500" />
              Otomatik Zamanlama
            </CardTitle>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Switch
                  data-testid="schedule-toggle"
                  checked={schedule.enabled}
                  onCheckedChange={handleQuickToggleSchedule}
                />
                <span className={`text-xs font-medium ${schedule.enabled ? "text-emerald-600" : "text-gray-400"}`}>
                  {schedule.enabled ? "Aktif" : "Devre Dışı"}
                </span>
              </div>
              <Button
                data-testid="schedule-settings-btn"
                variant="outline"
                size="sm"
                onClick={() => setShowScheduleDialog(true)}
              >
                <Settings2 className="w-3.5 h-3.5 mr-1" />
                Ayarlar
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <div className="rounded-lg p-2 bg-indigo-100">
                <Clock className="w-4 h-4 text-indigo-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900">
                  {String(schedule.scheduled_hour).padStart(2, "0")}:{String(schedule.scheduled_minute).padStart(2, "0")}
                </p>
                <p className="text-xs text-gray-500">{schedule.timezone || "Europe/Istanbul"}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <div className={`rounded-lg p-2 ${
                scheduleStatus?.last_auto_run_status === "completed" ? "bg-emerald-100"
                  : scheduleStatus?.last_auto_run_status === "failed" ? "bg-red-100" : "bg-gray-100"
              }`}>
                {scheduleStatus?.last_auto_run_status === "completed" ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                ) : scheduleStatus?.last_auto_run_status === "failed" ? (
                  <XCircle className="w-4 h-4 text-red-600" />
                ) : (
                  <Clock className="w-4 h-4 text-gray-400" />
                )}
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900">
                  {scheduleStatus?.last_auto_run
                    ? new Date(scheduleStatus.last_auto_run).toLocaleString("tr-TR")
                    : "Henüz çalıştırılmadı"}
                </p>
                <p className="text-xs text-gray-500">{t('cm.components_nightaudit_tabs_OverviewTab.son_otomatik_calistirma')}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
              <div className="rounded-lg p-2 bg-blue-100">
                <Zap className="w-4 h-4 text-blue-600" />
              </div>
              <div>
                <div className="flex flex-wrap gap-1">
                  {schedule.auto_retry && (
                    <Badge className="bg-blue-50 text-blue-700 border border-blue-200 text-[10px]">
                      Otomatik Yeniden Deneme
                    </Badge>
                  )}
                  {schedule.skip_validations && (
                    <Badge className="bg-amber-50 text-amber-700 border border-amber-200 text-[10px]">
                      {t('cm.components_nightaudit_tabs_OverviewTab.dogrulama_atla')}
                    </Badge>
                  )}
                  {!schedule.auto_retry && !schedule.skip_validations && (
                    <Badge className="bg-gray-50 text-gray-500 border border-gray-200 text-[10px]">
                      Standart Ayarlar
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{t('cm.components_nightaudit_tabs_OverviewTab.ozellikler')}</p>
              </div>
            </div>
          </div>
          {scheduleStatus?.recent_logs?.length > 0 && (
            <div className="mt-3 border-t pt-3">
              <p className="text-xs font-semibold text-gray-600 mb-2">{t('cm.components_nightaudit_tabs_OverviewTab.son_otomatik_calistirma_loglari')}</p>
              <div className="space-y-1.5 max-h-32 overflow-y-auto">
                {scheduleStatus.recent_logs.map((log) => (
                  <div key={log.id} className="flex items-center justify-between text-xs p-1.5 bg-gray-50 rounded">
                    <div className="flex items-center gap-2">
                      {log.status === "completed" ? (
                        <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                      ) : log.status === "failed" ? (
                        <XCircle className="w-3 h-3 text-red-500" />
                      ) : (
                        <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
                      )}
                      <span className="text-gray-700">{log.business_date}</span>
                    </div>
                    <span className="text-gray-400">
                      {log.triggered_at ? new Date(log.triggered_at).toLocaleString("tr-TR") : "-"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Latest Run Summary */}
      {lastRun && (
        <Card data-testid="last-run-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <FileText className="w-4 h-4 text-gray-500" />
              {t('cm.components_nightaudit_tabs_OverviewTab.son_denetim_ozeti')}
              <StatusBadge status={lastRun.status} />
              {lastRun.is_dry_run && (
                <Badge className="bg-indigo-100 text-indigo-700 border-indigo-200 border text-[11px]">
                  {t('cm.components_nightaudit_tabs_OverviewTab.simulasyon')}
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 text-sm">
              <div>
                <span className="text-gray-500 text-xs">Is Gunu</span>
                <p className="font-semibold">{lastRun.business_date}</p>
              </div>
              <div>
                <span className="text-gray-500 text-xs">Odalar</span>
                <p className="font-semibold">{lastRun.rooms_processed}</p>
              </div>
              <div>
                <span className="text-gray-500 text-xs">Masraflar</span>
                <p className="font-semibold">{lastRun.charges_posted}</p>
              </div>
              <div>
                <span className="text-gray-500 text-xs">{t('cm.components_nightaudit_tabs_OverviewTab.oda_geliri')}</span>
                <p className="font-semibold">{lastRun.total_room_revenue?.toFixed(2)} TL</p>
              </div>
              <div>
                <span className="text-gray-500 text-xs">Vergi</span>
                <p className="font-semibold">{lastRun.total_tax_amount?.toFixed(2)} TL</p>
              </div>
              <div>
                <span className="text-gray-500 text-xs">{t('cm.components_nightaudit_tabs_OverviewTab.sure')}</span>
                <p className="font-semibold">{lastRun.duration_ms ? `${lastRun.duration_ms}ms` : "-"}</p>
              </div>
            </div>
            {(lastRun.arrivals_pending > 0 || lastRun.departures_pending > 0 || lastRun.folios_unbalanced > 0) && (
              <div className="mt-3 flex flex-wrap gap-2">
                {lastRun.arrivals_pending > 0 && (
                  <Badge className="bg-blue-50 text-blue-700 border border-blue-200 text-xs">
                    {lastRun.arrivals_pending} {t('cm.components_nightaudit_tabs_OverviewTab.bekleyen_giris')}
                  </Badge>
                )}
                {lastRun.departures_pending > 0 && (
                  <Badge className="bg-amber-50 text-amber-700 border border-amber-200 text-xs">
                    {lastRun.departures_pending} {t('cm.components_nightaudit_tabs_OverviewTab.bekleyen_cikis')}
                  </Badge>
                )}
                {lastRun.folios_unbalanced > 0 && (
                  <Badge className="bg-red-50 text-red-700 border border-red-200 text-xs">
                    {lastRun.folios_unbalanced} dengesiz folio
                  </Badge>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* History Table */}
      <Card data-testid="audit-history-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-500" />
            {t('cm.components_nightaudit_tabs_OverviewTab.denetim_gecmisi')}{historyTotal})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
              {t('cm.components_nightaudit_tabs_OverviewTab.yukleniyor')}
            </div>
          ) : history.length === 0 ? (
            <div data-testid="no-history" className="py-10 text-center text-gray-500 text-sm">
              <Moon className="w-10 h-10 mx-auto text-gray-300 mb-2" />
              {t('cm.components_nightaudit_tabs_OverviewTab.henuz_gece_denetimi_yapilmamis')}
            </div>
          ) : (
            <div className="space-y-2">
              {history.map((run) => {
                const isExpanded = expandedRun === run.audit_id;
                const runExceptions = exceptions[run.audit_id] || [];
                const startedAt = run.started_at ? new Date(run.started_at) : null;
                return (
                  <div
                    key={run.audit_id}
                    data-testid={`audit-run-${run.audit_id}`}
                    className="border rounded-lg overflow-hidden"
                  >
                    <div
                      className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50/50 transition"
                      onClick={() => toggleExpand(run.audit_id)}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <StatusBadge status={run.status} />
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900">
                            {run.business_date}
                            {run.is_dry_run && <span className="ml-1.5 text-indigo-600 text-xs font-normal">{t('cm.components_nightaudit_tabs_OverviewTab.simulasyon_11963')}</span>}
                            {run.is_rerun && <span className="ml-1.5 text-amber-600 text-xs font-normal">(Tekrar)</span>}
                          </p>
                          <p className="text-xs text-gray-500">
                            {startedAt ? startedAt.toLocaleString("tr-TR") : "-"}
                            {run.duration_ms ? ` - ${run.duration_ms}ms` : ""}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="hidden md:flex items-center gap-4 text-xs text-gray-500">
                          <span>{run.rooms_processed} oda</span>
                          <span>{run.charges_posted} masraf</span>
                          <span>{run.total_room_revenue?.toFixed(0)} TL</span>
                          {run.exceptions_count > 0 && (
                            <Badge className="bg-amber-50 text-amber-700 border border-amber-200 text-[11px]">
                              {run.exceptions_count} istisna
                            </Badge>
                          )}
                        </div>
                        {isExpanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="border-t bg-gray-50/50 px-4 py-3 space-y-3">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          <div>
                            <span className="text-gray-500 text-xs">{t('cm.components_nightaudit_tabs_OverviewTab.oda_geliri_e569c')}</span>
                            <p className="font-semibold">{run.total_room_revenue?.toFixed(2)} TL</p>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs">Vergi</span>
                            <p className="font-semibold">{run.total_tax_amount?.toFixed(2)} TL</p>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs">No-Show</span>
                            <p className="font-semibold">{run.no_shows_processed}</p>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs">Folio (Dengeli/Dengesiz)</span>
                            <p className="font-semibold">
                              <span className="text-emerald-600">{run.folios_balanced}</span>
                              {" / "}
                              <span className={run.folios_unbalanced > 0 ? "text-red-600" : "text-gray-400"}>{run.folios_unbalanced}</span>
                            </p>
                          </div>
                        </div>
                        {runExceptions.length > 0 ? (
                          <div>
                            <p className="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-1">
                              <AlertTriangle className="w-3.5 h-3.5" /> {t('cm.components_nightaudit_tabs_OverviewTab.istisnalar')}{runExceptions.length})
                            </p>
                            <div className="space-y-1.5 max-h-60 overflow-y-auto">
                              {runExceptions.map((exc) => (
                                <div key={exc.id} className="flex items-start gap-2 p-2 bg-white border rounded text-xs">
                                  <SeverityBadge severity={exc.severity} />
                                  <div className="min-w-0 flex-1">
                                    <p className="text-gray-800">{exc.message}</p>
                                    <p className="text-gray-400 text-[11px] mt-0.5">
                                      {exc.category} - {exc.entity_type}
                                      {exc.entity_id ? ` - ${exc.entity_id.substring(0, 8)}...` : ""}
                                    </p>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : run.exceptions_count === 0 ? (
                          <p className="text-xs text-gray-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                            {t('cm.components_nightaudit_tabs_OverviewTab.istisna_yok_denetim_temiz_tamamlandi')}
                          </p>
                        ) : (
                          <p className="text-xs text-gray-400">{t('cm.components_nightaudit_tabs_OverviewTab.istisnalar_yukleniyor')}</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </TabsContent>
  );
}
