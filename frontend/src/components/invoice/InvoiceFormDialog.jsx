import { useEffect, useState } from 'react';
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
import { useCurrency } from '@/context/CurrencyContext';
import { formatCurrency } from '@/lib/currency';
import { calculateFinancialLine, parseExchangeRate, parseMoney, parseQuantity, parseTaxRate, roundMoney } from '@/lib/financialInput';

export const createAccountingInvoice = (invoice) => axios.post('/accounting/invoices', invoice);

export const withSubmittedDueDate = (invoice, dueDate) => ({
  ...invoice,
  due_date: String(dueDate || invoice.due_date || '').trim(),
});

export const INVOICE_ITEM_CATEGORIES = {
  accommodation: { label: 'Konaklama', vatRate: 10 },
  food_beverage: { label: 'Yiyecek / alkolsüz içecek', vatRate: 10 },
  alcoholic_beverage: { label: 'Alkollü içecek', vatRate: 20 },
  other: { label: 'Diğer mal / hizmet', vatRate: 20 },
};

export const SUPPORTED_INVOICE_CURRENCIES = ['TRY', 'EUR', 'USD', 'GBP'];

export const createInvoiceItem = (category = 'accommodation', accommodationVatRate = 10) => ({
  category,
  description: category === 'accommodation' ? 'Konaklama Bedeli' : '',
  quantity: 1,
  unit_price: 0,
  vat_rate: category === 'accommodation'
    ? Number(accommodationVatRate)
    : INVOICE_ITEM_CATEGORIES[category]?.vatRate ?? 20,
  vat_amount: 0,
  total: 0,
  additional_taxes: [],
});

export const calculateInvoiceItemTotals = (item) => calculateFinancialLine({
  unitAmount: item?.unit_price,
  quantity: item?.quantity,
  vatRate: item?.vat_rate,
});

