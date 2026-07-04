import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Network, Plus, RefreshCw, CheckCircle, AlertTriangle, XCircle,
  Clock, ArrowUpDown, Link2, Unlink, Shield, Activity, FileText,
  Download, Eye, ChevronRight, Zap, Settings, Database, Map,
  Loader2, Wifi, Key, Home, BedDouble, DollarSign, FileCode,
  RotateCcw, AlertOctagon, ChevronDown, ChevronUp, Timer,
  UserCheck, Ban, PackageCheck, AlertCircle, MailCheck, MailX,
  Search, Filter, ExternalLink
} from 'lucide-react';
import { HealthBadge, StatusBadge, AckBadge } from '../badges';

export default function ReservationsTab(props) {
  const {
    t,
    activeTab,
    setActiveTab,
    dashboard,
    setDashboard,
    connectors,
    setConnectors,
    mappings,
    setMappings,
    syncJobs,
    setSyncJobs,
    importedReservations,
    setImportedReservations,
    issues,
    setIssues,
    auditLogs,
    setAuditLogs,
    loading,
    setLoading,
    showNewConnector,
    setShowNewConnector,
    showNewMapping,
    setShowNewMapping,
    selectedConnector,
    setSelectedConnector,
    newConnector,
    setNewConnector,
    newMapping,
    setNewMapping,
    testResult,
    setTestResult,
    showTestResult,
    setShowTestResult,
    testLoading,
    setTestLoading,
    selectedJob,
    setSelectedJob,
    jobEvents,
    setJobEvents,
    showJobDetail,
    setShowJobDetail,
    jobDetailLoading,
    setJobDetailLoading,
    manualReviewQueue,
    setManualReviewQueue,
    importBatches,
    setImportBatches,
    reservationReviewQueue,
    setReservationReviewQueue,
    selectedReservation,
    setSelectedReservation,
    showReservationDetail,
    setShowReservationDetail,
    selectedBatch,
    setSelectedBatch,
    showBatchDetail,
    setShowBatchDetail,
    batchReservations,
    setBatchReservations,
    batchDetailLoading,
    setBatchDetailLoading,
    mappingReadiness,
    setMappingReadiness,
    mappingFilter,
    setMappingFilter,
    pullLoading,
    setPullLoading,
    fetchDashboard,
    fetchConnectors,
    fetchData,
    handleCreateConnector,
    handleActivate,
    handlePause,
    handleTestConnection,
    handleCreateMapping,
    fetchMappings,
    fetchMappingReadiness,
    handleValidateAllMappings,
    handleValidateMapping,
    handleDeactivateMapping,
    handleSyncInventory,
    handleSyncRates,
    handlePullReservations,
    handleViewBatchDetail,
    handleViewReservationDetail,
    handleReprocessReview,
    handleDismissReview,
    handleRunReconciliation,
    handleResolveIssue,
    handleViewJobDetail,
    handleRetryJob,
    handleDismissJob,
    hs
  } = props;
  return (
    <>
            <div className="space-y-4">
              {/* Pull Reservations Action */}
              {connectors.filter(c => c.status === 'active').length > 0 && (
                <Card className="bg-white shadow-sm border-slate-200">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Download className="w-4 h-4 text-blue-600" />
                        <span className="text-sm text-slate-900 font-medium">{t('cm.components_integrationhub_tabs_ReservationsTab.rezervasyon_cek')}</span>
                        <span className="text-xs text-slate-500">{t('cm.components_integrationhub_tabs_ReservationsTab.provider_dan_yeni_ve_guncellenmis_rezerv')}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {connectors.filter(c => c.status === 'active').map(c => (
                          <Button key={c.connector_id} size="sm" className="text-xs h-7 bg-blue-600 hover:bg-blue-700"
                            onClick={() => handlePullReservations(c.connector_id)}
                            disabled={pullLoading}
                            data-testid={`pull-res-${c.connector_id}`}>
                            {pullLoading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
                            {c.display_name || c.provider}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Reservation Review Queue */}
              {reservationReviewQueue.length > 0 && (
                <Card className="bg-amber-950/30 border-amber-800/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base text-amber-700 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" /> {t('cm.components_integrationhub_tabs_ReservationsTab.manuel_inceleme_kuyrugu')}{reservationReviewQueue.length})
                    </CardTitle>
                    <CardDescription className="text-amber-600/70 text-xs">
                      Bu rezervasyonlar manuel inceleme gerektiriyor
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {reservationReviewQueue.map((r) => (
                      <div key={r.id} className="flex items-center justify-between p-3 rounded-lg bg-white shadow-sm border border-amber-800/30"
                        data-testid={`res-review-${r.id?.slice(0, 8)}`}>
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="flex flex-col min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-slate-900 font-medium">{r.guest_name || 'Bilinmeyen Misafir'}</span>
                              <StatusBadge status={r.import_status} />
                              {r.review_reason_code && (
                                <Badge variant="outline" className="text-[10px] border-amber-700/50 text-amber-600 py-0">
                                  {r.review_reason_code.replace(/_/g, ' ')}
                                </Badge>
                              )}
                            </div>
                            <span className="text-xs text-slate-500 truncate">
                              {r.external_confirmation_number || r.external_reservation_id?.slice(0, 10)}
                              {r.review_reason && ` — ${r.review_reason}`}
                            </span>
                            {r.suggested_action && (
                              <span className="text-[10px] text-amber-600/70 mt-0.5">{t('cm.components_integrationhub_tabs_ReservationsTab.onerilen')} {r.suggested_action}</span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <Button size="sm" className="text-xs h-7 bg-emerald-600 hover:bg-emerald-700"
                            onClick={() => handleReprocessReview(r.id)} data-testid={`reprocess-${r.id?.slice(0, 8)}`}>
                            <RotateCcw className="w-3 h-3 mr-1" /> Reprocess
                          </Button>
                          <Button size="sm" variant="outline" className="text-xs h-7 border-slate-200 text-slate-500"
                            onClick={() => handleDismissReview(r.id)} data-testid={`dismiss-res-${r.id?.slice(0, 8)}`}>
                            Dismiss
                          </Button>
                          <Button size="sm" variant="ghost" className="text-xs h-7 text-slate-500"
                            onClick={() => handleViewReservationDetail(r.id)}>
                            <Eye className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Import Batches */}
              {importBatches.length > 0 && (
                <Card className="bg-white shadow-sm border-slate-200">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base text-slate-900 flex items-center gap-2">
                      <PackageCheck className="w-4 h-4 text-violet-400" /> Import Batches
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {importBatches.map((b) => (
                        <div key={b.id}
                          className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-200 transition-colors cursor-pointer"
                          onClick={() => handleViewBatchDetail(b.id)}
                          data-testid={`batch-row-${b.id?.slice(0, 8)}`}
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex flex-col">
                              <div className="flex items-center gap-2">
                                <span className="text-sm text-slate-900 font-medium font-mono">{b.id?.slice(0, 8)}</span>
                                <StatusBadge status={b.status} />
                              </div>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-xs text-slate-500">{new Date(b.started_at).toLocaleString('tr-TR')}</span>
                                {b.duration_ms != null && (
                                  <>
                                    <span className="text-xs text-slate-600">&middot;</span>
                                    <span className="text-xs text-slate-500 font-mono">{b.duration_ms}ms</span>
                                  </>
                                )}
                                <span className="text-xs text-slate-600">&middot;</span>
                                <span className="text-xs text-slate-500">{b.triggered_by}</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <div className="grid grid-cols-4 gap-2 text-center">
                              {b.new_count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">{b.new_count} yeni</span>}
                              {b.modified_count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">{b.modified_count} mod</span>}
                              {b.cancelled_count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600 border border-red-200">{b.cancelled_count} iptal</span>}
                              {b.review_count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 border border-amber-200">{b.review_count} review</span>}
                              {b.duplicate_count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-500 border border-slate-500/20">{b.duplicate_count} dup</span>}
                              {b.conflict_count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">{b.conflict_count} conflict</span>}
                              {b.out_of_order_count > 0 && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 border border-amber-200">{b.out_of_order_count} ooo</span>}
                            </div>
                            <div className="text-right">
                              <span className="text-[10px] text-slate-500 block">toplam</span>
                              <span className="text-xs text-slate-500">{b.total_reservations || 0}</span>
                            </div>
                            <ChevronRight className="w-4 h-4 text-slate-600" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Imported Reservations Table */}
              <Card className="bg-white shadow-sm border-slate-200">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base text-slate-900">Imported Reservations</CardTitle>
                  <CardDescription className="text-xs text-slate-500">{importedReservations.length} {t('cm.components_integrationhub_tabs_ReservationsTab.kayit')}</CardDescription>
                </CardHeader>
                <CardContent>
                  {importedReservations.length > 0 ? (
                    <div className="border border-slate-200 rounded-lg overflow-hidden">
                      <table className="w-full text-sm" data-testid="reservations-table">
                        <thead className="bg-slate-50 text-slate-500">
                          <tr>
                            <th className="text-left px-4 py-2">Ref</th>
                            <th className="text-left px-4 py-2">{t('cm.components_integrationhub_tabs_ReservationsTab.misafir')}</th>
                            <th className="text-left px-4 py-2">{t('cm.components_integrationhub_tabs_ReservationsTab.tarih')}</th>
                            <th className="text-left px-4 py-2">Kanal</th>
                            <th className="text-right px-4 py-2">{t('cm.components_integrationhub_tabs_ReservationsTab.tutar')}</th>
                            <th className="text-left px-4 py-2">{t('cm.components_integrationhub_tabs_ReservationsTab.durum')}</th>
                            <th className="text-left px-4 py-2">ACK</th>
                            <th className="text-center px-4 py-2">Detay</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                          {importedReservations.map((r) => (
                            <tr key={r.id} className="text-slate-600 hover:bg-slate-50" data-testid={`res-row-${r.id?.slice(0, 8)}`}>
                              <td className="px-4 py-2 text-xs font-mono">{r.external_confirmation_number || r.external_reservation_id?.slice(0, 10)}</td>
                              <td className="px-4 py-2">{r.guest_name}</td>
                              <td className="px-4 py-2 text-xs">{r.arrival_date} → {r.departure_date}</td>
                              <td className="px-4 py-2 text-xs">{r.channel_name}</td>
                              <td className="px-4 py-2 text-xs text-right font-mono">{r.total_amount?.toLocaleString('tr-TR')} {r.currency}</td>
                              <td className="px-4 py-2">
                                <div className="flex items-center gap-1">
                                  <StatusBadge status={r.import_status} />
                                  {r.is_modification && <Badge variant="outline" className="text-[10px] border-cyan-700/50 text-cyan-400 py-0">mod</Badge>}
                                  {r.is_cancellation && <Badge variant="outline" className="text-[10px] border-red-700/50 text-red-600 py-0">cancel</Badge>}
                                </div>
                              </td>
                              <td className="px-4 py-2"><AckBadge ackStatus={r.ack_status} /></td>
                              <td className="px-4 py-2 text-center">
                                <Button size="sm" variant="ghost" className="text-xs h-6 w-6 p-0 text-slate-500"
                                  onClick={() => handleViewReservationDetail(r.id)} data-testid={`view-res-${r.id?.slice(0, 8)}`}>
                                  <Eye className="w-3 h-3" />
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-slate-500 text-sm">{t('cm.components_integrationhub_tabs_ReservationsTab.henuz_import_edilen_rezervasyon_yok')}</div>
                  )}
                </CardContent>
              </Card>
            </div>
    </>
  );
}
