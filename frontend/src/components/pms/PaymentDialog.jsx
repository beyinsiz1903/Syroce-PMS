import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { DollarSign } from 'lucide-react';

const PaymentDialog = ({ open, onClose, selectedBooking, paymentForm, setPaymentForm, onPaymentDone }) => {
  const { t } = useTranslation();

  const handleSubmit = async () => {
    try {
      const folioRes = await axios.get(`/folio/booking/${selectedBooking.id}`);
      if (folioRes.data && folioRes.data.length > 0) {
        const folio = folioRes.data[0];
        await axios.post(`/folio/${folio.id}/payment`, paymentForm);
        toast.success(t('messages.success.saved'));
        onClose();
        setPaymentForm({ amount: 0, method: 'card', payment_type: 'interim', reference: '', notes: '' });
        onPaymentDone?.();
      } else {
        toast.error('No folio found for this booking');
      }
    } catch (error) {
      toast.error(t('messages.error.saveFailed'));
      console.error(error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('folio.postPayment')}</DialogTitle>
          <DialogDescription>Record payment for this booking</DialogDescription>
        </DialogHeader>
        
        {selectedBooking && (
          <div className="space-y-4">
            <div>
              <Label>{t('common.amount')}</Label>
              <Input type="number" value={paymentForm.amount}
                onChange={(e) => setPaymentForm({...paymentForm, amount: parseFloat(e.target.value)})}
                placeholder="0.00" />
            </div>
            <div>
              <Label>{t('folio.paymentMethod')}</Label>
              <Select value={paymentForm.method} onValueChange={(v) => setPaymentForm({...paymentForm, method: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">{t('folio.cash')}</SelectItem>
                  <SelectItem value="card">{t('folio.card')}</SelectItem>
                  <SelectItem value="bank_transfer">{t('folio.bankTransfer')}</SelectItem>
                  <SelectItem value="cheque">Cheque</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('folio.paymentType')}</Label>
              <Select value={paymentForm.payment_type} onValueChange={(v) => setPaymentForm({...paymentForm, payment_type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="prepayment">Prepayment</SelectItem>
                  <SelectItem value="deposit">Deposit</SelectItem>
                  <SelectItem value="interim">Interim</SelectItem>
                  <SelectItem value="final">Final</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Reference</Label>
              <Input value={paymentForm.reference}
                onChange={(e) => setPaymentForm({...paymentForm, reference: e.target.value})}
                placeholder="Transaction reference" />
            </div>
            <div>
              <Label>{t('common.notes')}</Label>
              <Textarea value={paymentForm.notes}
                onChange={(e) => setPaymentForm({...paymentForm, notes: e.target.value})}
                placeholder="Payment notes..." rows={2} />
            </div>
            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
              <Button onClick={handleSubmit}>
                <DollarSign className="w-4 h-4 mr-2" />
                {t('folio.postPayment')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default PaymentDialog;
