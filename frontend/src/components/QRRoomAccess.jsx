import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { QrCode, PlayCircle, StopCircle, Clock, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';

const QRRoomAccess = () => {
  const [activeSessions, setActiveSessions] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadActiveSessions();
    // Refresh every 30 seconds
    const interval = setInterval(loadActiveSessions, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadActiveSessions = async () => {
    try {
      const response = await axios.get('/housekeeping/my-active-sessions');
      setActiveSessions(response.data.active_sessions || []);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleScanQR = () => {
    setScanning(true);
    
    // Simulate QR scan (in production, use camera API)
    setTimeout(() => {
      const mockRoomData = {
        room_id: 'room_' + Math.floor(Math.random() * 100),
        room_number: String(Math.floor(Math.random() * 300) + 101)
      };
      
      setScanning(false);
      handleStartCleaning(mockRoomData);
    }, 1500);
  };

  const handleStartCleaning = async (roomData) => {
    try {
      const response = await axios.post('/housekeeping/qr-room-access', {
        room_id: roomData.room_id,
        room_number: roomData.room_number,
        action: 'start'
      });
      
      toast.success(`✓ Oda ${roomData.room_number} temizliğe başlandı`);
      loadActiveSessions();
    } catch (error) {
      if (error.response?.status === 400) {
        toast.error('⚠️ Aktif temizlik oturumu var');
      } else {
        toast.error('✗ Başlatma başarısız');
      }
    }
  };

  const handleEndCleaning = async (session) => {
    try {
      const response = await axios.post('/housekeeping/qr-room-access', {
        room_id: session.room_id,
        room_number: session.room_number,
        action: 'end'
      });
      
      toast.success(`✓ Oda ${session.room_number} tamamlandı (${response.data.duration_minutes} dk)`);
      loadActiveSessions();
    } catch (error) {
      toast.error('✗ Bitirme başarısız');
    }
  };

  const formatElapsedTime = (minutes) => {
    if (minutes < 60) {
      return `${Math.floor(minutes)} dakika`;
    }
    const hours = Math.floor(minutes / 60);
    const mins = Math.floor(minutes % 60);
    return `${hours} saat ${mins} dakika`;
  };

  if (loading) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <div className="space-y-4">
      {/* QR Scanner */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center text-lg">
            <QrCode className="w-5 h-5 mr-2" />
            QR ile Oda Girişi
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-6">
            {scanning ? (
              <div className="animate-pulse">
                <QrCode className="w-20 h-20 mx-auto text-blue-500 mb-4" />
                <p className="text-sm text-gray-600">QR kod taranıyor...</p>
              </div>
            ) : (
              <>
                <QrCode className="w-20 h-20 mx-auto text-gray-400 mb-4" />
                <p className="text-sm text-gray-600 mb-4">Oda kapısındaki QR kodu tarayın</p>
                <Button
                  className="bg-blue-600 hover:bg-blue-700"
                  onClick={handleScanQR}
                  disabled={scanning}
                >
                  <QrCode className="w-4 h-4 mr-2" />
                  QR Tara
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Active Sessions */}
      {activeSessions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-lg">
              <span className="flex items-center">
                <Clock className="w-5 h-5 mr-2" />
                Aktif Temizlikler
              </span>
              <Badge className="bg-orange-500">{activeSessions.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {activeSessions.map((session) => (
                <div key={session.id} className="p-4 bg-gradient-to-r from-orange-50 to-yellow-50 border border-orange-200 rounded-lg">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="font-bold text-lg">Oda {session.room_number}</div>
                      <div className="text-sm text-gray-600">
                        Başlama: {new Date(session.start_time).toLocaleTimeString('tr-TR', {
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </div>
                    </div>
                    <Badge className="bg-orange-500">
                      <Clock className="w-3 h-3 mr-1" />
                      {formatElapsedTime(session.elapsed_minutes)}
                    </Badge>
                  </div>

                  {/* Progress Bar */}
                  <div className="mb-3">
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-orange-500 h-2 rounded-full transition-all animate-pulse"
                        style={{ width: `${Math.min((session.elapsed_minutes / 30) * 100, 100)}%` }}
                      />
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Standart süre: 30 dakika
                    </div>
                  </div>

                  <Button
                    className="w-full bg-green-600 hover:bg-green-700"
                    onClick={() => handleEndCleaning(session)}
                  >
                    <CheckCircle className="w-4 h-4 mr-2" />
                    Temizliği Bitir
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Today's Summary */}
      <Card className="bg-gradient-to-br from-blue-50 to-indigo-100">
        <CardContent className="p-4">
          <div className="text-center">
            <div className="text-3xl font-bold text-blue-600 mb-1">
              {activeSessions.length}
            </div>
            <div className="text-sm text-gray-600">Bugün tamamlanan oda</div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default QRRoomAccess;
