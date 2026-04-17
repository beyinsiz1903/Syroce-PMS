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

export default function SyncTab(props) {
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
              {/* Manual Review Queue */}
              {manualReviewQueue.length > 0 && (
                <Card className="bg-rose-950/30 border-rose-800/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base text-rose-300 flex items-center gap-2">
                      <AlertOctagon className="w-4 h-4" /> Manual Review Queue ({manualReviewQueue.length})
                    </CardTitle>
                    <CardDescription className="text-rose-400/70 text-xs">
                      Bu job'lar maksimum retry sayısını aştı ve manuel inceleme gerektiriyor
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {manualReviewQueue.map((j) => (
                      <div key={j.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-rose-800/30">
                        <div className="flex items-center gap-3">
                          <div className="flex flex-col">
                            <span className="text-sm text-white font-medium">{j.sync_type} ({j.direction})</span>
                            <span className="text-xs text-slate-500">{j.id?.slice(0, 8)} &middot; {j.last_error?.slice(0, 60)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button size="sm" className="text-xs h-7 bg-amber-600 hover:bg-amber-700"
                            onClick={() => handleRetryJob(j.id)} data-testid={`retry-job-${j.id?.slice(0, 8)}`}>
                            <RotateCcw className="w-3 h-3 mr-1" /> Retry
                          </Button>
                          <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700 text-slate-400"
                            onClick={() => handleDismissJob(j.id)} data-testid={`dismiss-job-${j.id?.slice(0, 8)}`}>
                            Dismiss
                          </Button>
                          <Button size="sm" variant="ghost" className="text-xs h-7 text-slate-400"
                            onClick={() => handleViewJobDetail(j.id)}>
                            <Eye className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Sync History */}
              <Card className="bg-slate-900/50 border-slate-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base text-white">Sync History</CardTitle>
                </CardHeader>
                <CardContent>
                  {syncJobs.length > 0 ? (
                    <div className="space-y-2">
                      {syncJobs.map((j) => (
                        <div key={j.id}
                          className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-800 hover:border-slate-700 transition-colors cursor-pointer"
                          onClick={() => handleViewJobDetail(j.id)}
                          data-testid={`sync-job-row-${j.id?.slice(0, 8)}`}
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex flex-col">
                              <div className="flex items-center gap-2">
                                <span className="text-sm text-white font-medium">{j.sync_type} ({j.direction})</span>
                                {j.change_types?.length > 0 && (
                                  <div className="flex gap-1">
                                    {j.change_types.slice(0, 3).map((ct) => (
                                      <Badge key={ct} variant="outline" className="text-[10px] border-slate-700 text-slate-500 py-0">
                                        {ct.replace('_changed', '').replace('_', ' ')}
                                      </Badge>
                                    ))}
                                    {j.change_types.length > 3 && (
                                      <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-500 py-0">+{j.change_types.length - 3}</Badge>
                                    )}
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-xs text-slate-500">{j.id?.slice(0, 8)}</span>
                                <span className="text-xs text-slate-600">&middot;</span>
                                <span className="text-xs text-slate-500">{new Date(j.created_at).toLocaleString('tr-TR')}</span>
                                {j.duration_ms != null && (
                                  <>
                                    <span className="text-xs text-slate-600">&middot;</span>
                                    <span className="text-xs text-slate-500 font-mono flex items-center gap-0.5">
                                      <Timer className="w-3 h-3" /> {j.duration_ms}ms
                                    </span>
                                  </>
                                )}
                                {j.triggered_by && (
                                  <>
                                    <span className="text-xs text-slate-600">&middot;</span>
                                    <span className="text-xs text-slate-500">{j.triggered_by}</span>
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            {j.total_changes_detected > 0 && (
                              <div className="text-right">
                                <span className="text-[10px] text-slate-500 block">delta</span>
                                <span className="text-xs text-slate-400">{j.total_changes_after_coalescing || j.total_changes_detected}/{j.total_changes_detected}</span>
                              </div>
                            )}
                            <div className="text-right">
                              <span className="text-[10px] text-slate-500 block">events</span>
                              <span className="text-xs text-slate-400">{j.completed_events || 0}/{j.total_events || 0}</span>
                            </div>
                            <StatusBadge status={j.status} />
                            <ChevronRight className="w-4 h-4 text-slate-600" />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-slate-500 text-sm">Henüz sync job yok</div>
                  )}
                </CardContent>
              </Card>
            </div>
    </>
  );
}
