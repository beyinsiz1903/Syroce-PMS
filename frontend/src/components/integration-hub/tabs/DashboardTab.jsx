import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Network, Plus, RefreshCw, CheckCircle, AlertTriangle, XCircle, Clock, ArrowUpDown, Link2, Unlink, Shield, Activity, FileText, Download, Eye, ChevronRight, Zap, Settings, Database, Map, Loader2, Wifi, Key, Home, BedDouble, DollarSign, FileCode, RotateCcw, AlertOctagon, ChevronDown, ChevronUp, Timer, UserCheck, Ban, PackageCheck, AlertCircle, MailCheck, MailX, Search, Filter, ExternalLink } from 'lucide-react';
import { HealthBadge, StatusBadge, AckBadge } from '../badges';
export default function DashboardTab(props) {
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
  return <>
            <div className="grid md:grid-cols-2 gap-4">
              {connectors.map(c => <Card key={c.connector_id} className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-base text-white">{c.display_name || c.provider}</CardTitle>
                        <StatusBadge status={c.status} />
                      </div>
                      <HealthBadge health={c.health} />
                    </div>
                    <CardDescription className="text-xs text-slate-500">
                      {c.provider} &middot; Total syncs: {c.total_syncs || 0}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="pt-0 space-y-2">
                    {c.reasons?.length > 0 && <div className="text-xs text-amber-400/80 space-y-0.5">
                        {c.reasons.map((r, i) => <p key={r.id || i}>&#9888; {r}</p>)}
                      </div>}
                    <div className="flex gap-2 flex-wrap">
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700" onClick={() => handleSyncInventory(c.connector_id)} data-testid={`sync-inv-${c.connector_id}`}>
                        <ArrowUpDown className="w-3 h-3 mr-1" /> Push Inventory
                      </Button>
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700" onClick={() => handleSyncRates(c.connector_id)}>
                        <Zap className="w-3 h-3 mr-1" /> Push Rates
                      </Button>
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700" onClick={() => handlePullReservations(c.connector_id)}>
                        <Download className="w-3 h-3 mr-1" /> Pull Reservations
                      </Button>
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700" onClick={() => handleRunReconciliation(c.connector_id)}>
                        <Shield className="w-3 h-3 mr-1" /> Reconcile
                      </Button>
                    </div>
                  </CardContent>
                </Card>)}
              {connectors.length === 0 && !loading && <Card className="bg-slate-900/50 border-slate-800 col-span-2">
                  <CardContent className="p-12 text-center">
                    <Network className="w-12 h-12 mx-auto text-slate-600 mb-3" />
                    <p className="text-slate-400 text-sm">{t('cm.components_integrationhub_tabs_DashboardTab.henuz_connector_tanimlanmamis')}</p>
                    <Button size="sm" onClick={() => setShowNewConnector(true)} className="mt-3 bg-blue-600">
                      <Plus className="w-4 h-4 mr-1" /> {t('cm.components_integrationhub_tabs_DashboardTab.ilk_connector_i_ekle')}
                    </Button>
                  </CardContent>
                </Card>}
            </div>
    </>;
}