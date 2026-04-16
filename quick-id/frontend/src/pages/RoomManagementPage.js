import { useState, useEffect, useCallback } from 'react';

import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogClose } from '../components/ui/dialog';
import { api } from '../lib/api';
import {
  DoorOpen, Plus, RefreshCw, UserPlus, Check, X, Wrench, BedDouble,
} from 'lucide-react';

export default function RoomManagementPage() {
  const [rooms, setRooms] = useState([]);
  const [stats, setStats] = useState(null);
  const [roomTypes, setRoomTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newRoom, setNewRoom] = useState({ room_number: '', room_type: 'standard', floor: 1, capacity: 2 });
  const [guests, setGuests] = useState([]);
  const [assignDialog, setAssignDialog] = useState({ open: false, roomId: '' });
  const [selectedGuestId, setSelectedGuestId] = useState('');

  const fetchRooms = useCallback(async () => {
    setLoading(true);
    try {
      const [roomsRes, statsRes, typesRes, guestsRes] = await Promise.allSettled([
        api.getRooms(),
        api.getRoomStats(),
        api.getRoomTypes(),
        api.getGuests({ status: 'pending', limit: 100 }),
      ]);
      if (roomsRes.status === 'fulfilled') setRooms(roomsRes.value.rooms || []);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value);
      if (typesRes.status === 'fulfilled') setRoomTypes(typesRes.value.room_types || []);
      if (guestsRes.status === 'fulfilled') setGuests(guestsRes.value.guests || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchRooms(); }, [fetchRooms]);

  const handleCreateRoom = async () => {
    try {
      await api.createRoom(newRoom);
      setShowCreate(false);
      setNewRoom({ room_number: '', room_type: 'standard', floor: 1, capacity: 2 });
      fetchRooms();
    } catch (e) {
      alert(e.message || 'Hata oluştu');
    }
  };

  const handleAssignRoom = async () => {
    if (!selectedGuestId || !assignDialog.roomId) return;
    try {
      await api.assignRoom(assignDialog.roomId, selectedGuestId);
      setAssignDialog({ open: false, roomId: '' });
      setSelectedGuestId('');
      fetchRooms();
    } catch (e) {
      alert(e.message || 'Atama hatası');
    }
  };

  const handleReleaseRoom = async (roomId) => {
    try {
      await api.releaseRoom(roomId);
      fetchRooms();
    } catch (e) {
      alert(e.message || 'Hata');
    }
  };

  const handleStatusChange = async (roomId, newStatus) => {
    try {
      await api.updateRoom(roomId, { status: newStatus });
      fetchRooms();
    } catch (e) {
      alert(e.message || 'Hata');
    }
  };

  const statusColors = {
    available: 'bg-green-100 text-green-700 border-green-200',
    occupied: 'bg-blue-100 text-blue-700 border-blue-200',
    cleaning: 'bg-amber-100 text-amber-700 border-amber-200',
    maintenance: 'bg-red-100 text-red-700 border-red-200',
    reserved: 'bg-purple-100 text-purple-700 border-purple-200',
  };

  const statusLabels = {
    available: 'Müsait', occupied: 'Dolu', cleaning: 'Temizlik',
    maintenance: 'Bakım', reserved: 'Rezerve',
  };

  const typeLabels = {};
  roomTypes.forEach(t => { typeLabels[t.code] = t.name; });

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[60vh]">
        <RefreshCw className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <DoorOpen className="w-7 h-7 text-blue-500" /> Oda Yönetimi
          </h1>
          <p className="text-muted-foreground mt-1">Oda atama, durum takibi ve yönetim</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchRooms}><RefreshCw className="w-4 h-4 mr-2" />Yenile</Button>
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger asChild>
              <Button><Plus className="w-4 h-4 mr-2" />Yeni Oda</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Yeni Oda Ekle</DialogTitle></DialogHeader>
              <div className="space-y-4 pt-4">
                <div>
                  <Label>Oda Numarası</Label>
                  <Input value={newRoom.room_number} onChange={e => setNewRoom({ ...newRoom, room_number: e.target.value })} placeholder="101" />
                </div>
                <div>
                  <Label>Oda Tipi</Label>
                  <select className="w-full border rounded-md p-2 text-sm" value={newRoom.room_type} onChange={e => setNewRoom({ ...newRoom, room_type: e.target.value })}>
                    {roomTypes.map(t => <option key={t.code} value={t.code}>{t.name}</option>)}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Kat</Label>
                    <Input type="number" value={newRoom.floor} onChange={e => setNewRoom({ ...newRoom, floor: parseInt(e.target.value) || 1 })} />
                  </div>
                  <div>
                    <Label>Kapasite</Label>
                    <Input type="number" value={newRoom.capacity} onChange={e => setNewRoom({ ...newRoom, capacity: parseInt(e.target.value) || 2 })} />
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <DialogClose asChild><Button variant="outline">İptal</Button></DialogClose>
                  <Button onClick={handleCreateRoom} disabled={!newRoom.room_number}>Oluştur</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {[
            { label: 'Toplam', value: stats.total, color: 'blue' },
            { label: 'Müsait', value: stats.available, color: 'green' },
            { label: 'Dolu', value: stats.occupied, color: 'indigo' },
            { label: 'Temizlik', value: stats.cleaning, color: 'amber' },
            { label: 'Bakım', value: stats.maintenance, color: 'red' },
            { label: 'Doluluk', value: `%${stats.occupancy_rate}`, color: 'purple' },
          ].map((s, i) => (
            <Card key={i}>
              <CardContent className="p-3 text-center">
                <p className="text-xs text-muted-foreground">{s.label}</p>
                <p className="text-xl font-bold">{s.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Room Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {rooms.map(room => (
          <Card key={room.room_id} className={`border-2 ${statusColors[room.status] || 'border-gray-200'}`}>
            <CardContent className="p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-lg font-bold">{room.room_number}</span>
                <BedDouble className="w-4 h-4 text-muted-foreground" />
              </div>
              <Badge variant="outline" className={`text-xs ${statusColors[room.status]}`}>
                {statusLabels[room.status] || room.status}
              </Badge>
              <p className="text-xs text-muted-foreground">
                {typeLabels[room.room_type] || room.room_type} • Kat {room.floor} • {room.capacity} kişi
              </p>
              {room.current_guest_ids?.length > 0 && (
                <p className="text-xs text-blue-600">{room.current_guest_ids.length} misafir</p>
              )}

              <div className="flex gap-1 pt-1">
                {room.status === 'available' && (
                  <Button size="sm" variant="outline" className="text-xs h-7 flex-1" onClick={() => { setAssignDialog({ open: true, roomId: room.room_id }); }}>
                    <UserPlus className="w-3 h-3 mr-1" />Ata
                  </Button>
                )}
                {room.status === 'occupied' && (
                  <Button size="sm" variant="outline" className="text-xs h-7 flex-1" onClick={() => handleReleaseRoom(room.room_id)}>
                    <X className="w-3 h-3 mr-1" />Boşalt
                  </Button>
                )}
                {room.status === 'cleaning' && (
                  <Button size="sm" variant="outline" className="text-xs h-7 flex-1" onClick={() => handleStatusChange(room.room_id, 'available')}>
                    <Check className="w-3 h-3 mr-1" />Hazır
                  </Button>
                )}
                {room.status === 'maintenance' && (
                  <Button size="sm" variant="outline" className="text-xs h-7 flex-1" onClick={() => handleStatusChange(room.room_id, 'available')}>
                    <Wrench className="w-3 h-3 mr-1" />Tamam
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}

        {rooms.length === 0 && (
          <div className="col-span-full text-center py-12 text-muted-foreground">
            <BedDouble className="w-16 h-16 mx-auto mb-4 text-gray-300" />
            <p className="text-lg">Henüz oda eklenmemiş</p>
            <p className="text-sm">Yeni oda eklemek için yukarıdaki butonu kullanın</p>
          </div>
        )}
      </div>

      {/* Assign Dialog */}
      <Dialog open={assignDialog.open} onOpenChange={(open) => setAssignDialog({ ...assignDialog, open })}>
        <DialogContent>
          <DialogHeader><DialogTitle>Misafir Ata</DialogTitle></DialogHeader>
          <div className="space-y-4 pt-4">
            <div>
              <Label>Misafir Seçin</Label>
              <select className="w-full border rounded-md p-2 text-sm mt-1" value={selectedGuestId} onChange={e => setSelectedGuestId(e.target.value)}>
                <option value="">Seçiniz...</option>
                {guests.map(g => (
                  <option key={g.id} value={g.id}>{g.first_name} {g.last_name} - {g.id_number || 'ID yok'}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setAssignDialog({ open: false, roomId: '' })}>İptal</Button>
              <Button onClick={handleAssignRoom} disabled={!selectedGuestId}>Oda Ata</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
