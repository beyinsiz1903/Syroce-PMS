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

export default function AuditTab(props) {
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
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-white">Integration Audit Log</CardTitle>
              </CardHeader>
              <CardContent>
                {auditLogs.length > 0 ? (
                  <div className="space-y-1.5">
                    {auditLogs.map((log) => (
                      <div key={log.id} className="flex items-center gap-3 px-3 py-2 rounded bg-slate-800/20 text-xs">
                        <span className="text-slate-500 w-40 shrink-0">{new Date(log.created_at).toLocaleString('tr-TR')}</span>
                        <Badge variant="outline" className="text-xs border-slate-700 shrink-0">{log.action}</Badge>
                        <span className="text-slate-400 truncate">{log.entity_type} {log.entity_id?.slice(0, 8)}</span>
                        <span className="text-slate-600 ml-auto">{log.actor_type}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-slate-500 text-sm">{t('cm.components_integrationhub_tabs_AuditTab.audit_log_bos')}</div>
                )}
              </CardContent>
            </Card>
    </>
  );
}
