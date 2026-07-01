import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const RoomCreateDialog = ({ open, onClose, onRoomCreated }) => {
  const { t } = useTranslation();
  const [newRoom, setNewRoom] = useState({
    room_number: '',
    room_type: 'standard',
    floor: 1,
    capacity: 2,
    base_price: 100,
    amenities: [],
    view: '',
    bed_type: ''
  });

  const handleCreateRoom = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/pms/rooms', {
        ...newRoom,
        view: newRoom.view || null,
        bed_type: newRoom.bed_type || null,
      });
      toast.success('Room created');
      onClose();
      onRoomCreated();
      setNewRoom({
        room_number: '',
        room_type: 'standard',
        floor: 1,
        capacity: 2,
        base_price: 100,
        amenities: [],
        view: '',
        bed_type: ''
      });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create room');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('pms.createRoom', 'Create Room')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleCreateRoom} className="space-y-4">
          <div>
            <Label>{t('pms.roomNumber', 'Room Number')}</Label>
            <Input value={newRoom.room_number} onChange={(e) => setNewRoom({...newRoom, room_number: e.target.value})} required />
          </div>
          <div>
            <Label>{t('pms.roomType', 'Room Type')}</Label>
            <Select value={newRoom.room_type} onValueChange={(v) => setNewRoom({...newRoom, room_type: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">Standard</SelectItem>
                <SelectItem value="deluxe">Deluxe</SelectItem>
                <SelectItem value="suite">Suite</SelectItem>
                <SelectItem value="presidential">Presidential</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>{t('pms.floor', 'Floor')}</Label>
              <Input type="number" value={newRoom.floor} onChange={(e) => setNewRoom({...newRoom, floor: parseInt(e.target.value)})} required />
            </div>
            <div>
              <Label>{t('pms.capacity', 'Capacity')}</Label>
              <Input type="number" value={newRoom.capacity} onChange={(e) => setNewRoom({...newRoom, capacity: parseInt(e.target.value)})} required />
            </div>
          </div>
          <div>
            <Label>{t('pms.basePrice', 'Base Price')}</Label>
            <Input type="number" step="0.01" value={newRoom.base_price} onChange={(e) => setNewRoom({...newRoom, base_price: parseFloat(e.target.value)})} required />
          </div>
          <Button type="submit" className="w-full">{t('pms.createRoom', 'Create Room')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default RoomCreateDialog;
