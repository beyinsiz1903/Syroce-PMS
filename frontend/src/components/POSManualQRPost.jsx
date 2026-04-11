import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { QrCode, Scan, AlertTriangle, CheckCircle } from 'lucide-react';

/**
 * POS Manual QR/Barcode Post Component
 * Fallback mechanism when POS integration fails
 * Allows staff to manually post POS charges via QR/barcode scan
 */
const POSManualQRPost = () => {
  const [scanMode, setScanMode] = useState(false);
  const [qrCode, setQrCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastPosted, setLastPosted] = useState(null);

  const handleScan = async (code) => {
    setLoading(true);
    try {
      // Parse QR code (format: POS_CHARGE:{charge_id}:{folio_id})
      const parts = code.split(':');
      if (parts[0] !== 'POS_CHARGE' || parts.length !== 3) {
        toast.error('Geçersiz QR kod formatı');
        return;
      }

      const chargeId = parts[1];
      const folioId = parts[2];

      // Post charge to folio
      const response = await axios.post('/pos/manual-post', {
        charge_id: chargeId,
        folio_id: folioId,
        method: 'qr_scan'
      });

      setLastPosted(response.data);
      toast.success(`POS fişi başarıyla aktarıldı! Tutar: $${response.data.total}`);
      setQrCode('');
    } catch (error) {
      if (error.response?.status === 409) {
        toast.error('Bu fiş zaten aktarılmış!');
      } else {
        toast.error('Manuel aktarım başarısız. Lütfen tekrar deneyin.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleManualEntry = () => {
    if (!qrCode.trim()) {
      toast.error('Lütfen QR kod giriniz');
      return;
    }
    handleScan(qrCode);
  };

  return (
    <Card className="border-2 border-orange-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <QrCode className="w-5 h-5 text-orange-600" />
          Manuel QR/Barkod Post
        </CardTitle>
        <CardDescription>
          Entegrasyon düştüğünde kullanılır - POS fişini manuel olarak aktarın
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Warning Banner */}
        <div className="p-3 bg-orange-50 border-l-4 border-orange-500 rounded">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-orange-600 mt-0.5" />
            <div className="text-xs text-orange-800">
              <strong>Fallback Modu:</strong> Bu yöntemi sadece POS entegrasyonu çalışmadığında kullanın.
              Normal durumda otomatik aktarım kullanılmalıdır.
            </div>
          </div>
        </div>

        {/* Scan Mode Toggle */}
        <div className="flex gap-2">
          <Button
            variant={scanMode ? 'default' : 'outline'}
            onClick={() => setScanMode(true)}
            className="flex-1"
          >
            <Scan className="w-4 h-4 mr-2" />
            QR Scanner
          </Button>
          <Button
            variant={!scanMode ? 'default' : 'outline'}
            onClick={() => setScanMode(false)}
            className="flex-1"
          >
            <QrCode className="w-4 h-4 mr-2" />
            Manuel Giriş
          </Button>
        </div>

        {/* Scanner Interface */}
        {scanMode ? (
          <div className="space-y-3">
            <div className="p-8 bg-gray-100 rounded-lg border-2 border-dashed border-gray-300 text-center">
              <Scan className="w-16 h-16 mx-auto text-gray-400 mb-3" />
              <p className="text-sm text-gray-600 mb-2">Kamerayı QR koda yönlendirin</p>
              <p className="text-xs text-gray-500">
                Barkod tarayıcı bağlıysa, fişi taratın
              </p>
            </div>
            <Button
              onClick={() => {
                // TODO: Integrate with actual QR scanner library
                toast.info('QR Scanner başlatılıyor...');
              }}
              className="w-full bg-blue-600 hover:bg-blue-700"
              disabled={loading}
            >
              <Scan className="w-4 h-4 mr-2" />
              QR Scanner'ı Başlat
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium mb-2 block">
                QR Kod / Barkod Numarası:
              </label>
              <Input
                placeholder="POS_CHARGE:12345:67890"
                value={qrCode}
                onChange={(e) => setQrCode(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleManualEntry();
                  }
                }}
                disabled={loading}
              />
              <p className="text-xs text-gray-500 mt-1">
                Format: POS_CHARGE:[charge_id]:[folio_id]
              </p>
            </div>
            <Button
              onClick={handleManualEntry}
              className="w-full bg-orange-600 hover:bg-orange-700"
              disabled={loading || !qrCode.trim()}
            >
              {loading ? 'Aktarılıyor...' : 'Manuel Aktar'}
            </Button>
          </div>
        )}

        {/* Last Posted Info */}
        {lastPosted && (
          <div className="p-3 bg-green-50 border-l-4 border-green-500 rounded">
            <div className="flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-green-600 mt-0.5" />
              <div className="text-xs text-green-800">
                <strong>Son Aktarılan:</strong> ${lastPosted.total} - {lastPosted.description}
                <br />
                <span className="text-green-600">
                  Folio: {lastPosted.folio_id} | Zaman: {new Date(lastPosted.posted_at).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Instructions */}
        <div className="text-xs text-gray-500 space-y-1 pt-3 border-t">
          <p><strong>Nasıl Kullanılır:</strong></p>
          <ul className="list-disc list-inside space-y-0.5 ml-2">
            <li>POS sisteminden QR kod yazdırın</li>
            <li>Kamera ile QR'ı taratın veya numarayı girin</li>
            <li>Sistem otomatik olarak folio'ya aktarır</li>
            <li>Misafir faturasında görüntülenir</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
};

export default POSManualQRPost;
