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

export default function MappingsTab(props) {
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
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Label className="text-slate-400">Connector:</Label>
                  <select
                    className="bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-sm text-white"
                    value={selectedConnector || ''}
                    onChange={(e) => {
                      setSelectedConnector(e.target.value);
                      fetchMappings(e.target.value);
                      fetchMappingReadiness(e.target.value);
                      setMappingFilter('all');
                    }}
                    data-testid="mapping-connector-select"
                  >
                    <option value="">Secin...</option>
                    {connectors.map((c) => (
                      <option key={c.connector_id} value={c.connector_id}>{c.display_name || c.provider}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  {selectedConnector && (
                    <Button data-testid="validate-all-mappings-btn" size="sm" variant="outline"
                      className="border-slate-700 text-slate-300" onClick={handleValidateAllMappings}>
                      <Shield className="w-4 h-4 mr-1" /> Tumunu Dogrula
                    </Button>
                  )}
                  <Button data-testid="add-mapping-btn" size="sm" onClick={() => setShowNewMapping(true)} disabled={!selectedConnector}
                    className="bg-blue-600 hover:bg-blue-700">
                    <Plus className="w-4 h-4 mr-1" /> {t('cm.components_integrationhub_tabs_MappingsTab.mapping_ekle')}
                  </Button>
                </div>
              </div>

              {/* Readiness Score Card */}
              {selectedConnector && mappingReadiness && (
                <Card data-testid="mapping-readiness-card" className="bg-slate-900/50 border-slate-800">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-medium text-slate-300">Sync Readiness</span>
                        <span data-testid="readiness-score" className={`text-lg font-bold ${
                          (mappingReadiness.readiness_score || 0) >= 80 ? 'text-emerald-400' :
                          (mappingReadiness.readiness_score || 0) >= 50 ? 'text-amber-400' : 'text-red-400'
                        }`}>
                          %{mappingReadiness.readiness_score || 0}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-xs">
                        <span className="text-slate-500">
                          {t('cm.components_integrationhub_tabs_MappingsTab.toplam')} <span className="text-slate-300">{mappingReadiness.total_mappings || 0}</span>
                        </span>
                        {(mappingReadiness.missing_count || 0) > 0 && (
                          <span data-testid="missing-count" className="text-amber-400">
                            Eksik: {mappingReadiness.missing_count}
                          </span>
                        )}
                        {(mappingReadiness.invalid_count || 0) > 0 && (
                          <span data-testid="invalid-count" className="text-red-400">
                            {t('cm.components_integrationhub_tabs_MappingsTab.gecersiz')} {mappingReadiness.invalid_count}
                          </span>
                        )}
                        {(mappingReadiness.duplicate_count || 0) > 0 && (
                          <span data-testid="duplicate-count" className="text-violet-400">
                            Duplikat: {mappingReadiness.duplicate_count}
                          </span>
                        )}
                      </div>
                    </div>
                    {/* Progress Bar */}
                    <div data-testid="readiness-progress-bar" className="w-full bg-slate-800 rounded-full h-2.5">
                      <div className={`h-2.5 rounded-full transition-all duration-500 ${
                        (mappingReadiness.readiness_score || 0) >= 80 ? 'bg-emerald-500' :
                        (mappingReadiness.readiness_score || 0) >= 50 ? 'bg-amber-500' : 'bg-red-500'
                      }`} style={{ width: `${mappingReadiness.readiness_score || 0}%` }} />
                    </div>
                    {/* Blocked Reasons */}
                    {mappingReadiness.blocked_reasons?.length > 0 && (
                      <div className="mt-3 space-y-1">
                        {mappingReadiness.blocked_reasons.map((reason, i) => (
                          <div key={i} className="flex items-center gap-2 text-xs text-red-400/80">
                            <AlertCircle className="w-3 h-3 flex-shrink-0" />
                            <span>{reason}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Mapping Filters */}
              {selectedConnector && mappings.length > 0 && (
                <div className="flex items-center gap-2" data-testid="mapping-filters">
                  {[
                    { key: 'all', label: 'Tumu', count: mappings.length },
                    { key: 'valid', label: 'Geçerli', count: mappings.filter(m => m.validation_status === 'valid').length },
                    { key: 'invalid', label: 'Geçersiz', count: mappings.filter(m => m.validation_status === 'invalid').length },
                    { key: 'not_validated', label: 'Dogrulanmamis', count: mappings.filter(m => !m.validation_status || m.validation_status === 'not_validated').length },
                    { key: 'inactive', label: 'Inaktif', count: mappings.filter(m => m.status === 'inactive').length },
                  ].filter(f => f.key === 'all' || f.count > 0).map(f => (
                    <Button key={f.key} size="sm" variant={mappingFilter === f.key ? 'default' : 'outline'}
                      className={`text-xs h-7 ${mappingFilter === f.key ? 'bg-blue-600 hover:bg-blue-700' : 'border-slate-700 text-slate-400'}`}
                      onClick={() => setMappingFilter(f.key)}
                      data-testid={`mapping-filter-${f.key}`}
                    >
                      {f.label} ({f.count})
                    </Button>
                  ))}
                </div>
              )}

              {/* Mapping Table */}
              {mappings.length > 0 ? (
                <div className="border border-slate-800 rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-800/50 text-slate-400">
                      <tr>
                        <th className="text-left px-4 py-2">Tip</th>
                        <th className="text-left px-4 py-2">PMS Entity</th>
                        <th className="text-center px-4 py-2"><ArrowUpDown className="w-3 h-3 inline" /></th>
                        <th className="text-left px-4 py-2">External Entity</th>
                        <th className="text-left px-4 py-2">{t('cm.components_integrationhub_tabs_MappingsTab.durum')}</th>
                        <th className="text-left px-4 py-2">Dogrulama</th>
                        <th className="text-right px-4 py-2">Islemler</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {mappings.filter(m => {
                        if (mappingFilter === 'all') return true;
                        if (mappingFilter === 'valid') return m.validation_status === 'valid';
                        if (mappingFilter === 'invalid') return m.validation_status === 'invalid';
                        if (mappingFilter === 'not_validated') return !m.validation_status || m.validation_status === 'not_validated';
                        if (mappingFilter === 'inactive') return m.status === 'inactive';
                        return true;
                      }).map((m) => (
                        <tr key={m.id} className="text-slate-300 hover:bg-slate-800/30" data-testid={`mapping-row-${m.id?.slice(0, 8)}`}>
                          <td className="px-4 py-2">
                            <Badge variant="outline" className="text-xs border-slate-700">{m.entity_type}</Badge>
                          </td>
                          <td className="px-4 py-2">{m.pms_entity_name || m.pms_entity_id}</td>
                          <td className="px-4 py-2 text-center"><Link2 className="w-4 h-4 inline text-slate-500" /></td>
                          <td className="px-4 py-2">{m.external_entity_name || m.external_entity_id}</td>
                          <td className="px-4 py-2"><StatusBadge status={m.status} /></td>
                          <td className="px-4 py-2">
                            {m.validation_status === 'valid' && (
                              <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 border text-[10px]" data-testid="badge-valid">
                                <CheckCircle className="w-2.5 h-2.5 mr-0.5" /> valid
                              </Badge>
                            )}
                            {m.validation_status === 'invalid' && (
                              <Badge className="bg-red-500/15 text-red-400 border-red-500/30 border text-[10px]" data-testid="badge-invalid"
                                title={m.invalid_reason || ''}>
                                <XCircle className="w-2.5 h-2.5 mr-0.5" /> invalid
                              </Badge>
                            )}
                            {(!m.validation_status || m.validation_status === 'not_validated') && (
                              <Badge className="bg-slate-500/15 text-slate-500 border-slate-600 border text-[10px]" data-testid="badge-not-validated">
                                <Clock className="w-2.5 h-2.5 mr-0.5" /> pending
                              </Badge>
                            )}
                          </td>
                          <td className="px-4 py-2 text-right">
                            <div className="flex items-center gap-1 justify-end">
                              <Button size="sm" variant="ghost" className="text-xs h-6 px-2 text-slate-400 hover:text-white"
                                onClick={() => handleValidateMapping(m.id)} data-testid={`validate-mapping-${m.id?.slice(0, 8)}`}
                                title="Dogrula">
                                <Shield className="w-3 h-3" />
                              </Button>
                              {m.status === 'active' && (
                                <Button size="sm" variant="ghost" className="text-xs h-6 px-2 text-slate-400 hover:text-amber-400"
                                  onClick={() => handleDeactivateMapping(m.id)} data-testid={`deactivate-mapping-${m.id?.slice(0, 8)}`}
                                  title="Deaktif Et">
                                  <Ban className="w-3 h-3" />
                                </Button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : selectedConnector ? (
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardContent className="p-8 text-center">
                    <Unlink className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-slate-400 text-sm">{t('cm.components_integrationhub_tabs_MappingsTab.bu_connector_icin_mapping_yok')}</p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardContent className="p-8 text-center">
                    <Map className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-slate-400 text-sm">{t('cm.components_integrationhub_tabs_MappingsTab.connector_secin')}</p>
                  </CardContent>
                </Card>
              )}
            </div>
    </>
  );
}
