import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, ClipboardList, DollarSign } from 'lucide-react';

const FolioViewDialog = ({
  open,
  onClose,
  selectedFolio,
  folioCharges,
  folioPayments,
  guests,
  bookings,
  onChargePosted,
  onPaymentPosted,
}) => {
  const { t } = useTranslation();
  const [subDialog, setSubDialog] = useState(null);
  const [expandedChargeItems, setExpandedChargeItems] = useState({});

  const [newFolioCharge, setNewFolioCharge] = useState({
    charge_category: 'room',
    description: '',
    amount: 0,
    quantity: 1,
    auto_calculate_tax: false
  });

  const [newFolioPayment, setNewFolioPayment] = useState({
    amount: 0,
    method: 'card',
    payment_type: 'interim',
    reference: '',
    notes: ''
  });

  const handlePostCharge = async (e) => {
    e.preventDefault();
    if (!selectedFolio) return;
    try {
      await axios.post(`/folio/${selectedFolio.id}/charge`, newFolioCharge);
      toast.success('Charge posted');
      onChargePosted(selectedFolio.id);
      setNewFolioCharge({ charge_category: 'room', description: '', amount: 0, quantity: 1, auto_calculate_tax: false });
      setSubDialog(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to post charge');
    }
  };

  const handlePostPayment = async (e) => {
    e.preventDefault();
    if (!selectedFolio) return;
    try {
      await axios.post(`/folio/${selectedFolio.id}/payment`, newFolioPayment);
      toast.success('Payment posted');
      onPaymentPosted(selectedFolio.id);
      setNewFolioPayment({ amount: 0, method: 'card', payment_type: 'interim', reference: '', notes: '' });
      setSubDialog(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to post payment');
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('pms.folioManagement', 'Folio Management')}</DialogTitle>
            <DialogDescription>
              {selectedFolio && `Folio ${selectedFolio.folio_number} - ${selectedFolio.folio_type.toUpperCase()}`}
            </DialogDescription>
          </DialogHeader>

          {selectedFolio && (
            <div className="space-y-6">
              <div className="bg-gradient-to-r from-blue-50 to-purple-50 p-6 rounded-lg border">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="text-sm text-gray-600">{t('pms.guest', 'Guest')}</div>
                    <div className="font-semibold">
                      {guests.find(g => g.id === selectedFolio.guest_id)?.name || t('common.unknown', 'Unknown')}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">{t('pms.reservation', 'Reservation')}</div>
                    <div className="font-semibold">
                      {(() => {
                        const booking = bookings.find(b => b.id === selectedFolio.booking_id);
                        if (!booking) return t('common.unknown', 'Unknown');
                        return `${new Date(booking.check_in).toLocaleDateString()} - ${new Date(booking.check_out).toLocaleDateString()}`;
                      })()}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">{t('pms.currentBalance', 'Current Balance')}</div>
                    <div className={`text-2xl font-bold ${selectedFolio.balance > 0 ? 'text-red-600' : selectedFolio.balance < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                      {selectedFolio.balance?.toFixed(2) || '0.00'} ₺
                    </div>
                    <div className="text-xs text-gray-500">
                      {selectedFolio.balance > 0 ? t('pms.guestOwes', 'Guest owes') : selectedFolio.balance < 0 ? t('pms.hotelOwes', 'Hotel owes') : t('pms.balanced', 'Balanced')}
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex gap-2">
                <Button onClick={() => setSubDialog('post-charge')} variant="default">
                  <Plus className="w-4 h-4 mr-2" />
                  {t('pms.addCharge', 'Add Charge')}
                </Button>
                <Button onClick={() => setSubDialog('post-payment')} variant="default">
                  <Plus className="w-4 h-4 mr-2" />
                  {t('pms.addPayment', 'Add Payment')}
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center">
                    <ClipboardList className="w-5 h-5 mr-2" />
                    {t('pms.charges', 'Charges')}
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {folioCharges.length === 0 ? (
                      <div className="text-center text-gray-400 py-8">{t('pms.noChargesYet', 'No charges posted yet')}</div>
                    ) :
                      folioCharges.map((charge) => {
                        const isPOSCharge = charge.charge_category === 'restaurant' || charge.charge_category === 'bar' || charge.charge_category === 'room_service';
                        const hasLineItems = charge.line_items && charge.line_items.length > 0;
                        const isExpanded = expandedChargeItems[charge.id];

                        return (
                          <Card key={charge.id} className={charge.voided ? 'opacity-50 bg-gray-50' : ''}>
                            <CardContent className="p-4">
                              <div
                                className={`flex justify-between items-start ${isPOSCharge && hasLineItems ? 'cursor-pointer hover:bg-gray-50' : ''}`}
                                onClick={() => {
                                  if (isPOSCharge && hasLineItems) {
                                    setExpandedChargeItems(prev => ({ ...prev, [charge.id]: !prev[charge.id] }));
                                  }
                                }}
                              >
                                <div className="flex-1">
                                  <div className="flex items-center gap-2">
                                    <div className="font-semibold">{charge.description}</div>
                                    {charge.voided && (
                                      <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">VOID</span>
                                    )}
                                  </div>
                                  <div className="text-xs text-gray-500 capitalize">{charge.charge_category}</div>
                                  <div className="text-xs text-gray-400">
                                    {new Date(charge.created_at).toLocaleString()}
                                  </div>
                                </div>
                                <div className="text-right">
                                  <div className="font-bold">{(charge.total_amount || charge.amount || 0).toFixed(2)} ₺</div>
                                  {charge.tax_amount > 0 && (
                                    <div className="text-xs text-gray-500">Tax: {charge.tax_amount.toFixed(2)} ₺</div>
                                  )}
                                </div>
                              </div>
                              {isExpanded && hasLineItems && (
                                <div className="mt-3 pt-3 border-t space-y-1">
                                  {charge.line_items.map((li, i) => (
                                    <div key={i} className="flex justify-between text-xs text-gray-600">
                                      <span>{li.name || li.description} x{li.quantity}</span>
                                      <span>{(li.total || li.amount || 0).toFixed(2)} ₺</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        );
                      })
                    }
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center">
                    <DollarSign className="w-5 h-5 mr-2" />
                    {t('pms.payments', 'Payments')}
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {folioPayments.length === 0 ? (
                      <div className="text-center text-gray-400 py-8">{t('pms.noPaymentsYet', 'No payments posted yet')}</div>
                    ) :
                      folioPayments.map((payment) => (
                        <Card key={payment.id}>
                          <CardContent className="p-4">
                            <div className="flex justify-between items-start">
                              <div>
                                <div className="font-semibold capitalize">{payment.method}</div>
                                <div className="text-xs text-gray-500 capitalize">{payment.payment_type}</div>
                                {payment.reference && <div className="text-xs text-gray-400">Ref: {payment.reference}</div>}
                                <div className="text-xs text-gray-400">
                                  {new Date(payment.created_at).toLocaleString()}
                                </div>
                              </div>
                              <div className="text-green-600 font-bold">{payment.amount.toFixed(2)} ₺</div>
                            </div>
                          </CardContent>
                        </Card>
                      ))
                    }
                  </div>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={subDialog === 'post-charge'} onOpenChange={(o) => !o && setSubDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('pms.postCharge', 'Post Charge')}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handlePostCharge} className="space-y-4">
            <div>
              <Label>{t('pms.chargeCategory', 'Category')}</Label>
              <Select value={newFolioCharge.charge_category} onValueChange={(v) => setNewFolioCharge({...newFolioCharge, charge_category: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="room">{t('pms.room', 'Room')}</SelectItem>
                  <SelectItem value="restaurant">{t('pms.restaurant', 'Restaurant')}</SelectItem>
                  <SelectItem value="bar">Bar</SelectItem>
                  <SelectItem value="minibar">Minibar</SelectItem>
                  <SelectItem value="laundry">{t('pms.laundry', 'Laundry')}</SelectItem>
                  <SelectItem value="spa">Spa</SelectItem>
                  <SelectItem value="phone">{t('pms.phone', 'Phone')}</SelectItem>
                  <SelectItem value="other">{t('common.other', 'Other')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('common.description', 'Description')}</Label>
              <Input value={newFolioCharge.description} onChange={(e) => setNewFolioCharge({...newFolioCharge, description: e.target.value})} required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{t('common.amount', 'Amount')}</Label>
                <Input type="number" step="0.01" value={newFolioCharge.amount} onChange={(e) => setNewFolioCharge({...newFolioCharge, amount: parseFloat(e.target.value)})} required />
              </div>
              <div>
                <Label>{t('common.quantity', 'Quantity')}</Label>
                <Input type="number" value={newFolioCharge.quantity} onChange={(e) => setNewFolioCharge({...newFolioCharge, quantity: parseInt(e.target.value)})} required />
              </div>
            </div>
            <Button type="submit" className="w-full">{t('pms.postCharge', 'Post Charge')}</Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={subDialog === 'post-payment'} onOpenChange={(o) => !o && setSubDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('pms.postPayment', 'Post Payment')}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handlePostPayment} className="space-y-4">
            <div>
              <Label>{t('common.amount', 'Amount')}</Label>
              <Input type="number" step="0.01" value={newFolioPayment.amount} onChange={(e) => setNewFolioPayment({...newFolioPayment, amount: parseFloat(e.target.value)})} required />
            </div>
            <div>
              <Label>{t('pms.paymentMethod', 'Payment Method')}</Label>
              <Select value={newFolioPayment.method} onValueChange={(v) => setNewFolioPayment({...newFolioPayment, method: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">{t('pms.cash', 'Cash')}</SelectItem>
                  <SelectItem value="card">{t('pms.creditCard', 'Credit Card')}</SelectItem>
                  <SelectItem value="bank_transfer">{t('pms.bankTransfer', 'Bank Transfer')}</SelectItem>
                  <SelectItem value="online">Online</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('pms.paymentType', 'Payment Type')}</Label>
              <Select value={newFolioPayment.payment_type} onValueChange={(v) => setNewFolioPayment({...newFolioPayment, payment_type: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="interim">Interim</SelectItem>
                  <SelectItem value="final">Final</SelectItem>
                  <SelectItem value="deposit">Deposit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('pms.reference', 'Reference')}</Label>
              <Input value={newFolioPayment.reference} onChange={(e) => setNewFolioPayment({...newFolioPayment, reference: e.target.value})} />
            </div>
            <Button type="submit" className="w-full">{t('pms.postPayment', 'Post Payment')}</Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default FolioViewDialog;
