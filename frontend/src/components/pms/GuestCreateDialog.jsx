import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import IDScanner from './IDScanner';

const GuestCreateDialog = ({ open, onClose, onGuestCreated }) => {
  const { t } = useTranslation();
  const [newGuest, setNewGuest] = useState({
    name: '', email: '', phone: '', id_number: '', address: '', kvkk_consent: false, scanned_via_quick_id: false
  });

  const handleScanSuccess = (doc) => {
    setNewGuest(prev => ({
      ...prev,
      name: `${doc.first_name || ''} ${doc.last_name || ''}`.trim(),
      id_number: doc.document_number || doc.id_number || '',
      scanned_via_quick_id: true,
      // Default to consenting if they scanned
      kvkk_consent: true
    }));
  };

  const handleCreateGuest = async (e) => {
    e.preventDefault();
    if (!newGuest.kvkk_consent) {
      toast.error(t('pms.kvkkRequired', 'KVKK onay metnini kabul etmeniz zorunludur.'));
      return;
    }

    try {
      await axios.post('/pms/guests', newGuest);
      toast.success(t('pms.guestCreated', 'Misafir başarıyla oluşturuldu'));
      onClose();
      onGuestCreated();
      setNewGuest({ name: '', email: '', phone: '', id_number: '', address: '', kvkk_consent: false, scanned_via_quick_id: false });
    } catch (error) {
      toast.error(error.response?.data?.detail || t('pms.createFailed', 'Misafir oluşturulamadı'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('pms.registerGuest', 'Register Guest')}</DialogTitle>
          <DialogDescription>
            {t('pms.registerGuestDesc', 'Kimlik tarayıcı kullanarak bilgileri otomatik doldurabilirsiniz.')}
          </DialogDescription>
        </DialogHeader>

        <div className="mb-4">
          <IDScanner onScanSuccess={handleScanSuccess} />
        </div>

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

          <div className="flex items-start space-x-2 pt-2 pb-2">
            <Checkbox 
              id="kvkk_consent" 
              checked={newGuest.kvkk_consent} 
              onCheckedChange={(checked) => setNewGuest({...newGuest, kvkk_consent: checked})}
            />
            <div className="grid gap-1.5 leading-none">
              <label
                htmlFor="kvkk_consent"
                className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
              >
                {t('pms.kvkkConsentTitle', 'KVKK Aydınlatma Metni')}
              </label>
              <p className="text-xs text-slate-500">
                {t('pms.kvkkConsentDesc', 'Kişisel verilerimin işlenmesini ve kimlik fotoğrafımın analiz edilmesini onaylıyorum.')}
              </p>
            </div>
          </div>

          <Button type="submit" className="w-full">{t('pms.saveGuest', 'Save Guest')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default GuestCreateDialog;
