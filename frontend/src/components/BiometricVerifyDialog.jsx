import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  X, Camera, Loader2, ShieldCheck, ShieldAlert, RefreshCcw,
  AlertTriangle, CheckCircle2, ScanFace,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

function dataUrlToBase64(url) {
  if (!url) return '';
  const i = url.indexOf(',');
  return i >= 0 ? url.slice(i + 1) : url;
}

/**
 * Biyometrik doğrulama: kimlik fotoğrafı ↔ canlı selfie
 *
 * props:
 *   open, onClose
 *   documentImageBase64: string  → kimlik üzerindeki fotoğraf (zorunlu)
 *   onResult?: (res) => void     → (match, confidence_score, is_live)
 */
export default function BiometricVerifyDialog({
  open, onClose, documentImageBase64, onResult,
}) {
  const { t } = useTranslation();
  const [step, setStep] = useState('selfie'); // 'selfie' | 'compare' | 'done'
  const [streamReady, setStreamReady] = useState(false);
  const [streamErr, setStreamErr] = useState(null);
  const [selfie, setSelfie] = useState(null); // dataURL
  const [challenge, setChallenge] = useState(null);
  const [busy, setBusy] = useState(false);
  const [livenessRes, setLivenessRes] = useState(null);
  const [matchRes, setMatchRes] = useState(null);

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
      setStep('selfie'); setSelfie(null); setLivenessRes(null); setMatchRes(null);
      setChallenge(null); setStreamErr(null); setStreamReady(false);
      return;
    }
    // Liveness sorusunu çek
    axios.get('/quick-id/biometric/liveness-challenge')
      .then(r => setChallenge(r.data))
      .catch(() => setChallenge(null));
    clearStartTimer();
    startTimerRef.current = setTimeout(startStream, 60);
  }, [open]);

  useEffect(() => () => { clearStartTimer(); stopStream(); }, []);

  const stopStream = () => {
    try {
      const s = streamRef.current;
      if (s) s.getTracks().forEach(t => t.stop());
    } catch (_) {
      /* stream zaten kapalı olabilir */
    }
    streamRef.current = null;
    setStreamReady(false);
  };

  const startStream = async () => {
    setStreamErr(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setStreamErr('Bu tarayıcı kamerayı desteklemiyor');
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = s;
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play().catch((e) => {
        console.debug('[BiometricVerifyDialog] video.play() blocked (browser autoplay policy):', e?.name);
      });
      }
      setStreamReady(true);
    } catch (e) {
      const name = e?.name || '';
      setStreamErr(name === 'NotAllowedError' ? 'Kamera izni reddedildi' : 'Kamera açılamadı');
    }
  };

  const captureSelfie = () => {
    const v = videoRef.current; const c = canvasRef.current;
    if (!v || !c || !v.videoWidth) { toast.error('Kamera henüz hazır değil'); return; }
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
    const dataUrl = c.toDataURL('image/jpeg', 0.9);
    setSelfie(dataUrl);
    stopStream();
  };

  const retake = () => {
    setSelfie(null); setLivenessRes(null); setMatchRes(null);
    setStep('selfie');
    clearStartTimer();
    startTimerRef.current = setTimeout(startStream, 50);
  };

  const runVerification = async () => {
    if (!selfie) return;
    if (!documentImageBase64) { toast.error('Kimlik fotoğrafı yok — önce kimlik tarayın'); return; }
    setBusy(true);
    setStep('compare');
    try {
      const selfieB64 = dataUrlToBase64(selfie);

      // 1) Liveness
      const liv = await axios.post('/quick-id/biometric/liveness-check', {
        image_base64: selfieB64,
        challenge_id: challenge?.challenge_id || '',
        session_id: `pms_${Date.now()}`,
      }).catch(e => ({ data: { success: false, error: e?.response?.data?.detail || e?.message } }));
      setLivenessRes(liv.data);

      // 2) Face compare
      const cmp = await axios.post('/quick-id/biometric/face-compare', {
        document_image_base64: documentImageBase64,
        selfie_image_base64: selfieB64,
      }).catch(e => ({ data: { success: false, error: e?.response?.data?.detail || e?.message } }));
      setMatchRes(cmp.data);

      setStep('done');
      onResult?.({
        match: !!cmp.data?.match,
        confidence_score: cmp.data?.confidence_score || 0,
        is_live: !!liv.data?.is_live,
      });
    } catch (e) {
      toast.error('Biyometrik doğrulama hatası');
      setStep('selfie');
    }
    setBusy(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b bg-gradient-to-r from-emerald-600 to-teal-600 text-white">
          <div className="flex items-center gap-2">
            <ScanFace className="w-5 h-5" />
            <h3 className="font-semibold">{t('cm.components_BiometricVerifyDialog.biyometrik_dogrulama')}</h3>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white p-1 rounded"><X className="w-5 h-5" /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Challenge */}
          {challenge?.instruction && step === 'selfie' && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded text-sm text-emerald-900">
              <b>{t('cm.components_BiometricVerifyDialog.canlilik_testi')}</b> {challenge.instruction}
            </div>
          )}

          {/* Selfie capture */}
          {step === 'selfie' && (
            <>
              {!selfie && (
                <div className="space-y-3">
                  <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
                    <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-contain" />
                    {!streamReady && !streamErr && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center text-white/80 gap-2">
                        <Loader2 className="w-8 h-8 animate-spin" />
                        <span className="text-xs">{t('cm.components_BiometricVerifyDialog.kamera_aciliyor')}</span>
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
                  <div className="flex justify-end">
                    <Button onClick={captureSelfie} disabled={!streamReady} className="bg-emerald-600 hover:bg-emerald-700">
                      <Camera className="w-4 h-4 mr-1" /> {t('cm.components_BiometricVerifyDialog.selfie_cek')}
                    </Button>
                  </div>
                </div>
              )}
              {selfie && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="border rounded-lg overflow-hidden">
                      <div className="px-3 py-2 border-b text-xs font-medium text-gray-600 bg-gray-50">Kimlik</div>
                      <img src={`data:image/jpeg;base64,${documentImageBase64}`} alt="kimlik" className="w-full h-48 object-contain bg-gray-100" />
                    </div>
                    <div className="border rounded-lg overflow-hidden">
                      <div className="px-3 py-2 border-b text-xs font-medium text-gray-600 bg-gray-50">Selfie</div>
                      <img src={selfie} alt="selfie" className="w-full h-48 object-contain bg-gray-100" />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={retake}><RefreshCcw className="w-4 h-4 mr-1" /> {t('cm.components_BiometricVerifyDialog.tekrar_cek')}</Button>
                    <Button onClick={runVerification} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700">
                      {busy ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <ShieldCheck className="w-4 h-4 mr-1" />}
                      {t('cm.components_BiometricVerifyDialog.dogrula')}
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Comparing */}
          {step === 'compare' && (
            <div className="py-12 flex flex-col items-center gap-3">
              <Loader2 className="w-10 h-10 animate-spin text-emerald-600" />
              <span className="text-sm text-gray-600">{t('cm.components_BiometricVerifyDialog.yuz_karsilastiriliyor_ve_canlilik_testi_')}</span>
            </div>
          )}

          {/* Result */}
          {step === 'done' && (
            <div className="space-y-3">
              <div className={`p-4 rounded-lg border flex items-center gap-3 ${
                matchRes?.match && livenessRes?.is_live
                  ? 'bg-emerald-50 border-emerald-200'
                  : 'bg-amber-50 border-amber-200'
              }`}>
                {matchRes?.match && livenessRes?.is_live ? (
                  <ShieldCheck className="w-10 h-10 text-emerald-600" />
                ) : (
                  <ShieldAlert className="w-10 h-10 text-amber-600" />
                )}
                <div className="flex-1">
                  <div className="text-sm font-semibold text-gray-900">
                    {matchRes?.match && livenessRes?.is_live
                      ? 'Doğrulama başarılı'
                      : 'Doğrulama gözden geçirilmeli'}
                  </div>
                  <div className="text-xs text-gray-600 mt-0.5">
                    {t('cm.components_BiometricVerifyDialog.eslesme')} {matchRes?.match ? 'EVET' : 'HAYIR'} {t('cm.components_BiometricVerifyDialog.guven')}{matchRes?.confidence_score ?? 0}
                    {' · '}{t('cm.components_BiometricVerifyDialog.canli')} {livenessRes?.is_live ? 'EVET' : 'HAYIR'}
                  </div>
                </div>
              </div>

              {matchRes?.warnings?.length > 0 && (
                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
                  {matchRes.warnings.slice(0, 3).map((w, i) => <div key={i}>• {w}</div>)}
                </div>
              )}
              {livenessRes?.spoof_indicators?.length > 0 && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
                  <b>{t('cm.components_BiometricVerifyDialog.sahtekarlik_gostergeleri')}</b>
                  {livenessRes.spoof_indicators.slice(0, 3).map((s, i) => <div key={i}>• {s}</div>)}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={retake}><RefreshCcw className="w-4 h-4 mr-1" /> Yeniden Dene</Button>
                <Button onClick={onClose} className="bg-emerald-600 hover:bg-emerald-700">
                  <CheckCircle2 className="w-4 h-4 mr-1" /> {t('cm.components_BiometricVerifyDialog.tamam')}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
