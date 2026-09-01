import { useRef, useState } from 'react';
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
    name: '', email: '', phone: '', id_number: '', id_type: '', nationality: '', birth_date: '',
    gender: '', birth_place: '', document_expiry_date: '', address: '', kvkk_consent: false,
    scanned_via_quick_id: false
  });
  const [submitting, setSubmitting] = useState(false);
  const idempotencyKeyRef = useRef(null);

  const handleScanSuccess = (doc) => {
    setNewGuest(prev => ({
      ...prev,
      name: `${doc.first_name || ''} ${doc.last_name || ''}`.trim(),
      id_number: doc.document_number || doc.id_number || '',
      id_type: doc.document_type || '',
      nationality: doc.nationality || '',
      birth_date: doc.birth_date || '',
      gender: doc.gender || '',
      birth_place: doc.birth_place || '',
      document_expiry_date: doc.expiry_date || '',
      address: doc.address || prev.address,
      scanned_via_quick_id: true,
    }));
  };

  const handleCreateGuest = async (e) => {
    e.preventDefault();
    const requiredValues = [newGuest.name, newGuest.email, newGuest.phone, newGuest.id_number];
    if (requiredValues.some((value) => !String(value || '').trim())) {
      toast.error(t('pms.guestRequiredFields', 'Ad soyad, e-posta, telefon ve kimlik/pasaport numarası zorunludur.'));
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newGuest.email.trim())) {
      toast.error(t('pms.invalidGuestEmail', 'Geçerli bir e-posta adresi girin.'));
      return;
    }
    if (!newGuest.kvkk_consent) {
      toast.error(t('pms.kvkkRequired', 'KVKK onay metnini kabul etmeniz zorunludur.'));
      return;
    }

    if (submitting) return;
    setSubmitting(true);
    idempotencyKeyRef.current ||= crypto.randomUUID();
    try {
      await axios.post('/pms/guests', newGuest, {
        headers: { 'Idempotency-Key': idempotencyKeyRef.current },
      });
      toast.success(t('pms.guestCreated', 'Misafir başarıyla oluşturuldu'));
      onClose();
      onGuestCreated();
      setNewGuest({
        name: '', email: '', phone: '', id_number: '', id_type: '', nationality: '', birth_date: '',
        gender: '', birth_place: '', document_expiry_date: '', address: '', kvkk_consent: false,
        scanned_via_quick_id: false
      });
      idempotencyKeyRef.current = null;
    } catch (error) {
      toast.error(error.response?.data?.detail || t('pms.createFailed', 'Misafir oluşturulamadı'));
    } finally {
      setSubmitting(false);
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

        <form onSubmit={handleCreateGuest} noValidate className="space-y-4">
          <div>
            <Label>{t('pms.fullName', 'Full Name')} *</Label>
            <Input value={newGuest.name} onChange={(e) => setNewGuest({...newGuest, name: e.target.value})} required />
          </div>
          <div>
            <Label>{t('common.email', 'Email')} *</Label>
            <Input type="email" value={newGuest.email} onChange={(e) => setNewGuest({...newGuest, email: e.target.value})} required />
          </div>
          <div>
            <Label>{t('common.phone', 'Phone')} *</Label>
            <Input value={newGuest.phone} onChange={(e) => setNewGuest({...newGuest, phone: e.target.value})} required />
          </div>
          <div>
            <Label>{t('pms.idPassport', 'ID / Passport No')} *</Label>
            <Input value={newGuest.id_number} onChange={(e) => setNewGuest({...newGuest, id_number: e.target.value})} required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>{t('pms.nationality', 'Uyruk')}</Label>
              <Input value={newGuest.nationality} onChange={(e) => setNewGuest({...newGuest, nationality: e.target.value})} />
            </div>
            <div>
              <Label>{t('pms.birthDate', 'Doğum tarihi')}</Label>
              <Input type="date" value={newGuest.birth_date} onChange={(e) => setNewGuest({...newGuest, birth_date: e.target.value})} />
            </div>
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

          <Button type="submit" className="w-full" disabled={submitting}>{t('pms.saveGuest', 'Save Guest')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default GuestCreateDialog;
