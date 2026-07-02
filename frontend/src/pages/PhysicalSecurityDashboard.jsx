import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Shield, ShieldAlert, ShieldCheck, Video, History, AlertTriangle, Loader2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import MaybeLayout from '@/components/MaybeLayout';

// LOCKDOWN için gerekli onay PIN'i (front-desk seviyesinde ek güvence)
const LOCKDOWN_CONFIRM_PHRASE = 'LOCKDOWN';

const PhysicalSecurityDashboard = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [cameras, setCameras] = useState([]);
  const [logs, setLogs] = useState([]);
  const [lockdownState, setLockdownState] = useState('inactive'); // 'inactive' | 'active'
  const [acting, setActing] = useState(false);

  // Custom confirmation dialog state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const [confirmError, setConfirmError] = useState('');
  const phraseInputRef = useRef(null);

  useEffect(() => {
    fetchData();
  }, []);

  // Otomatik dialog açıldığında input'a odaklan
  useEffect(() => {
    if (confirmOpen && phraseInputRef.current) {
      setTimeout(() => phraseInputRef.current?.focus(), 100);
    }
  }, [confirmOpen]);

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
      console.error('[PhysicalSecurity] fetchData error:', err);
      toast.error('Güvenlik verileri yüklenirken bir hata oluştu.');
    } finally {
      setLoading(false);
    }
  };

  const openLockdownConfirm = () => {
    setConfirmPhrase('');
    setConfirmError('');
    setConfirmOpen(true);
  };

  const handleLockdownConfirmed = async () => {
    if (confirmPhrase.trim().toUpperCase() !== LOCKDOWN_CONFIRM_PHRASE) {
      setConfirmError(`Lütfen tam olarak "${LOCKDOWN_CONFIRM_PHRASE}" yazın.`);
      phraseInputRef.current?.focus();
      return;
    }
    setConfirmOpen(false);
    await executeLockdown(true);
  };

  const executeLockdown = async (activate) => {
    try {
      setActing(true);
      if (activate) {
        await axios.post('/physical-security/lockdown');
        setLockdownState('active');
        toast.error('🔴 LOCKDOWN AKTİFLEŞTİRİLDİ! Tüm dijital anahtarlar iptal edildi.', { duration: 10000 });
      } else {
        await axios.post('/physical-security/lockdown/release');
        setLockdownState('inactive');
        toast.success('✅ Lockdown iptal edildi. Sistem normale döndü.');
      }
    } catch (err) {
      console.error('[PhysicalSecurity] lockdown error:', err);
      toast.error('İşlem başarısız oldu. Lütfen tekrar deneyin.');
    } finally {
      setActing(false);
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="physical_security">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6" role="main" aria-label="Fiziksel Güvenlik ve Kilit Yönetimi">

        {/* Başlık Alanı */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Shield className="w-6 h-6 text-slate-700" aria-hidden="true" />
              Fiziksel Güvenlik ve Kilit Yönetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1">Oda kilit erişim logları, CCTV yönetimi ve acil durum protokolleri.</p>
          </div>
          <div className="flex items-center gap-3" role="toolbar" aria-label="Güvenlik kontrolleri">
            <Button
              variant="outline"
              onClick={fetchData}
              disabled={loading}
              aria-label="Güvenlik verilerini yenile"
            >
              Verileri Yenile
            </Button>

            {lockdownState === 'inactive' ? (
              <Button
                onClick={openLockdownConfirm}
                disabled={acting}
                variant="destructive"
                className="gap-2"
                aria-label="Tesis genelinde LOCKDOWN başlat — kritik acil durum aksiyonu"
                aria-describedby="lockdown-warning-text"
              >
                {acting ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <ShieldAlert className="w-4 h-4" aria-hidden="true" />}
                Sistemi Kilitle (Lockdown)
              </Button>
            ) : (
              <Button
                onClick={() => executeLockdown(false)}
                disabled={acting}
                className="gap-2 bg-green-600 hover:bg-green-700 text-white"
                aria-label="Aktif LOCKDOWN'ı kaldır ve sistemi normale döndür"
              >
                {acting ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="w-4 h-4" aria-hidden="true" />}
                Lockdown'ı Kaldır
              </Button>
            )}
          </div>
        </div>

        {/* Lockdown Aktif Uyarısı */}
        {lockdownState === 'active' && (
          <div
            className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg"
            role="alert"
            aria-live="assertive"
            aria-label="Kırmızı alarm — Lockdown aktif"
          >
            <div className="flex items-center">
              <AlertTriangle className="h-6 w-6 text-red-500 mr-3" aria-hidden="true" />
              <div>
                <h3 className="text-red-800 font-bold">KIRMIZI ALARM - LOCKDOWN AKTİF</h3>
                <p className="text-red-700 text-sm mt-1">
                  Tesis genelinde acil durum protokolü devrede. Tüm dijital anahtar girişleri iptal edildi.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* CCTV + Log grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* CCTV Kameralar */}
          <Card role="region" aria-label="CCTV kamera listesi">
            <CardHeader className="flex flex-row items-center gap-2">
              <Video className="w-5 h-5 text-gray-500" aria-hidden="true" />
              <div>
                <CardTitle className="text-lg">CCTV Kameralar</CardTitle>
                <CardDescription>Sisteme entegre kameraların canlı durumları.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex justify-center p-6" role="status" aria-label="Yükleniyor">
                  <Loader2 className="w-6 h-6 animate-spin text-gray-400" aria-hidden="true" />
                </div>
              ) : cameras.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">Kayıtlı kamera bulunmuyor.</p>
              ) : (
                <ul className="grid grid-cols-2 gap-4" aria-label="Kamera listesi">
                  {cameras.map(cam => (
                    <li key={cam.id} className="border rounded-lg p-3 bg-gray-50 relative overflow-hidden">
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-sm font-semibold text-gray-900">{cam.name}</span>
                        <span
                          className="flex h-2 w-2 relative mt-1"
                          aria-label="Kamera aktif"
                          title="Canlı"
                        >
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" aria-hidden="true"></span>
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" aria-hidden="true"></span>
                        </span>
                      </div>
                      <p className="text-xs text-gray-500">Oda/Bölge: {cam.room_number}</p>
                      <div
                        className="mt-3 h-24 bg-gray-800 rounded flex items-center justify-center"
                        role="img"
                        aria-label={`${cam.name} canlı görüntü akışı`}
                      >
                        <span className="text-gray-500 text-xs font-mono">CANLI AKIŞ: {cam.camera_id}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Kilit Erişim Logları */}
          <Card role="region" aria-label="Kilit erişim logları">
            <CardHeader className="flex flex-row items-center gap-2">
              <History className="w-5 h-5 text-gray-500" aria-hidden="true" />
              <div>
                <CardTitle className="text-lg">Kilit Erişim Logları</CardTitle>
                <CardDescription>Son 10 giriş çıkış denemesi.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex justify-center p-6" role="status" aria-label="Yükleniyor">
                  <Loader2 className="w-6 h-6 animate-spin text-gray-400" aria-hidden="true" />
                </div>
              ) : logs.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">Erişim logu bulunmuyor.</p>
              ) : (
                <ul className="space-y-3" aria-label="Erişim log listesi">
                  {logs.map((log, idx) => (
                    <li
                      key={idx}
                      className="flex items-center justify-between p-3 border rounded-lg bg-white"
                      aria-label={`Oda ${log.room_number} — ${log.access_decision === 'granted' ? 'Erişim kabul edildi' : 'Erişim reddedildi'}`}
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">Oda {log.room_number}</span>
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full ${
                              log.access_decision === 'granted' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                            }`}
                            aria-hidden="true"
                          >
                            {log.access_decision === 'granted' ? 'Kabul' : 'Red'}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">Kullanıcı ID: {log.guest_id || 'Bilinmiyor'}</p>
                        {log.denial_reason && (
                          <p className="text-xs text-red-500 mt-1" role="alert">Sebep: {log.denial_reason}</p>
                        )}
                      </div>
                      <div className="text-xs text-gray-400 text-right" aria-label={`Zaman: ${new Date(log.timestamp).toLocaleString('tr-TR')}`}>
                        {new Date(log.timestamp).toLocaleString('tr-TR')}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── LOCKDOWN Onay Dialogu ────────────────────────────────────── */}
        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogContent
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="lockdown-dialog-title"
            aria-describedby="lockdown-dialog-desc"
          >
            <AlertDialogHeader>
              <AlertDialogTitle
                id="lockdown-dialog-title"
                className="flex items-center gap-2 text-red-700"
              >
                <ShieldAlert className="w-5 h-5" aria-hidden="true" />
                ⚠️ KRİTİK EYLEM: Tesis Lockdown
              </AlertDialogTitle>
              <AlertDialogDescription
                id="lockdown-dialog-desc"
                className="space-y-3"
              >
                <p className="font-semibold text-gray-800">
                  Bu işlem aşağıdakileri gerçekleştirecektir:
                </p>
                <ul className="list-disc list-inside text-sm text-gray-700 space-y-1">
                  <li>Tüm dijital oda anahtarları anında iptal edilir</li>
                  <li>Tüm elektronik kapılar kilitlenir</li>
                  <li>Güvenlik personeline acil bildirim gönderilir</li>
                  <li>Tüm aktif check-in/check-out işlemleri askıya alınır</li>
                </ul>
                <p className="text-sm text-gray-600 mt-3">
                  Onaylamak için aşağıya <strong className="font-mono text-red-700">{LOCKDOWN_CONFIRM_PHRASE}</strong> yazın:
                </p>
                <div className="mt-2 space-y-1">
                  <Input
                    ref={phraseInputRef}
                    id="lockdown-phrase-input"
                    value={confirmPhrase}
                    onChange={(e) => {
                      setConfirmPhrase(e.target.value);
                      setConfirmError('');
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleLockdownConfirmed();
                    }}
                    placeholder={`Yazın: ${LOCKDOWN_CONFIRM_PHRASE}`}
                    className="border-red-300 focus-visible:ring-red-400 font-mono uppercase"
                    aria-label="Lockdown onay ifadesi"
                    aria-required="true"
                    aria-invalid={!!confirmError}
                    aria-describedby={confirmError ? 'lockdown-phrase-error' : undefined}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  {confirmError && (
                    <p
                      id="lockdown-phrase-error"
                      className="text-xs text-red-600 font-medium"
                      role="alert"
                      aria-live="polite"
                    >
                      {confirmError}
                    </p>
                  )}
                </div>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel
                onClick={() => { setConfirmPhrase(''); setConfirmError(''); }}
                aria-label="Lockdown işlemini iptal et ve geri dön"
              >
                İptal — Geri Dön
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={handleLockdownConfirmed}
                className="bg-red-600 hover:bg-red-700 focus-visible:ring-red-600"
                aria-label="Lockdown'ı onayla ve başlat"
                disabled={confirmPhrase.trim().toUpperCase() !== LOCKDOWN_CONFIRM_PHRASE}
              >
                <ShieldAlert className="w-4 h-4 mr-2" aria-hidden="true" />
                LOCKDOWN'I BAŞLAT
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </MaybeLayout>
  );
};

export default PhysicalSecurityDashboard;
