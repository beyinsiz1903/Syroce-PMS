import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import RoomConfigurationFields, {
  EMPTY_ROOM_CONFIGURATION,
  normalizeRoomConfiguration,
  validateRoomConfiguration,
} from '@/components/pms/RoomConfigurationFields';

const RoomCreateDialog = ({ open, onClose, onRoomCreated }) => {
  const { t } = useTranslation();
  const [newRoom, setNewRoom] = useState(() => ({ ...EMPTY_ROOM_CONFIGURATION }));

  const handleCreateRoom = async (e) => {
    e.preventDefault();
    const validationError = validateRoomConfiguration(newRoom);
    if (validationError) {
      toast.error(validationError);
      return;
    }
    try {
      await axios.post('/pms/rooms', normalizeRoomConfiguration(newRoom));
      toast.success('Oda oluşturuldu');
      onClose();
      onRoomCreated?.();
      setNewRoom({ ...EMPTY_ROOM_CONFIGURATION });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Oda oluşturulamadı');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('pms.createRoom', 'Create Room')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleCreateRoom} className="space-y-4">
          <RoomConfigurationFields value={newRoom} onChange={setNewRoom} testIdPrefix="quick-new-room" />
          <Button type="submit" className="w-full">{t('pms.createRoom', 'Create Room')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default RoomCreateDialog;
