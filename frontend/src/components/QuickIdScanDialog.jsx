import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Loader2, Camera, Upload, X, CheckCircle2, AlertTriangle,
  ScanLine, FileImage, Video, RefreshCcw, Image as ImageIcon
} from 'lucide-react';

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

function dataUrlToBase64(url) {
  if (!url) return '';
  const i = url.indexOf(',');
  return i >= 0 ? url.slice(i + 1) : url;
}

const DOC_LABELS = {
  tc_kimlik: 'TC Kimlik',
  passport: 'Pasaport',
  drivers_license: 'Sürücü Belgesi',
  old_nufus_cuzdani: 'Nüfus Cüzdanı (Eski)',
  other: 'Diğer Belge',
};

/**
 * Kimlik tarama diyaloğu
 * props:
 *   open, onClose
 *   onExtracted: (doc) => void          → form'a doldurmak için
 *   guestId?: string                    → verilirse "profil fotoğrafı kaydet" toggle aktif olur
 *   defaultSavePhoto?: boolean          → toggle varsayılanı (default: true)
 */
export default function QuickIdScanDialog({
  open, onClose, onExtracted, onImageCaptured, guestId = null, defaultSavePhoto = true,
}) {
  const [mode, setMode] = useState('upload'); // 'upload' | 'camera' | 'live'
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [serviceStatus, setServiceStatus] = useState(null);
  const [savePhoto, setSavePhoto] = useState(defaultSavePhoto);
  const [savingPhoto, setSavingPhoto] = useState(false);
  const [streamErr, setStreamErr] = useState(null);
  const [streamReady, setStreamReady] = useState(false);

  const fileInputRef = useRef(null);
  const camInputRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const startTimerRef = useRef(null);

  const clearStartTimer = () => {
    if (startTimerRef.current) { clearTimeout(startTimerRef.current); startTimerRef.current = null; }
  };

  useEffect(() => {
    if (!open) {
      clearStartTimer();
      stopStream();
      setFile(null); setPreview(null); setResult(null);
      setMode('upload'); setStreamErr(null); setStreamReady(false);
      return;
    }
    axios.get('/quick-id/health').then(r => setServiceStatus(r.data)).catch(() => setServiceStatus({ available: false }));
  }, [open]);

  useEffect(() => () => { clearStartTimer(); stopStream(); }, []);

  const stopStream = () => {
    try {
      const s = streamRef.current;
      if (s) s.getTracks().forEach(t => t.stop());
    } catch (_) {}
    streamRef.current = null;
    setStreamReady(false);
  };

  const startStream = async () => {
    setStreamErr(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setStreamErr('Bu tarayıcı canlı kamerayı desteklemiyor. "Kamera ile Çek" seçeneğini kullanın.');
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = s;
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play().catch(() => {});
      }
      setStreamReady(true);
    } catch (e) {
      const name = e?.name || '';
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        setStreamErr('Kamera izni reddedildi. Tarayıcı ayarlarından izin verin.');
      } else if (name === 'NotFoundError') {
        setStreamErr('Kamera bulunamadı.');
      } else {
        setStreamErr('Kamera açılamadı: ' + (e?.message || name || 'bilinmeyen hata'));
      }
    }
  };

  const captureFromVideo = () => {
    const v = videoRef.current; const c = canvasRef.current;
    if (!v || !c || !v.videoWidth) { toast.error('Kamera henüz hazır değil'); return; }
    c.width = v.videoWidth; c.height = v.videoHeight;
    const ctx = c.getContext('2d');
    ctx.drawImage(v, 0, 0, c.width, c.height);
    c.toBlob((blob) => {
      if (!blob) { toast.error('Kare yakalanamadı'); return; }
      const f = new File([blob], `id_capture_${Date.now()}.jpg`, { type: 'image/jpeg' });
      handleFile(f);
      stopStream();
      setMode('upload');
    }, 'image/jpeg', 0.92);
  };

  if (!open) return null;

  const handleFile = (f) => {
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { toast.error('Dosya 8MB sınırını aşıyor'); return; }
    setFile(f); setResult(null);
    const url = URL.createObjectURL(f);
    setPreview(url);
  };

  const handleScan = async () => {
    if (!file) { toast.error('Önce bir kimlik fotoğrafı seçin'); return; }
    setScanning(true);
    try {
      const b64 = await fileToBase64(file);
      const res = await axios.post('/quick-id/scan', { image_base64: b64, smart_mode: true });
      setResult(res.data);
      onImageCaptured?.(b64);
      const doc = res.data?.extracted_data?.documents?.[0] || res.data?.documents?.[0];
      if (doc) {
        if (res.data.demo_mode) {
          toast.warning('Demo veri gösteriliyor (OCR sağlayıcı yapılandırılmadı)');
        } else {
          const conf = res.data?.scan?.confidence_score ?? res.data?.confidence?.overall_score;
          toast.success(`Kimlik tarandı${conf ? ` (güven: %${conf})` : ''}`);
        }
      } else {
        toast.error('Belgede bilgi bulunamadı');
      }
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || 'Tarama hatası';
      toast.error(msg);
    }
    setScanning(false);
  };

  const handleApply = async () => {
    const doc = result?.extracted_data?.documents?.[0] || result?.documents?.[0];
    if (!doc) return;
    onExtracted?.(doc);

    // Profil fotoğrafı kaydet (opsiyonel)
    if (guestId && savePhoto && preview) {
      setSavingPhoto(true);
      try {
        // preview bir blob URL → fetch + blob → base64
        const blob = await fetch(preview).then(r => r.blob());
        const dataUrl = await new Promise((res, rej) => {
          const fr = new FileReader();
          fr.onload = () => res(fr.result);
          fr.onerror = rej;
          fr.readAsDataURL(blob);
        });
        const b64 = dataUrlToBase64(dataUrl);
        await axios.post(`/guests/${guestId}/photo`, { photo_base64: b64, source: 'quick_id_scan' });
      } catch (e) {
        // PMS'in kendi guest photo endpoint'i olmayabilir → sessiz geç
        console.warn('Profil fotoğrafı kaydedilemedi:', e?.message);
      }
      setSavingPhoto(false);
    }

    toast.success('Bilgiler forma aktarıldı');
    onClose?.();
  };

  const doc = result?.extracted_data?.documents?.[0] || result?.documents?.[0];
  const docTypeLabel = doc?.document_type ? (DOC_LABELS[doc.document_type] || doc.document_type) : null;
  const mrzList = result?.mrz_results || [];
  const mrz = Array.isArray(mrzList) && mrzList.length ? mrzList[0] : null;
  const confidence = result?.scan?.confidence_score ?? result?.confidence?.overall_score;
  const confLevel = result?.scan?.confidence_level ?? result?.confidence?.confidence_level;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" data-testid="quickid-scan-dialog">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[92vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b bg-gradient-to-r from-indigo-600 to-blue-600 text-white">
          <div className="flex items-center gap-2">
            <ScanLine className="w-5 h-5" />
            <h3 className="font-semibold">Kimlik Tara (Quick-ID)</h3>
            {serviceStatus?.available === false && (
              <Badge className="bg-amber-400/30 border-amber-300/50 text-amber-50 ml-2 text-[10px]">Servis kapalı</Badge>
            )}
            {serviceStatus?.available && !serviceStatus?.service_key_configured && (
              <Badge className="bg-yellow-400/30 border-yellow-300/50 text-yellow-50 ml-2 text-[10px]">Demo mod</Badge>
            )}
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white p-1 rounded"><X className="w-5 h-5" /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Mode tabs */}
          {!preview && mode !== 'live' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 hover:border-blue-400 hover:bg-blue-50 rounded-xl p-6 flex flex-col items-center gap-2 transition-colors"
                data-testid="quickid-upload-btn"
              >
                <Upload className="w-8 h-8 text-gray-400" />
                <div className="text-sm font-medium text-gray-700">Dosyadan Yükle</div>
                <div className="text-[11px] text-gray-500 text-center">JPEG, PNG (en fazla 8MB)</div>
              </button>
              <button
                onClick={() => camInputRef.current?.click()}
                className="border-2 border-dashed border-gray-300 hover:border-indigo-400 hover:bg-indigo-50 rounded-xl p-6 flex flex-col items-center gap-2 transition-colors"
                data-testid="quickid-camera-btn"
              >
                <Camera className="w-8 h-8 text-gray-400" />
                <div className="text-sm font-medium text-gray-700">Mobilden Çek</div>
                <div className="text-[11px] text-gray-500 text-center">Telefonun arka kamerası</div>
              </button>
              <button
                onClick={() => { setMode('live'); clearStartTimer(); startTimerRef.current = setTimeout(startStream, 50); }}
                className="border-2 border-dashed border-gray-300 hover:border-emerald-400 hover:bg-emerald-50 rounded-xl p-6 flex flex-col items-center gap-2 transition-colors"
                data-testid="quickid-live-btn"
              >
                <Video className="w-8 h-8 text-gray-400" />
                <div className="text-sm font-medium text-gray-700">Canlı Webcam</div>
                <div className="text-[11px] text-gray-500 text-center">Resepsiyon kamerası</div>
              </button>
              <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={e => handleFile(e.target.files?.[0])} />
              <input ref={camInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={e => handleFile(e.target.files?.[0])} />
            </div>
          )}

          {/* Live webcam */}
          {!preview && mode === 'live' && (
            <div className="space-y-3">
              <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
                <video
                  ref={videoRef}
                  autoPlay playsInline muted
                  className="w-full h-full object-contain"
                />
                {!streamReady && !streamErr && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-white/80 gap-2">
                    <Loader2 className="w-8 h-8 animate-spin" />
                    <span className="text-xs">Kamera açılıyor…</span>
                  </div>
                )}
                {streamErr && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-white p-4 text-center gap-2">
                    <AlertTriangle className="w-8 h-8 text-amber-400" />
                    <span className="text-xs">{streamErr}</span>
                    <Button size="sm" variant="outline" className="text-gray-800" onClick={startStream}>
                      <RefreshCcw className="w-3 h-3 mr-1" /> Tekrar dene
                    </Button>
                  </div>
                )}
                <canvas ref={canvasRef} className="hidden" />
              </div>
              <div className="flex items-center justify-between gap-2">
                <Button variant="outline" size="sm" onClick={() => { stopStream(); setMode('upload'); setStreamErr(null); }}>
                  Geri
                </Button>
                <Button
                  size="sm"
                  className="bg-emerald-600 hover:bg-emerald-700"
                  onClick={captureFromVideo}
                  disabled={!streamReady}
                >
                  <Camera className="w-4 h-4 mr-1" /> Kareyi Yakala
                </Button>
              </div>
            </div>
          )}

          {/* Preview */}
          {preview && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="border rounded-lg overflow-hidden bg-gray-50 flex flex-col">
                <div className="flex items-center justify-between px-3 py-2 border-b bg-white">
                  <span className="text-xs font-medium text-gray-600 flex items-center gap-1">
                    <FileImage className="w-3.5 h-3.5" /> Belge Önizleme
                  </span>
                  <Button size="sm" variant="ghost" className="h-6 px-2 text-xs"
                    onClick={() => { setFile(null); setPreview(null); setResult(null); }}>
                    Değiştir
                  </Button>
                </div>
                <div className="flex-1 flex items-center justify-center p-3 min-h-[200px]">
                  <img src={preview} alt="kimlik" className="max-h-[320px] max-w-full object-contain rounded" />
                </div>
              </div>

              <div className="border rounded-lg bg-white flex flex-col">
                <div className="px-3 py-2 border-b text-xs font-medium text-gray-600 flex items-center justify-between">
                  <span>Çıkarılan Bilgiler</span>
                  {docTypeLabel && (
                    <Badge variant="secondary" className="text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-200">
                      {docTypeLabel}
                    </Badge>
                  )}
                </div>
                <div className="flex-1 p-3 text-sm">
                  {!result && !scanning && (
                    <div className="h-full flex flex-col items-center justify-center gap-3 text-gray-400 py-8">
                      <ScanLine className="w-10 h-10" />
                      <span className="text-xs">Taramak için aşağıdaki düğmeye basın</span>
                    </div>
                  )}
                  {scanning && (
                    <div className="h-full flex flex-col items-center justify-center gap-3 py-8">
                      <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                      <span className="text-xs text-gray-600">Kimlik taranıyor…</span>
                    </div>
                  )}
                  {doc && (
                    <div className="space-y-1.5 text-xs">
                      <Row label="Ad" value={doc.first_name} />
                      <Row label="Soyad" value={doc.last_name} />
                      <Row label="Belge Tipi" value={docTypeLabel || doc.document_type} />
                      <Row label="Kimlik/Pasaport No" value={doc.id_number || doc.document_number} />
                      <Row label="Doğum Tarihi" value={doc.birth_date} />
                      <Row label="Cinsiyet" value={doc.gender} />
                      <Row label="Uyruk" value={doc.nationality} />
                      <Row label="Doğum Yeri" value={doc.birth_place} />
                      <Row label="Anne Adı" value={doc.mother_name} />
                      <Row label="Baba Adı" value={doc.father_name} />
                      <Row label="Veriliş" value={doc.issue_date} />
                      <Row label="Son Geçerlilik" value={doc.expiry_date} />

                      {/* Confidence + MRZ */}
                      <div className="pt-2 mt-2 border-t flex flex-wrap items-center gap-2 text-[11px]">
                        {!!confidence && (
                          <span className="inline-flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                            <span className="text-gray-700">Güven <b>%{confidence}</b>{confLevel ? ` (${confLevel})` : ''}</span>
                          </span>
                        )}
                        {mrz && (
                          <Badge className={`text-[10px] ${mrz.is_valid ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                            MRZ {mrz.is_valid ? 'geçerli' : 'şüpheli'}
                          </Badge>
                        )}
                      </div>

                      {result?.demo_mode && (
                        <div className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-[11px] text-amber-800 flex gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                          <span><b>Demo mod:</b> Gerçek OCR için OPENAI_API_KEY veya GEMINI_API_KEY yapılandırılmalıdır.</span>
                        </div>
                      )}
                      {doc?.warnings?.length > 0 && (
                        <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-[10px] text-yellow-800">
                          {doc.warnings.slice(0, 3).map((w, i) => <div key={i}>• {w}</div>)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Save photo toggle */}
          {preview && doc && guestId && (
            <label className="flex items-center gap-2 text-xs text-gray-700 bg-blue-50 border border-blue-200 rounded p-2 cursor-pointer">
              <input
                type="checkbox"
                checked={savePhoto}
                onChange={e => setSavePhoto(e.target.checked)}
                className="rounded"
              />
              <ImageIcon className="w-4 h-4 text-blue-600" />
              <span>Çekilen kareyi misafirin profil fotoğrafı olarak kaydet</span>
            </label>
          )}
        </div>

        {/* Footer actions */}
        <div className="border-t px-5 py-3 flex items-center justify-between bg-gray-50">
          <div className="text-[11px] text-gray-500">
            {serviceStatus?.available ? 'Servis çevrimiçi' : 'Servis çevrimdışı — lütfen Quick-ID API\'yi başlatın'}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} size="sm">Kapat</Button>
            {preview && !result && (
              <Button onClick={handleScan} disabled={scanning || !file} size="sm" className="bg-indigo-600 hover:bg-indigo-700">
                {scanning ? <><Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> Taranıyor</> : <><ScanLine className="w-3.5 h-3.5 mr-1" /> Tara</>}
              </Button>
            )}
            {result && doc && (
              <Button onClick={handleApply} size="sm" className="bg-emerald-600 hover:bg-emerald-700" disabled={savingPhoto}>
                {savingPhoto ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1" />}
                Formu Doldur
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-2 py-0.5 border-b border-gray-100 last:border-0">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-800 truncate max-w-[60%]" title={value || ''}>{value || '—'}</span>
    </div>
  );
}
