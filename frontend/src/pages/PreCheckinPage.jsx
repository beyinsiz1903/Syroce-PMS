import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, CheckCircle2, ScanLine, Camera, Upload, X, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const res = reader.result || '';
      const comma = res.indexOf(',');
      resolve(comma >= 0 ? res.slice(comma + 1) : res);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

/**
 * Public ön check-in sayfası — QR ile erişilir.
 * Misafir, otele varmadan kendi telefonundan kimliğini tarar.
 *
 * Path: /precheckin/:token
 */
export default function PreCheckinPage() {
  const { t } = useTranslation();
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [loadErr, setLoadErr] = useState(null);
  const [consent, setConsent] = useState(false);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    if (!token) return;
    axios.get(`/quick-id/precheckin/${token}/info`)
      .then(r => setInfo(r.data))
      .catch(e => setLoadErr(e?.response?.data?.detail || 'QR kodu geçersiz veya süresi dolmuş'));
  }, [token]);

  const handleFile = (f) => {
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { toast.error('Dosya 8MB sınırını aşıyor'); return; }
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const submit = async () => {
    if (!file) { toast.error('Önce kimlik fotoğrafı çekin veya yükleyin'); return; }
    if (!consent) { toast.error('KVKK onayı gerekli'); return; }
    setScanning(true);
    try {
      const b64 = await fileToBase64(file);
      const r = await axios.post(`/quick-id/precheckin/${token}/scan`, {
        image_base64: b64,
        kvkk_consent: true,
      });
      setDone(r.data);
      toast.success('Kimlik başarıyla iletildi');
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || 'Tarama hatası';
      toast.error(msg);
    }
    setScanning(false);
  };

  if (loadErr) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-8 pb-8 text-center">
            <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-900">{t('cm.pages_PreCheckinPage.gecersiz_qr_kod')}</h2>
            <p className="text-sm text-gray-600 mt-2">{loadErr}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!info) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (done) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-8 pb-8 text-center">
            <CheckCircle2 className="w-14 h-14 text-emerald-600 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-900">{t('cm.pages_PreCheckinPage.tesekkurler')}</h2>
            <p className="text-sm text-gray-600 mt-2">
              {t('cm.pages_PreCheckinPage.kimliginiz')} <b>{info.property_name}</b> {t('cm.pages_PreCheckinPage.resepsiyonuna_iletildi_otele_vardiginizd')}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 p-4">
      <div className="max-w-md mx-auto pt-8 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ScanLine className="w-5 h-5 text-indigo-600" />
              {t('cm.pages_PreCheckinPage.hizli_on_check_in')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div><span className="text-gray-500">Otel:</span> <b>{info.property_name}</b></div>
            {info.guest_name && <div><span className="text-gray-500">{t('cm.pages_PreCheckinPage.misafir')}</span> <b>{info.guest_name}</b></div>}
            {info.reservation_ref && <div><span className="text-gray-500">{t('cm.pages_PreCheckinPage.rezervasyon')}</span> <b>{info.reservation_ref}</b></div>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('cm.pages_PreCheckinPage.kimliginizi_tarayin')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!preview && (
              <div className="grid grid-cols-2 gap-2">
                <label className="border-2 border-dashed border-gray-300 hover:border-indigo-400 rounded-xl p-4 flex flex-col items-center gap-2 cursor-pointer">
                  <Camera className="w-8 h-8 text-gray-400" />
                  <span className="text-xs font-medium text-gray-700">{t('cm.pages_PreCheckinPage.kamerayla_cek')}</span>
                  <input type="file" accept="image/*" capture="environment" className="hidden" onChange={e => handleFile(e.target.files?.[0])} />
                </label>
                <label className="border-2 border-dashed border-gray-300 hover:border-blue-400 rounded-xl p-4 flex flex-col items-center gap-2 cursor-pointer">
                  <Upload className="w-8 h-8 text-gray-400" />
                  <span className="text-xs font-medium text-gray-700">{t('cm.pages_PreCheckinPage.galeriden_sec')}</span>
                  <input type="file" accept="image/*" className="hidden" onChange={e => handleFile(e.target.files?.[0])} />
                </label>
              </div>
            )}
            {preview && (
              <div className="relative">
                <img src={preview} alt="kimlik" className="w-full max-h-80 object-contain rounded-lg border" />
                <button onClick={() => { setFile(null); setPreview(null); }}
                  className="absolute top-2 right-2 bg-white/90 rounded-full p-1 shadow">
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            <label className="flex items-start gap-2 text-xs text-gray-700 mt-3">
              <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-0.5" />
              <span>
                {t('cm.pages_PreCheckinPage.kimligimin')} <b>{info.property_name}</b> {t('cm.pages_PreCheckinPage.tarafindan_check_in_icin_islenmesine_ona')}
              </span>
            </label>

            <Button onClick={submit} disabled={scanning || !file || !consent} className="w-full bg-indigo-600 hover:bg-indigo-700">
              {scanning ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> {t('cm.pages_PreCheckinPage.gonderiliyor')}</> : <><CheckCircle2 className="w-4 h-4 mr-2" /> {t('cm.pages_PreCheckinPage.gonder')}</>}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
