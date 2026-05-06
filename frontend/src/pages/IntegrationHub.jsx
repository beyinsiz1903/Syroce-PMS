import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Network, Plus, RefreshCw, CheckCircle, AlertTriangle, XCircle,
  Clock, ArrowUpDown, Link2, Unlink, Shield, Activity, FileText,
  Download, Eye, ChevronRight, Zap, Settings, Database, Map,
  Loader2, Wifi, Key, Home, BedDouble, DollarSign, FileCode,
  RotateCcw, AlertOctagon, ChevronDown, ChevronUp, Timer,
  UserCheck, Ban, PackageCheck, AlertCircle, MailCheck, MailX,
  Search, Filter, ExternalLink
} from 'lucide-react';

const API_BASE = '/channel-manager/v2';

import { HealthBadge, StatusBadge, AckBadge } from '@/components/integration-hub/badges';
import DashboardTab from '@/components/integration-hub/tabs/DashboardTab';
import ConnectorsTab from '@/components/integration-hub/tabs/ConnectorsTab';
import MappingsTab from '@/components/integration-hub/tabs/MappingsTab';
import SyncTab from '@/components/integration-hub/tabs/SyncTab';
import ReservationsTab from '@/components/integration-hub/tabs/ReservationsTab';
import ReconciliationTab from '@/components/integration-hub/tabs/ReconciliationTab';
import AuditTab from '@/components/integration-hub/tabs/AuditTab';


