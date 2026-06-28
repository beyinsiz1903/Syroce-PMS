import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Shield, ShieldAlert, ShieldCheck, Video, History, AlertTriangle, Loader2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import MaybeLayout from '@/components/MaybeLayout';

const PhysicalSecurityDashboard = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [cameras, setCameras] = useState([]);
  const [logs, setLogs] = useState([]);
  const [lockdownState, setLockdownState] = useState('inactive'); // 'inactive', 'active'
  const [acting, setActing] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [camRes, logRes] = await Promise.all([
        axios.get('/physical-security/cctv/cameras'),
        axios.get('/physical-security/access-logs?limit=10')
      ]);
      setCameras(camRes.data.cameras || []);
      setLogs(logRes.data.logs || []);
    } catch (err) {
      console.error(err);
      toast.error('Güvenlik verileri yüklenirken bir hata oluştu.');
    } finally {
      setLoading(false);
    }
  };

  const handleLockdown = async (activate) => {
    if (activate && !window.confirm('DİKKAT: Tüm dijital anahtarlar iptal edilecek ve otel LOCKDOWN durumuna geçecek. Emin misiniz?')) {
      return;
    }
    
    try {
      setActing(true);
      if (activate) {
        await axios.post('/physical-security/lockdown');
        setLockdownState('active');
        toast.error('LOCKDOWN AKTİFLEŞTİRİLDİ!', { duration: 10000 });
      } else {
        await axios.post('/physical-security/lockdown/release');
        setLockdownState('inactive');
        toast.success('Lockdown iptal edildi. Sistem normale döndü.');
      }
    } catch (err) {
      console.error(err);
      toast.error('İşlem başarısız oldu.');
    } finally {
      setActing(false);
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="physical_security">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Shield className="w-6 h-6 text-slate-700" />
              Fiziksel Güvenlik ve Kilit Yönetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1">Oda kilit erişim logları, CCTV yönetimi ve acil durum protokolleri.</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={fetchData} disabled={loading}>
              Verileri Yenile
            </Button>
            {lockdownState === 'inactive' ? (
              <Button onClick={() => handleLockdown(true)} disabled={acting} variant="destructive" className="gap-2">
                {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldAlert className="w-4 h-4" />}
                Sistemi Kilitle (Lockdown)
              </Button>
            ) : (
              <Button onClick={() => handleLockdown(false)} disabled={acting} className="gap-2 bg-green-600 hover:bg-green-700 text-white">
                {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                Lockdown'ı Kaldır
              </Button>
            )}
          </div>
        </div>

        {lockdownState === 'active' && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg">
            <div className="flex items-center">
              <AlertTriangle className="h-6 w-6 text-red-500 mr-3" />
              <div>
                <h3 className="text-red-800 font-bold">KIRMIZI ALARM - LOCKDOWN AKTİF</h3>
                <p className="text-red-700 text-sm mt-1">Tesis genelinde acil durum protokolü devrede. Tüm dijital anahtar girişleri iptal edildi.</p>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center gap-2">
              <Video className="w-5 h-5 text-gray-500" />
              <div>
                <CardTitle className="text-lg">CCTV Kameralar</CardTitle>
                <CardDescription>Sisteme entegre kameraların canlı durumları.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex justify-center p-6"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
              ) : cameras.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">Kayıtlı kamera bulunmuyor.</p>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  {cameras.map(cam => (
                    <div key={cam.id} className="border rounded-lg p-3 bg-gray-50 relative overflow-hidden group">
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-sm font-semibold text-gray-900">{cam.name}</span>
                        <span className="flex h-2 w-2 relative mt-1">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                        </span>
                      </div>
                      <p className="text-xs text-gray-500">Oda/Bölge: {cam.room_number}</p>
                      {/* Fake stream placeholder */}
                      <div className="mt-3 h-24 bg-gray-800 rounded flex items-center justify-center">
                        <span className="text-gray-500 text-xs font-mono">CANLI AKIŞ: {cam.camera_id}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center gap-2">
              <History className="w-5 h-5 text-gray-500" />
              <div>
                <CardTitle className="text-lg">Kilit Erişim Logları</CardTitle>
                <CardDescription>Son 10 giriş çıkış denemesi.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex justify-center p-6"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
              ) : logs.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">Erişim logu bulunmuyor.</p>
              ) : (
                <div className="space-y-3">
                  {logs.map((log, idx) => (
                    <div key={idx} className="flex items-center justify-between p-3 border rounded-lg bg-white">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">Oda {log.room_number}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            log.access_decision === 'granted' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                          }`}>
                            {log.access_decision === 'granted' ? 'Kabul' : 'Red'}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">Kullanıcı ID: {log.guest_id || 'Bilinmiyor'}</p>
                        {log.denial_reason && <p className="text-xs text-red-500 mt-1">Sebep: {log.denial_reason}</p>}
                      </div>
                      <div className="text-xs text-gray-400 text-right">
                        {new Date(log.timestamp).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </MaybeLayout>
  );
};

export default PhysicalSecurityDashboard;
