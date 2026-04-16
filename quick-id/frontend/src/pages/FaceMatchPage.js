import { useState, useRef, useCallback, useEffect } from 'react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Progress } from '../components/ui/progress';
import { Camera, UserCheck, ShieldCheck, AlertTriangle, Loader2, CheckCircle, XCircle, RefreshCw, Eye } from 'lucide-react';

export default function FaceMatchPage() {
  const [tab, setTab] = useState('match');
  
  // Face matching state
  const [documentImage, setDocumentImage] = useState(null);
  const [selfieImage, setSelfieImage] = useState(null);
  const [matchResult, setMatchResult] = useState(null);
  const [matching, setMatching] = useState(false);
  
  // Liveness state
  const [livenessChallenge, setLivenessChallenge] = useState(null);
  const [livenessResult, setLivenessResult] = useState(null);
  const [checkingLiveness, setCheckingLiveness] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const docInputRef = useRef(null);
  const selfieInputRef = useRef(null);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraActive(true);
    } catch {
      alert('Kamera erişimi reddedildi');
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setCameraActive(false);
  }, []);

  useEffect(() => () => stopCamera(), [stopCamera]);

  const captureFrame = () => {
    if (!videoRef.current || !canvasRef.current) return null;
    const canvas = canvasRef.current;
    const video = videoRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.85);
  };

  const handleFileUpload = (setter) => (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setter(reader.result);
    reader.readAsDataURL(file);
  };

  const runFaceMatch = async () => {
    if (!documentImage || !selfieImage) return;
    setMatching(true);
    setMatchResult(null);
    try {
      const result = await api.compareFaces(documentImage, selfieImage);
      setMatchResult(result);
    } catch (err) {
      setMatchResult({ success: false, match: false, confidence_score: 0, notes: err.message });
    } finally {
      setMatching(false);
    }
  };

  const loadLivenessChallenge = async () => {
    try {
      const challenge = await api.getLivenessChallenge();
      setLivenessChallenge(challenge);
      setLivenessResult(null);
      startCamera();
    } catch (err) {
      alert('Canlılık testi yüklenemedi: ' + err.message);
    }
  };

  const runLivenessCheck = async () => {
    const image = captureFrame();
    if (!image || !livenessChallenge) return;
    setCheckingLiveness(true);
    try {
      const result = await api.checkLiveness(image, livenessChallenge.challenge.challenge_id, livenessChallenge.session_id);
      setLivenessResult(result);
      stopCamera();
    } catch (err) {
      setLivenessResult({ success: false, is_live: false, notes: err.message });
    } finally {
      setCheckingLiveness(false);
    }
  };

  const ScoreBar = ({ score, label }) => (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="font-semibold">%{score}</span>
      </div>
      <Progress value={score} className={`h-2 ${score >= 80 ? '[&>div]:bg-green-500' : score >= 50 ? '[&>div]:bg-yellow-500' : '[&>div]:bg-red-500'}`} />
    </div>
  );

  const AnalysisItem = ({ label, value }) => {
    const colors = { match: 'text-green-600', partial: 'text-yellow-600', mismatch: 'text-red-600' };
    const labels = { match: 'Eşleşme', partial: 'Kısmen', mismatch: 'Eşleşmez' };
    return (
      <div className="flex justify-between text-sm py-1 border-b border-gray-100 last:border-0">
        <span className="text-gray-600">{label}</span>
        <span className={`font-medium ${colors[value] || 'text-gray-500'}`}>{labels[value] || value}</span>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Biyometrik Doğrulama</h1>
        <p className="text-gray-500 mt-1">Yüz eşleştirme ve canlılık testi</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-2 w-full max-w-md">
          <TabsTrigger value="match"><UserCheck className="w-4 h-4 mr-2" />Yüz Eşleştirme</TabsTrigger>
          <TabsTrigger value="liveness"><Eye className="w-4 h-4 mr-2" />Canlılık Testi</TabsTrigger>
        </TabsList>

        {/* Face Matching Tab */}
        <TabsContent value="match" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Document Photo */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Belge Fotoğrafı</CardTitle>
                <CardDescription>Kimlik belgesindeki fotoğraf</CardDescription>
              </CardHeader>
              <CardContent>
                <input ref={docInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileUpload(setDocumentImage)} />
                {documentImage ? (
                  <div className="relative">
                    <img src={documentImage} alt="Belge" className="w-full h-48 object-cover rounded-lg" />
                    <Button size="sm" variant="outline" className="absolute bottom-2 right-2" onClick={() => { setDocumentImage(null); setMatchResult(null); }}>
                      <RefreshCw className="w-3 h-3 mr-1" />Değiştir
                    </Button>
                  </div>
                ) : (
                  <div className="w-full h-48 border-2 border-dashed border-gray-200 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 transition-colors" onClick={() => docInputRef.current?.click()}>
                    <Camera className="w-8 h-8 text-gray-400 mb-2" />
                    <span className="text-sm text-gray-500">Fotoğraf Yükle</span>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Selfie Photo */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Canlı Fotoğraf (Selfie)</CardTitle>
                <CardDescription>Misafirin güncel fotoğrafı</CardDescription>
              </CardHeader>
              <CardContent>
                <input ref={selfieInputRef} type="file" accept="image/*" capture="user" className="hidden" onChange={handleFileUpload(setSelfieImage)} />
                {selfieImage ? (
                  <div className="relative">
                    <img src={selfieImage} alt="Selfie" className="w-full h-48 object-cover rounded-lg" />
                    <Button size="sm" variant="outline" className="absolute bottom-2 right-2" onClick={() => { setSelfieImage(null); setMatchResult(null); }}>
                      <RefreshCw className="w-3 h-3 mr-1" />Değiştir
                    </Button>
                  </div>
                ) : (
                  <div className="w-full h-48 border-2 border-dashed border-gray-200 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 transition-colors" onClick={() => selfieInputRef.current?.click()}>
                    <Camera className="w-8 h-8 text-gray-400 mb-2" />
                    <span className="text-sm text-gray-500">Selfie Çek/Yükle</span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <Button onClick={runFaceMatch} disabled={!documentImage || !selfieImage || matching} className="w-full md:w-auto">
            {matching ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <UserCheck className="w-4 h-4 mr-2" />}
            {matching ? 'Karşılaştırılıyor...' : 'Yüzleri Karşılaştır'}
          </Button>

          {/* Match Result */}
          {matchResult && (
            <Card className={matchResult.match ? 'border-green-200 bg-green-50/30' : 'border-red-200 bg-red-50/30'}>
              <CardContent className="pt-6 space-y-4">
                <div className="flex items-center gap-3">
                  {matchResult.match ? (
                    <CheckCircle className="w-10 h-10 text-green-500" />
                  ) : (
                    <XCircle className="w-10 h-10 text-red-500" />
                  )}
                  <div>
                    <h3 className="text-lg font-bold">{matchResult.match ? 'Yüzler Eşleşti' : 'Yüzler Eşleşmedi'}</h3>
                    <p className="text-sm text-gray-600">{matchResult.notes}</p>
                  </div>
                  <Badge className={`ml-auto text-lg px-3 py-1 ${
                    matchResult.confidence_score >= 80 ? 'bg-green-100 text-green-800' :
                    matchResult.confidence_score >= 50 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    %{matchResult.confidence_score}
                  </Badge>
                </div>

                <ScoreBar score={matchResult.confidence_score} label="Eşleştirme Güven Skoru" />

                {matchResult.analysis && (
                  <div className="bg-white rounded-lg p-3">
                    <p className="text-sm font-medium mb-2">Detaylı Analiz:</p>
                    <AnalysisItem label="Yüz yapısı" value={matchResult.analysis.facial_structure} />
                    <AnalysisItem label="Gözler" value={matchResult.analysis.eyes} />
                    <AnalysisItem label="Burun" value={matchResult.analysis.nose} />
                    <AnalysisItem label="Ağız" value={matchResult.analysis.mouth} />
                    <AnalysisItem label="Genel oranlar" value={matchResult.analysis.overall_proportions} />
                  </div>
                )}

                {matchResult.warnings && matchResult.warnings.length > 0 && (
                  <div className="bg-amber-50 rounded-lg p-3">
                    <p className="text-sm font-medium text-amber-700 mb-1">
                      <AlertTriangle className="w-4 h-4 inline mr-1" />Uyarılar:
                    </p>
                    <ul className="text-sm text-amber-600 space-y-0.5">
                      {matchResult.warnings.map((w, i) => <li key={i}>• {w}</li>)}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Liveness Tab */}
        <TabsContent value="liveness" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-blue-500" />
                Canlılık Testi (Liveness Detection)
              </CardTitle>
              <CardDescription>Fotoğraf/video spoofing'i tespit eder. Kişinin gerçekten canlı olup olmadığını kontrol eder.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!livenessChallenge ? (
                <Button onClick={loadLivenessChallenge} className="w-full">
                  <Eye className="w-4 h-4 mr-2" />
                  Canlılık Testi Başlat
                </Button>
              ) : (
                <>
                  {/* Challenge instruction */}
                  <div className="bg-blue-50 rounded-xl p-4 text-center">
                    <p className="text-lg font-bold text-blue-800">{livenessChallenge.challenge.instruction}</p>
                    <p className="text-sm text-blue-600 mt-1">Bu hareketi yapın ve fotoğraf çekin</p>
                  </div>

                  {/* Camera */}
                  <div className="relative rounded-xl overflow-hidden bg-black aspect-video">
                    <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                      <div className="w-48 h-48 border-4 border-white/40 rounded-full" />
                    </div>
                  </div>
                  <canvas ref={canvasRef} className="hidden" />

                  <div className="grid grid-cols-2 gap-3">
                    <Button variant="outline" onClick={() => { stopCamera(); setLivenessChallenge(null); setLivenessResult(null); }}>
                      İptal
                    </Button>
                    <Button onClick={runLivenessCheck} disabled={checkingLiveness || !cameraActive}>
                      {checkingLiveness ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Camera className="w-4 h-4 mr-2" />}
                      {checkingLiveness ? 'Kontrol...' : 'Fotoğraf Çek'}
                    </Button>
                  </div>

                  <Button variant="outline" size="sm" onClick={loadLivenessChallenge} className="w-full">
                    <RefreshCw className="w-3 h-3 mr-1" />Yeni Soru
                  </Button>
                </>
              )}

              {/* Liveness Result */}
              {livenessResult && (
                <div className={`rounded-lg p-4 ${livenessResult.is_live ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                  <div className="flex items-center gap-3">
                    {livenessResult.is_live ? (
                      <CheckCircle className="w-8 h-8 text-green-500" />
                    ) : (
                      <XCircle className="w-8 h-8 text-red-500" />
                    )}
                    <div>
                      <p className="font-bold text-lg">{livenessResult.is_live ? 'Canlı Kişi Doğrulandı' : 'Canlılık Doğrulanamadı'}</p>
                      <p className="text-sm text-gray-600">{livenessResult.notes}</p>
                    </div>
                    <Badge className={`ml-auto ${livenessResult.confidence_score >= 80 ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      %{livenessResult.confidence_score}
                    </Badge>
                  </div>
                  
                  {livenessResult.challenge_completed !== undefined && (
                    <p className="text-sm mt-2">
                      Hareket: {livenessResult.challenge_completed ? '✅ Tamamlandı' : '❌ Tamamlanmadı'}
                    </p>
                  )}

                  {livenessResult.spoof_indicators && livenessResult.spoof_indicators.length > 0 && (
                    <div className="mt-2 text-sm text-red-600">
                      <p className="font-medium">Spoofing göstergeleri:</p>
                      <ul>{livenessResult.spoof_indicators.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