const InvoiceFormDialog = ({
  open,
  onClose,
  onCreated,
}) => {
  const {
    t
  } = useTranslation();
  const { code: tenantCurrency } = useCurrency();
  const [accommodationVatRate, setAccommodationVatRate] = useState(10);
  const [newInvoice, setNewInvoice] = useState({
    invoice_type: 'sales',
    customer_name: '',
    customer_email: '',
    customer_tax_office: '',
    customer_tax_number: '',
    customer_address: '',
    items: [createInvoiceItem()],
    due_date: '',
    notes: '',
    currency: tenantCurrency || 'TRY',
    exchange_rate: 1,
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

  useEffect(() => {
    if (!open) return undefined;
    let active = true;
    axios.get('/pms/hotel-settings').then(({ data }) => {
      if (!active) return;
      const configuredRate = Number(data?.default_accommodation_vat_rate);
      if (!Number.isFinite(configuredRate) || configuredRate < 0 || configuredRate > 100) return;
      setAccommodationVatRate(configuredRate);
      setNewInvoice(current => ({
        ...current,
        items: current.items.map(item => {
          if (item.category !== 'accommodation' || Number(item.unit_price) !== 0) return item;
          return { ...item, vat_rate: configuredRate, vat_amount: 0, total: 0 };
        }),
      }));
    }).catch(() => {
      // The statutory fallback remains 10% when settings are unavailable.
    });
    return () => {
      active = false;
    };
  }, [open]);

  const calculateInvoiceItem = (index, field, value) => {
    const items = [...newInvoice.items];
    items[index][field] = value;
    if (field === 'category') {
      items[index].vat_rate = value === 'accommodation'
        ? accommodationVatRate
        : INVOICE_ITEM_CATEGORIES[value]?.vatRate ?? 20;
      if (!items[index].description || items[index].description === 'Konaklama Bedeli') {
        items[index].description = value === 'accommodation' ? 'Konaklama Bedeli' : '';
      }
    }
    if (field === 'quantity' || field === 'unit_price' || field === 'vat_rate' || field === 'category') {
      const totals = calculateInvoiceItemTotals(items[index]);
      items[index].vat_amount = totals.vat;
      items[index].total = totals.total;
    }
    setNewInvoice({
      ...newInvoice,
      items
    });
  };
  const addInvoiceItem = () => {
    setNewInvoice({
      ...newInvoice,
      items: [...newInvoice.items, createInvoiceItem('other')]
    });
  };
  const addAdditionalTax = () => {
    if (currentItemIndex === null) return;
    const items = [...newInvoice.items];
    const item = items[currentItemIndex];
    let calculatedAmount = 0;
    const subtotal = calculateInvoiceItemTotals(item).subtotal;
    if (newAdditionalTax.tax_type === 'withholding' && newAdditionalTax.withholding_rate) {
      const rateParts = newAdditionalTax.withholding_rate.split('/');
      const ratePercent = parseInt(rateParts[0]) / parseInt(rateParts[1]) * 100;
      calculatedAmount = roundMoney(item.vat_amount * (ratePercent / 100));
    } else if (newAdditionalTax.is_percentage) {
      const rate = parseTaxRate(newAdditionalTax.rate);
      if (!Number.isFinite(rate) || rate < 0) {
        toast.error('Vergi oranını virgül veya nokta ile doğru girin.');
        return;
      }
      calculatedAmount = roundMoney(subtotal * (rate / 100));
    } else {
      const amount = parseMoney(newAdditionalTax.amount);
      if (!Number.isFinite(amount) || amount < 0) {
        toast.error('Vergi tutarını virgül veya nokta ile doğru girin.');
        return;
      }
      calculatedAmount = roundMoney(amount);
    }
    if (!item.additional_taxes) item.additional_taxes = [];
    item.additional_taxes.push({
      ...newAdditionalTax,
      rate: newAdditionalTax.is_percentage ? parseTaxRate(newAdditionalTax.rate) : 0,
      amount: newAdditionalTax.is_percentage ? 0 : parseMoney(newAdditionalTax.amount),
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
      const dueDate = new FormData(e.currentTarget).get('due_date');
      const payload = withSubmittedDueDate(newInvoice, dueDate);
      const exchangeRate = payload.currency === tenantCurrency ? 1 : parseExchangeRate(payload.exchange_rate);
      if (!Number.isFinite(exchangeRate) || exchangeRate <= 0) throw new Error('Muhasebe döviz kuru virgül veya nokta ile doğru girilmelidir.');
      payload.exchange_rate = exchangeRate;
      payload.items = payload.items.map((item) => {
        const quantity = parseQuantity(item.quantity);
        const unitPrice = parseMoney(item.unit_price);
        const vatRate = parseTaxRate(item.vat_rate);
        if (!Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(unitPrice) || unitPrice < 0 || !Number.isFinite(vatRate) || vatRate < 0) {
          throw new Error('Fatura kalemlerinde adet, birim fiyat ve KDV oranını doğru girin.');
        }
        const totals = calculateFinancialLine({ unitAmount: unitPrice, quantity, vatRate });
        return { ...item, quantity, unit_price: unitPrice, vat_rate: vatRate, vat_amount: totals.vat, total: totals.total };
      });
      const response = await createAccountingInvoice(payload);
      if (!response.data?.id) throw new Error('Fatura kaydı doğrulanamadı.');
      toast.success('Fatura oluşturuldu');
      if (onCreated) onCreated(); else onClose();
    } catch (error) {
      toast.error(error.response?.data?.detail || error.message || 'Fatura oluşturulamadı');
    }
  };
  const invoiceSubtotal = newInvoice.items.reduce((sum, item) => sum + calculateInvoiceItemTotals(item).subtotal, 0);
  const invoiceTotalVAT = newInvoice.items.reduce((sum, item) => sum + calculateInvoiceItemTotals(item).vat, 0);
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
          const subtotal = calculateInvoiceItemTotals(item).subtotal;
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
  const selectedCurrency = newInvoice.currency || tenantCurrency || 'TRY';
  const isForeignCurrency = selectedCurrency !== tenantCurrency;
  const selectedExchangeRate = parseExchangeRate(newInvoice.exchange_rate);
  const formatInvoiceMoney = value => formatCurrency(value, selectedCurrency, { decimals: 2 });
  const accountingEquivalent = Number.isFinite(selectedExchangeRate) && selectedExchangeRate > 0
    ? calculateFinancialLine({ unitAmount: invoiceTotal, quantity: 1, exchangeRate: selectedExchangeRate }).accountingTotal
    : null;
  return <>
      <Dialog open={open} onOpenChange={o => !o && onClose()}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('invoice.createInvoice')}</DialogTitle>
            <DialogDescription>{t('invoice.subtitle')}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateInvoice} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
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
                <Label>Fatura Para Birimi *</Label>
                <Select value={selectedCurrency} onValueChange={currency => setNewInvoice({
                  ...newInvoice,
                  currency,
                  exchange_rate: currency === tenantCurrency ? 1 : '',
                })}>
                  <SelectTrigger data-testid="invoice-currency-select" aria-label="Fatura para birimi">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SUPPORTED_INVOICE_CURRENCIES.map(currency => (
                      <SelectItem key={currency} value={currency}>{currency}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="mt-1 text-xs text-slate-500">Tüm kalemler ve vergiler bu para biriminde kaydedilir.</p>
              </div>
              <div>
                <Label>{t('invoice.customerName')} *</Label>
                <Input value={newInvoice.customer_name} onChange={e => setNewInvoice({
                ...newInvoice,
                customer_name: e.target.value
              })} required />
              </div>
            </div>

            {isForeignCurrency && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                <Label htmlFor="invoice-exchange-rate">Muhasebe Döviz Kuru *</Label>
                <div className="mt-2 flex items-center gap-2">
                  <span className="whitespace-nowrap text-sm text-blue-900">1 {selectedCurrency} =</span>
                  <Input
                    id="invoice-exchange-rate"
                    data-testid="invoice-exchange-rate"
                    type="text"
                    inputMode="decimal"
                    value={newInvoice.exchange_rate}
                    onChange={e => setNewInvoice({ ...newInvoice, exchange_rate: e.target.value })}
                    required
                  />
                  <span className="text-sm font-medium text-blue-900">{tenantCurrency}</span>
                </div>
                <p className="mt-2 text-xs text-blue-800">Fatura tutarı değişmez; bu kur yalnızca muhasebe karşılığını kaydeder.</p>
              </div>
            )}

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
              <p className="mb-3 text-xs text-slate-500">
                KDV her satırın hizmet türüne göre uygulanır: konaklama ile yiyecek/alkolsüz içecek %10; alkollü içecek ve genel oranlı hizmetler %20. Konaklama vergisi KDV matrahına eklenmez.
              </p>
              <div className="space-y-3">
                {newInvoice.items.map((item, index) => <div key={item.id || index} className="border rounded-lg p-3 space-y-2">
                    <div className="grid grid-cols-1 md:grid-cols-7 gap-2 items-center">
                      <Select value={item.category || 'other'} onValueChange={v => calculateInvoiceItem(index, 'category', v)}>
                        <SelectTrigger aria-label="Hizmet türü"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {Object.entries(INVOICE_ITEM_CATEGORIES).map(([value, option]) => (
                            <SelectItem key={value} value={value}>{option.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Input placeholder={t('invoice.description')} value={item.description} onChange={e => calculateInvoiceItem(index, 'description', e.target.value)} required />
                      <Input type="text" inputMode="decimal" placeholder={t('invoice.qty')} value={item.quantity} onChange={e => calculateInvoiceItem(index, 'quantity', e.target.value)} required />
                      <Input type="text" inputMode="decimal" placeholder={t('invoice.price')} value={item.unit_price} onChange={e => calculateInvoiceItem(index, 'unit_price', e.target.value)} required />
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
                      <Input type="text" placeholder={t('invoice.total')} value={calculateInvoiceItemTotals(item).total.toFixed(2)} readOnly />
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
                              {tax.tax_name}: {tax.is_percentage ? `${tax.rate}%` : formatInvoiceMoney(tax.amount)}
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
                  <span className="font-medium">{formatInvoiceMoney(invoiceSubtotal)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">{t('invoice.totalVAT')}:</span>
                  <span className="font-medium">{formatInvoiceMoney(invoiceTotalVAT)}</span>
                </div>
                {invoiceAdditionalTaxes > 0 && <div className="flex justify-between">
                    <span className="text-gray-600">{t('invoice.additionalTaxes')}:</span>
                    <span className="font-medium">{formatInvoiceMoney(invoiceAdditionalTaxes)}</span>
                  </div>}
                {invoiceVATWithholding > 0 && <>
                    <div className="flex justify-between text-red-600">
                      <span>{t('invoice.vatWithholding')}:</span>
                      <span className="font-medium">-{formatInvoiceMoney(invoiceVATWithholding)}</span>
                    </div>
                    <div className="flex justify-between text-red-600">
                      <span>{t('invoice.totalWithholding')}:</span>
                      <span className="font-medium">-{formatInvoiceMoney(invoiceVATWithholding)}</span>
                    </div>
                  </>}
                <div className="flex justify-between text-lg font-bold border-t pt-2">
                  <span>{t('invoice.grandTotal')}:</span>
                  <span>{formatInvoiceMoney(invoiceTotal)}</span>
                </div>
                {isForeignCurrency && accountingEquivalent !== null && (
                  <div className="flex justify-between text-sm text-slate-500" data-testid="invoice-accounting-equivalent">
                    <span>Muhasebe karşılığı:</span>
                    <span>{formatCurrency(accountingEquivalent, tenantCurrency, { decimals: 2 })}</span>
                  </div>
                )}
              </div>
            </div>

            <div>
              <Label>{t('invoice.dueDate')}</Label>
              <Input name="due_date" type="date" value={newInvoice.due_date} onChange={e => setNewInvoice({
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
                    <Input type="text" inputMode="decimal" value={newAdditionalTax.rate} onChange={e => setNewAdditionalTax({
                ...newAdditionalTax,
                rate: e.target.value
              })} />
                  </div> : <div>
                    <Label>{t('invoice.taxAmount')}</Label>
                    <Input type="text" inputMode="decimal" value={newAdditionalTax.amount} onChange={e => setNewAdditionalTax({
                ...newAdditionalTax,
                amount: e.target.value
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
