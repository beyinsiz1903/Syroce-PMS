import { useEffect, useState, useCallback } from 'react';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Loader2, Map as MapIcon, Crown, Calendar, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

const today = () => new Date().toISOString().slice(0, 10);

const STATUS_COLOR = {
  occupied: 'bg-rose-100 border-rose-300',
  dirty: 'bg-amber-50 border-amber-200',
  clean: 'bg-emerald-50 border-emerald-200',
  out_of_order: 'bg-gray-200 border-gray-400',
  maintenance: 'bg-gray-100 border-gray-300',
};

function RoomCell({ room, onDrop }) {
  const [over, setOver] = useState(false);
  const occupied = !!room.booking;
  const cls = occupied ? 'bg-rose-50 border-rose-300' : (STATUS_COLOR[room.status] || 'bg-white border-gray-200');
  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); const id = e.dataTransfer.getData('booking_id'); if (id) onDrop(id, room.id); }}
      draggable={occupied}
      onDragStart={e => { if (occupied) e.dataTransfer.setData('booking_id', room.booking.booking_id); }}
      className={`border rounded-lg p-2 min-h-[88px] transition ${cls} ${over ? 'ring-2 ring-blue-400' : ''} ${occupied ? 'cursor-move' : ''}`}
      data-testid={`room-cell-${room.room_number}`}
    >
      <div className="flex items-center justify-between">
        <div className="font-bold text-sm">{room.room_number}</div>
        <div className="text-[10px] text-gray-500">{room.room_type || ''}</div>
      </div>
      {occupied ? (
        <div className="mt-1.5 text-xs">
          <div className="font-semibold flex items-center gap-1 truncate">
            {room.booking.vip && <Crown className="w-3 h-3 text-amber-600" />}
            {room.booking.guest_name}
          </div>
          <div className="text-[11px] text-gray-600 mt-0.5">
            {room.booking.check_in?.slice(5)} → {room.booking.check_out?.slice(5)}
          </div>
          <div className="text-[10px] text-gray-500 mt-0.5">
            {room.booking.adults}+{room.booking.children} · {room.booking.status}
          </div>
        </div>
      ) : (
        <div className="text-[11px] text-gray-400 mt-2">Boş — {room.status || 'müsait'}</div>
      )}
    </div>
  );
}

function UnassignedItem({ b }) {
  return (
    <div
      draggable
      onDragStart={e => e.dataTransfer.setData('booking_id', b.booking_id)}
      className="border border-blue-300 bg-blue-50 rounded p-2 cursor-move text-xs"
    >
      <div className="font-semibold flex items-center gap-1">
        {b.vip && <Crown className="w-3 h-3 text-amber-600" />}
        {b.guest_name}
      </div>
      <div className="text-[10px] text-gray-600">{b.check_in?.slice(5)} → {b.check_out?.slice(5)} · {b.adults}+{b.children}</div>
    </div>
  );
}

export default function RoomMapPage() {
  const [date, setDate] = useState(today());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/pms/room-map', { params: { business_date: date } });
      setData(data);
    } catch (e) { toast.error('Yükleme hatası'); }
    finally { setLoading(false); }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  const assign = async (booking_id, room_id) => {
    try {
      await api.post('/pms/room-map/assign', { booking_id, room_id, business_date: date });
      toast.success('Oda değiştirildi');
      load();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const byFloor = (data?.rooms || []).reduce((acc, r) => {
    const f = r.floor ?? '—';
    (acc[f] = acc[f] || []).push(r);
    return acc;
  }, {});

  return (
    <div className="p-6 space-y-4" data-testid="room-map-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MapIcon className="w-6 h-6 text-blue-600" /> Oda Haritası
          </h1>
          <p className="text-sm text-gray-500 mt-1">Misafiri başka odaya sürükleyip bırakın</p>
        </div>
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-gray-500" />
          <Input type="date" value={date} onChange={e => setDate(e.target.value)} className="h-9 w-40" />
          <Button size="sm" variant="outline" onClick={load}>
            <RefreshCw className="w-3 h-3 mr-1" /> Yenile
          </Button>
        </div>
      </div>

      {data?.unassigned?.length > 0 && (
        <Card className="p-3 bg-blue-50 border-blue-200">
          <div className="font-semibold text-sm mb-2">Atanmamış Rezervasyonlar ({data.unassigned.length})</div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {data.unassigned.map(b => <UnassignedItem key={b.booking_id} b={b} />)}
          </div>
        </Card>
      )}

      {loading && <div className="text-center py-8"><Loader2 className="inline w-5 h-5 animate-spin" /></div>}

      {data && Object.entries(byFloor).sort().map(([floor, rooms]) => (
        <Card key={floor} className="p-3">
          <div className="text-sm font-semibold text-gray-700 mb-2">Kat {floor} ({rooms.length})</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
            {rooms.map(r => <RoomCell key={r.id} room={r} onDrop={assign} />)}
          </div>
        </Card>
      ))}
    </div>
  );
}
