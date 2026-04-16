import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Skeleton } from '../components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { api } from '../lib/api';
import {
  Shield,
  FileText,
  AlertTriangle,
  CheckCircle,
  Clock,
  Database,
  Plus,
  ArrowRight,
  XCircle,
  Info,
  RefreshCcw,
  Loader2,
  ChevronRight,
  BarChart3,
} from 'lucide-react';

const REQUEST_TYPE_LABELS = {
  access: 'Erişim Hakkı',
  rectification: 'Düzeltme Hakkı',
  erasure: 'Silme/Yok Etme',
  portability: 'Veri Taşıma',
  objection: 'İtiraz Hakkı',
};

const STATUS_LABELS = {
  pending: 'Beklemede',
  in_progress: 'İşleniyor',
  completed: 'Tamamlandı',
  rejected: 'Reddedildi',
};

const STATUS_COLORS = {
  pending: 'bg-[var(--brand-warning-soft)] text-[var(--brand-warning)] border-[#FED7AA]',
  in_progress: 'bg-[var(--brand-info-soft)] text-[var(--brand-info)] border-[#BFDBFE]',
  completed: 'bg-[var(--brand-success-soft)] text-[var(--brand-success)] border-[#A7F3D0]',
  rejected: 'bg-[var(--brand-danger-soft)] text-[var(--brand-danger)] border-[#FECDD3]',
};

const WARNING_ICONS = {
  critical: <XCircle className="w-4 h-4 text-[var(--brand-danger)]" />,
  warning: <AlertTriangle className="w-4 h-4 text-[var(--brand-warning)]" />,
  info: <Info className="w-4 h-4 text-[var(--brand-info)]" />,
};

