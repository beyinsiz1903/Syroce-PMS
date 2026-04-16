import { useState, useEffect, useCallback } from 'react';

import { api } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  BarChart3, Activity, AlertTriangle, DollarSign, RefreshCw, TrendingUp,
  CheckCircle2, Clock, Database, HardDrive, Shield, Download,
} from 'lucide-react';

export default function MonitoringPage() {
  const [dashboard, setDashboard] = useState(null);
  const [scanStats, setScanStats] = useState(null);
  const [errorLog, setErrorLog] = useState(null);
  const [aiCosts, setAiCosts] = useState(null);
  const [backups, setBackups] = useState([]);
  const [backupSchedule, setBackupSchedule] = useState(null);
  const [loading, setLoading] = useState(true);
  const [backupLoading, setBackupLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, scanRes, errorRes, costRes, backupRes, scheduleRes] = await Promise.allSettled([
        api.getMonitoringDashboard(),
        api.getScanStatistics(30),
        api.getErrorLog({ days: 7, limit: 20 }),
        api.getAiCostReport(30),
        api.getBackups(),
        api.getBackupSchedule(),
      ]);
      if (dashRes.status === 'fulfilled') setDashboard(dashRes.value);
      if (scanRes.status === 'fulfilled') setScanStats(scanRes.value);
      if (errorRes.status === 'fulfilled') setErrorLog(errorRes.value);
      if (costRes.status === 'fulfilled') setAiCosts(costRes.value);
      if (backupRes.status === 'fulfilled') setBackups(backupRes.value.backups || []);
      if (scheduleRes.status === 'fulfilled') setBackupSchedule(scheduleRes.value);
    } catch (e) {
      console.error('Monitoring fetch error:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreateBackup = async () => {
    setBackupLoading(true);
    try {
      await api.createBackup('Manuel yedekleme');
      const data = await api.getBackups();
      setBackups(data.backups || []);
    } catch (e) {
      console.error('Backup error:', e);
    }
    setBackupLoading(false);
  };

  const StatCard = ({ title, value, icon: Icon, subtitle, color = 'blue' }) => (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
            {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
          </div>
          <div className={`w-12 h-12 rounded-xl bg-${color}-50 flex items-center justify-center`}>
            <Icon className={`w-6 h-6 text-${color}-500`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[60vh]">
        <RefreshCw className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="w-7 h-7 text-blue-500" /> Monitoring Dashboard
          </h1>
          <p className="text-muted-foreground mt-1">Sistem izleme, metrikler ve yedekleme yönetimi</p>
        </div>
        <Button variant="outline" onClick={fetchData}>
          <RefreshCw className="w-4 h-4 mr-2" /> Yenile
        </Button>
      </div>

      {/* Overview Stats */}
      {dashboard && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard title="Toplam Tarama" value={dashboard.overview?.total_scans || 0} icon={Activity} subtitle="Tüm zamanlar" />
          <StatCard title="Bugünkü Tarama" value={dashboard.overview?.today_scans || 0} icon={TrendingUp} subtitle="Bugün" color="green" />
          <StatCard title="Başarı Oranı" value={`%${dashboard.scan_performance?.success_rate || 0}`} icon={CheckCircle2} subtitle="Son 7 gün" color="emerald" />
          <StatCard title="Aktif Misafir" value={dashboard.overview?.checked_in || 0} icon={Clock} subtitle="Şu an konaklamakta" color="amber" />
        </div>
      )}

      <Tabs defaultValue="scans" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="scans">Tarama İstatistik</TabsTrigger>
          <TabsTrigger value="errors">Hata İzleme</TabsTrigger>
          <TabsTrigger value="costs">AI Maliyet</TabsTrigger>
          <TabsTrigger value="compliance">Uyumluluk</TabsTrigger>
          <TabsTrigger value="backup">Yedekleme</TabsTrigger>
        </TabsList>

        {/* Scan Statistics */}
        <TabsContent value="scans">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="w-5 h-5" /> Tarama İstatistikleri (Son 30 Gün)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {scanStats ? (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 rounded-lg bg-blue-50 border border-blue-100">
                      <p className="text-sm text-blue-600">Toplam</p>
                      <p className="text-2xl font-bold text-blue-700">{scanStats.total_scans}</p>
                    </div>
                    <div className="p-4 rounded-lg bg-green-50 border border-green-100">
                      <p className="text-sm text-green-600">Başarılı</p>
                      <p className="text-2xl font-bold text-green-700">{scanStats.successful_scans}</p>
                    </div>
                    <div className="p-4 rounded-lg bg-red-50 border border-red-100">
                      <p className="text-sm text-red-600">Başarısız</p>
                      <p className="text-2xl font-bold text-red-700">{scanStats.failed_scans}</p>
                    </div>
                    <div className="p-4 rounded-lg bg-amber-50 border border-amber-100">
                      <p className="text-sm text-amber-600">İnceleme Bekliyor</p>
                      <p className="text-2xl font-bold text-amber-700">{scanStats.needs_review}</p>
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium mb-3">Güven Puanı Dağılımı</h4>
                    <div className="space-y-2">
                      {['high', 'medium', 'low'].map(level => {
                        const count = scanStats.confidence_distribution?.[level] || 0;
                        const total = scanStats.total_scans || 1;
                        const pct = Math.round((count / total) * 100);
                        const colors = { high: 'bg-green-500', medium: 'bg-amber-500', low: 'bg-red-500' };
                        const labels = { high: 'Yüksek', medium: 'Orta', low: 'Düşük' };
                        return (
                          <div key={level} className="flex items-center gap-3">
                            <span className="text-sm w-16">{labels[level]}</span>
                            <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                              <div className={`h-full ${colors[level]} rounded-full`} style={{ width: `${pct}%` }} />
                            </div>
                            <span className="text-sm font-medium w-16 text-right">{count} (%{pct})</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {scanStats.daily_stats && scanStats.daily_stats.length > 0 && (
                    <div>
                      <h4 className="font-medium mb-3">Günlük Tarama Trendi</h4>
                      <div className="flex items-end gap-1 h-32">
                        {scanStats.daily_stats.slice(-14).map((day, i) => {
                          const maxVal = Math.max(...scanStats.daily_stats.slice(-14).map(d => d.total), 1);
                          const height = Math.max((day.total / maxVal) * 100, 4);
                          return (
                            <div key={i} className="flex-1 flex flex-col items-center gap-1">
                              <div className="w-full bg-blue-500 rounded-t" style={{ height: `${height}%` }} title={`${day.date}: ${day.total} tarama`} />
                              <span className="text-[10px] text-muted-foreground">{day.date?.slice(5)}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-muted-foreground">Veri yükleniyor...</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Error Log */}
        <TabsContent value="errors">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-500" /> Hata İzleme (Son 7 Gün)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {errorLog ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(errorLog.error_types || {}).map(([type, count]) => {
                      const typeLabels = {
                        connection_error: 'Bağlantı Hatası',
                        rate_limit: 'Limit Aşımı',
                        parse_error: 'Ayrıştırma Hatası',
                        auth_error: 'Yetki Hatası',
                        other: 'Diğer',
                      };
                      return (
                        <div key={type} className="p-3 rounded-lg border">
                          <p className="text-xs text-muted-foreground">{typeLabels[type] || type}</p>
                          <p className="text-xl font-bold">{count}</p>
                        </div>
                      );
                    })}
                  </div>

                  {errorLog.errors?.length > 0 ? (
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {errorLog.errors.map((err, i) => (
                        <div key={i} className="p-3 border rounded-lg bg-red-50/50">
                          <div className="flex items-center justify-between mb-1">
                            <Badge variant="destructive" className="text-xs">Hata</Badge>
                            <span className="text-xs text-muted-foreground">{err.created_at?.slice(0, 19)}</span>
                          </div>
                          <p className="text-sm font-mono break-all">{err.error?.slice(0, 200)}</p>
                          <p className="text-xs text-muted-foreground mt-1">Kullanıcı: {err.scanned_by || '-'}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <CheckCircle2 className="w-12 h-12 mx-auto mb-3 text-green-400" />
                      <p>Son 7 günde hata kaydı yok</p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-muted-foreground">Veri yükleniyor...</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* AI Costs */}
        <TabsContent value="costs">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-green-500" /> AI API Maliyet Takibi (Son 30 Gün)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {aiCosts ? (
                <div className="space-y-6">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <div className="p-4 rounded-lg bg-green-50 border border-green-100">
                      <p className="text-sm text-green-600">Toplam Maliyet</p>
                      <p className="text-2xl font-bold text-green-700">${aiCosts.total_cost_usd}</p>
                    </div>
                    <div className="p-4 rounded-lg bg-blue-50 border border-blue-100">
                      <p className="text-sm text-blue-600">Günlük Ortalama</p>
                      <p className="text-2xl font-bold text-blue-700">${aiCosts.avg_daily_cost}</p>
                    </div>
                    <div className="p-4 rounded-lg bg-purple-50 border border-purple-100">
                      <p className="text-sm text-purple-600">Toplam Token</p>
                      <p className="text-2xl font-bold text-purple-700">{(aiCosts.total_input_tokens + aiCosts.total_output_tokens).toLocaleString()}</p>
                    </div>
                  </div>

                  {Object.keys(aiCosts.model_breakdown || {}).length > 0 && (
                    <div>
                      <h4 className="font-medium mb-3">Model Bazlı Maliyet</h4>
                      <div className="space-y-2">
                        {Object.entries(aiCosts.model_breakdown).map(([model, cost]) => (
                          <div key={model} className="flex items-center justify-between p-3 border rounded-lg">
                            <span className="font-medium">{model}</span>
                            <span className="text-green-600 font-bold">${cost}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <DollarSign className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                  <p>Henüz maliyet verisi yok</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Compliance */}
        <TabsContent value="compliance">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-purple-500" /> Yasal Uyumluluk Durumu
              </CardTitle>
            </CardHeader>
            <CardContent>
              {dashboard ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="p-4 rounded-lg border space-y-3">
                    <h4 className="font-medium">Emniyet Bildirimleri</h4>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Toplam</span>
                      <Badge>{dashboard.compliance?.total_emniyet_bildirimi || 0}</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Taslak (gönderilmemiş)</span>
                      <Badge variant="outline" className="text-amber-600">{dashboard.compliance?.draft_bildirimi || 0}</Badge>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg border space-y-3">
                    <h4 className="font-medium">KVKK Talepleri</h4>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Bekleyen Talep</span>
                      <Badge variant={dashboard.compliance?.pending_kvkk_requests > 0 ? 'destructive' : 'default'}>
                        {dashboard.compliance?.pending_kvkk_requests || 0}
                      </Badge>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg border space-y-3">
                    <h4 className="font-medium">Oda Durumu</h4>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Toplam Oda</span>
                      <Badge>{dashboard.rooms?.total || 0}</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Doluluk Oranı</span>
                      <Badge variant="outline">%{dashboard.rooms?.occupancy_rate || 0}</Badge>
                    </div>
                  </div>
                  <div className="p-4 rounded-lg border space-y-3">
                    <h4 className="font-medium">Genel Durum</h4>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Bekleyen Misafir</span>
                      <Badge variant="outline">{dashboard.overview?.pending_guests || 0}</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">Konaklayan</span>
                      <Badge className="bg-green-500">{dashboard.overview?.checked_in || 0}</Badge>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-muted-foreground">Veri yükleniyor...</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Backup */}
        <TabsContent value="backup">
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Database className="w-5 h-5 text-indigo-500" /> Veritabanı Yedekleme
                  </span>
                  <Button onClick={handleCreateBackup} disabled={backupLoading} size="sm">
                    {backupLoading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Download className="w-4 h-4 mr-2" />}
                    Yedek Oluştur
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {backupSchedule && (
                  <div className="mb-6 p-4 rounded-lg bg-indigo-50 border border-indigo-100">
                    <h4 className="font-medium text-indigo-700 mb-2">Yedekleme Planı</h4>
                    <div className="grid grid-cols-3 gap-3 text-sm">
                      <div><span className="text-indigo-600 font-medium">Günlük:</span> {backupSchedule.schedule?.daily?.time}</div>
                      <div><span className="text-indigo-600 font-medium">Haftalık:</span> {backupSchedule.schedule?.weekly?.day} {backupSchedule.schedule?.weekly?.time}</div>
                      <div><span className="text-indigo-600 font-medium">Aylık:</span> Her ayın {backupSchedule.schedule?.monthly?.day}. günü</div>
                    </div>
                    <p className="text-xs text-indigo-500 mt-2">Yedeklenen koleksiyon: {backupSchedule.collections?.length || 0} adet</p>
                  </div>
                )}

                {backups.length > 0 ? (
                  <div className="space-y-2">
                    {backups.map((backup, i) => (
                      <div key={i} className="flex items-center justify-between p-3 border rounded-lg">
                        <div>
                          <p className="font-medium text-sm">{backup.filename}</p>
                          <p className="text-xs text-muted-foreground">
                            {backup.total_records} kayıt • {(backup.file_size_bytes / 1024).toFixed(1)} KB • {backup.created_at?.slice(0, 19)}
                          </p>
                        </div>
                        <Badge variant="outline">{backup.description || 'Yedek'}</Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <HardDrive className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                    <p>Henüz yedek oluşturulmamış</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
