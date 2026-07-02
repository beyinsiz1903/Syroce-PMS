import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus } from 'lucide-react';
const InvoiceFormDialog = ({
  open,
  onClose
}) => {
  const {
    t
  } = useTranslation();
  const [newInvoice, setNewInvoice] = useState({
    invoice_type: 'sales',
    customer_name: '',
    customer_email: '',
    customer_tax_office: '',
    customer_tax_number: '',
    customer_address: '',
    items: [{
      description: '',
      quantity: 1,
      unit_price: 0,
      vat_rate: 18,
      vat_amount: 0,
      total: 0,
      additional_taxes: []
    }],
    due_date: '',
    notes: ''
  });
  const [showAdditionalTaxDialog, setShowAdditionalTaxDialog] = useState(false);
  const [currentItemIndex, setCurrentItemIndex] = useState(null);
  const [newAdditionalTax, setNewAdditionalTax] = useState({
    tax_type: 'otv',
    tax_name: 'SCT',
    rate: 0,
    amount: 0,
    is_percentage: true,
    withholding_rate: null
  });
  const calculateInvoiceItem = (index, field, value) => {
    const items = [...newInvoice.items];
    items[index][field] = value;
    if (field === 'quantity' || field === 'unit_price' || field === 'vat_rate') {
      const subtotal = items[index].quantity * items[index].unit_price;
      items[index].vat_amount = subtotal * (items[index].vat_rate / 100);
      items[index].total = subtotal + items[index].vat_amount;
    }
    setNewInvoice({
      ...newInvoice,
      items
    });
  };
  const addInvoiceItem = () => {
    setNewInvoice({
      ...newInvoice,
      items: [...newInvoice.items, {
        description: '',
        quantity: 1,
        unit_price: 0,
        vat_rate: 18,
        vat_amount: 0,
        total: 0,
        additional_taxes: []
      }]
    });
  };
  const addAdditionalTax = () => {
    if (currentItemIndex === null) return;
    const items = [...newInvoice.items];
    const item = items[currentItemIndex];
    let calculatedAmount = 0;
    const subtotal = item.quantity * item.unit_price;
    if (newAdditionalTax.tax_type === 'withholding' && newAdditionalTax.withholding_rate) {
      const rateParts = newAdditionalTax.withholding_rate.split('/');
      const ratePercent = parseInt(rateParts[0]) / parseInt(rateParts[1]) * 100;
      calculatedAmount = item.vat_amount * (ratePercent / 100);
    } else if (newAdditionalTax.is_percentage) {
      calculatedAmount = subtotal * (newAdditionalTax.rate / 100);
    } else {
      calculatedAmount = newAdditionalTax.amount;
    }
    if (!item.additional_taxes) item.additional_taxes = [];
    item.additional_taxes.push({
      ...newAdditionalTax,
      calculated_amount: calculatedAmount
    });
    items[currentItemIndex] = item;
    setNewInvoice({
      ...newInvoice,
      items
    });
    setShowAdditionalTaxDialog(false);
    setNewAdditionalTax({
      tax_type: 'otv',
      tax_name: 'SCT',
      rate: 0,
      amount: 0,
      is_percentage: true,
      withholding_rate: null
    });
  };
  const removeAdditionalTax = (itemIndex, taxIndex) => {
    const items = [...newInvoice.items];
    items[itemIndex].additional_taxes.splice(taxIndex, 1);
    setNewInvoice({
      ...newInvoice,
      items
    });
  };
  const handleCreateInvoice = async e => {
    e.preventDefault();
    try {
      await axios.post('/accounting/invoices', null, {
        params: newInvoice
      });
      toast.success('Invoice created');
      onClose();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create invoice');
    }
  };
  const invoiceSubtotal = newInvoice.items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
  const invoiceTotalVAT = newInvoice.items.reduce((sum, item) => sum + item.vat_amount, 0);
  let invoiceVATWithholding = 0;
  let invoiceAdditionalTaxes = 0;
  newInvoice.items.forEach(item => {
    if (item.additional_taxes && item.additional_taxes.length > 0) {
      item.additional_taxes.forEach(tax => {
        if (tax.tax_type === 'withholding') {
          if (tax.withholding_rate) {
            const rateParts = tax.withholding_rate.split('/');
            const ratePercent = parseInt(rateParts[0]) / parseInt(rateParts[1]) * 100;
            invoiceVATWithholding += item.vat_amount * (ratePercent / 100);
          }
        } else {
          const subtotal = item.quantity * item.unit_price;
          if (tax.is_percentage) {
            invoiceAdditionalTaxes += subtotal * (tax.rate / 100);
          } else {
            invoiceAdditionalTaxes += tax.amount;
          }
        }
      });
    }
  });
  const invoiceTotal = invoiceSubtotal + invoiceTotalVAT + invoiceAdditionalTaxes - invoiceVATWithholding;
  return <>
      <Dialog open={open} onOpenChange={o => !o && onClose()}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('invoice.createInvoice')}</DialogTitle>
            <DialogDescription>{t('invoice.subtitle')}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateInvoice} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{t('invoice.invoiceType')}</Label>
                <Select value={newInvoice.invoice_type} onValueChange={v => setNewInvoice({
                ...newInvoice,
                invoice_type: v
              })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sales">{t('invoice.salesInvoice')}</SelectItem>
                    <SelectItem value="e_invoice">{t('invoice.eInvoice')}</SelectItem>
                    <SelectItem value="proforma">{t('invoice.proforma')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{t('invoice.customerName')} *</Label>
                <Input value={newInvoice.customer_name} onChange={e => setNewInvoice({
                ...newInvoice,
                customer_name: e.target.value
              })} required />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{t('common.email')}</Label>
                <Input type="email" value={newInvoice.customer_email} onChange={e => setNewInvoice({
                ...newInvoice,
                customer_email: e.target.value
              })} />
              </div>
              <div>
                <Label>{t('invoice.taxNumber')}</Label>
                <Input value={newInvoice.customer_tax_number} onChange={e => setNewInvoice({
                ...newInvoice,
                customer_tax_number: e.target.value
              })} />
              </div>
            </div>

            <div>
              <Label>{t('invoice.address')}</Label>
              <Textarea value={newInvoice.customer_address} onChange={e => setNewInvoice({
              ...newInvoice,
              customer_address: e.target.value
            })} rows={2} />
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <Label>{t('invoice.invoiceItems')}</Label>
                <Button type="button" size="sm" variant="outline" onClick={addInvoiceItem}>
                  <Plus className="w-4 h-4 mr-1" /> {t('invoice.addItem')}
                </Button>
              </div>
              <div className="space-y-3">
                {newInvoice.items.map((item, index) => <div key={item.id || index} className="border rounded-lg p-3 space-y-2">
                    <div className="grid grid-cols-6 gap-2 items-center">
                      <Input placeholder={t('invoice.description')} value={item.description} onChange={e => calculateInvoiceItem(index, 'description', e.target.value)} required />
                      <Input type="number" placeholder={t('invoice.qty')} value={item.quantity} onChange={e => calculateInvoiceItem(index, 'quantity', parseFloat(e.target.value))} required />
                      <Input type="number" step="0.01" placeholder={t('invoice.price')} value={item.unit_price} onChange={e => calculateInvoiceItem(index, 'unit_price', parseFloat(e.target.value))} required />
                      <Select value={item.vat_rate.toString()} onValueChange={v => calculateInvoiceItem(index, 'vat_rate', parseFloat(v))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="0">0%</SelectItem>
                          <SelectItem value="1">1%</SelectItem>
                          <SelectItem value="8">8%</SelectItem>
                          <SelectItem value="10">10%</SelectItem>
                          <SelectItem value="18">18%</SelectItem>
                          <SelectItem value="20">20%</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input type="number" placeholder={t('invoice.total')} value={item.total.toFixed(2)} readOnly />
                      <Button type="button" size="sm" variant="outline" onClick={() => {
                    setCurrentItemIndex(index);
                    setShowAdditionalTaxDialog(true);
                  }} title={t('invoice.addAdditionalTax')}>
                        <Plus className="w-4 h-4" />
                      </Button>
                    </div>

                    {item.additional_taxes && item.additional_taxes.length > 0 && <div className="ml-4 space-y-1">
                        {item.additional_taxes.map((tax, taxIndex) => <div key={taxIndex} className="flex items-center justify-between text-sm bg-blue-50 px-2 py-1 rounded">
                            <span className="text-blue-700">
                              {tax.tax_name}: {tax.is_percentage ? `${tax.rate}%` : `₺${tax.amount}`}
                              {tax.withholding_rate && ` (${tax.withholding_rate})`}
                            </span>
                            <Button type="button" size="sm" variant="ghost" onClick={() => removeAdditionalTax(index, taxIndex)} className="h-6 w-6 p-0 text-red-600">
                              ×
                            </Button>
                          </div>)}
                      </div>}
                  </div>)}
              </div>
            </div>

            <div className="border-t pt-4">
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('invoice.subtotal')}:</span>
                  <span className="font-medium">${invoiceSubtotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('invoice.totalVAT')}:</span>
                  <span className="font-medium">${invoiceTotalVAT.toFixed(2)}</span>
                </div>
                {invoiceAdditionalTaxes > 0 && <div className="flex justify-between">
                    <span className="text-gray-600">{t('invoice.additionalTaxes')}:</span>
                    <span className="font-medium">${invoiceAdditionalTaxes.toFixed(2)}</span>
                  </div>}
                {invoiceVATWithholding > 0 && <>
                    <div className="flex justify-between text-red-600">
                      <span>{t('invoice.vatWithholding')}:</span>
                      <span className="font-medium">-${invoiceVATWithholding.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-red-600">
                      <span>{t('invoice.totalWithholding')}:</span>
                      <span className="font-medium">-${invoiceVATWithholding.toFixed(2)}</span>
                    </div>
                  </>}
                <div className="flex justify-between text-lg font-bold border-t pt-2">
                  <span>{t('invoice.grandTotal')}:</span>
                  <span>${invoiceTotal.toFixed(2)}</span>
                </div>
              </div>
            </div>

            <div>
              <Label>{t('invoice.dueDate')}</Label>
              <Input type="date" value={newInvoice.due_date} onChange={e => setNewInvoice({
              ...newInvoice,
              due_date: e.target.value
            })} required />
            </div>

            <Button type="submit" className="w-full" data-testid="submit-invoice-btn">{t('invoice.createInvoice')}</Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={showAdditionalTaxDialog} onOpenChange={setShowAdditionalTaxDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('invoice.addAdditionalTax')}</DialogTitle>
            <DialogDescription>{t('invoice.subtitle')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('invoice.taxType')}</Label>
              <Select value={newAdditionalTax.tax_type} onValueChange={v => {
              let taxName = 'SCT';
              if (v === 'withholding') taxName = 'Withholding';else if (v === 'accommodation') taxName = 'Accommodation Tax';else if (v === 'special_communication') taxName = 'SCL';
              setNewAdditionalTax({
                ...newAdditionalTax,
                tax_type: v,
                tax_name: taxName
              });
            }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="otv">{t('invoice.specialConsumptionTax')}</SelectItem>
                  <SelectItem value="withholding">{t('invoice.withholdingTax')}</SelectItem>
                  <SelectItem value="accommodation">{t('invoice.accommodationTax')}</SelectItem>
                  <SelectItem value="special_communication">{t('invoice.specialCommunicationTax')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {newAdditionalTax.tax_type === 'withholding' ? <div>
                <Label>{t('invoice.withholdingRate')}</Label>
                <Select value={newAdditionalTax.withholding_rate || ''} onValueChange={v => setNewAdditionalTax({
              ...newAdditionalTax,
              withholding_rate: v
            })}>
                  <SelectTrigger><SelectValue placeholder={t('invoice.selectRate', 'Select rate')} /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10/10">Full Withholding (All)</SelectItem>
                    <SelectItem value="9/10">9/10 Withholding (90%)</SelectItem>
                    <SelectItem value="7/10">7/10 Withholding (70%)</SelectItem>
                    <SelectItem value="5/10">5/10 Withholding (50%)</SelectItem>
                    <SelectItem value="4/10">4/10 Withholding (40%)</SelectItem>
                    <SelectItem value="3/10">3/10 Withholding (30%)</SelectItem>
                    <SelectItem value="2/10">2/10 Withholding (20%)</SelectItem>
                  </SelectContent>
                </Select>
              </div> : <>
                <div>
                  <Label>{t('invoice.calculationMethod')}</Label>
                  <Select value={newAdditionalTax.is_percentage ? 'percentage' : 'fixed'} onValueChange={v => setNewAdditionalTax({
                ...newAdditionalTax,
                is_percentage: v === 'percentage'
              })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="percentage">{t('invoice.percentage')}</SelectItem>
                      <SelectItem value="fixed">{t('invoice.fixedAmount')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {newAdditionalTax.is_percentage ? <div>
                    <Label>{t('invoice.taxRate')}</Label>
                    <Input type="number" step="0.01" value={newAdditionalTax.rate} onChange={e => setNewAdditionalTax({
                ...newAdditionalTax,
                rate: parseFloat(e.target.value)
              })} />
                  </div> : <div>
                    <Label>{t('invoice.taxAmount')}</Label>
                    <Input type="number" step="0.01" value={newAdditionalTax.amount} onChange={e => setNewAdditionalTax({
                ...newAdditionalTax,
                amount: parseFloat(e.target.value)
              })} />
                  </div>}
              </>}

            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setShowAdditionalTaxDialog(false)} className="flex-1">
                {t('common.cancel')}
              </Button>
              <Button type="button" onClick={addAdditionalTax} className="flex-1">
                {t('invoice.addTax')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>;
};
export default InvoiceFormDialog;