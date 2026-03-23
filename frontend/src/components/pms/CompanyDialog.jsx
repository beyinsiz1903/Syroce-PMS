import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

const CompanyDialog = ({ open, onClose, newCompany, setNewCompany, onSubmit }) => {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Quick Company Creation</DialogTitle>
          <DialogDescription>Create a new company profile (status: pending)</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div><Label>{t('common.name')} *</Label><Input value={newCompany.name} onChange={(e) => setNewCompany({...newCompany, name: e.target.value})} required /></div>
            <div><Label>Corporate Code</Label><Input value={newCompany.corporate_code} onChange={(e) => setNewCompany({...newCompany, corporate_code: e.target.value})} /></div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div><Label>Tax Number</Label><Input value={newCompany.tax_number} onChange={(e) => setNewCompany({...newCompany, tax_number: e.target.value})} /></div>
            <div><Label>Contact Person</Label><Input value={newCompany.contact_person} onChange={(e) => setNewCompany({...newCompany, contact_person: e.target.value})} /></div>
          </div>
          <div><Label>{t('common.address')}</Label><Textarea value={newCompany.billing_address} onChange={(e) => setNewCompany({...newCompany, billing_address: e.target.value})} rows={2} /></div>
          <div className="grid grid-cols-2 gap-4">
            <div><Label>{t('common.email')}</Label><Input type="email" value={newCompany.contact_email} onChange={(e) => setNewCompany({...newCompany, contact_email: e.target.value})} /></div>
            <div><Label>{t('common.phone')}</Label><Input value={newCompany.contact_phone} onChange={(e) => setNewCompany({...newCompany, contact_phone: e.target.value})} /></div>
          </div>
          <div className="text-sm text-gray-500 bg-blue-50 p-3 rounded">This company will be created with Pending status.</div>
          <Button type="submit" className="w-full">{t('common.create')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default CompanyDialog;
