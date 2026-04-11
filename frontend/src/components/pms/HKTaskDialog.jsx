import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

const HKTaskDialog = ({ open, onClose, rooms, newHKTask, setNewHKTask, onSubmit }) => {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t('housekeeping.assignTask')}</DialogTitle></DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <Label>{t('common.room')}</Label>
            <Select value={newHKTask.room_id} onValueChange={(v) => setNewHKTask({...newHKTask, room_id: v})}>
              <SelectTrigger><SelectValue placeholder="Select room" /></SelectTrigger>
              <SelectContent>{rooms.map(r => <SelectItem key={r.id} value={r.id}>Room {r.room_number}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>{t('housekeeping.taskType')}</Label>
            <Select value={newHKTask.task_type} onValueChange={(v) => setNewHKTask({...newHKTask, task_type: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cleaning">{t('housekeeping.cleaning')}</SelectItem>
                <SelectItem value="inspection">{t('housekeeping.inspected')}</SelectItem>
                <SelectItem value="maintenance">{t('housekeeping.maintenance')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>{t('common.priority')}</Label>
            <Select value={newHKTask.priority} onValueChange={(v) => setNewHKTask({...newHKTask, priority: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="low">{t('common.low')}</SelectItem>
                <SelectItem value="normal">{t('common.normal')}</SelectItem>
                <SelectItem value="high">{t('common.high')}</SelectItem>
                <SelectItem value="urgent">{t('common.urgent')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><Label>{t('common.notes')}</Label><Textarea value={newHKTask.notes} onChange={(e) => setNewHKTask({...newHKTask, notes: e.target.value})} /></div>
          <Button type="submit" className="w-full">{t('common.create')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default HKTaskDialog;
