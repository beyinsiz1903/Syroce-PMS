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

export default function ConnectorsTab(props) {
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
            <div className="space-y-3">
              {connectors.map((c) => (
                <Card key={c.connector_id} className="bg-slate-900/50 border-slate-800">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full ${c.status === 'active' ? 'bg-emerald-400' : c.status === 'paused' ? 'bg-amber-400' : 'bg-slate-500'}`} />
                        <div>
                          <p className="font-medium text-white">{c.display_name || c.provider}</p>
                          <p className="text-xs text-slate-500">{c.provider} &middot; {c.connector_id?.slice(0, 8)}</p>
                        </div>
                        <StatusBadge status={c.status} />
                        <HealthBadge health={c.health} />
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700"
                          onClick={() => handleTestConnection(c.connector_id)} data-testid={`test-conn-${c.connector_id}`}>
                          Test
                        </Button>
                        {c.status !== 'active' && (
                          <Button size="sm" className="text-xs h-7 bg-emerald-600"
                            onClick={() => handleActivate(c.connector_id)}>
                            Activate
                          </Button>
                        )}
                        {c.status === 'active' && (
                          <Button size="sm" variant="outline" className="text-xs h-7 border-amber-700 text-amber-400"
                            onClick={() => handlePause(c.connector_id)}>
                            Pause
                          </Button>
                        )}
                      </div>
                    </div>
                    {c.last_successful_sync && (
                      <p className="text-xs text-slate-500 mt-2">
                        <Clock className="w-3 h-3 inline mr-1" />
                        Son sync: {new Date(c.last_successful_sync).toLocaleString('tr-TR')}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
    </>
  );
}
