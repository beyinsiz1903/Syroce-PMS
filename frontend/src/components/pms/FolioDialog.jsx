import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const FolioDialog = ({ open, onClose, folio, bookingId, onFolioUpdated }) => {
  const { t } = useTranslation();
  const [newCharge, setNewCharge] = useState({
    charge_type: 'food', description: '', amount: 0, quantity: 1
  });
  const [newPayment, setNewPayment] = useState({
    amount: 0, method: 'card', reference: '', notes: ''
  });

  const handleAddCharge = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`/frontdesk/folio/${bookingId}/charge`, null, { params: newCharge });
      toast.success('Charge added');
      onFolioUpdated();
      setNewCharge({ charge_type: 'food', description: '', amount: 0, quantity: 1 });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add charge');
    }
  };

  const handleProcessPayment = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`/frontdesk/payment/${bookingId}`, null, { params: newPayment });
      toast.success('Payment processed');
      onFolioUpdated();
      setNewPayment({ amount: 0, method: 'card', reference: '', notes: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to process payment');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('pms.guestFolio', 'Guest Folio')}</DialogTitle>
        </DialogHeader>
        {folio && (
          <div className="space-y-6">
            <div>
              <h3 className="font-semibold mb-2">{t('pms.charges', 'Charges')}</h3>
              <div className="space-y-2">
                {folio.charges.map((charge, idx) => (
                  <div key={idx} className="flex justify-between text-sm border-b pb-2">
                    <div>
                      <div className="font-medium">{charge.description}</div>
                      <div className="text-xs text-gray-500 capitalize">{charge.charge_type}</div>
                    </div>
                    <div className="text-right">
                      <div>{charge.total.toFixed(2)} ₺</div>
                      <div className="text-xs text-gray-500">{charge.quantity} × {charge.amount} ₺</div>
                    </div>
                  </div>
                ))}
              </div>

              <form onSubmit={handleAddCharge} className="mt-4 p-4 bg-gray-50 rounded">
                <div className="grid grid-cols-2 gap-4">
                  <Select value={newCharge.charge_type} onValueChange={(v) => setNewCharge({...newCharge, charge_type: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="food">{t('pms.foodBeverage', 'Food & Beverage')}</SelectItem>
                      <SelectItem value="laundry">{t('pms.laundry', 'Laundry')}</SelectItem>
                      <SelectItem value="minibar">Minibar</SelectItem>
                      <SelectItem value="spa">Spa</SelectItem>
                      <SelectItem value="phone">{t('pms.phone', 'Phone')}</SelectItem>
                      <SelectItem value="other">{t('common.other', 'Other')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    placeholder={t("common.description")}
                    value={newCharge.description}
                    onChange={(e) => setNewCharge({...newCharge, description: e.target.value})}
                    required
                  />
                  <Input
                    type="number"
                    step="0.01"
                    placeholder={t('common.amount', 'Amount')}
                    value={newCharge.amount}
                    onChange={(e) => setNewCharge({...newCharge, amount: parseFloat(e.target.value)})}
                    required
                  />
                  <Button type="submit">{t('pms.addCharge', 'Add Charge')}</Button>
                </div>
              </form>
            </div>

            <div>
              <h3 className="font-semibold mb-2">{t('pms.payments', 'Payments')}</h3>
              <div className="space-y-2">
                {folio.payments.map((payment, idx) => (
                  <div key={idx} className="flex justify-between text-sm border-b pb-2">
                    <div>
                      <div className="font-medium capitalize">{payment.method}</div>
                      {payment.reference && <div className="text-xs text-gray-500">Ref: {payment.reference}</div>}
                    </div>
                    <div className="text-green-600 font-medium">{payment.amount.toFixed(2)} ₺</div>
                  </div>
                ))}
              </div>

              <form onSubmit={handleProcessPayment} className="mt-4 p-4 bg-gray-50 rounded">
                <div className="grid grid-cols-2 gap-4">
                  <Input
                    type="number"
                    step="0.01"
                    placeholder={t('common.amount', 'Amount')}
                    value={newPayment.amount}
                    onChange={(e) => setNewPayment({...newPayment, amount: parseFloat(e.target.value)})}
                    required
                  />
                  <Select value={newPayment.method} onValueChange={(v) => setNewPayment({...newPayment, method: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cash">{t('pms.cash', 'Cash')}</SelectItem>
                      <SelectItem value="card">{t('pms.creditCard', 'Credit Card')}</SelectItem>
                      <SelectItem value="bank_transfer">{t('pms.bankTransfer', 'Bank Transfer')}</SelectItem>
                      <SelectItem value="online">Online</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    placeholder={t('pms.referenceOptional', 'Reference (optional)')}
                    value={newPayment.reference}
                    onChange={(e) => setNewPayment({...newPayment, reference: e.target.value})}
                  />
                  <Button type="submit">{t('pms.processPayment', 'Process Payment')}</Button>
                </div>
              </form>
            </div>

            <div className="border-t pt-4">
              <div className="flex justify-between text-lg font-bold">
                <span>{t('pms.totalCharges', 'Total Charges')}:</span>
                <span>{folio.total_charges.toFixed(2)} ₺</span>
              </div>
              <div className="flex justify-between text-lg font-bold text-green-600">
                <span>{t('pms.totalPayments', 'Total Payments')}:</span>
                <span>{folio.total_paid.toFixed(2)} ₺</span>
              </div>
              <div className={`flex justify-between text-2xl font-bold ${folio.balance > 0 ? 'text-red-600' : 'text-gray-600'}`}>
                <span>{t('pms.balance', 'Balance')}:</span>
                <span>{folio.balance.toFixed(2)} ₺</span>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default FolioDialog;
