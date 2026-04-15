import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import Layout from '../components/Layout';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogClose } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Progress } from '../components/ui/progress';
import { toast } from 'sonner';
import { 
  Key, Shield, RefreshCw, AlertTriangle, CheckCircle, 
  XCircle, Clock, Play, Pause, RotateCcw, Trash2, 
  Eye, Settings, History, AlertOctagon, Database
} from 'lucide-react';

const API_URL = import.meta.env.VITE_BACKEND_URL || '';

// State badge colors
const stateColors = {
  active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  pending_rotation: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  retired: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
  revoked: 'bg-red-500/20 text-red-400 border-red-500/30',
};

// Job state colors
const jobStateColors = {
  pending: 'bg-slate-500/20 text-slate-400',
  running: 'bg-blue-500/20 text-blue-400',
  paused: 'bg-amber-500/20 text-amber-400',
  completed: 'bg-emerald-500/20 text-emerald-400',
  failed: 'bg-red-500/20 text-red-400',
  cancelled: 'bg-slate-500/20 text-slate-400',
};

// Key type icons
const keyTypeIcons = {
  master: Key,
  connector: RefreshCw,
  webhook: Shield,
  api: Settings,
  pii: Database,
};

export default function EncryptionManagementPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [keyAudit, setKeyAudit] = useState([]);
  const [jobAudit, setJobAudit] = useState([]);
  
  // Dialog states
  const [showRegisterDialog, setShowRegisterDialog] = useState(false);
  const [showRevokeDialog, setShowRevokeDialog] = useState(false);
  const [showJobDialog, setShowJobDialog] = useState(false);
  
  // Form states
  const [registerForm, setRegisterForm] = useState({
    key_id: '',
    key_type: 'master',
    description: '',
    rotation_policy_days: 90,
  });
  const [revokeReason, setRevokeReason] = useState('');
  const [jobForm, setJobForm] = useState({
    key_id: '',
    collections: ['guests', 'bookings'],
    batch_size: 100,
    description: '',
  });

  const fetchDashboard = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`/ops/encryption/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setDashboard(response.data);
    } catch (error) {
      console.error('Failed to fetch dashboard:', error);
      toast.error('Dashboard yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchKeyAudit = async (keyId = null) => {
    try {
      const token = localStorage.getItem('token');
      const params = keyId ? `?key_id=${keyId}` : '';
      const response = await axios.get(`/ops/encryption/audit/keys${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setKeyAudit(response.data.items || []);
    } catch (error) {
      console.error('Failed to fetch key audit:', error);
    }
  };

  const fetchJobAudit = async (jobId = null) => {
    try {
      const token = localStorage.getItem('token');
      const params = jobId ? `?job_id=${jobId}` : '';
      const response = await axios.get(`/ops/encryption/audit/jobs${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setJobAudit(response.data.items || []);
    } catch (error) {
      console.error('Failed to fetch job audit:', error);
    }
  };

  useEffect(() => {
    fetchDashboard();
    const interval = setInterval(fetchDashboard, 30000);
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  useEffect(() => {
    if (activeTab === 'audit') {
      fetchKeyAudit();
      fetchJobAudit();
    }
  }, [activeTab]);

  // Key Actions
  const handleRegisterKey = async () => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/ops/encryption/keys/register`, registerForm, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success('Anahtar başarıyla kaydedildi');
      setShowRegisterDialog(false);
      setRegisterForm({ key_id: '', key_type: 'master', description: '', rotation_policy_days: 90 });
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Anahtar kaydedilemedi');
    }
  };

  const handleInitiateRotation = async (keyId) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/ops/encryption/keys/rotation/initiate`, 
        { key_id: keyId, reason: 'scheduled' },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Rotasyon baslatildi');
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Rotasyon baslatilamadi');
    }
  };

  const handleCompleteRotation = async (keyId) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/ops/encryption/keys/rotation/complete`, 
        { key_id: keyId },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Rotasyon tamamlandi');
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Rotasyon tamamlanamadi');
    }
  };

  const handleCancelRotation = async (keyId) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/ops/encryption/keys/rotation/cancel`, 
        { key_id: keyId, reason: 'manual_cancel' },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Rotasyon iptal edildi');
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Rotasyon iptal edilemedi');
    }
  };

  const handleEmergencyRevoke = async () => {
    if (!selectedKey || revokeReason.length < 10) {
      toast.error('Lutfen detayli bir sebep girin (min 10 karakter)');
      return;
    }
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/ops/encryption/keys/emergency-revoke`, 
        { key_id: selectedKey.key_id, reason: revokeReason },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Anahtar acil olarak iptal edildi');
      setShowRevokeDialog(false);
      setRevokeReason('');
      setSelectedKey(null);
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'İptal işlemi başarısız');
    }
  };

  // Job Actions
  const handleCreateJob = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(`/ops/encryption/reencryption/create`, jobForm, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success(`Is oluşturuldu: ${response.data.job_id}`);
      setShowJobDialog(false);
      setJobForm({ key_id: '', collections: ['guests', 'bookings'], batch_size: 100, description: '' });
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Is oluşturulamadı');
    }
  };

  const handleJobAction = async (jobId, action) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/ops/encryption/reencryption/${action}`, 
        { job_id: jobId },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`Is ${action === 'start' ? 'baslatildi' : action === 'pause' ? 'durduruldu' : 'iptal edildi'}`);
      fetchDashboard();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'İşlem başarısız');
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-96">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500" />
        </div>
      </Layout>
    );
  }

  const keysSummary = dashboard?.keys?.summary || {};
  const jobsSummary = dashboard?.reencryption_jobs?.summary || {};
  const keys = dashboard?.keys?.keys || [];
  const jobs = dashboard?.reencryption_jobs?.recent_jobs || [];
  const overdueKeys = dashboard?.keys?.overdue_rotations || [];
  const warningKeys = dashboard?.keys?.rotation_warnings || [];

  return (
    <Layout>
      <div className="space-y-6 p-6" data-testid="encryption-management-page">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Key className="h-6 w-6 text-emerald-400" />
              Sifreleme Yonetimi
            </h1>
            <p className="text-slate-400 mt-1">
              Anahtar yasam dongusu, rotasyon ve yeniden sifreleme işlemleri
            </p>
          </div>
          <div className="flex gap-2">
            <Button 
              onClick={() => setShowRegisterDialog(true)}
              className="bg-emerald-600 hover:bg-emerald-700"
              data-testid="register-key-btn"
            >
              <Key className="h-4 w-4 mr-2" />
              Yeni Anahtar
            </Button>
            <Button 
              onClick={() => setShowJobDialog(true)}
              variant="outline"
              className="border-slate-600"
              data-testid="create-job-btn"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Re-encryption Job
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-emerald-500/20">
                  <CheckCircle className="h-5 w-5 text-emerald-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Aktif</p>
                  <p className="text-2xl font-bold text-white">{keysSummary.active || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-500/20">
                  <RefreshCw className="h-5 w-5 text-amber-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Rotasyonda</p>
                  <p className="text-2xl font-bold text-white">{keysSummary.pending_rotation || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-slate-500/20">
                  <Clock className="h-5 w-5 text-slate-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Emekli</p>
                  <p className="text-2xl font-bold text-white">{keysSummary.retired || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-red-500/20">
                  <XCircle className="h-5 w-5 text-red-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">İptal</p>
                  <p className="text-2xl font-bold text-white">{keysSummary.revoked || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-orange-500/20">
                  <AlertTriangle className="h-5 w-5 text-orange-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Geciken</p>
                  <p className="text-2xl font-bold text-white">{keysSummary.overdue_count || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-500/20">
                  <Database className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <p className="text-sm text-slate-400">Isler</p>
                  <p className="text-2xl font-bold text-white">{jobsSummary.total_jobs || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Warning Alerts */}
        {(overdueKeys.length > 0 || warningKeys.length > 0) && (
          <div className="space-y-2">
            {overdueKeys.map(key => (
              <div key={key.key_id} className="flex items-center gap-3 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
                <AlertOctagon className="h-5 w-5 text-red-400" />
                <span className="text-red-300">
                  <strong>{key.key_id}</strong> rotasyonu {key.days_overdue} gun gecikti
                </span>
                <Button 
                  size="sm" 
                  className="ml-auto bg-red-600 hover:bg-red-700"
                  onClick={() => handleInitiateRotation(key.key_id)}
                >
                  Rotasyon Baslat
                </Button>
              </div>
            ))}
            {warningKeys.map(key => (
              <div key={key.key_id} className="flex items-center gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <AlertTriangle className="h-5 w-5 text-amber-400" />
                <span className="text-amber-300">
                  <strong>{key.key_id}</strong> rotasyonuna {key.days_until_due} gun kaldi
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Main Content Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="bg-slate-800 border border-slate-700">
            <TabsTrigger value="overview" className="data-[state=active]:bg-slate-700">
              Genel Bakis
            </TabsTrigger>
            <TabsTrigger value="keys" className="data-[state=active]:bg-slate-700">
              Anahtarlar
            </TabsTrigger>
            <TabsTrigger value="jobs" className="data-[state=active]:bg-slate-700">
              Yeniden Sifreleme
            </TabsTrigger>
            <TabsTrigger value="audit" className="data-[state=active]:bg-slate-700">
              Denetim Gunlugu
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Active Keys */}
              <Card className="bg-slate-800/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2">
                    <Key className="h-5 w-5 text-emerald-400" />
                    Aktif Anahtarlar
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {keys.filter(k => k.state === 'active').slice(0, 5).map(key => {
                      const Icon = keyTypeIcons[key.key_type] || Key;
                      return (
                        <div key={key.key_id} className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50">
                          <div className="flex items-center gap-3">
                            <Icon className="h-4 w-4 text-emerald-400" />
                            <div>
                              <p className="text-white font-medium">{key.key_id}</p>
                              <p className="text-xs text-slate-400">{key.description || key.key_type}</p>
                            </div>
                          </div>
                          <Badge className={stateColors[key.state]}>
                            {key.state}
                          </Badge>
                        </div>
                      );
                    })}
                    {keys.filter(k => k.state === 'active').length === 0 && (
                      <p className="text-slate-400 text-center py-4">Aktif anahtar yok</p>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Running Jobs */}
              <Card className="bg-slate-800/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2">
                    <RefreshCw className="h-5 w-5 text-blue-400" />
                    Aktif Isler
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {jobs.filter(j => j.state === 'running').map(job => (
                      <div key={job.job_id} className="p-3 rounded-lg bg-slate-900/50">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-white font-medium">{job.job_id}</p>
                          <Badge className={jobStateColors[job.state]}>{job.state}</Badge>
                        </div>
                        <Progress value={job.progress_percent || 0} className="h-2" />
                        <p className="text-xs text-slate-400 mt-1">
                          {job.processed_documents || 0} / {job.total_documents || 0} dokuman
                        </p>
                      </div>
                    ))}
                    {jobs.filter(j => j.state === 'running').length === 0 && (
                      <p className="text-slate-400 text-center py-4">Calisan is yok</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Keys Tab */}
          <TabsContent value="keys" className="space-y-4">
            <Card className="bg-slate-800/50 border-slate-700">
              <CardHeader>
                <CardTitle className="text-white">Tum Anahtarlar</CardTitle>
                <CardDescription className="text-slate-400">
                  Kayıtlı sifreleme anahtarlari ve durumlari
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {keys.map(key => {
                    const Icon = keyTypeIcons[key.key_type] || Key;
                    const nextDue = key.next_rotation_due ? new Date(key.next_rotation_due) : null;
                    const daysUntil = nextDue ? Math.ceil((nextDue - new Date()) / (1000 * 60 * 60 * 24)) : null;
                    
                    return (
                      <div key={key.key_id} className="flex items-center justify-between p-4 rounded-lg bg-slate-900/50 border border-slate-700">
                        <div className="flex items-center gap-4">
                          <div className="p-2 rounded-lg bg-slate-800">
                            <Icon className="h-5 w-5 text-emerald-400" />
                          </div>
                          <div>
                            <p className="text-white font-medium">{key.key_id}</p>
                            <p className="text-sm text-slate-400">{key.description || `Tip: ${key.key_type}`}</p>
                            <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                              <span>v{key.version}</span>
                              {key.provider && <span>Provider: {key.provider}</span>}
                              {daysUntil !== null && (
                                <span className={daysUntil < 0 ? 'text-red-400' : daysUntil < 14 ? 'text-amber-400' : ''}>
                                  Rotasyon: {daysUntil < 0 ? `${Math.abs(daysUntil)} gun gecikti` : `${daysUntil} gun`}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge className={stateColors[key.state]}>{key.state}</Badge>
                          
                          {key.state === 'active' && (
                            <>
                              <Button 
                                size="sm" 
                                variant="outline"
                                className="border-slate-600"
                                onClick={() => handleInitiateRotation(key.key_id)}
                              >
                                <RefreshCw className="h-3 w-3 mr-1" />
                                Rotasyon
                              </Button>
                              <Button 
                                size="sm" 
                                variant="outline"
                                className="border-red-600 text-red-400 hover:bg-red-600/20"
                                onClick={() => { setSelectedKey(key); setShowRevokeDialog(true); }}
                              >
                                <AlertOctagon className="h-3 w-3" />
                              </Button>
                            </>
                          )}
                          
                          {key.state === 'pending_rotation' && (
                            <>
                              <Button 
                                size="sm" 
                                className="bg-emerald-600 hover:bg-emerald-700"
                                onClick={() => handleCompleteRotation(key.key_id)}
                              >
                                <CheckCircle className="h-3 w-3 mr-1" />
                                Tamamla
                              </Button>
                              <Button 
                                size="sm" 
                                variant="outline"
                                className="border-slate-600"
                                onClick={() => handleCancelRotation(key.key_id)}
                              >
                                <XCircle className="h-3 w-3 mr-1" />
                                İptal
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {keys.length === 0 && (
                    <p className="text-slate-400 text-center py-8">Henüz anahtar kaydedilmemis</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Jobs Tab */}
          <TabsContent value="jobs" className="space-y-4">
            <Card className="bg-slate-800/50 border-slate-700">
              <CardHeader>
                <CardTitle className="text-white">Yeniden Sifreleme Isleri</CardTitle>
                <CardDescription className="text-slate-400">
                  Anahtar rotasyonu sonrasi veri migrasyonu isleri
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {jobs.map(job => (
                    <div key={job.job_id} className="p-4 rounded-lg bg-slate-900/50 border border-slate-700">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <p className="text-white font-medium">{job.job_id}</p>
                          <p className="text-sm text-slate-400">{job.description || `Key: ${job.key_id}`}</p>
                        </div>
                        <Badge className={jobStateColors[job.state]}>{job.state}</Badge>
                      </div>
                      
                      <Progress value={job.progress_percent || 0} className="h-2 mb-2" />
                      
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-400">
                          {job.processed_documents || 0} / {job.total_documents || 0} dokuman 
                          ({job.progress_percent?.toFixed(1) || 0}%)
                        </span>
                        {job.failed_documents > 0 && (
                          <span className="text-red-400">{job.failed_documents} başarısız</span>
                        )}
                      </div>
                      
                      <div className="flex gap-2 mt-3">
                        {job.state === 'pending' && (
                          <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={() => handleJobAction(job.job_id, 'start')}>
                            <Play className="h-3 w-3 mr-1" /> Baslat
                          </Button>
                        )}
                        {job.state === 'running' && (
                          <Button size="sm" variant="outline" className="border-amber-600 text-amber-400" onClick={() => handleJobAction(job.job_id, 'pause')}>
                            <Pause className="h-3 w-3 mr-1" /> Durdur
                          </Button>
                        )}
                        {job.state === 'paused' && (
                          <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={() => handleJobAction(job.job_id, 'start')}>
                            <Play className="h-3 w-3 mr-1" /> Devam
                          </Button>
                        )}
                        {['pending', 'running', 'paused'].includes(job.state) && (
                          <Button size="sm" variant="outline" className="border-red-600 text-red-400" onClick={() => handleJobAction(job.job_id, 'cancel')}>
                            <Trash2 className="h-3 w-3 mr-1" /> İptal
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                  {jobs.length === 0 && (
                    <p className="text-slate-400 text-center py-8">Henüz is olusturulmamis</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Audit Tab */}
          <TabsContent value="audit" className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Key Audit */}
              <Card className="bg-slate-800/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2">
                    <History className="h-5 w-5 text-emerald-400" />
                    Anahtar Islemleri
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {keyAudit.map((entry, idx) => (
                      <div key={idx} className="flex items-start gap-3 p-2 rounded bg-slate-900/50 text-sm">
                        <div className={`w-2 h-2 rounded-full mt-1.5 ${
                          entry.severity === 'critical' ? 'bg-red-500' :
                          entry.severity === 'error' ? 'bg-orange-500' :
                          entry.severity === 'warning' ? 'bg-amber-500' : 'bg-emerald-500'
                        }`} />
                        <div className="flex-1">
                          <p className="text-white">
                            <span className="text-slate-400">{entry.key_id}</span> — {entry.action}
                          </p>
                          <p className="text-xs text-slate-500">
                            {entry.actor} • {new Date(entry.timestamp).toLocaleString('tr-TR')}
                          </p>
                        </div>
                      </div>
                    ))}
                    {keyAudit.length === 0 && (
                      <p className="text-slate-400 text-center py-4">Kayıt yok</p>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Job Audit */}
              <Card className="bg-slate-800/50 border-slate-700">
                <CardHeader>
                  <CardTitle className="text-white flex items-center gap-2">
                    <History className="h-5 w-5 text-blue-400" />
                    Is Islemleri
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {jobAudit.map((entry, idx) => (
                      <div key={idx} className="flex items-start gap-3 p-2 rounded bg-slate-900/50 text-sm">
                        <div className={`w-2 h-2 rounded-full mt-1.5 ${
                          entry.severity === 'error' ? 'bg-red-500' :
                          entry.severity === 'warning' ? 'bg-amber-500' : 'bg-blue-500'
                        }`} />
                        <div className="flex-1">
                          <p className="text-white">
                            <span className="text-slate-400">{entry.job_id}</span> — {entry.action}
                          </p>
                          <p className="text-xs text-slate-500">
                            {entry.actor} • {new Date(entry.timestamp).toLocaleString('tr-TR')}
                          </p>
                        </div>
                      </div>
                    ))}
                    {jobAudit.length === 0 && (
                      <p className="text-slate-400 text-center py-4">Kayıt yok</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>

        {/* Register Key Dialog */}
        <Dialog open={showRegisterDialog} onOpenChange={setShowRegisterDialog}>
          <DialogContent className="bg-slate-800 border-slate-700">
            <DialogHeader>
              <DialogTitle className="text-white">Yeni Anahtar Kaydet</DialogTitle>
              <DialogDescription className="text-slate-400">
                Yeni bir sifreleme anahtari kaydedin
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label className="text-slate-300">Anahtar ID</Label>
                <Input 
                  value={registerForm.key_id}
                  onChange={e => setRegisterForm({...registerForm, key_id: e.target.value})}
                  placeholder="ornek: master-key-v2"
                  className="bg-slate-900 border-slate-600 text-white"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Tip</Label>
                <Select value={registerForm.key_type} onValueChange={v => setRegisterForm({...registerForm, key_type: v})}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    <SelectItem value="master">Master (Ana)</SelectItem>
                    <SelectItem value="connector">Connector (Baglanti)</SelectItem>
                    <SelectItem value="webhook">Webhook</SelectItem>
                    <SelectItem value="api">API</SelectItem>
                    <SelectItem value="pii">PII (Kisisel Veri)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Aciklama</Label>
                <Input 
                  value={registerForm.description}
                  onChange={e => setRegisterForm({...registerForm, description: e.target.value})}
                  placeholder="Anahtar aciklamasi"
                  className="bg-slate-900 border-slate-600 text-white"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Rotasyon Suresi (gun)</Label>
                <Input 
                  type="number"
                  value={registerForm.rotation_policy_days}
                  onChange={e => setRegisterForm({...registerForm, rotation_policy_days: parseInt(e.target.value) || 90})}
                  className="bg-slate-900 border-slate-600 text-white"
                />
              </div>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" className="border-slate-600">İptal</Button>
              </DialogClose>
              <Button onClick={handleRegisterKey} className="bg-emerald-600 hover:bg-emerald-700">
                Kaydet
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Emergency Revoke Dialog */}
        <Dialog open={showRevokeDialog} onOpenChange={setShowRevokeDialog}>
          <DialogContent className="bg-slate-800 border-red-700">
            <DialogHeader>
              <DialogTitle className="text-red-400 flex items-center gap-2">
                <AlertOctagon className="h-5 w-5" />
                Acil Anahtar Iptali
              </DialogTitle>
              <DialogDescription className="text-slate-400">
                Bu işlem geri alınamaz. Anahtar hemen kullanilmaz hale gelir.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="p-3 rounded bg-red-500/10 border border-red-500/30">
                <p className="text-red-300 font-medium">{selectedKey?.key_id}</p>
                <p className="text-sm text-red-400">{selectedKey?.description}</p>
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">İptal Sebebi (min 10 karakter)</Label>
                <Textarea 
                  value={revokeReason}
                  onChange={e => setRevokeReason(e.target.value)}
                  placeholder="Anahtarin neden iptal edildigini aciklayin..."
                  className="bg-slate-900 border-slate-600 text-white"
                  rows={3}
                />
              </div>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" className="border-slate-600">Vazgec</Button>
              </DialogClose>
              <Button 
                onClick={handleEmergencyRevoke} 
                className="bg-red-600 hover:bg-red-700"
                disabled={revokeReason.length < 10}
              >
                <AlertOctagon className="h-4 w-4 mr-2" />
                Acil İptal Et
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Create Job Dialog */}
        <Dialog open={showJobDialog} onOpenChange={setShowJobDialog}>
          <DialogContent className="bg-slate-800 border-slate-700">
            <DialogHeader>
              <DialogTitle className="text-white">Yeniden Sifreleme Isi Olustur</DialogTitle>
              <DialogDescription className="text-slate-400">
                Veri migrasyonu için yeni bir is oluşturun
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label className="text-slate-300">Anahtar ID</Label>
                <Select value={jobForm.key_id} onValueChange={v => setJobForm({...jobForm, key_id: v})}>
                  <SelectTrigger className="bg-slate-900 border-slate-600 text-white">
                    <SelectValue placeholder="Anahtar seçin" />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-800 border-slate-700">
                    {keys.map(k => (
                      <SelectItem key={k.key_id} value={k.key_id}>{k.key_id}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Koleksiyonlar</Label>
                <div className="flex flex-wrap gap-2">
                  {['guests', 'bookings', 'reservations', 'users'].map(col => (
                    <Badge 
                      key={col}
                      variant="outline"
                      className={`cursor-pointer ${jobForm.collections.includes(col) ? 'bg-emerald-500/20 border-emerald-500' : 'border-slate-600'}`}
                      onClick={() => {
                        const cols = jobForm.collections.includes(col) 
                          ? jobForm.collections.filter(c => c !== col)
                          : [...jobForm.collections, col];
                        setJobForm({...jobForm, collections: cols});
                      }}
                    >
                      {col}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Batch Boyutu</Label>
                <Input 
                  type="number"
                  value={jobForm.batch_size}
                  onChange={e => setJobForm({...jobForm, batch_size: parseInt(e.target.value) || 100})}
                  className="bg-slate-900 border-slate-600 text-white"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Aciklama</Label>
                <Input 
                  value={jobForm.description}
                  onChange={e => setJobForm({...jobForm, description: e.target.value})}
                  placeholder="Is aciklamasi"
                  className="bg-slate-900 border-slate-600 text-white"
                />
              </div>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" className="border-slate-600">İptal</Button>
              </DialogClose>
              <Button 
                onClick={handleCreateJob} 
                className="bg-blue-600 hover:bg-blue-700"
                disabled={!jobForm.key_id || jobForm.collections.length === 0}
              >
                Olustur
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}
