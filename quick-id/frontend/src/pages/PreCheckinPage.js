import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Checkbox } from '../components/ui/checkbox';
import { Camera, CheckCircle, AlertTriangle, Loader2, Shield, QrCode, RefreshCw } from 'lucide-react';

export default function PreCheckinPage() {
  const { tokenId } = useParams();
  const [tokenInfo, setTokenInfo] = useState(null);
  const [consentInfo, setConsentInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [step, setStep] = useState('consent'); // consent, scan, result
  const [kvkkConsent, setKvkkConsent] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [fallbackGuidance, setFallbackGuidance] = useState([]);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    loadData();
    return () => stopCamera();
  }, [tokenId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [tokenRes, consentRes] = await Promise.all([
        api.getPreCheckinInfo(tokenId),
        api.getKvkkConsentInfo(),
      ]);
      setTokenInfo(tokenRes);
      setConsentInfo(consentRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraActive(true);
    } catch (err) {
      setError('Kamera erişimi reddedildi. Lütfen kamera iznini verin.');
    }
  }, []);

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setCameraActive(false);
  };

  const captureAndScan = async () => {
    if (!videoRef.current || !canvasRef.current) return;
    setScanning(true);
    setFallbackGuidance([]);
    try {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0);
      const imageBase64 = canvas.toDataURL('image/jpeg', 0.85);
      
      const result = await api.preCheckinScan(tokenId, imageBase64, kvkkConsent);
      setScanResult(result);
      setStep('result');
      stopCamera();
    } catch (err) {
      if (err.fallback_guidance) {
        setFallbackGuidance(err.fallback_guidance);
      } else {
        setError(err.message);
      }
    } finally {
      setScanning(false);
    }
  };

  if (loading) return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white flex items-center justify-center">
      <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
    </div>
  );

  if (error && !tokenInfo) return (
    <div className="min-h-screen bg-gradient-to-b from-red-50 to-white flex items-center justify-center p-4">
      <Card className="max-w-md w-full">
        <CardContent className="pt-6 text-center">
          <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-lg font-semibold mb-2">QR Kod Geçersiz</h2>
          <p className="text-gray-600">{error}</p>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-lg mx-auto px-4 py-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center">
            <QrCode className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold">Quick ID</h1>
            <p className="text-xs text-gray-500">Ön Check-in</p>
          </div>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-4">
        {/* Property Info */}
        {tokenInfo && (
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-lg">{tokenInfo.property_name}</p>
                  {tokenInfo.guest_name && <p className="text-sm text-gray-500">Misafir: {tokenInfo.guest_name}</p>}
                  {tokenInfo.reservation_ref && <p className="text-sm text-gray-500">Rezervasyon: {tokenInfo.reservation_ref}</p>}
                </div>
                <Badge variant="outline" className="text-green-600 border-green-200 bg-green-50">Aktif</Badge>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 1: KVKK Consent */}
        {step === 'consent' && consentInfo && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Shield className="w-5 h-5 text-blue-500" />
                KVKK Bilgilendirme
              </CardTitle>
              <CardDescription>Kimlik taraması öncesi aydınlatma metni</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-4 max-h-64 overflow-y-auto text-sm whitespace-pre-line">
                {consentInfo.consent_text}
              </div>
              
              <div className="flex items-start gap-3 p-3 bg-blue-50 rounded-lg">
                <Checkbox 
                  id="consent" 
                  checked={kvkkConsent} 
                  onCheckedChange={setKvkkConsent}
                  className="mt-0.5"
                />
                <label htmlFor="consent" className="text-sm font-medium cursor-pointer">
                  Yukarıdaki KVKK aydınlatma metnini okudum ve kişisel verilerimin işlenmesine açık rıza veriyorum.
                </label>
              </div>

              <Button 
                onClick={() => { setStep('scan'); startCamera(); }}
                disabled={!kvkkConsent}
                className="w-full"
              >
                <Camera className="w-4 h-4 mr-2" />
                Kimlik Taramaya Geç
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Step 2: Camera Scan */}
        {step === 'scan' && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Camera className="w-5 h-5 text-blue-500" />
                Kimlik Belgesi Tarama
              </CardTitle>
              <CardDescription>Kimlik belgenizi kameraya gösterin ve fotoğrafını çekin</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="relative rounded-xl overflow-hidden bg-black aspect-video">
                <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
                {!cameraActive && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Loader2 className="w-8 h-8 animate-spin text-white" />
                  </div>
                )}
                {/* Guide overlay */}
                <div className="absolute inset-4 border-2 border-white/40 rounded-lg pointer-events-none" />
              </div>
              <canvas ref={canvasRef} className="hidden" />

              {fallbackGuidance.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <p className="font-medium text-amber-800 text-sm mb-2">
                    <AlertTriangle className="w-4 h-4 inline mr-1" />
                    Tarama başarısız. Öneriler:
                  </p>
                  <ul className="text-sm text-amber-700 space-y-1">
                    {fallbackGuidance.map((g, i) => <li key={i}>{g}</li>)}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <Button variant="outline" onClick={() => { stopCamera(); setStep('consent'); }}>
                  Geri
                </Button>
                <Button onClick={captureAndScan} disabled={scanning || !cameraActive}>
                  {scanning ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Camera className="w-4 h-4 mr-2" />}
                  {scanning ? 'Taranıyor...' : 'Fotoğraf Çek'}
                </Button>
              </div>

              <div className="bg-blue-50 rounded-lg p-3 space-y-1">
                <p className="text-xs font-medium text-blue-700">İpuçları:</p>
                <ul className="text-xs text-blue-600 space-y-0.5">
                  <li>• Belgeyi düz bir yüzeye yerleştirin</li>
                  <li>• İyi aydınlatma altında çekin</li>
                  <li>• Parlama ve gölgeden kaçının</li>
                  <li>• Belgenin tamamı görünür olsun</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 3: Result */}
        {step === 'result' && scanResult && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <CheckCircle className="w-5 h-5 text-green-500" />
                Tarama Başarılı!
              </CardTitle>
              <CardDescription>Kimlik bilgileriniz başarıyla okundu</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
                <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-2" />
                <p className="font-semibold text-green-800">{scanResult.message}</p>
                {scanResult.confidence && (
                  <div className="mt-2">
                    <Badge className={
                      scanResult.confidence.confidence_level === 'high' ? 'bg-green-100 text-green-800' :
                      scanResult.confidence.confidence_level === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-red-100 text-red-800'
                    }>
                      Güvenilirlik: %{scanResult.confidence.overall_score}
                    </Badge>
                  </div>
                )}
              </div>

              {scanResult.documents && scanResult.documents.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Okunan Bilgiler:</p>
                  {scanResult.documents.map((doc, i) => (
                    <div key={i} className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                      {doc.first_name && <p><span className="text-gray-500">Ad:</span> {doc.first_name}</p>}
                      {doc.last_name && <p><span className="text-gray-500">Soyad:</span> {doc.last_name}</p>}
                      {doc.id_number && <p><span className="text-gray-500">Kimlik No:</span> {doc.id_number}</p>}
                      {doc.nationality && <p><span className="text-gray-500">Uyruk:</span> {doc.nationality}</p>}
                      {doc.document_type && <p><span className="text-gray-500">Belge:</span> {doc.document_type}</p>}
                    </div>
                  ))}
                </div>
              )}

              <div className="bg-blue-50 rounded-lg p-3 text-center text-sm text-blue-700">
                <p className="font-medium">Otele vardığınızda resepsiyona QR kodunuzu göstermeniz yeterli!</p>
                <p className="text-xs mt-1">Check-in işleminiz 30 saniyede tamamlanacaktır.</p>
              </div>

              <Button variant="outline" onClick={() => { setScanResult(null); setStep('consent'); setKvkkConsent(false); }} className="w-full">
                <RefreshCw className="w-4 h-4 mr-2" />
                Yeni Tarama
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