const IntegrationHub = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [connectors, setConnectors] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [syncJobs, setSyncJobs] = useState([]);
  const [importedReservations, setImportedReservations] = useState([]);
  const [issues, setIssues] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNewConnector, setShowNewConnector] = useState(false);
  const [showNewMapping, setShowNewMapping] = useState(false);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [newConnector, setNewConnector] = useState({
    provider: 'hotelrunner', display_name: '', credentials: { token: '', hr_id: '' },
  });
  const [newMapping, setNewMapping] = useState({
    connector_id: '', entity_type: 'room_type',
    pms_entity_id: '', pms_entity_name: '',
    external_entity_id: '', external_entity_name: '',
  });
  const [testResult, setTestResult] = useState(null);
  const [showTestResult, setShowTestResult] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobEvents, setJobEvents] = useState([]);
  const [showJobDetail, setShowJobDetail] = useState(false);
  const [jobDetailLoading, setJobDetailLoading] = useState(false);
  const [manualReviewQueue, setManualReviewQueue] = useState([]);
  const [importBatches, setImportBatches] = useState([]);
  const [reservationReviewQueue, setReservationReviewQueue] = useState([]);
  const [selectedReservation, setSelectedReservation] = useState(null);
  const [showReservationDetail, setShowReservationDetail] = useState(false);
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [showBatchDetail, setShowBatchDetail] = useState(false);
  const [batchReservations, setBatchReservations] = useState([]);
  const [batchDetailLoading, setBatchDetailLoading] = useState(false);
  const [mappingReadiness, setMappingReadiness] = useState(null);
  const [mappingFilter, setMappingFilter] = useState('all');
  const [pullLoading, setPullLoading] = useState(false);

  const fetchDashboard = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/dashboard`);
      setDashboard(data);
      setConnectors(data.connectors || []);
    } catch { /* silent */ }
  }, []);

  const fetchConnectors = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/connectors`);
      setConnectors(data.connectors || []);
    } catch { /* silent */ }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    await fetchDashboard();
    try {
      const [jobsRes, importRes, issuesRes, auditRes, reviewRes, batchRes, resReviewRes] = await Promise.all([
        axios.get(`${API_BASE}/sync/jobs`).catch(() => ({ data: { jobs: [] } })),
        axios.get(`${API_BASE}/reservations/imported`).catch(() => ({ data: { reservations: [] } })),
        axios.get(`${API_BASE}/reconciliation/issues`).catch(() => ({ data: { issues: [] } })),
        axios.get(`${API_BASE}/audit`).catch(() => ({ data: { logs: [] } })),
        axios.get(`${API_BASE}/sync/manual-review`).catch(() => ({ data: { queue: [] } })),
        axios.get(`${API_BASE}/reservations/batches`).catch(() => ({ data: { batches: [] } })),
        axios.get(`${API_BASE}/reservations/review-queue`).catch(() => ({ data: { queue: [] } })),
      ]);
      setSyncJobs(jobsRes.data.jobs || []);
      setImportedReservations(importRes.data.reservations || []);
      setIssues(issuesRes.data.issues || []);
      setAuditLogs(auditRes.data.logs || []);
      setManualReviewQueue(reviewRes.data.queue || []);
      setImportBatches(batchRes.data.batches || []);
      setReservationReviewQueue(resReviewRes.data.queue || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [fetchDashboard]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreateConnector = async () => {
    try {
      await axios.post(`${API_BASE}/connectors`, newConnector);
      toast.success('Connector oluşturuldu');
      setShowNewConnector(false);
      setNewConnector({ provider: 'hotelrunner', display_name: '', credentials: { token: '', hr_id: '' } });
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleActivate = async (id) => {
    try {
      await axios.post(`${API_BASE}/connectors/${id}/activate`);
      toast.success('Connector aktifleştirildi');
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handlePause = async (id) => {
    try {
      await axios.post(`${API_BASE}/connectors/${id}/pause`);
      toast.success('Connector duraklatıldı');
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleTestConnection = async (id) => {
    setTestLoading(true);
    setTestResult(null);
    setShowTestResult(true);
    try {
      const { data } = await axios.post(`${API_BASE}/connectors/${id}/test`);
      setTestResult(data);
    } catch (e) {
      setTestResult({
        success: false,
        summary: 'Bağlantı testi başarısız oldu',
        tested_at: new Date().toISOString(),
        total_latency_ms: 0,
        auth_status: { status: 'fail', latency_ms: 0, error_code: 'NETWORK', message: 'Sunucuya ulaşılamadı' },
        property_access_status: { status: 'fail', latency_ms: 0, error_code: 'SKIPPED', message: 'Önceki adım başarısız' },
        inventory_read_status: { status: 'fail', latency_ms: 0, error_code: 'SKIPPED', message: 'Önceki adım başarısız' },
        rate_read_status: { status: 'fail', latency_ms: 0, error_code: 'SKIPPED', message: 'Önceki adım başarısız' },
        xml_connectivity_status: { status: 'fail', latency_ms: 0, error_code: 'SKIPPED', message: 'Önceki adım başarısız' },
      });
    } finally {
      setTestLoading(false);
    }
  };

  const handleCreateMapping = async () => {
    try {
      const payload = { ...newMapping, connector_id: selectedConnector };
      await axios.post(`${API_BASE}/mappings`, payload);
      toast.success('Mapping oluşturuldu');
      setShowNewMapping(false);
      fetchMappings(selectedConnector);
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const fetchMappings = async (connectorId) => {
    if (!connectorId) return;
    try {
      const { data } = await axios.get(`${API_BASE}/mappings/${connectorId}`);
      setMappings(data.mappings || []);
    } catch { setMappings([]); }
  };

  const fetchMappingReadiness = async (connectorId) => {
    if (!connectorId) return;
    try {
      // Use the correct endpoint: /mappings/{connector_id}/sync-readiness
      const { data } = await axios.get(`${API_BASE}/mappings/${connectorId}/sync-readiness`);
      // Map the backend response to expected frontend format
      setMappingReadiness({
        readiness_score: data.score || 0,
        total_mappings: data.total_mappings || 0,
        missing_count: data.missing_mappings?.length || 0,
        invalid_count: data.invalid_mappings_count || 0,
        duplicate_count: 0,
        blocked_reasons: data.blocked_reasons || [],
      });
    } catch { setMappingReadiness(null); }
  };

  const handleValidateAllMappings = async () => {
    if (!selectedConnector) return;
    try {
      // Use the correct endpoint: /mappings/{connector_id}/validate
      const { data } = await axios.post(`${API_BASE}/mappings/${selectedConnector}/validate`);
      toast.success(`Dogrulama tamamlandi: ${data.validated || data.total || 0} mapping kontrol edildi`);
      fetchMappings(selectedConnector);
      fetchMappingReadiness(selectedConnector);
    } catch (e) { toast.error(e.response?.data?.detail || 'Doğrulama başarısız'); }
  };

  const handleValidateMapping = async (mappingId) => {
    if (!selectedConnector) return;
    try {
      // Use the correct endpoint: /mappings/{connector_id}/validate/{mapping_id}
      await axios.post(`${API_BASE}/mappings/${selectedConnector}/validate/${mappingId}`);
      toast.success('Mapping dogrulandi');
      fetchMappings(selectedConnector);
      fetchMappingReadiness(selectedConnector);
    } catch (e) { toast.error(e.response?.data?.detail || 'Doğrulama başarısız'); }
  };

  const handleDeactivateMapping = async (mappingId) => {
    try {
      await axios.put(`${API_BASE}/mappings/${mappingId}`, { status: 'inactive' });
      toast.success('Mapping deaktif edildi');
      fetchMappings(selectedConnector);
      fetchMappingReadiness(selectedConnector);
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleSyncInventory = async (connectorId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/sync/inventory`, { connector_id: connectorId, reason: 'Manual trigger' });
      toast.success(`Sync başlatıldı (Job: ${data.job_id?.slice(0, 8)})`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Sync başarısız'); }
  };

  const handleSyncRates = async (connectorId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/sync/rates`, { connector_id: connectorId, reason: 'Manual rate sync' });
      toast.success(`Rate sync başlatıldı (Job: ${data.job_id?.slice(0, 8)})`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Rate sync başarısız'); }
  };

  const handlePullReservations = async (connectorId) => {
    setPullLoading(true);
    try {
      const { data } = await axios.post(`${API_BASE}/reservations/pull`, { connector_id: connectorId });
      const summary = [];
      if (data.new > 0) summary.push(`${data.new} yeni`);
      if (data.modified > 0) summary.push(`${data.modified} değişiklik`);
      if (data.cancelled > 0) summary.push(`${data.cancelled} iptal`);
      if (data.duplicate > 0) summary.push(`${data.duplicate} duplikat`);
      if (data.review > 0) summary.push(`${data.review} inceleme`);
      if (data.conflict > 0) summary.push(`${data.conflict} çakışma`);
      const msg = summary.length > 0 ? summary.join(', ') : 'Yeni kayıt yok';
      toast.success(`Rezervasyon çekme tamamlandı: ${data.total || 0} kayıt — ${msg}`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Rezervasyon çekme başarısız'); }
    setPullLoading(false);
  };

  const handleViewBatchDetail = async (batchId) => {
    setBatchDetailLoading(true);
    setShowBatchDetail(true);
    setBatchReservations([]);
    try {
      const { data } = await axios.get(`${API_BASE}/reservations/batches/${batchId}`);
      setSelectedBatch(data.batch || null);
      setBatchReservations(data.reservations || []);
    } catch { toast.error('Batch detayları yüklenemedi'); }
    setBatchDetailLoading(false);
  };

  const handleViewReservationDetail = async (reservationId) => {
    try {
      const { data } = await axios.get(`${API_BASE}/reservations/imported/${reservationId}`);
      setSelectedReservation(data);
      setShowReservationDetail(true);
    } catch { toast.error('Rezervasyon detayı yüklenemedi'); }
  };

  const handleReprocessReview = async (reservationId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/reservations/review-queue/${reservationId}/reprocess`);
      toast.success(`Yeniden işlendi: ${data.status}`);
      fetchData();
      setShowReservationDetail(false);
    } catch (e) { toast.error(e.response?.data?.detail || 'Reprocess başarısız'); }
  };

  const handleDismissReview = async (reservationId) => {
    try {
      await axios.post(`${API_BASE}/reservations/review-queue/${reservationId}/dismiss`);
      toast.success('Rezervasyon inceleme kuyruğundan kaldırıldı');
      fetchData();
      setShowReservationDetail(false);
    } catch (e) { toast.error(e.response?.data?.detail || 'Dismiss başarısız'); }
  };

  const handleRunReconciliation = async (connectorId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/reconciliation/run`, { connector_id: connectorId });
      toast.success(`Reconciliation tamamlandı: ${data.issues_found || 0} sorun bulundu`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Reconciliation başarısız'); }
  };

  const handleResolveIssue = async (issueId) => {
    try {
      await axios.post(`${API_BASE}/reconciliation/issues/${issueId}/resolve`, { resolution: 'Manual resolution' });
      toast.success('Sorun çözüldü');
      fetchData();
    } catch { toast.error('Çözüm başarısız'); }
  };

  const handleViewJobDetail = async (jobId) => {
    setJobDetailLoading(true);
    setShowJobDetail(true);
    setJobEvents([]);
    try {
      const { data } = await axios.get(`${API_BASE}/sync/jobs/${jobId}`);
      setSelectedJob(data.job || null);
      setJobEvents(data.events || []);
    } catch { toast.error('Job detayları yüklenemedi'); }
    setJobDetailLoading(false);
  };

  const handleRetryJob = async (jobId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/sync/manual-review/${jobId}/retry`);
      toast.success(`Retry tamamlandı: ${data.succeeded || 0} başarılı, ${data.still_failed || 0} hala başarısız`);
      fetchData();
      if (showJobDetail) handleViewJobDetail(jobId);
    } catch (e) { toast.error(e.response?.data?.detail || 'Retry başarısız'); }
  };

  const handleDismissJob = async (jobId) => {
    try {
      await axios.post(`${API_BASE}/sync/manual-review/${jobId}/dismiss`);
      toast.success('Job manual review\'dan kaldırıldı');
      fetchData();
      setShowJobDetail(false);
    } catch (e) { toast.error(e.response?.data?.detail || 'Dismiss başarısız'); }
  };

  const hs = dashboard?.health_summary || {};

  const ctx = { t, activeTab, setActiveTab, dashboard, setDashboard, connectors, setConnectors, mappings, setMappings, syncJobs, setSyncJobs, importedReservations, setImportedReservations, issues, setIssues, auditLogs, setAuditLogs, loading, setLoading, showNewConnector, setShowNewConnector, showNewMapping, setShowNewMapping, selectedConnector, setSelectedConnector, newConnector, setNewConnector, newMapping, setNewMapping, testResult, setTestResult, showTestResult, setShowTestResult, testLoading, setTestLoading, selectedJob, setSelectedJob, jobEvents, setJobEvents, showJobDetail, setShowJobDetail, jobDetailLoading, setJobDetailLoading, manualReviewQueue, setManualReviewQueue, importBatches, setImportBatches, reservationReviewQueue, setReservationReviewQueue, selectedReservation, setSelectedReservation, showReservationDetail, setShowReservationDetail, selectedBatch, setSelectedBatch, showBatchDetail, setShowBatchDetail, batchReservations, setBatchReservations, batchDetailLoading, setBatchDetailLoading, mappingReadiness, setMappingReadiness, mappingFilter, setMappingFilter, pullLoading, setPullLoading, fetchDashboard, fetchConnectors, fetchData, handleCreateConnector, handleActivate, handlePause, handleTestConnection, handleCreateMapping, fetchMappings, fetchMappingReadiness, handleValidateAllMappings, handleValidateMapping, handleDeactivateMapping, handleSyncInventory, handleSyncRates, handlePullReservations, handleViewBatchDetail, handleViewReservationDetail, handleReprocessReview, handleDismissReview, handleRunReconciliation, handleResolveIssue, handleViewJobDetail, handleRetryJob, handleDismissJob, hs };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="integration-hub">
      <div data-testid="integration-hub" className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t("techDashboards.integrationHub")}</h1>
            <p className="text-sm text-slate-400 mt-1">Channel Manager &middot; Connector Architecture</p>
          </div>
          <div className="flex items-center gap-3">
            <Button data-testid="refresh-btn" variant="outline" size="sm" onClick={fetchData} className="border-slate-700 text-slate-300">
              <RefreshCw className="w-4 h-4 mr-1" /> Yenile
            </Button>
            <Button data-testid="add-connector-btn" size="sm" onClick={() => setShowNewConnector(true)} className="bg-blue-600 hover:bg-blue-700">
              <Plus className="w-4 h-4 mr-1" /> Connector Ekle
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Connectors</p>
                  <p data-testid="total-connectors" className="text-2xl font-bold text-white">{dashboard?.total_connectors || 0}</p>
                </div>
                <Network className="w-8 h-8 text-blue-400 opacity-60" />
              </div>
              <p className="text-xs text-emerald-400 mt-1">{dashboard?.active_connectors || 0} active</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Health</p>
                  <p className="text-2xl font-bold text-white">{(hs.green || 0) + (hs.yellow || 0) + (hs.red || 0)}</p>
                </div>
                <Activity className="w-8 h-8 text-emerald-400 opacity-60" />
              </div>
              <div className="flex gap-2 mt-1 text-xs">
                <span className="text-emerald-400">{hs.green || 0} green</span>
                <span className="text-amber-400">{hs.yellow || 0} yellow</span>
                <span className="text-red-400">{hs.red || 0} red</span>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Sync Jobs</p>
                  <p className="text-2xl font-bold text-white">{syncJobs.length}</p>
                </div>
                <ArrowUpDown className="w-8 h-8 text-violet-400 opacity-60" />
              </div>
              <p className="text-xs text-slate-400 mt-1">Son 50 job</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Issues</p>
                  <p data-testid="open-issues" className="text-2xl font-bold text-white">{dashboard?.open_issue_count || 0}</p>
                </div>
                <AlertTriangle className="w-8 h-8 text-amber-400 opacity-60" />
              </div>
              <p className="text-xs text-amber-400 mt-1">Açık sorunlar</p>
            </CardContent>
          </Card>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-900/50 border border-slate-800">
            <TabsTrigger value="dashboard" className="data-[state=active]:bg-slate-700">
              <Activity className="w-4 h-4 mr-1" /> Dashboard
            </TabsTrigger>
            <TabsTrigger value="connectors" className="data-[state=active]:bg-slate-700">
              <Network className="w-4 h-4 mr-1" /> Connectors
            </TabsTrigger>
            <TabsTrigger value="mappings" className="data-[state=active]:bg-slate-700">
              <Map className="w-4 h-4 mr-1" /> Mappings
            </TabsTrigger>
            <TabsTrigger value="sync" className="data-[state=active]:bg-slate-700">
              <ArrowUpDown className="w-4 h-4 mr-1" /> Sync Jobs
            </TabsTrigger>
            <TabsTrigger value="reservations" className="data-[state=active]:bg-slate-700">
              <FileText className="w-4 h-4 mr-1" /> Reservations
            </TabsTrigger>
            <TabsTrigger value="reconciliation" className="data-[state=active]:bg-slate-700">
              <Shield className="w-4 h-4 mr-1" /> Reconciliation
            </TabsTrigger>
            <TabsTrigger value="audit" className="data-[state=active]:bg-slate-700">
              <Eye className="w-4 h-4 mr-1" /> Audit
            </TabsTrigger>
          </TabsList>

          {/* Dashboard Tab */}
          <TabsContent value="dashboard">
            <DashboardTab {...ctx} />
          </TabsContent>

          {/* Connectors Tab */}
          <TabsContent value="connectors">
            <ConnectorsTab {...ctx} />
          </TabsContent>

          {/* Mappings Tab */}
          <TabsContent value="mappings">
            <MappingsTab {...ctx} />
          </TabsContent>

          {/* Sync Jobs Tab */}
          <TabsContent value="sync">
            <SyncTab {...ctx} />
          </TabsContent>

          {/* Reservations Tab */}
          <TabsContent value="reservations">
            <ReservationsTab {...ctx} />
          </TabsContent>

          {/* Reconciliation Tab */}
          <TabsContent value="reconciliation">
            <ReconciliationTab {...ctx} />
          </TabsContent>

          {/* Audit Tab */}
          <TabsContent value="audit">
            <AuditTab {...ctx} />
          </TabsContent>
        </Tabs>

        {/* New Connector Dialog */}
        <Dialog open={showNewConnector} onOpenChange={setShowNewConnector}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white">
            <DialogHeader>
              <DialogTitle>Yeni Connector Ekle</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label className="text-slate-400">Provider</Label>
                <select
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white mt-1"
                  value={newConnector.provider}
                  onChange={(e) => setNewConnector({ ...newConnector, provider: e.target.value })}
                  data-testid="new-connector-provider"
                >
                  <option value="hotelrunner">HotelRunner</option>
                  <option value="exely">Exely (SOAP)</option>
                  <option value="siteminder">SiteMinder</option>
                  <option value="channex">Channex</option>
                </select>
              </div>
              <div>
                <Label className="text-slate-400">Display Name</Label>
                <Input
                  value={newConnector.display_name}
                  onChange={(e) => setNewConnector({ ...newConnector, display_name: e.target.value })}
                  placeholder="HotelRunner Production"
                  className="bg-slate-800 border-slate-700 text-white"
                  data-testid="new-connector-name"
                />
              </div>
              <div>
                <Label className="text-slate-400">Token</Label>
                <Input
                  value={newConnector.credentials.token}
                  onChange={(e) => setNewConnector({ ...newConnector, credentials: { ...newConnector.credentials, token: e.target.value } })}
                  placeholder="HotelRunner API Token"
                  className="bg-slate-800 border-slate-700 text-white"
                  data-testid="new-connector-token"
                />
              </div>
              <div>
                <Label className="text-slate-400">HR ID</Label>
                <Input
                  value={newConnector.credentials.hr_id}
                  onChange={(e) => setNewConnector({ ...newConnector, credentials: { ...newConnector.credentials, hr_id: e.target.value } })}
                  placeholder="HotelRunner Hotel ID"
                  className="bg-slate-800 border-slate-700 text-white"
                  data-testid="new-connector-hrid"
                />
              </div>
              <Button data-testid="create-connector-submit" className="w-full bg-blue-600" onClick={handleCreateConnector}>
                Connector Oluştur
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* New Mapping Dialog */}
        <Dialog open={showNewMapping} onOpenChange={setShowNewMapping}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white">
            <DialogHeader>
              <DialogTitle>Yeni Mapping Ekle</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label className="text-slate-400">Entity Type</Label>
                <select
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white mt-1"
                  value={newMapping.entity_type}
                  onChange={(e) => setNewMapping({ ...newMapping, entity_type: e.target.value })}
                  data-testid="new-mapping-type"
                >
                  <option value="room_type">Room Type</option>
                  <option value="rate_plan">Rate Plan</option>
                  <option value="meal_plan">Meal Plan</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-slate-400 text-xs">PMS Entity ID</Label>
                  <Input value={newMapping.pms_entity_id}
                    onChange={(e) => setNewMapping({ ...newMapping, pms_entity_id: e.target.value })}
                    placeholder="Standard" className="bg-slate-800 border-slate-700 text-white" />
                </div>
                <div>
                  <Label className="text-slate-400 text-xs">PMS Entity Name</Label>
                  <Input value={newMapping.pms_entity_name}
                    onChange={(e) => setNewMapping({ ...newMapping, pms_entity_name: e.target.value })}
                    placeholder="Standard Room" className="bg-slate-800 border-slate-700 text-white" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-slate-400 text-xs">External Entity ID</Label>
                  <Input value={newMapping.external_entity_id}
                    onChange={(e) => setNewMapping({ ...newMapping, external_entity_id: e.target.value })}
                    placeholder="STD_HR" className="bg-slate-800 border-slate-700 text-white" />
                </div>
                <div>
                  <Label className="text-slate-400 text-xs">External Entity Name</Label>
                  <Input value={newMapping.external_entity_name}
                    onChange={(e) => setNewMapping({ ...newMapping, external_entity_name: e.target.value })}
                    placeholder="Standard - HotelRunner" className="bg-slate-800 border-slate-700 text-white" />
                </div>
              </div>
              <Button data-testid="create-mapping-submit" className="w-full bg-blue-600"
                onClick={handleCreateMapping}>
                Mapping Oluştur
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Connection Test Result Dialog */}
        <Dialog open={showTestResult} onOpenChange={setShowTestResult}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-lg" data-testid="test-result-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Wifi className="w-5 h-5" />
                Bağlantı Test Sonuçları
              </DialogTitle>
            </DialogHeader>

            {testLoading ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3" data-testid="test-loading">
                <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
                <p className="text-sm text-slate-400">Bağlantı testleri çalıştırılıyor...</p>
                <p className="text-xs text-slate-500">5 farklı bağlantı noktası doğrulanıyor</p>
              </div>
            ) : testResult ? (
              <div className="space-y-4">
                {/* Overall Status */}
                <div className={`flex items-center justify-between p-3 rounded-lg border ${
                  testResult.success
                    ? 'bg-emerald-500/10 border-emerald-500/30'
                    : 'bg-red-500/10 border-red-500/30'
                }`} data-testid="test-overall-status">
                  <div className="flex items-center gap-2">
                    {testResult.success
                      ? <CheckCircle className="w-5 h-5 text-emerald-400" />
                      : <XCircle className="w-5 h-5 text-red-400" />}
                    <div>
                      <p className={`text-sm font-medium ${testResult.success ? 'text-emerald-300' : 'text-red-300'}`}>
                        {testResult.success ? 'Bağlantı Başarılı' : 'Bağlantı Başarısız'}
                      </p>
                      <p className="text-xs text-slate-400">{testResult.summary}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-400">Toplam Latency</p>
                    <p className="text-sm font-mono text-slate-300">{testResult.total_latency_ms}ms</p>
                  </div>
                </div>

                {/* Individual test steps */}
                <div className="space-y-2">
                  {[
                    { key: 'auth_status', label: 'Authentication', icon: Key, desc: 'Token ve kimlik doğrulama' },
                    { key: 'property_access_status', label: 'Property Access', icon: Home, desc: 'Otel erişim kontrolü' },
                    { key: 'inventory_read_status', label: 'Room Types', icon: BedDouble, desc: 'Oda tipleri okuma' },
                    { key: 'rate_read_status', label: 'Rate Plans', icon: DollarSign, desc: 'Fiyat planları okuma' },
                    { key: 'xml_connectivity_status', label: 'XML API', icon: FileCode, desc: 'OTA XML bağlantısı' },
                  ].map(({ key, label, icon: Icon, desc }) => {
                    const step = testResult[key];
                    if (!step) return null;
                    const isPassing = step.status === 'pass';
                    const isWarn = step.status === 'warn';
                    const isFail = step.status === 'fail';
                    return (
                      <div key={key}
                        className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                          isPassing ? 'bg-emerald-500/5 border-emerald-500/20' :
                          isWarn ? 'bg-amber-500/5 border-amber-500/20' :
                          'bg-red-500/5 border-red-500/20'
                        }`}
                        data-testid={`test-step-${key}`}
                      >
                        <div className={`mt-0.5 p-1.5 rounded ${
                          isPassing ? 'bg-emerald-500/20' : isWarn ? 'bg-amber-500/20' : 'bg-red-500/20'
                        }`}>
                          <Icon className={`w-4 h-4 ${
                            isPassing ? 'text-emerald-400' : isWarn ? 'text-amber-400' : 'text-red-400'
                          }`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-white">{label}</span>
                              {isPassing && <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />}
                              {isWarn && <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />}
                              {isFail && <XCircle className="w-3.5 h-3.5 text-red-400" />}
                            </div>
                            <span className="text-xs font-mono text-slate-500">{step.latency_ms}ms</span>
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                          {(isFail || isWarn) && step.message && (
                            <div className={`mt-1.5 px-2 py-1 rounded text-xs ${
                              isWarn ? 'bg-amber-500/10 text-amber-300' : 'bg-red-500/10 text-red-300'
                            }`}>
                              {step.message}
                            </div>
                          )}
                          {step.error_code && step.error_code !== 'SKIPPED' && isFail && (
                            <p className="text-[10px] text-slate-600 mt-1 font-mono">Hata kodu: {step.error_code}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Footer info */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                  <p className="text-[10px] text-slate-600">
                    Test zamanı: {testResult.tested_at ? new Date(testResult.tested_at).toLocaleString('tr-TR') : '-'}
                  </p>
                  {testResult.provider && (
                    <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-500">
                      {testResult.provider}
                    </Badge>
                  )}
                </div>
              </div>
            ) : null}
          </DialogContent>
        </Dialog>

        {/* Sync Job Detail Dialog */}
        <Dialog open={showJobDetail} onOpenChange={setShowJobDetail}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="job-detail-dialog" aria-describedby="job-detail-desc">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ArrowUpDown className="w-5 h-5" />
                Sync Job Detayı
              </DialogTitle>
            </DialogHeader>
            <p id="job-detail-desc" className="sr-only">Sync job lifecycle detayları, değişiklik istatistikleri ve event listesi</p>

            {jobDetailLoading ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
                <p className="text-sm text-slate-400">Job detayları yükleniyor...</p>
              </div>
            ) : selectedJob ? (
              <div className="space-y-4">
                {/* Job Header */}
                <div className="flex items-start justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-white">{selectedJob.sync_type} ({selectedJob.direction})</span>
                      <StatusBadge status={selectedJob.status} />
                    </div>
                    <div className="text-xs text-slate-500 space-y-0.5">
                      <p>ID: <span className="font-mono">{selectedJob.id?.slice(0, 12)}</span></p>
                      <p>Tetikleyen: {selectedJob.triggered_by} {selectedJob.trigger_reason ? `— ${selectedJob.trigger_reason}` : ''}</p>
                      <p>Tarih aralığı: {selectedJob.date_range_start} → {selectedJob.date_range_end}</p>
                    </div>
                  </div>
                  <div className="text-right text-xs text-slate-400">
                    {selectedJob.duration_ms != null && (
                      <p className="font-mono text-sm text-slate-300">{selectedJob.duration_ms}ms</p>
                    )}
                    <p>{new Date(selectedJob.created_at).toLocaleString('tr-TR')}</p>
                  </div>
                </div>

                {/* Lifecycle Timeline */}
                <div className="flex items-center gap-1 px-2 overflow-x-auto">
                  {['pending', 'batched', 'dispatched', 'succeeded'].map((step, idx) => {
                    const isActive = selectedJob.status === step;
                    const isFailed = selectedJob.status === 'failed' || selectedJob.status === 'manual_review';
                    const isPast = ['pending', 'batched', 'dispatched', 'succeeded'].indexOf(selectedJob.status) > idx
                      || (isFailed && idx <= 2);
                    const isFailStep = idx === 3 && isFailed;
                    return (
                      <div key={step} className="flex items-center gap-1">
                        <div className={`px-2.5 py-1 rounded text-[10px] font-medium border transition-colors ${
                          isActive ? 'bg-blue-500/20 border-blue-500/40 text-blue-300' :
                          isFailStep ? 'bg-red-500/20 border-red-500/40 text-red-300' :
                          isPast ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                          'bg-slate-800/50 border-slate-700 text-slate-600'
                        }`}>
                          {isFailStep ? (selectedJob.status === 'manual_review' ? 'manual review' : 'failed') : step}
                        </div>
                        {idx < 3 && <ChevronRight className="w-3 h-3 text-slate-700" />}
                      </div>
                    );
                  })}
                </div>

                {/* Delta Stats */}
                <div className="grid grid-cols-4 gap-3">
                  <div className="p-2.5 rounded-lg bg-slate-800/30 border border-slate-800 text-center">
                    <p className="text-[10px] text-slate-500">Algılanan</p>
                    <p className="text-lg font-bold text-white" data-testid="detected-count">{selectedJob.total_changes_detected || 0}</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-800/30 border border-slate-800 text-center">
                    <p className="text-[10px] text-slate-500">Birleştirilen</p>
                    <p className="text-lg font-bold text-white" data-testid="coalesced-count">{selectedJob.total_changes_after_coalescing || 0}</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
                    <p className="text-[10px] text-emerald-400">Başarılı</p>
                    <p className="text-lg font-bold text-emerald-300" data-testid="completed-count">{selectedJob.completed_events || 0}</p>
                  </div>
                  <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-center">
                    <p className="text-[10px] text-red-400">Başarısız</p>
                    <p className="text-lg font-bold text-red-300" data-testid="failed-count">{selectedJob.failed_events || 0}</p>
                  </div>
                </div>

                {/* Change Types */}
                {selectedJob.change_types?.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-1.5">Değişiklik Türleri</p>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedJob.change_types.map((ct) => (
                        <Badge key={ct} variant="outline" className="text-xs border-slate-700 text-slate-400">
                          {ct.replace('_changed', '').replace(/_/g, ' ')}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Error Display */}
                {selectedJob.last_error && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                    <p className="text-xs text-red-400 font-medium mb-1">Son Hata</p>
                    <p className="text-xs text-red-300 font-mono">{selectedJob.last_error}</p>
                  </div>
                )}

                {/* Action Buttons for failed/manual_review */}
                {(selectedJob.status === 'failed' || selectedJob.status === 'manual_review') && (
                  <div className="flex gap-2">
                    <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-xs"
                      onClick={() => handleRetryJob(selectedJob.id)} data-testid="detail-retry-btn">
                      <RotateCcw className="w-3 h-3 mr-1" /> Yeniden Dene
                    </Button>
                    {selectedJob.status === 'manual_review' && (
                      <Button size="sm" variant="outline" className="text-xs border-slate-700 text-slate-400"
                        onClick={() => handleDismissJob(selectedJob.id)} data-testid="detail-dismiss-btn">
                        Dismiss
                      </Button>
                    )}
                  </div>
                )}

                {/* Event List */}
                {jobEvents.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-2">Sync Events ({jobEvents.length})</p>
                    <div className="space-y-1.5 max-h-60 overflow-y-auto">
                      {jobEvents.map((evt) => (
                        <div key={evt.id} className="flex items-center justify-between p-2.5 rounded bg-slate-800/20 border border-slate-800/50" data-testid={`event-row-${evt.id?.slice(0, 8)}`}>
                          <div className="flex items-center gap-2 min-w-0">
                            <StatusBadge status={evt.status} />
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs text-white font-medium">{evt.sync_type}</span>
                                {evt.change_type && (
                                  <Badge variant="outline" className="text-[10px] border-slate-700 text-slate-500 py-0">
                                    {evt.change_type.replace('_changed', '').replace(/_/g, ' ')}
                                  </Badge>
                                )}
                                <span className="text-[10px] text-slate-600">batch #{evt.batch_index}</span>
                              </div>
                              {evt.error_message && (
                                <p className="text-[10px] text-red-400 truncate mt-0.5">{evt.error_message}</p>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-3 shrink-0">
                            {evt.coalesced_count > 1 && (
                              <span className="text-[10px] text-slate-500">{evt.coalesced_count} merged</span>
                            )}
                            {evt.latency_ms != null && (
                              <span className="text-xs font-mono text-slate-500">{evt.latency_ms}ms</span>
                            )}
                            {evt.retry_count > 0 && (
                              <span className="text-[10px] text-amber-400">retry:{evt.retry_count}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Timestamps */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                  <div className="flex gap-4 text-[10px] text-slate-600">
                    {selectedJob.started_at && <span>Start: {new Date(selectedJob.started_at).toLocaleTimeString('tr-TR')}</span>}
                    {selectedJob.batched_at && <span>Batch: {new Date(selectedJob.batched_at).toLocaleTimeString('tr-TR')}</span>}
                    {selectedJob.dispatched_at && <span>Dispatch: {new Date(selectedJob.dispatched_at).toLocaleTimeString('tr-TR')}</span>}
                    {selectedJob.completed_at && <span>End: {new Date(selectedJob.completed_at).toLocaleTimeString('tr-TR')}</span>}
                  </div>
                </div>
              </div>
            ) : null}
          </DialogContent>
        </Dialog>

        {/* Reservation Detail Dialog */}
        <Dialog open={showReservationDetail} onOpenChange={setShowReservationDetail}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-lg max-h-[85vh] overflow-y-auto" data-testid="reservation-detail-dialog" aria-describedby="res-detail-desc">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5" />
                Rezervasyon Detayı
              </DialogTitle>
            </DialogHeader>
            <p id="res-detail-desc" className="sr-only">İthal edilen rezervasyon detayları, durum bilgisi ve aksiyonlar</p>

            {selectedReservation ? (
              <div className="space-y-4">
                {/* Status Header */}
                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={selectedReservation.import_status} />
                    <AckBadge ackStatus={selectedReservation.ack_status} />
                    {selectedReservation.is_modification && <Badge variant="outline" className="text-[10px] border-cyan-700/50 text-cyan-400 py-0">modification</Badge>}
                    {selectedReservation.is_cancellation && <Badge variant="outline" className="text-[10px] border-red-700/50 text-red-400 py-0">cancellation</Badge>}
                  </div>
                  <span className="text-xs font-mono text-slate-500">{selectedReservation.id?.slice(0, 12)}</span>
                </div>

                {/* Guest & Stay Info */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                    <p className="text-[10px] text-slate-500 mb-1">Misafir</p>
                    <p className="text-sm text-white font-medium">{selectedReservation.guest_name || '-'}</p>
                    {selectedReservation.guest_email && <p className="text-xs text-slate-400">{selectedReservation.guest_email}</p>}
                    {selectedReservation.guest_phone && <p className="text-xs text-slate-400">{selectedReservation.guest_phone}</p>}
                  </div>
                  <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                    <p className="text-[10px] text-slate-500 mb-1">Konaklama</p>
                    <p className="text-sm text-white">{selectedReservation.arrival_date} → {selectedReservation.departure_date}</p>
                    <p className="text-xs text-slate-400">{selectedReservation.adult_count} yetişkin, {selectedReservation.child_count} çocuk</p>
                  </div>
                </div>

                {/* Booking & Payment */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                    <p className="text-[10px] text-slate-500 mb-1">Referans</p>
                    <p className="text-xs text-white font-mono">{selectedReservation.external_confirmation_number || selectedReservation.external_reservation_id?.slice(0, 16)}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{selectedReservation.channel_name}</p>
                    {selectedReservation.pms_booking_id && (
                      <p className="text-[10px] text-emerald-400 mt-1">PMS: {selectedReservation.pms_booking_id.slice(0, 12)}</p>
                    )}
                  </div>
                  <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                    <p className="text-[10px] text-slate-500 mb-1">Ödeme</p>
                    <p className="text-lg font-bold text-white">{selectedReservation.total_amount?.toLocaleString('tr-TR')} {selectedReservation.currency}</p>
                    {selectedReservation.payment_type && <p className="text-xs text-slate-400">{selectedReservation.payment_type}</p>}
                  </div>
                </div>

                {/* Mapping Info */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                    <p className="text-[10px] text-slate-500 mb-1">Oda Tipi</p>
                    <p className="text-xs text-white">{selectedReservation.room_type_external_id}</p>
                    {selectedReservation.room_type_mapped_id ? (
                      <p className="text-[10px] text-emerald-400">→ {selectedReservation.room_type_mapped_id}</p>
                    ) : (
                      <p className="text-[10px] text-amber-400">Mapping yok</p>
                    )}
                  </div>
                  <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                    <p className="text-[10px] text-slate-500 mb-1">Fiyat Planı</p>
                    <p className="text-xs text-white">{selectedReservation.rate_plan_external_id || '-'}</p>
                    {selectedReservation.rate_plan_mapped_id && (
                      <p className="text-[10px] text-emerald-400">→ {selectedReservation.rate_plan_mapped_id}</p>
                    )}
                  </div>
                </div>

                {/* Fingerprint */}
                {selectedReservation.payload_fingerprint && (
                  <div className="px-3 py-2 rounded bg-slate-800/20 border border-slate-800">
                    <span className="text-[10px] text-slate-500">Fingerprint: </span>
                    <span className="text-[10px] font-mono text-slate-400">{selectedReservation.payload_fingerprint}</span>
                  </div>
                )}

                {/* Review Info */}
                {selectedReservation.review_reason && (
                  <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle className="w-3 h-3 text-amber-400" />
                      <p className="text-xs text-amber-400 font-medium">İnceleme Sebebi</p>
                      {selectedReservation.review_reason_code && (
                        <Badge variant="outline" className="text-[10px] border-amber-700/50 text-amber-400 py-0">
                          {selectedReservation.review_reason_code.replace(/_/g, ' ')}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-amber-300">{selectedReservation.review_reason}</p>
                    {selectedReservation.suggested_action && (
                      <p className="text-[10px] text-amber-400/70 mt-1">Önerilen: {selectedReservation.suggested_action}</p>
                    )}
                  </div>
                )}

                {/* Conflict Info */}
                {selectedReservation.conflict_reason && (
                  <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20">
                    <p className="text-xs text-rose-400 font-medium mb-1">Çakışma Sebebi</p>
                    <p className="text-xs text-rose-300">{selectedReservation.conflict_reason}</p>
                  </div>
                )}

                {/* Error */}
                {selectedReservation.error_message && (
                  <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                    <p className="text-xs text-red-400 font-medium mb-1">Hata</p>
                    <p className="text-xs text-red-300 font-mono">{selectedReservation.error_message}</p>
                  </div>
                )}

                {/* Actions for review items */}
                {['review', 'conflict', 'out_of_order'].includes(selectedReservation.import_status) && (
                  <div className="flex gap-2 pt-2 border-t border-slate-800">
                    <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-xs"
                      onClick={() => handleReprocessReview(selectedReservation.id)} data-testid="detail-reprocess-btn">
                      <RotateCcw className="w-3 h-3 mr-1" /> Reprocess
                    </Button>
                    <Button size="sm" variant="outline" className="text-xs border-slate-700 text-slate-400"
                      onClick={() => handleDismissReview(selectedReservation.id)} data-testid="detail-dismiss-res-btn">
                      Dismiss
                    </Button>
                  </div>
                )}

                {/* Timestamps */}
                <div className="flex flex-wrap gap-3 pt-2 border-t border-slate-800 text-[10px] text-slate-600">
                  <span>Oluşturulma: {new Date(selectedReservation.created_at).toLocaleString('tr-TR')}</span>
                  {selectedReservation.reviewed_at && <span>İncelendi: {new Date(selectedReservation.reviewed_at).toLocaleString('tr-TR')}</span>}
                  {selectedReservation.reprocessed_at && <span>Reprocess: {new Date(selectedReservation.reprocessed_at).toLocaleString('tr-TR')}</span>}
                  {selectedReservation.ack_sent_at && <span>ACK: {new Date(selectedReservation.ack_sent_at).toLocaleString('tr-TR')}</span>}
                </div>
              </div>
            ) : null}
          </DialogContent>
        </Dialog>

        {/* Batch Detail Dialog */}
        <Dialog open={showBatchDetail} onOpenChange={setShowBatchDetail}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white sm:max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="batch-detail-dialog" aria-describedby="batch-detail-desc">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <PackageCheck className="w-5 h-5" />
                Import Batch Detayı
              </DialogTitle>
            </DialogHeader>
            <p id="batch-detail-desc" className="sr-only">Import batch detayları ve içerdiği rezervasyonlar</p>

            {batchDetailLoading ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <Loader2 className="w-8 h-8 animate-spin text-blue-400" />
                <p className="text-sm text-slate-400">Batch detayları yükleniyor...</p>
              </div>
            ) : selectedBatch ? (
              <div className="space-y-4">
                {/* Batch Header */}
                <div className="flex items-start justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-white font-mono">{selectedBatch.id?.slice(0, 12)}</span>
                      <StatusBadge status={selectedBatch.status} />
                    </div>
                    <div className="text-xs text-slate-500">
                      <p>Tetikleyen: {selectedBatch.triggered_by}</p>
                      {selectedBatch.pull_from && <p>Tarih aralığı: {selectedBatch.pull_from} → {selectedBatch.pull_to || '...'}</p>}
                    </div>
                  </div>
                  <div className="text-right text-xs text-slate-400">
                    {selectedBatch.duration_ms != null && <p className="font-mono text-sm text-slate-300">{selectedBatch.duration_ms}ms</p>}
                    <p>{new Date(selectedBatch.started_at).toLocaleString('tr-TR')}</p>
                  </div>
                </div>

                {/* Summary Stats */}
                <div className="grid grid-cols-4 gap-2">
                  <div className="p-2 rounded-lg bg-slate-800/30 border border-slate-800 text-center">
                    <p className="text-[10px] text-slate-500">Toplam</p>
                    <p className="text-lg font-bold text-white">{selectedBatch.total_reservations || 0}</p>
                  </div>
                  <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-center">
                    <p className="text-[10px] text-emerald-400">Yeni</p>
                    <p className="text-lg font-bold text-emerald-300">{selectedBatch.new_count || 0}</p>
                  </div>
                  <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-center">
                    <p className="text-[10px] text-cyan-400">Değişiklik</p>
                    <p className="text-lg font-bold text-cyan-300">{selectedBatch.modified_count || 0}</p>
                  </div>
                  <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-center">
                    <p className="text-[10px] text-red-400">İptal</p>
                    <p className="text-lg font-bold text-red-300">{selectedBatch.cancelled_count || 0}</p>
                  </div>
                </div>
                <div className="grid grid-cols-5 gap-2">
                  {selectedBatch.duplicate_count > 0 && (
                    <div className="p-2 rounded bg-slate-800/30 border border-slate-800 text-center">
                      <p className="text-[10px] text-slate-500">Duplikat</p>
                      <p className="text-sm font-bold text-slate-400">{selectedBatch.duplicate_count}</p>
                    </div>
                  )}
                  {selectedBatch.duplicate_cancel_count > 0 && (
                    <div className="p-2 rounded bg-slate-800/30 border border-slate-800 text-center">
                      <p className="text-[10px] text-slate-500">Dup.İptal</p>
                      <p className="text-sm font-bold text-slate-400">{selectedBatch.duplicate_cancel_count}</p>
                    </div>
                  )}
                  {selectedBatch.conflict_count > 0 && (
                    <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-center">
                      <p className="text-[10px] text-rose-400">Çakışma</p>
                      <p className="text-sm font-bold text-rose-300">{selectedBatch.conflict_count}</p>
                    </div>
                  )}
                  {selectedBatch.review_count > 0 && (
                    <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-center">
                      <p className="text-[10px] text-amber-400">İnceleme</p>
                      <p className="text-sm font-bold text-amber-300">{selectedBatch.review_count}</p>
                    </div>
                  )}
                  {selectedBatch.out_of_order_count > 0 && (
                    <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-center">
                      <p className="text-[10px] text-amber-400">OOO</p>
                      <p className="text-sm font-bold text-amber-300">{selectedBatch.out_of_order_count}</p>
                    </div>
                  )}
                  {selectedBatch.failed_count > 0 && (
                    <div className="p-2 rounded bg-red-500/10 border border-red-500/20 text-center">
                      <p className="text-[10px] text-red-400">Başarısız</p>
                      <p className="text-sm font-bold text-red-300">{selectedBatch.failed_count}</p>
                    </div>
                  )}
                </div>

                {/* ACK Summary */}
                {(selectedBatch.ack_sent_count > 0 || selectedBatch.ack_failed_count > 0) && (
                  <div className="flex items-center gap-3 px-3 py-2 rounded bg-slate-800/20 border border-slate-800">
                    <MailCheck className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs text-slate-400">ACK Gönderildi: {selectedBatch.ack_sent_count || 0}</span>
                    {selectedBatch.ack_failed_count > 0 && (
                      <>
                        <MailX className="w-4 h-4 text-red-400" />
                        <span className="text-xs text-red-400">ACK Başarısız: {selectedBatch.ack_failed_count}</span>
                      </>
                    )}
                  </div>
                )}

                {/* Batch Reservations */}
                {batchReservations.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-2">Rezervasyonlar ({batchReservations.length})</p>
                    <div className="space-y-1.5 max-h-60 overflow-y-auto">
                      {batchReservations.map((r) => (
                        <div key={r.id}
                          className="flex items-center justify-between p-2.5 rounded bg-slate-800/20 border border-slate-800/50 cursor-pointer hover:border-slate-700"
                          onClick={() => { setShowBatchDetail(false); handleViewReservationDetail(r.id); }}
                          data-testid={`batch-res-${r.id?.slice(0, 8)}`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <StatusBadge status={r.import_status} />
                            <span className="text-xs text-white">{r.guest_name || '-'}</span>
                            <span className="text-[10px] text-slate-500 font-mono">{r.external_confirmation_number || r.external_reservation_id?.slice(0, 8)}</span>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <AckBadge ackStatus={r.ack_status} />
                            <span className="text-xs text-slate-500">{r.arrival_date}</span>
                            <ChevronRight className="w-3 h-3 text-slate-600" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default IntegrationHub;
