import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { BellOff, Wine, ArrowRight, Clock } from 'lucide-react';

const RoomFeaturesPanel = ({ room, onUpdate }) => {
  const navigate = useNavigate();
  const roomId = room?.id || room?._id;
  const [dndEnabled, setDndEnabled] = useState(room?.dnd === true);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const selectedRoomRef = useRef(roomId);
  selectedRoomRef.current = roomId;

  useEffect(() => { setDndEnabled(room?.dnd === true); }, [roomId, room?.dnd]);

  const toggleDND = async () => {
    if (!roomId || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    const targetRoomId = roomId;
    try {
      const response = await axios.patch(`/pms/rooms/${encodeURIComponent(roomId)}/features`, {
        dnd: !dndEnabled, expected_dnd: dndEnabled,
      });
      if (selectedRoomRef.current === targetRoomId) setDndEnabled(response.data.dnd);
      toast.success(response.data.dnd ? 'Rahatsız etmeyin etkinleştirildi' : 'Rahatsız etmeyin kapatıldı');
      onUpdate?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'DND durumu güncellenemedi');
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2">
            <BellOff className="h-4 w-4" /> Rahatsız Etmeyin (DND)
          </CardTitle></CardHeader>
          <CardContent><div className="flex items-center justify-between">
            <Badge variant={dndEnabled ? 'destructive' : 'outline'}>{dndEnabled ? 'AKTİF' : 'KAPALI'}</Badge>
            <Button size="sm" variant={dndEnabled ? 'destructive' : 'default'} onClick={toggleDND} disabled={!roomId || saving}>
              {saving ? 'Kaydediliyor…' : dndEnabled ? 'Kapat' : 'Aktif Et'}
            </Button>
          </div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2">
            <Wine className="h-4 w-4" /> Minibar
          </CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">Ürün, fiyat, para birimi ve stok doğrulaması için Minibar ekranını kullanın. Tüketim eklemeden önce ilgili odayı seçin.</p>
            <Button size="sm" onClick={() => navigate('/minibar')}>
              Minibar ekranını aç <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2">
          <Clock className="h-4 w-4" /> Erken / Geç Çıkış
        </CardTitle></CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Güncel çıkış saati ve ücret politikasını rezervasyon detayından kontrol edin. Bu panel sabit bir ücret veya ücretsiz çıkış garantisi vermez.
        </CardContent>
      </Card>
    </div>
  );
};

export default RoomFeaturesPanel;
