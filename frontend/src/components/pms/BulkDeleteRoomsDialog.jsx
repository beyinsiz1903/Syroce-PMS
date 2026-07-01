import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const BulkDeleteRoomsDialog = ({ open, onClose, selectedRooms, rooms, onDeleted }) => {
  const { t } = useTranslation();
  const [confirmText, setConfirmText] = useState('');

  const handleDelete = async () => {
    try {
      const res = await axios.post('/pms/rooms/bulk/delete', {
        ids: selectedRooms,
        confirm_text: confirmText,
      });

      const msgParts = [`Deleted: ${res.data.deleted}`];
      if (res.data.blocked > 0) msgParts.push(`Blocked: ${res.data.blocked}`);
      toast.success(msgParts.join(' | '));

      if (res.data.blocked > 0) {
        toast.info(`Blocked rooms: ${(res.data.blocked_rooms || []).slice(0, 10).join(', ')}`);
      }

      setConfirmText('');
      onDeleted();
      onClose();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Bulk delete failed');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('pms.bulkDeleteRooms', 'Bulk Delete Rooms')}</DialogTitle>
          <DialogDescription>
            {t('pms.bulkDeleteWarning', 'This action is irreversible (soft delete). Type DELETE below to confirm. Rooms with active reservations will be blocked instead.')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="rounded-md border bg-gray-50 p-3 text-sm">
            <div className="font-semibold">{t('pms.roomsToDelete', 'Rooms to delete')}: {selectedRooms.length}</div>
            <div className="text-xs text-gray-600 mt-1">
              {t('pms.firstFive', 'First 5')}: {rooms.filter(r => selectedRooms.includes(r.id)).slice(0,5).map(r => r.room_number).join(', ') || '-'}
            </div>
          </div>

          <div className="space-y-1">
            <Label>{t('pms.confirmation', 'Confirmation')}</Label>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="DELETE"
            />
            <p className="text-[11px] text-gray-500">{t('pms.requiredToPreventAccidental', 'Required to prevent accidental deletion.')}</p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose}>{t('common.cancel', 'Cancel')}</Button>
            <Button
              variant="destructive"
              disabled={selectedRooms.length === 0 || confirmText.trim().toUpperCase() !== 'DELETE'}
              onClick={handleDelete}
            >
              {t('common.delete', 'Delete')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default BulkDeleteRoomsDialog;
