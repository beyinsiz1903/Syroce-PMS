import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { QrCode, Key, Clock, RefreshCw, Download } from 'lucide-react';
import QRCode from 'qrcode';
import { useTranslation } from 'react-i18next';

const DigitalKey = ({ bookingId }) => {
  const { t } = useTranslation();
  const [keyData, setKeyData] = useState(null);
  const [qrCodeUrl, setQrCodeUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [timeRemaining, setTimeRemaining] = useState(null);

  useEffect(() => {
    loadDigitalKey();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [bookingId]);

  useEffect(() => {
    if (keyData?.expires_at) {
      const interval = setInterval(() => {
        const now = new Date();
        const expiresAt = new Date(keyData.expires_at);
        const diff = expiresAt - now;
        
        if (diff <= 0) {
          setTimeRemaining('Expired');
          clearInterval(interval);
        } else {
          const hours = Math.floor(diff / (1000 * 60 * 60));
          const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
          setTimeRemaining(`${hours}h ${minutes}m`);
        }
      }, 1000);

      return () => clearInterval(interval);
    }
  }, [keyData]);

  const loadDigitalKey = async () => {
    try {
      const response = await axios.get(`/guest/digital-key/${bookingId}`);
      setKeyData(response.data);
      
      // Generate QR code
      const qrData = JSON.stringify({
        key_id: response.data.key_id,
        room_number: response.data.room_number,
        guest_id: response.data.guest_id,
        expires_at: response.data.expires_at
      });
      
      const qrUrl = await QRCode.toDataURL(qrData, {
        width: 300,
        margin: 2,
        color: {
          dark: '#000000',
          light: '#FFFFFF'
        }
      });
      
      setQrCodeUrl(qrUrl);
    } catch (error) {
      toast.error('Dijital anahtar yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshKey = async () => {
    setLoading(true);
    try {
      await axios.post(`/guest/digital-key/${bookingId}/refresh`);
      await loadDigitalKey();
      toast.success('Digital key refreshed');
    } catch (error) {
      toast.error('Anahtar yenilenemedi');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadKey = () => {
    const link = document.createElement('a');
    link.href = qrCodeUrl;
    link.download = `room-key-${keyData.room_number}.png`;
    link.click();
    toast.success('QR code downloaded');
  };

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
      </div>
    );
  }

  if (!keyData) {
    return (
      <Card>
        <CardContent className="text-center py-12">
          <Key className="w-16 h-16 mx-auto text-gray-400 mb-4" />
          <p className="text-gray-600">Digital key not available</p>
          <p className="text-sm text-gray-500 mt-2">Please complete check-in first</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="max-w-md mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-center flex items-center justify-center gap-2">
            <Key className="w-6 h-6" />
            Digital Room Key
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Room Info */}
          <div className="text-center">
            <div className="text-sm text-gray-600">Room Number</div>
            <div className="text-4xl font-bold text-blue-600 mt-2">{keyData.room_number}</div>
          </div>

          {/* QR Code */}
          <div className="flex justify-center">
            <div className="bg-white p-4 rounded-lg shadow-lg">
              {qrCodeUrl && (
                <img src={qrCodeUrl} alt="{t('guestPortal.digitalKey')} QR Code" className="w-64 h-64" />
              )}
            </div>
          </div>

          {/* Key Info */}
          <div className="space-y-2 text-sm">
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded">
              <span className="text-gray-600">Status</span>
              <span className="font-semibold text-green-600">{keyData.status}</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 rounded">
              <span className="text-gray-600 flex items-center gap-2">
                <Clock className="w-4 h-4" />
                Valid For
              </span>
              <span className="font-semibold">{timeRemaining}</span>
            </div>
          </div>

          {/* Instructions */}
          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="font-semibold text-blue-800 mb-2">How to Use:</div>
            <ol className="text-sm text-blue-700 space-y-1 list-decimal list-inside">
              <li>Approach your room door</li>
              <li>Show this QR code to the door reader</li>
              <li>Wait for the green light</li>
              <li>Turn the handle to open</li>
            </ol>
          </div>

          {/* Actions */}
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" onClick={handleRefreshKey} disabled={loading}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
            <Button onClick={handleDownloadKey}>
              <Download className="w-4 h-4 mr-2" />
              Download
            </Button>
          </div>

          {/* Security Note */}
          <div className="text-xs text-gray-500 text-center">
            This key is unique to you and expires at checkout.
            Do not share with others.
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default DigitalKey;