export default function KvkkCompliancePage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [verbisReport, setVerbisReport] = useState(null);
  const [dataInventory, setDataInventory] = useState(null);
  const [retentionWarnings, setRetentionWarnings] = useState(null);
  const [rightsRequests, setRightsRequests] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showNewRequest, setShowNewRequest] = useState(false);
  const [newRequest, setNewRequest] = useState({
    request_type: 'access',
    requester_name: '',
    requester_email: '',
    requester_id_number: '',
    description: '',
    guest_id: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [processDialog, setProcessDialog] = useState(null);
  const [processNote, setProcessNote] = useState('');
  const [processStatus, setProcessStatus] = useState('completed');

  useEffect(() => {
    loadAllData();
  }, []);

  const loadAllData = async () => {
    setLoading(true);
    try {
      const [verbis, inventory, warnings, requests] = await Promise.all([
        api.getVerbisReport().catch(() => null),
        api.getDataInventory().catch(() => null),
        api.getRetentionWarnings().catch(() => null),
        api.getRightsRequests().catch(() => null),
      ]);
      setVerbisReport(verbis);
      setDataInventory(inventory);
      setRetentionWarnings(warnings);
      setRightsRequests(requests);
    } catch (err) {
      toast.error('Veri yüklenirken hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRequest = async () => {
    if (!newRequest.requester_name || !newRequest.requester_email || !newRequest.description) {
      toast.error('Lütfen zorunlu alanları doldurun');
      return;
    }
    setSubmitting(true);
    try {
      await api.createRightsRequest(newRequest);
      toast.success('KVKK hak talebi oluşturuldu');
      setShowNewRequest(false);
      setNewRequest({ request_type: 'access', requester_name: '', requester_email: '', requester_id_number: '', description: '', guest_id: '' });
      const requests = await api.getRightsRequests();
      setRightsRequests(requests);
    } catch (err) {
      toast.error(err.message || 'Talep oluşturulamadı');
    } finally {
      setSubmitting(false);
    }
  };

  const handleProcessRequest = async (requestId) => {
    if (!processNote) {
      toast.error('Yanıt notu zorunludur');
      return;
    }
    try {
      await api.processRightsRequest(requestId, {
        status: processStatus,
        response_note: processNote,
      });
      toast.success('Talep güncellendi');
      setProcessDialog(null);
      setProcessNote('');
      const requests = await api.getRightsRequests();
      setRightsRequests(requests);
    } catch (err) {
      toast.error(err.message || 'İşlem başarısız');
    }
  };

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  const compliance = verbisReport?.uyumluluk_durumu || {};
  const complianceItems = [
    { key: 'aydinlatma_metni', label: 'Aydınlatma Metni', ok: compliance.aydinlatma_metni },
    { key: 'riza_mekanizmasi', label: 'Rıza Mekanizması', ok: compliance.riza_mekanizmasi },
    { key: 'veri_saklama_politikasi', label: 'Veri Saklama Politikası', ok: compliance.veri_saklama_politikasi },
    { key: 'hak_talebi_sureci', label: 'Hak Talebi Süreci', ok: compliance.hak_talebi_sureci },
    { key: 'anonimlestime', label: 'Anonimleştirme', ok: compliance.anonimlestime },
    { key: 'denetim_izi', label: 'Denetim İzi', ok: compliance.denetim_izi },
    { key: 'erisim_kontrolu', label: 'Erişim Kontrolü', ok: compliance.erisim_kontrolu },
    { key: 'verbis_kaydi', label: 'VERBİS Kaydı', ok: compliance.verbis_kaydi },
  ];

  const stats = verbisReport?.istatistikler || {};

  return (
    <div className="space-y-4" data-testid="kvkk-compliance-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-[var(--brand-ink)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            KVKK Uyumluluk Merkezi
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">6698 sayılı kanun kapsamında veri koruma yönetimi</p>
        </div>
        <Button onClick={loadAllData} variant="outline" size="sm">
          <RefreshCcw className="w-4 h-4 mr-1" /> Yenile
        </Button>
      </div>

      {/* Warning Banner */}
      {retentionWarnings && retentionWarnings.critical_count > 0 && (
        <div className="bg-[var(--brand-danger-soft)] border border-[#FECDD3] rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-[var(--brand-danger)] shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-[var(--brand-danger)]">
              {retentionWarnings.critical_count} kritik uyarı mevcut!
            </p>
            <p className="text-xs text-[var(--brand-danger)] mt-0.5">
              Saklama süresi aşan veriler ve/veya süresi geçmiş hak talepleri var.
            </p>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">Uyumluluk Puanı</p>
              <Shield className="w-4 h-4 text-[var(--brand-success)]" />
            </div>
            <p className="text-2xl font-semibold mt-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {complianceItems.filter(c => c.ok).length}/{complianceItems.length}
            </p>
          </CardContent>
        </Card>
        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">Açık Talepler</p>
              <Clock className="w-4 h-4 text-[var(--brand-warning)]" />
            </div>
            <p className="text-2xl font-semibold mt-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {stats.bekleyen_talepler || 0}
            </p>
          </CardContent>
        </Card>
        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">Rızalı Misafir</p>
              <CheckCircle className="w-4 h-4 text-[var(--brand-success)]" />
            </div>
            <p className="text-2xl font-semibold mt-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {stats.rizali_misafir || 0}
            </p>
          </CardContent>
        </Card>
        <Card className="bg-white">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">Uyarılar</p>
              <AlertTriangle className="w-4 h-4 text-[var(--brand-warning)]" />
            </div>
            <p className="text-2xl font-semibold mt-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              {retentionWarnings?.total_warnings || 0}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid">
          <TabsTrigger value="overview">Genel Bakış</TabsTrigger>
          <TabsTrigger value="requests">Hak Talepleri</TabsTrigger>
          <TabsTrigger value="verbis">VERBİS Raporu</TabsTrigger>
          <TabsTrigger value="inventory">Veri Envanteri</TabsTrigger>
          <TabsTrigger value="warnings">Uyarılar</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Compliance Checklist */}
            <Card className="bg-white">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Shield className="w-4 h-4 text-[var(--brand-sky)]" />
                  Uyumluluk Kontrol Listesi
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {complianceItems.map((item) => (
                    <div key={item.key} className="flex items-center justify-between py-2 border-b last:border-0">
                      <span className="text-sm">{item.label}</span>
                      {item.ok ? (
                        <Badge className="bg-[var(--brand-success-soft)] text-[var(--brand-success)] border border-[#A7F3D0]">
                          <CheckCircle className="w-3 h-3 mr-1" /> Tamam
                        </Badge>
                      ) : (
                        <Badge className="bg-[var(--brand-warning-soft)] text-[var(--brand-warning)] border border-[#FED7AA]">
                          <AlertTriangle className="w-3 h-3 mr-1" /> Eksik
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Quick Stats */}
            <Card className="bg-white">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-[var(--brand-sky)]" />
                  Veri İstatistikleri
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {[
                    { label: 'Toplam Misafir', value: stats.toplam_misafir },
                    { label: 'Anonimleştirilmiş', value: stats.anonimlestirilmis },
                    { label: 'Toplam Tarama', value: stats.toplam_tarama },
                    { label: 'Denetim Kaydı', value: stats.toplam_denetim_kaydi },
                    { label: 'Sistem Kullanıcısı', value: stats.toplam_kullanici },
                    { label: 'Rızalı Misafir', value: stats.rizali_misafir },
                    { label: 'Rızasız Misafir', value: stats.rizasiz_misafir },
                    { label: 'Toplam Talepler', value: stats.toplam_talepler },
                  ].map((item) => (
                    <div key={item.label} className="flex items-center justify-between py-2 border-b last:border-0">
                      <span className="text-sm text-muted-foreground">{item.label}</span>
                      <span className="text-sm font-medium">{item.value ?? '—'}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Technical & Administrative Measures */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="bg-white">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Teknik Tedbirler</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {(verbisReport?.teknik_tedbirler || []).map((t, i) => (
                    <li key={i} className="flex items-center gap-2 text-sm">
                      <CheckCircle className="w-3.5 h-3.5 text-[var(--brand-success)] shrink-0" />
                      {t}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <Card className="bg-white">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">İdari Tedbirler</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {(verbisReport?.idari_tedbirler || []).map((t, i) => (
                    <li key={i} className="flex items-center gap-2 text-sm">
                      <CheckCircle className="w-3.5 h-3.5 text-[var(--brand-success)] shrink-0" />
                      {t}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Rights Requests Tab */}
        <TabsContent value="requests" className="mt-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">KVKK Hak Talepleri</h2>
            <Button size="sm" onClick={() => setShowNewRequest(true)} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white">
              <Plus className="w-4 h-4 mr-1" /> Yeni Talep
            </Button>
          </div>

          {/* New Request Form */}
          {showNewRequest && (
            <Card className="bg-white border-2 border-[var(--brand-sky)]">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Yeni Hak Talebi Oluştur</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label>Talep Türü *</Label>
                    <Select value={newRequest.request_type} onValueChange={v => setNewRequest(p => ({ ...p, request_type: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(REQUEST_TYPE_LABELS).map(([k, v]) => (
                          <SelectItem key={k} value={k}>{v}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Talep Sahibi Ad Soyad *</Label>
                    <Input value={newRequest.requester_name} onChange={e => setNewRequest(p => ({ ...p, requester_name: e.target.value }))} />
                  </div>
                  <div>
                    <Label>E-posta *</Label>
                    <Input type="email" value={newRequest.requester_email} onChange={e => setNewRequest(p => ({ ...p, requester_email: e.target.value }))} />
                  </div>
                  <div>
                    <Label>TCKN / Kimlik No</Label>
                    <Input value={newRequest.requester_id_number} onChange={e => setNewRequest(p => ({ ...p, requester_id_number: e.target.value }))} />
                  </div>
                </div>
                <div>
                  <Label>Açıklama *</Label>
                  <Textarea rows={3} value={newRequest.description} onChange={e => setNewRequest(p => ({ ...p, description: e.target.value }))} placeholder="Talep detaylarını yazınız..." />
                </div>
                <div className="flex gap-2">
                  <Button onClick={handleCreateRequest} disabled={submitting} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white">
                    {submitting ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Plus className="w-4 h-4 mr-1" />}
                    Talebi Oluştur
                  </Button>
                  <Button variant="outline" onClick={() => setShowNewRequest(false)}>İptal</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Requests List */}
          {rightsRequests?.requests?.length > 0 ? (
            <div className="space-y-3">
              {rightsRequests.requests.map((req) => (
                <Card key={req.request_id} className="bg-white">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge className={`${STATUS_COLORS[req.status]} border text-xs`}>
                            {STATUS_LABELS[req.status]}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            {REQUEST_TYPE_LABELS[req.request_type]}
                          </Badge>
                        </div>
                        <p className="text-sm font-medium">{req.requester_name}</p>
                        <p className="text-xs text-muted-foreground">{req.requester_email}</p>
                        <p className="text-sm mt-1">{req.description}</p>
                        {req.response && (
                          <div className="mt-2 p-2 bg-[hsl(var(--secondary))] rounded-lg">
                            <p className="text-xs font-medium text-muted-foreground">Yanıt:</p>
                            <p className="text-sm">{req.response}</p>
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground mt-2">
                          Oluşturma: {new Date(req.created_at).toLocaleString('tr-TR')} | Son Tarih: {new Date(req.deadline).toLocaleDateString('tr-TR')}
                        </p>
                      </div>
                      {req.status === 'pending' && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => { setProcessDialog(req); setProcessNote(''); setProcessStatus('completed'); }}
                        >
                          İşle <ChevronRight className="w-4 h-4 ml-1" />
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="bg-white">
              <CardContent className="p-8 text-center">
                <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">Henüz hak talebi bulunmuyor</p>
              </CardContent>
            </Card>
          )}

          {/* Process Dialog */}
          {processDialog && (
            <Dialog open={!!processDialog} onOpenChange={() => setProcessDialog(null)}>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Hak Talebini İşle</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <div>
                    <p className="text-sm"><strong>Talep:</strong> {REQUEST_TYPE_LABELS[processDialog.request_type]}</p>
                    <p className="text-sm"><strong>Sahibi:</strong> {processDialog.requester_name}</p>
                    <p className="text-sm">{processDialog.description}</p>
                  </div>
                  <div>
                    <Label>Sonuç Durumu</Label>
                    <Select value={processStatus} onValueChange={setProcessStatus}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="in_progress">İşleniyor</SelectItem>
                        <SelectItem value="completed">Tamamlandı</SelectItem>
                        <SelectItem value="rejected">Reddedildi</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Yanıt Notu *</Label>
                    <Textarea rows={3} value={processNote} onChange={e => setProcessNote(e.target.value)} placeholder="İşlem sonucu ve açıklama..." />
                  </div>
                  <div className="flex gap-2">
                    <Button onClick={() => handleProcessRequest(processDialog.request_id)} className="bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white">
                      Kaydet
                    </Button>
                    <Button variant="outline" onClick={() => setProcessDialog(null)}>İptal</Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          )}
        </TabsContent>

        {/* VERBİS Tab */}
        <TabsContent value="verbis" className="mt-4 space-y-4">
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[var(--brand-sky)]" />
                  VERBİS Uyumluluk Raporu
                </CardTitle>
                <p className="text-xs text-muted-foreground">Rapor Tarihi: {verbisReport?.report_date ? new Date(verbisReport.report_date).toLocaleDateString('tr-TR') : '—'}</p>
              </div>
            </CardHeader>
            <CardContent>
              {/* Veri Sorumlusu */}
              <div className="mb-4 p-3 bg-[hsl(var(--secondary))] rounded-lg">
                <p className="text-xs font-medium text-muted-foreground">Veri Sorumlusu</p>
                <p className="text-sm font-medium">{verbisReport?.veri_sorumlusu?.unvan}</p>
                <p className="text-xs text-muted-foreground">Sicil No: {verbisReport?.veri_sorumlusu?.sicil_no}</p>
              </div>

              {/* Veri Kategorileri */}
              <h3 className="text-sm font-semibold mb-2">Veri Kategorileri ve İşleme Amaçları</h3>
              <div className="space-y-3">
                {(verbisReport?.veri_kategorileri || []).map((cat, i) => (
                  <div key={i} className="p-3 border rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <p className="text-sm font-medium">{cat.kategori}</p>
                      <Badge variant="outline" className="text-xs">{cat.kayit_sayisi} kayıt</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mb-1">{cat.aciklama}</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-1 text-xs">
                      <div><span className="text-muted-foreground">Amaç:</span> {cat.isleme_amaci}</div>
                      <div><span className="text-muted-foreground">Dayanak:</span> {cat.hukuki_dayanak}</div>
                      <div><span className="text-muted-foreground">Saklama:</span> {cat.saklama_suresi}</div>
                      <div><span className="text-muted-foreground">Aktarım:</span> {cat.aktarim}</div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Data Inventory Tab */}
        <TabsContent value="inventory" className="mt-4 space-y-4">
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Database className="w-4 h-4 text-[var(--brand-sky)]" />
                Veri İşleme Envanteri
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(dataInventory?.koleksiyonlar || []).map((col, i) => (
                  <div key={i} className="p-3 border rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium font-mono">{col.ad}</p>
                        {col.hassas_veri && (
                          <Badge className="bg-[var(--brand-danger-soft)] text-[var(--brand-danger)] border border-[#FECDD3] text-[10px]">
                            Hassas Veri
                          </Badge>
                        )}
                        {col.kisisel_veri_iceriyor && (
                          <Badge className="bg-[var(--brand-warning-soft)] text-[var(--brand-warning)] border border-[#FED7AA] text-[10px]">
                            Kişisel Veri
                          </Badge>
                        )}
                      </div>
                      <span className="text-sm font-medium tabular-nums">{col.kayit_sayisi} kayıt</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{col.aciklama}</p>
                    <p className="text-xs mt-1"><span className="text-muted-foreground">Saklama:</span> {col.saklama_politikasi}</p>
                    {col.en_eski_kayit && (
                      <p className="text-xs"><span className="text-muted-foreground">Tarih Aralığı:</span> {new Date(col.en_eski_kayit).toLocaleDateString('tr-TR')} – {col.en_yeni_kayit ? new Date(col.en_yeni_kayit).toLocaleDateString('tr-TR') : 'şimdi'}</p>
                    )}
                  </div>
                ))}
              </div>

              {/* Data Flow */}
              <h3 className="text-sm font-semibold mt-6 mb-2">Veri Akış Diyagramı</h3>
              <div className="space-y-2">
                {(dataInventory?.veri_akisi || []).map((flow, i) => (
                  <div key={i} className="flex items-center gap-2 p-2 bg-[hsl(var(--secondary))] rounded-lg text-xs">
                    <span className="font-medium">{flow.kaynak}</span>
                    <ArrowRight className="w-3 h-3 text-muted-foreground shrink-0" />
                    <span className="font-medium">{flow.hedef}</span>
                    <span className="text-muted-foreground ml-2">({flow.amac})</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Warnings Tab */}
        <TabsContent value="warnings" className="mt-4 space-y-4">
          <Card className="bg-white">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-[var(--brand-warning)]" />
                  Saklama Süresi Uyarıları
                </CardTitle>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>Tarama: {retentionWarnings?.settings?.scan_retention_days} gün</span>
                  <span>|</span>
                  <span>Denetim: {retentionWarnings?.settings?.audit_retention_days} gün</span>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {retentionWarnings?.warnings?.length > 0 ? (
                <div className="space-y-2">
                  {retentionWarnings.warnings.map((w, i) => (
                    <div key={i} className={`flex items-start gap-3 p-3 rounded-lg border ${
                      w.type === 'critical' ? 'bg-[var(--brand-danger-soft)] border-[#FECDD3]' :
                      w.type === 'warning' ? 'bg-[var(--brand-warning-soft)] border-[#FED7AA]' :
                      'bg-[var(--brand-info-soft)] border-[#BFDBFE]'
                    }`}>
                      {WARNING_ICONS[w.type]}
                      <div className="flex-1">
                        <p className="text-sm font-medium">{w.message}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{w.action}</p>
                      </div>
                      <Badge variant="outline" className="text-xs shrink-0">{w.count}</Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <CheckCircle className="w-8 h-8 text-[var(--brand-success)] mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">Herhangi bir uyarı bulunmuyor</p>
                  <p className="text-xs text-muted-foreground mt-1">Tüm veriler saklama süresi dahilinde</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
