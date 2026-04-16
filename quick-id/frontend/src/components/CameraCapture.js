import { useRef, useState, useCallback, useEffect } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Camera, RefreshCcw, SwitchCamera, AlertTriangle, Upload, FileImage } from 'lucide-react';

const MAX_FILE_SIZE_MB = 10;
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];

export default function CameraCapture({ onCapture, disabled }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const fileInputRef = useRef(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [error, setError] = useState(null);
  const [facingMode, setFacingMode] = useState('environment');
  const [showFlash, setShowFlash] = useState(false);
  const [capturedImage, setCapturedImage] = useState(null);
  const [mode, setMode] = useState('camera'); // 'camera' | 'upload'
  const [dragActive, setDragActive] = useState(false);

  const startCamera = useCallback(async () => {
    try {
      setError(null);
      setCameraReady(false);
      
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
      
      const constraints = {
        video: {
          facingMode: facingMode,
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        }
      };
      
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current.play();
          setCameraReady(true);
        };
      }
    } catch (err) {
      console.error('Camera error:', err);
      if (err.name === 'NotAllowedError') {
        setError('Kamera erişimi reddedildi. Lütfen tarayıcı izinlerini kontrol edin.');
      } else if (err.name === 'NotFoundError') {
        setError('Kamera bulunamadı. Dosya yükleme modunu kullanabilirsiniz.');
      } else {
        setError(`Kamera hatası: ${err.message}`);
      }
    }
  }, [facingMode]);

  useEffect(() => {
    if (mode === 'camera') {
      startCamera();
    } else {
      // Stop camera when switching to upload mode
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
    }
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
    };
  }, [startCamera, mode]);

  const capture = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;
    
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    
    // Flash effect
    setShowFlash(true);
    setTimeout(() => setShowFlash(false), 200);
    
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
    setCapturedImage(dataUrl);
    
    if (onCapture) {
      onCapture(dataUrl);
    }
  }, [onCapture]);

  const retake = useCallback(() => {
    setCapturedImage(null);
    if (mode === 'camera') {
      startCamera();
    }
  }, [startCamera, mode]);

  const switchCamera = useCallback(() => {
    setFacingMode(prev => prev === 'environment' ? 'user' : 'environment');
    setCapturedImage(null);
  }, []);

  // File upload handling
  const handleFileSelect = useCallback((file) => {
    if (!file) return;

    // File type check
    if (!ACCEPTED_TYPES.includes(file.type) && !file.name.match(/\.(jpg|jpeg|png|webp|heic|heif)$/i)) {
      setError('Desteklenmeyen dosya formatı. JPEG, PNG veya WebP kullanın.');
      return;
    }

    // File size check
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setError(`Dosya boyutu çok büyük. Maksimum ${MAX_FILE_SIZE_MB}MB.`);
      return;
    }

    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target.result;
      setCapturedImage(dataUrl);
      if (onCapture) {
        onCapture(dataUrl);
      }
    };
    reader.onerror = () => {
      setError('Dosya okunamadı. Lütfen tekrar deneyin.');
    };
    reader.readAsDataURL(file);
  }, [onCapture]);

  const handleFileInput = useCallback((e) => {
    handleFileSelect(e.target.files?.[0]);
    // Reset input so same file can be selected again
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [handleFileSelect]);

  // Drag & Drop handlers
  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    handleFileSelect(e.dataTransfer.files?.[0]);
  }, [handleFileSelect]);

  return (
    <Card className="overflow-hidden bg-white">
      <div className="p-3 sm:p-4">
        {/* Mode Selector */}
        <div className="flex items-center gap-1 mb-3 p-1 bg-gray-100 rounded-lg">
          <button
            onClick={() => { setMode('camera'); setCapturedImage(null); setError(null); }}
            className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              mode === 'camera' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
            Kamera
          </button>
          <button
            onClick={() => { setMode('upload'); setCapturedImage(null); setError(null); }}
            className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              mode === 'upload' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Upload className="w-3.5 h-3.5" />
            Dosya Yükle
          </button>
        </div>

        <div className="relative bg-gray-900 rounded-xl overflow-hidden" style={{ aspectRatio: '4/3' }}>
          {mode === 'upload' && !capturedImage ? (
            /* File Upload Area */
            <div
              className={`absolute inset-0 flex flex-col items-center justify-center p-6 text-center transition-colors ${
                dragActive
                  ? 'bg-blue-50 border-2 border-dashed border-blue-400'
                  : 'bg-gray-50 border-2 border-dashed border-gray-200 hover:border-gray-300'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              <div className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 ${
                dragActive ? 'bg-blue-100' : 'bg-gray-100'
              }`}>
                <FileImage className={`w-8 h-8 ${dragActive ? 'text-blue-500' : 'text-gray-400'}`} />
              </div>
              <p className="text-sm font-medium text-gray-700 mb-1">
                {dragActive ? 'Dosyayı bırakın' : 'Kimlik fotoğrafını yükleyin'}
              </p>
              <p className="text-xs text-gray-500 mb-4">
                Sürükle-bırak veya dosya seçin (JPEG, PNG, max {MAX_FILE_SIZE_MB}MB)
              </p>
              <Button
                onClick={() => fileInputRef.current?.click()}
                variant="outline"
                size="sm"
                disabled={disabled}
                className="gap-2"
              >
                <Upload className="w-4 h-4" />
                Dosya Seç
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp,.heic,.heif"
                className="hidden"
                onChange={handleFileInput}
              />
            </div>
          ) : error && mode === 'camera' ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-gray-50">
              <AlertTriangle className="w-12 h-12 text-[var(--brand-warning)] mb-3" />
              <p className="text-sm text-[var(--brand-slate)] mb-4" data-testid="camera-permission-alert">{error}</p>
              <div className="flex gap-2">
                <Button onClick={startCamera} variant="outline" size="sm">
                  <RefreshCcw className="w-4 h-4 mr-2" />
                  Tekrar Dene
                </Button>
                <Button onClick={() => { setMode('upload'); setError(null); }} variant="outline" size="sm" className="text-blue-600">
                  <Upload className="w-4 h-4 mr-2" />
                  Dosya Yükle
                </Button>
              </div>
            </div>
          ) : error && mode === 'upload' ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-gray-50">
              <AlertTriangle className="w-12 h-12 text-red-400 mb-3" />
              <p className="text-sm text-red-600 mb-4">{error}</p>
              <Button onClick={() => { setError(null); setCapturedImage(null); }} variant="outline" size="sm">
                <RefreshCcw className="w-4 h-4 mr-2" />
                Tekrar Dene
              </Button>
            </div>
          ) : capturedImage ? (
            <img 
              src={capturedImage} 
              alt="Yakalanan" 
              className="w-full h-full object-contain"
              data-testid="capture-thumbnail"
            />
          ) : (
            <>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
                data-testid="camera-live-preview"
              />
              {/* Corner guides */}
              <div className="camera-overlay">
                <div className="camera-corner camera-corner-tl" />
                <div className="camera-corner camera-corner-tr" />
                <div className="camera-corner camera-corner-bl" />
                <div className="camera-corner camera-corner-br" />
                {!cameraReady && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <div className="text-white text-sm">Kamera başlatılıyor...</div>
                  </div>
                )}
              </div>
            </>
          )}
          {/* Flash overlay */}
          {showFlash && (
            <div className="absolute inset-0 bg-white camera-flash" />
          )}
        </div>
        
        <canvas ref={canvasRef} className="hidden" />
        
        <div className="flex items-center gap-2 mt-3">
          {capturedImage ? (
            <Button
              onClick={retake}
              variant="outline"
              className="flex-1"
              data-testid="camera-retake-button"
            >
              <RefreshCcw className="w-4 h-4 mr-2" />
              {mode === 'upload' ? 'Başka Dosya Seç' : 'Yeniden Çek'}
            </Button>
          ) : mode === 'camera' ? (
            <>
              <Button
                onClick={capture}
                disabled={!cameraReady || disabled}
                className="flex-1 bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white"
                data-testid="camera-capture-button"
              >
                <Camera className="w-4 h-4 mr-2" />
                Yakala
              </Button>
              <Button
                onClick={switchCamera}
                variant="outline"
                size="icon"
                data-testid="camera-switch-button"
              >
                <SwitchCamera className="w-4 h-4" />
              </Button>
            </>
          ) : (
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="flex-1 bg-[var(--brand-sky)] hover:bg-[#094C6E] text-white"
            >
              <Upload className="w-4 h-4 mr-2" />
              Dosya Seç
            </Button>
          )}
        </div>
        
        {!capturedImage && !error && mode === 'camera' && (
          <p className="text-xs text-center text-muted-foreground mt-2">
            Belgeyi çerçeveye hizalayın ve "Yakala"ya basın
          </p>
        )}
      </div>
    </Card>
  );
}
