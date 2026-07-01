import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

const MaintenanceDialog = ({ open, onClose, maintenanceForm = {}, setMaintenanceForm, onSuccess }) => {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!maintenanceForm.description?.trim()) {
      toast.error('Lutfen bir açıklama girin');
      return;
    }
    if (submitting) return;
    setSubmitting(true);
    try {
      const payload = {
        room_id: maintenanceForm.room_id,
        room_number: maintenanceForm.room_number,
        issue_type: maintenanceForm.issue_type,
        priority: maintenanceForm.priority,
        source: 'housekeeping',
        description: maintenanceForm.description || undefined
      };
      const res = await axios.post('/maintenance/work-orders', payload, {
        headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
      });
      toast.success(`Maintenance work order created for room ${res.data.room_number || maintenanceForm.room_number}`);
      if (onSuccess) onSuccess();
      onClose();
    } catch (error) {
      console.error('Failed to create maintenance work order', error);
      toast.error(t('messages.error.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('maintenance.createWorkOrder')}</DialogTitle>
          <DialogDescription>
            {t('common.room')} {maintenanceForm.room_number}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div>
            <Label className="text-xs text-gray-600">Issue Type</Label>
            <Select value={maintenanceForm.issue_type} onValueChange={(v) => setMaintenanceForm(prev => ({...prev, issue_type: v}))}>
              <SelectTrigger className="h-9 mt-1 text-sm"><SelectValue placeholder="Select issue type" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="housekeeping_damage">Housekeeping Damage</SelectItem>
                <SelectItem value="plumbing">Plumbing</SelectItem>
                <SelectItem value="hvac">HVAC</SelectItem>
                <SelectItem value="electrical">Electrical</SelectItem>
                <SelectItem value="furniture">Furniture</SelectItem>
                <SelectItem value="other">{t('folio.other')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-gray-600">{t('common.priority')}</Label>
            <Select value={maintenanceForm.priority} onValueChange={(v) => setMaintenanceForm(prev => ({...prev, priority: v}))}>
              <SelectTrigger className="h-9 mt-1 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="low">{t('common.low')}</SelectItem>
                <SelectItem value="normal">{t('common.normal')}</SelectItem>
                <SelectItem value="high">{t('common.high')}</SelectItem>
                <SelectItem value="urgent">{t('common.urgent')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-gray-600">{t('common.description')}</Label>
            <Textarea className="mt-1 text-sm min-h-[80px]" value={maintenanceForm.description}
              onChange={(e) => setMaintenanceForm(prev => ({...prev, description: e.target.value}))}
              placeholder="Short description of the issue..." />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>{t('common.cancel')}</Button>
          <Button size="sm" onClick={handleSubmit} disabled={submitting}>{submitting ? 'Kaydediliyor...' : t('maintenance.createWorkOrder')}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default MaintenanceDialog;
