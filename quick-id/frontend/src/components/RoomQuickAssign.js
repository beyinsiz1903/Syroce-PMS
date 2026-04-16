import { useState, useEffect } from 'react';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';

import { api } from '../lib/api';
import { toast } from 'sonner';
import {
  DoorOpen, Loader2, Check, BedDouble, SkipForward, Users,
} from 'lucide-react';

const statusColors = {
  available: 'border-green-200 bg-green-50 hover:bg-green-100 hover:border-green-400',
  occupied: 'border-blue-200 bg-blue-50 opacity-50 cursor-not-allowed',
  cleaning: 'border-amber-200 bg-amber-50 opacity-50 cursor-not-allowed',
  maintenance: 'border-red-200 bg-red-50 opacity-50 cursor-not-allowed',
};

export default function RoomQuickAssign({ guestId, guestName, onComplete, onSkip }) {
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(null);
  const [assigned, setAssigned] = useState(null);

  useEffect(() => {
    loadRooms();
  }, []);

  const loadRooms = async () => {
    try {
      const res = await api.getRooms();
      setRooms(res.rooms || []);
    } catch (e) {
      toast.error('Odalar yüklenemedi');
    }
    setLoading(false);
  };

  const handleAssign = async (room) => {
    if (room.status !== 'available') return;
    setAssigning(room.room_id);
    try {
      await api.assignRoom(room.room_id, guestId);
      setAssigned(room.room_number);
      onComplete && onComplete(room.room_number);
    } catch (e) {
      toast.error(e.message || 'Oda atama hatası');
      setAssigning(null);
    }
  };

  if (assigned) {
    return (
      <Card className="border-2 border-green-300 bg-green-50">
        <CardContent className="p-6 text-center">
          <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3">
            <Check className="w-7 h-7 text-green-600" />
          </div>
          <p className="font-semibold text-green-800 text-lg">
            Oda {assigned} atandı
          </p>
          <p className="text-sm text-green-600 mt-1">{guestName}</p>
        </CardContent>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card className="bg-white">
        <CardContent className="p-6 flex items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">Odalar yükleniyor...</span>
        </CardContent>
      </Card>
    );
  }

  const availableRooms = rooms.filter(r => r.status === 'available');

  return (
    <Card className="bg-white border-2 border-[var(--brand-sky)]/30">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <DoorOpen className="w-5 h-5 text-[var(--brand-sky)]" />
            <div>
              <p className="font-semibold text-sm">Oda Seçin</p>
              <p className="text-xs text-muted-foreground">
                {availableRooms.length} müsait oda
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onSkip} className="text-xs text-muted-foreground">
            <SkipForward className="w-3.5 h-3.5 mr-1" />
            Atla
          </Button>
        </div>

        {availableRooms.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <BedDouble className="w-10 h-10 mx-auto mb-2 text-gray-300" />
            <p className="text-sm">Müsait oda bulunamadı</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={onSkip}>
              Oda atamadan devam et
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
            {availableRooms.map(room => (
              <button
                key={room.room_id}
                onClick={() => handleAssign(room)}
                disabled={assigning === room.room_id}
                className={`relative p-3 rounded-lg border-2 text-center transition-all ${statusColors.available} ${
                  assigning === room.room_id ? 'ring-2 ring-[var(--brand-sky)] ring-offset-1' : ''
                }`}
              >
                {assigning === room.room_id ? (
                  <Loader2 className="w-5 h-5 animate-spin mx-auto text-[var(--brand-sky)]" />
                ) : (
                  <>
                    <span className="text-lg font-bold text-gray-800 block">{room.room_number}</span>
                    <span className="text-[10px] text-muted-foreground block mt-0.5">
                      Kat {room.floor}
                    </span>
                    <div className="flex items-center justify-center gap-0.5 mt-1">
                      <Users className="w-2.5 h-2.5 text-muted-foreground" />
                      <span className="text-[10px] text-muted-foreground">{room.capacity}</span>
                    </div>
                  </>
                )}
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
