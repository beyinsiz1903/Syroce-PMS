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

export default function ReconciliationTab(props) {
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
                <CardTitle className="text-base text-white">Reconciliation Issues</CardTitle>
              </CardHeader>
              <CardContent>
                {issues.length > 0 ? (
                  <div className="space-y-2">
                    {issues.map((issue) => (
                      <div key={issue.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                        <div>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-xs border-slate-700">{issue.issue_type}</Badge>
                            <Badge className={`text-xs ${issue.severity === 'critical' ? 'bg-red-500/15 text-red-400' : issue.severity === 'high' ? 'bg-amber-500/15 text-amber-400' : 'bg-slate-500/15 text-slate-400'} border`}>
                              {issue.severity}
                            </Badge>
                          </div>
                          <p className="text-sm text-slate-300 mt-1">{issue.description}</p>
                        </div>
                        <Button size="sm" variant="outline" className="text-xs h-7 border-emerald-700 text-emerald-400"
                          onClick={() => handleResolveIssue(issue.id)}>
                          Resolve
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <CheckCircle className="w-10 h-10 mx-auto text-emerald-500/50 mb-2" />
                    <p className="text-slate-500 text-sm">{t('cm.components_integrationhub_tabs_ReconciliationTab.acik_reconciliation_sorunu_yok')}</p>
                  </div>
                )}
              </CardContent>
            </Card>
    </>
  );
}
