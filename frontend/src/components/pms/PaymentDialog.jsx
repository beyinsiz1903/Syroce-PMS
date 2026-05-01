import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { DollarSign, AlertTriangle, Lightbulb } from 'lucide-react';

const PaymentDialog = ({ open, onClose, selectedBooking, paymentForm, setPaymentForm, onPaymentDone }) => {
  const { t } = useTranslation();

  const balance = selectedBooking
    ? Math.max(0, (selectedBooking.total_amount || 0) - (selectedBooking.paid_amount || 0))
    : 0;
  const isPartialPayment = paymentForm.amount > 0 && paymentForm.amount < balance;
  const isOverPayment = paymentForm.amount > balance && balance > 0;

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
          <DialogTitle style={{ fontFamily: 'Manrope' }}>{t('folio.postPayment')}</DialogTitle>
          <DialogDescription>Record payment for this booking</DialogDescription>
        </DialogHeader>
        
        {selectedBooking && (
          <div className="space-y-4">
            {/* Payment Intelligence Bar */}
            {balance > 0 && (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2" data-testid="payment-intelligence">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Toplam</span>
                  <span className="font-medium">{(selectedBooking.total_amount || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Odenen</span>
                  <span className="font-medium text-emerald-600">{(selectedBooking.paid_amount || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL</span>
                </div>
                <div className="flex justify-between text-xs border-t pt-1.5">
                  <span className="text-slate-700 font-semibold">Kalan</span>
                  <span className="font-bold text-red-600">{balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL</span>
                </div>
                {/* Quick fill button */}
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full h-8 text-xs border-[#C09D63] text-[#C09D63] hover:bg-[#C09D63]/10"
                  onClick={() => setPaymentForm({ ...paymentForm, amount: parseFloat(balance.toFixed(2)) })}
                  data-testid="payment-fill-balance"
                >
                  <Lightbulb className="w-3 h-3 mr-1" />
                  Tüm bakiyeyi al: {balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL
                </Button>
              </div>
            )}

            {/* Smart suggestions */}
            {isPartialPayment && (
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-md px-3 py-2" data-testid="payment-partial-warning">
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-amber-700">
                  Kismi ödeme. Kalan bakiye: {(balance - paymentForm.amount).toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL
                </p>
              </div>
            )}

            <div>
              <Label>{t('common.amount')}</Label>
              <Input type="number" value={paymentForm.amount}
                onChange={(e) => setPaymentForm({...paymentForm, amount: parseFloat(e.target.value)})}
                placeholder="0.00"
                data-testid="payment-amount-input" />
            </div>
            <div>
              <Label>{t('folio.paymentMethod')}</Label>
              <Select value={paymentForm.method} onValueChange={(v) => setPaymentForm({...paymentForm, method: v})}>
                <SelectTrigger data-testid="payment-method-select"><SelectValue /></SelectTrigger>
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
                <SelectTrigger data-testid="payment-type-select"><SelectValue /></SelectTrigger>
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
                placeholder="Transaction reference"
                data-testid="payment-reference-input" />
            </div>
            <div>
              <Label>{t('common.notes')}</Label>
              <Textarea value={paymentForm.notes}
                onChange={(e) => setPaymentForm({...paymentForm, notes: e.target.value})}
                placeholder="Payment notes..." rows={2}
                data-testid="payment-notes-input" />
            </div>
            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
              <Button onClick={handleSubmit} className="bg-[#C09D63] hover:bg-[#B08D55] text-white" data-testid="payment-submit-btn">
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
