import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { QrCode, PlayCircle, StopCircle, Clock, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const QRRoomAccess = () => {
  const { t } = useTranslation();
  const [activeSessions, setActiveSessions] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [selectedRoomId, setSelectedRoomId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadActiveSessions();
    loadRooms();
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

  const loadRooms = async () => {
    try {
      const response = await axios.get('/housekeeping/rooms');
      setRooms(response.data.rooms || []);
    } catch (error) {
      console.error('Failed to load rooms:', error);
    }
  };

  const handleStartFromSelection = async () => {
    const room = rooms.find((r) => r.id === selectedRoomId);
    if (!room) {
      toast.error('Lütfen bir oda seçin');
      return;
    }
    setSubmitting(true);
    try {
      await handleStartCleaning({ room_id: room.id, room_number: room.room_number });
      setSelectedRoomId('');
    } finally {
      setSubmitting(false);
    }
  };

  const handleStartCleaning = async (roomData) => {
    try {
      const response = await axios.post('/housekeeping/qr-room-access', {
        room_id: roomData.room_id,
        room_number: roomData.room_number,
        action: 'start'
      });
      
      toast.success(`Oda ${roomData.room_number} temizliğe başlandı`);
      loadActiveSessions();
    } catch (error) {
      if (error.response?.status === 400) {
        toast.error('Aktif temizlik oturumu var');
      } else {
        toast.error('Başlatma başarısız');
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
      
      toast.success(`Oda ${session.room_number} tamamlandı (${response.data.duration_minutes} dk)`);
      loadActiveSessions();
    } catch (error) {
      toast.error('Bitirme başarısız');
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
    return <div className="text-center py-4">{t('cm.components_QRRoomAccess.yukleniyor')}</div>;
  }

  return (
    <div className="space-y-4">
      {/* QR Scanner */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center text-lg">
            <QrCode className="w-5 h-5 mr-2" />
            {t('cm.components_QRRoomAccess.qr_ile_oda_girisi')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="py-4">
            <p className="text-sm text-gray-600 mb-3">Temizliğe başlamak için oda seçin</p>
            <select
              className="w-full border rounded-md px-3 py-2 mb-4 text-sm"
              value={selectedRoomId}
              onChange={(e) => setSelectedRoomId(e.target.value)}
            >
              <option value="">Oda seçin…</option>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  Oda {room.room_number}{room.hk_status ? ` — ${room.hk_status}` : ''}
                </option>
              ))}
            </select>
            <Button
              className="w-full bg-blue-600 hover:bg-blue-700"
              onClick={handleStartFromSelection}
              disabled={submitting || !selectedRoomId}
            >
              <PlayCircle className="w-4 h-4 mr-2" />
              {submitting ? 'Başlatılıyor…' : 'Temizliğe Başla'}
            </Button>
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
                {t('cm.components_QRRoomAccess.aktif_temizlikler')}
              </span>
              <Badge className="bg-amber-500">{activeSessions.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {activeSessions.map((session) => (
                <div key={session.id} className="p-4 bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200 rounded-lg">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="font-bold text-lg">{t('cm.components_QRRoomAccess.oda')} {session.room_number}</div>
                      <div className="text-sm text-gray-600">
                        {t('cm.components_QRRoomAccess.baslama')} {new Date(session.start_time).toLocaleTimeString('tr-TR', {
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </div>
                    </div>
                    <Badge className="bg-amber-500">
                      <Clock className="w-3 h-3 mr-1" />
                      {formatElapsedTime(session.elapsed_minutes)}
                    </Badge>
                  </div>

                  {/* Progress Bar */}
                  <div className="mb-3">
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-amber-500 h-2 rounded-full transition-all animate-pulse"
                        style={{ width: `${Math.min((session.elapsed_minutes / 30) * 100, 100)}%` }}
                      />
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {t('cm.components_QRRoomAccess.standart_sure_30_dakika')}
                    </div>
                  </div>

                  <Button
                    className="w-full bg-green-600 hover:bg-green-700"
                    onClick={() => handleEndCleaning(session)}
                  >
                    <CheckCircle className="w-4 h-4 mr-2" />
                    {t('cm.components_QRRoomAccess.temizligi_bitir')}
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
            <div className="text-sm text-gray-600">{t('cm.components_QRRoomAccess.bugun_tamamlanan_oda')}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default QRRoomAccess;
