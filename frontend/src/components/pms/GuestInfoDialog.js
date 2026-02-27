import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { User } from 'lucide-react';

const GuestInfoDialog = ({ open, onClose, selectedGuest, setSelectedGuest, onSaved }) => {
  const { t } = useTranslation();

  const handleSave = async () => {
    try {
      await axios.put(`/pms/guests/${selectedGuest.id}`, selectedGuest);
      toast.success(t('messages.success.updated'));
      onClose();
      onSaved?.();
    } catch (error) {
      toast.error(t('messages.error.saveFailed'));
      console.error(error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="w-5 h-5" />
            {t('guest.guestProfile')}
          </DialogTitle>
          <DialogDescription>
            View and update guest personal and identification details
          </DialogDescription>
        </DialogHeader>
        
        {selectedGuest && (
          <div className="space-y-6">
            <div className="space-y-4">
              <h3 className="text-lg font-semibold border-b pb-2">Personal Information</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>{t('common.name')}</Label>
                  <Input 
                    value={selectedGuest.name || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, name: e.target.value})}
                    placeholder="Full Name"
                  />
                </div>
                <div>
                  <Label>{t('common.email')}</Label>
                  <Input 
                    type="email"
                    value={selectedGuest.email || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, email: e.target.value})}
                    placeholder="email@example.com"
                  />
                </div>
                <div>
                  <Label>{t('common.phone')}</Label>
                  <Input 
                    value={selectedGuest.phone || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, phone: e.target.value})}
                    placeholder="+90 555 123 4567"
                  />
                </div>
                <div>
                  <Label>{t('guest.dateOfBirth')}</Label>
                  <Input 
                    type="date"
                    value={selectedGuest.date_of_birth?.split('T')[0] || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, date_of_birth: e.target.value})}
                  />
                </div>
                <div>
                  <Label>{t('guest.nationality')}</Label>
                  <Input 
                    value={selectedGuest.nationality || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, nationality: e.target.value})}
                    placeholder="TR"
                  />
                </div>
                <div>
                  <Label>Gender</Label>
                  <Select 
                    value={selectedGuest.gender || ''} 
                    onValueChange={(v) => setSelectedGuest({...selectedGuest, gender: v})}
                  >
                    <SelectTrigger><SelectValue placeholder="Select gender" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="male">Male</SelectItem>
                      <SelectItem value="female">Female</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold border-b pb-2">Identification Details</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>ID Type</Label>
                  <Select 
                    value={selectedGuest.id_type || 'passport'} 
                    onValueChange={(v) => setSelectedGuest({...selectedGuest, id_type: v})}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="passport">Passport</SelectItem>
                      <SelectItem value="national_id">National ID</SelectItem>
                      <SelectItem value="drivers_license">Driver&apos;s License</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>{t('guest.idNumber')}</Label>
                  <Input 
                    value={selectedGuest.id_number || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, id_number: e.target.value})}
                    placeholder="ID/Passport Number"
                  />
                </div>
                <div>
                  <Label>Issue Date</Label>
                  <Input 
                    type="date"
                    value={selectedGuest.id_issue_date?.split('T')[0] || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, id_issue_date: e.target.value})}
                  />
                </div>
                <div>
                  <Label>Expiry Date</Label>
                  <Input 
                    type="date"
                    value={selectedGuest.id_expiry_date?.split('T')[0] || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, id_expiry_date: e.target.value})}
                  />
                </div>
                <div className="col-span-2">
                  <Label>Issuing Authority</Label>
                  <Input 
                    value={selectedGuest.id_issuing_authority || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, id_issuing_authority: e.target.value})}
                    placeholder="e.g., Ministry of Interior"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold border-b pb-2">{t('common.address')}</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <Label>Street Address</Label>
                  <Input 
                    value={selectedGuest.address || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, address: e.target.value})}
                    placeholder="Street address"
                  />
                </div>
                <div>
                  <Label>City</Label>
                  <Input 
                    value={selectedGuest.city || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, city: e.target.value})}
                    placeholder="City"
                  />
                </div>
                <div>
                  <Label>Postal Code</Label>
                  <Input 
                    value={selectedGuest.postal_code || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, postal_code: e.target.value})}
                    placeholder="Postal code"
                  />
                </div>
                <div>
                  <Label>Country</Label>
                  <Input 
                    value={selectedGuest.country || ''} 
                    onChange={(e) => setSelectedGuest({...selectedGuest, country: e.target.value})}
                    placeholder="Country"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label>{t('common.notes')}</Label>
              <Textarea 
                value={selectedGuest.notes || ''} 
                onChange={(e) => setSelectedGuest({...selectedGuest, notes: e.target.value})}
                placeholder="Additional notes about the guest..."
                rows={3}
              />
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button variant="outline" onClick={onClose}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleSave}>
                <User className="w-4 h-4 mr-2" />
                {t('common.save')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default GuestInfoDialog;
