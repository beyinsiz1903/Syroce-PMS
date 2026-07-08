import React, { useState, useRef } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Camera, Upload, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

const IDScanner = ({ onScanSuccess, onScanError }) => {
  const { t } = useTranslation();
  const [isScanning, setIsScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState(null); // 'success' | 'error' | null
  const [errorMessage, setErrorMessage] = useState('');
  const fileInputRef = useRef(null);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Convert file to base64
    const reader = new FileReader();
    reader.onload = async (event) => {
      const base64String = event.target.result.split(',')[1];
      await performScan(base64String);
    };
    reader.readAsDataURL(file);
    // Reset input
    e.target.value = null;
  };

  const performScan = async (base64Image) => {
    setIsScanning(true);
    setScanStatus(null);
    setErrorMessage('');

    try {
      const response = await axios.post('/api/quick-id/scan', {
        image_base64: base64Image,
        smart_mode: true
      });

      if (response.data?.success && response.data?.extracted_data?.documents?.length > 0) {
        setScanStatus('success');
        const doc = response.data.extracted_data.documents[0];
        if (onScanSuccess) {
          onScanSuccess(doc);
        }
      } else {
        throw new Error('Geçerli bir belge bulunamadı veya okunamadı.');
      }
    } catch (error) {
      setScanStatus('error');
      const msg = error.response?.data?.detail || error.message || 'Kimlik tarama başarısız.';
      setErrorMessage(msg);
      if (onScanError) {
        onScanError(msg);
      }
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <div className="w-full space-y-4 p-4 border rounded-lg bg-slate-50/50">
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <input
          type="file"
          accept="image/*"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileChange}
        />
        
        <Button 
          type="button" 
          variant="outline" 
          className="w-full sm:w-1/2 flex items-center justify-center gap-2"
          onClick={() => fileInputRef.current?.click()}
          disabled={isScanning}
        >
          {isScanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {t('pms.uploadID', 'Kimlik/Pasaport Yükle')}
        </Button>

        {/* Mobile devices usually support capture="environment" for camera */}
        <Button 
          type="button" 
          variant="secondary" 
          className="w-full sm:w-1/2 flex items-center justify-center gap-2"
          onClick={() => {
             if (fileInputRef.current) {
                fileInputRef.current.setAttribute('capture', 'environment');
                fileInputRef.current.click();
                fileInputRef.current.removeAttribute('capture');
             }
          }}
          disabled={isScanning}
        >
          {isScanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera className="w-4 h-4" />}
          {t('pms.takePhoto', 'Fotoğraf Çek')}
        </Button>
      </div>

      {scanStatus === 'success' && (
        <Alert className="bg-green-50 border-green-200">
          <CheckCircle2 className="w-4 h-4 text-green-600" />
          <AlertDescription className="text-green-700 ml-2">
            {t('pms.scanSuccess', 'Kimlik başarıyla tarandı. Bilgiler forma aktarıldı.')}
          </AlertDescription>
        </Alert>
      )}

      {scanStatus === 'error' && (
        <Alert variant="destructive">
          <AlertCircle className="w-4 h-4" />
          <AlertDescription className="ml-2">
            {errorMessage}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
};

export default IDScanner;
