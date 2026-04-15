import { useState } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export const ExpenseDialog = ({ open, onClose, suppliers }) => {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    category: 'supplies', description: '', amount: 0, vat_rate: 18,
    date: new Date().toISOString().split('T')[0], supplier_id: '', payment_method: 'cash', notes: ''
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/expenses', null, { params: form });
      toast.success('Expense recorded');
      onClose();
      setForm({ category: 'supplies', description: '', amount: 0, vat_rate: 18, date: new Date().toISOString().split('T')[0], supplier_id: '', payment_method: 'cash', notes: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create expense');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('invoice.recordExpense', 'Record Expense')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label>{t('common.category', 'Category')}</Label>
            <Select value={form.category} onValueChange={(v) => setForm({...form, category: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="salaries">{t('invoice.salaries', 'Salaries')}</SelectItem>
                <SelectItem value="utilities">{t('invoice.utilities', 'Utilities')}</SelectItem>
                <SelectItem value="supplies">{t('invoice.supplies', 'Supplies')}</SelectItem>
                <SelectItem value="maintenance">{t('invoice.maintenance', 'Maintenance')}</SelectItem>
                <SelectItem value="marketing">{t('invoice.marketing', 'Marketing')}</SelectItem>
                <SelectItem value="rent">{t('invoice.rent', 'Rent')}</SelectItem>
                <SelectItem value="insurance">{t('invoice.insurance', 'Insurance')}</SelectItem>
                <SelectItem value="taxes">{t('invoice.taxes', 'Taxes')}</SelectItem>
                <SelectItem value="other">{t('common.other', 'Other')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>{t('common.description', 'Description')}</Label>
            <Input value={form.description} onChange={(e) => setForm({...form, description: e.target.value})} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>{t('invoice.amountExclVAT', 'Amount (excl. VAT)')}</Label>
              <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({...form, amount: parseFloat(e.target.value)})} required />
            </div>
            <div>
              <Label>{t('invoice.vatRate', 'VAT Rate %')}</Label>
              <Select value={form.vat_rate.toString()} onValueChange={(v) => setForm({...form, vat_rate: parseFloat(v)})}>
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
            </div>
          </div>
          <div>
            <Label>{t('common.date', 'Date')}</Label>
            <Input type="date" value={form.date} onChange={(e) => setForm({...form, date: e.target.value})} required />
          </div>
          <div>
            <Label>{t('invoice.supplierOptional', 'Supplier (Optional)')}</Label>
            <Select value={form.supplier_id} onValueChange={(v) => setForm({...form, supplier_id: v})}>
              <SelectTrigger><SelectValue placeholder={t('invoice.selectSupplier', 'Select supplier')} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('common.none', 'None')}</SelectItem>
                {suppliers.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>{t('invoice.paymentMethod', 'Payment Method')}</Label>
            <Select value={form.payment_method} onValueChange={(v) => setForm({...form, payment_method: v})}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cash">{t('pms.cash', 'Cash')}</SelectItem>
                <SelectItem value="card">{t('pms.creditCard', 'Card')}</SelectItem>
                <SelectItem value="bank_transfer">{t('pms.bankTransfer', 'Bank Transfer')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="pt-4 border-t">
            <div className="flex justify-between text-lg font-bold">
              <span>{t('invoice.totalInclVAT', 'Total (incl. VAT)')}:</span>
              <span>₺{(form.amount * (1 + form.vat_rate / 100)).toFixed(2)}</span>
            </div>
          </div>
          <Button type="submit" className="w-full">{t('invoice.recordExpense', 'Record Expense')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export const SupplierDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    name: '', tax_office: '', tax_number: '', email: '', phone: '', address: '', category: 'general'
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/suppliers', null, { params: form });
      toast.success('Supplier added');
      onClose();
      setForm({ name: '', tax_office: '', tax_number: '', email: '', phone: '', address: '', category: 'general' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add supplier');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('invoice.addSupplier', 'Add Supplier')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label>{t('common.name', 'Name')} *</Label>
            <Input value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>{t('invoice.taxOffice', 'Tax Office')}</Label>
              <Input value={form.tax_office} onChange={(e) => setForm({...form, tax_office: e.target.value})} />
            </div>
            <div>
              <Label>{t('invoice.taxNumber', 'Tax No')}</Label>
              <Input value={form.tax_number} onChange={(e) => setForm({...form, tax_number: e.target.value})} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>{t('common.email', 'Email')}</Label>
              <Input type="email" value={form.email} onChange={(e) => setForm({...form, email: e.target.value})} />
            </div>
            <div>
              <Label>{t('common.phone', 'Phone')}</Label>
              <Input value={form.phone} onChange={(e) => setForm({...form, phone: e.target.value})} />
            </div>
          </div>
          <div>
            <Label>{t('common.address', 'Address')}</Label>
            <Textarea value={form.address} onChange={(e) => setForm({...form, address: e.target.value})} rows={2} />
          </div>
          <Button type="submit" className="w-full">{t('invoice.addSupplier', 'Add Supplier')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export const BankAccountDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    name: '', bank_name: '', account_number: '', iban: '', currency: 'TRY', balance: 0
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/bank-accounts', null, { params: form });
      toast.success('Bank account added');
      onClose();
      setForm({ name: '', bank_name: '', account_number: '', iban: '', currency: 'TRY', balance: 0 });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add bank account');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('invoice.addBankAccount', 'Add Bank Account')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label>{t('invoice.accountName', 'Account Name')} *</Label>
            <Input value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} required />
          </div>
          <div>
            <Label>{t('invoice.bankName', 'Bank Name')} *</Label>
            <Input value={form.bank_name} onChange={(e) => setForm({...form, bank_name: e.target.value})} required />
          </div>
          <div>
            <Label>{t('invoice.accountNumber', 'Account No')} *</Label>
            <Input value={form.account_number} onChange={(e) => setForm({...form, account_number: e.target.value})} required />
          </div>
          <div>
            <Label>IBAN</Label>
            <Input value={form.iban} onChange={(e) => setForm({...form, iban: e.target.value})} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>{t('invoice.currency', 'Currency')}</Label>
              <Select value={form.currency} onValueChange={(v) => setForm({...form, currency: v})}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="USD">USD</SelectItem>
                  <SelectItem value="EUR">EUR</SelectItem>
                  <SelectItem value="TRY">TRY</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('invoice.openingBalance', 'Opening Balance')}</Label>
              <Input type="number" step="0.01" value={form.balance} onChange={(e) => setForm({...form, balance: parseFloat(e.target.value)})} />
            </div>
          </div>
          <Button type="submit" className="w-full">{t('invoice.addBankAccount', 'Add Bank Account')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export const InventoryDialog = ({ open, onClose }) => {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    name: '', category: 'supplies', unit: 'piece', quantity: 0, unit_cost: 0, reorder_level: 10, sku: ''
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/inventory', null, { params: form });
      toast.success('Inventory item added');
      onClose();
      setForm({ name: '', category: 'supplies', unit: 'piece', quantity: 0, unit_cost: 0, reorder_level: 10, sku: '' });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add inventory item');
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('invoice.addInventoryItem', 'Add Inventory Item')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label>{t('invoice.itemName', 'Item Name')} *</Label>
            <Input value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>{t('common.category', 'Category')}</Label>
              <Input value={form.category} onChange={(e) => setForm({...form, category: e.target.value})} required />
            </div>
            <div>
              <Label>SKU</Label>
              <Input value={form.sku} onChange={(e) => setForm({...form, sku: e.target.value})} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>{t('common.quantity', 'Quantity')}</Label>
              <Input type="number" step="0.01" value={form.quantity} onChange={(e) => setForm({...form, quantity: parseFloat(e.target.value)})} required />
            </div>
            <div>
              <Label>{t('invoice.unit', 'Unit')}</Label>
              <Input value={form.unit} onChange={(e) => setForm({...form, unit: e.target.value})} required />
            </div>
            <div>
              <Label>{t('invoice.unitPrice', 'Unit Price')}</Label>
              <Input type="number" step="0.01" value={form.unit_cost} onChange={(e) => setForm({...form, unit_cost: parseFloat(e.target.value)})} required />
            </div>
          </div>
          <div>
            <Label>{t('invoice.reorderLevel', 'Reorder Level')}</Label>
            <Input type="number" value={form.reorder_level} onChange={(e) => setForm({...form, reorder_level: parseFloat(e.target.value)})} />
          </div>
          <Button type="submit" className="w-full">{t('invoice.addItem', 'Add Item')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};
