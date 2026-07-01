import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const GuestCreateDialog = ({ open, onClose, onGuestCreated }) => {
  const { t } = useTranslation();
  const [newGuest, setNewGuest] = useState({
    name: '', email: '', phone: '', id_number: '', address: ''
  });

  const handleCreateGuest = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/pms/guests', newGuest);
      toast.success('Guest created');
      onClose();
      onGuestCreated();
      setNewGuest({ name: '', email: '', phone: '', id_number: '', address: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create guest');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('pms.registerGuest', 'Register Guest')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleCreateGuest} className="space-y-4">
          <div>
            <Label>{t('pms.fullName', 'Full Name')}</Label>
            <Input value={newGuest.name} onChange={(e) => setNewGuest({...newGuest, name: e.target.value})} required />
          </div>
          <div>
            <Label>{t('common.email', 'Email')}</Label>
            <Input type="email" value={newGuest.email} onChange={(e) => setNewGuest({...newGuest, email: e.target.value})} required />
          </div>
          <div>
            <Label>{t('common.phone', 'Phone')}</Label>
            <Input value={newGuest.phone} onChange={(e) => setNewGuest({...newGuest, phone: e.target.value})} required />
          </div>
          <div>
            <Label>{t('pms.idPassport', 'ID / Passport No')}</Label>
            <Input value={newGuest.id_number} onChange={(e) => setNewGuest({...newGuest, id_number: e.target.value})} required />
          </div>
          <div>
            <Label>{t('common.address', 'Address')}</Label>
            <Input value={newGuest.address} onChange={(e) => setNewGuest({...newGuest, address: e.target.value})} />
          </div>
          <Button type="submit" className="w-full">{t('pms.saveGuest', 'Save Guest')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default GuestCreateDialog;
