import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { QrCode, Camera, Wrench } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const QRMaintenanceScanner = () => {
  const [scanning, setScanning] = useState(false);
  const [scannedAsset, setScannedAsset] = useState(null);

  const handleScan = () => {
    setScanning(true);
    
    // Simulate QR scan (in production, use camera API)
    setTimeout(() => {
      const mockAsset = {
        id: 'ASSET-' + Math.floor(Math.random() * 1000),
        name: 'Klima Ünitesi',
        location: 'Oda 205',
        type: 'HVAC',
        last_maintenance: '2025-01-10'
      };
      
      setScannedAsset(mockAsset);
      setScanning(false);
      toast.success('QR Kod Okundu');
    }, 1500);
  };

  const handleCreateTask = async () => {
    if (!scannedAsset) return;

    try {
      await axios.post('/maintenance/task', {
        asset_id: scannedAsset.id,
        asset_name: scannedAsset.name,
        location: scannedAsset.location,
        task_type: 'routine_check',
        priority: 'normal',
        description: `${scannedAsset.name} için bakım görevi (QR ile oluşturuldu)`
      });
      
      toast.success('Bakım görevi oluşturuldu');
      setScannedAsset(null);
    } catch (error) {
      toast.error('Görev oluşturulamadı');
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <QrCode className="w-5 h-5 mr-2" />
          QR ile Bakım Aç
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!scannedAsset ? (
          <div className="text-center py-8">
            <div className="mb-4">
              {scanning ? (
                <div className="animate-pulse">
                  <Camera className="w-16 h-16 mx-auto text-blue-500" />
                  <p className="text-sm text-gray-600 mt-4">QR kod taranıyor...</p>
                </div>
              ) : (
                <>
                  <QrCode className="w-16 h-16 mx-auto text-gray-400" />
                  <p className="text-sm text-gray-600 mt-4">Ekipman QR kodunu tarayın</p>
                </>
              )}
            </div>
            <Button
              className="bg-blue-600 hover:bg-blue-700"
              onClick={handleScan}
              disabled={scanning}
            >
              <Camera className="w-4 h-4 mr-2" />
              QR Tara
            </Button>
          </div>
        ) : (
          <div>
            <div className="bg-green-50 border-2 border-green-200 rounded-lg p-4 mb-4">
              <div className="flex items-start space-x-3">
                <Wrench className="w-8 h-8 text-green-600" />
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900">{scannedAsset.name}</h3>
                  <p className="text-sm text-gray-600">
                    {scannedAsset.location}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Tip: {scannedAsset.type}
                  </p>
                  <p className="text-xs text-gray-500">
                    Son Bakım: {scannedAsset.last_maintenance}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                onClick={() => setScannedAsset(null)}
              >
                İptal
              </Button>
              <Button
                className="bg-green-600 hover:bg-green-700"
                onClick={handleCreateTask}
              >
                Görev Oluştur
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default QRMaintenanceScanner;
