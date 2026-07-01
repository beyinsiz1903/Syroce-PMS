import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Wallet, CreditCard, TrendingUp, AlertTriangle, FileText, DollarSign, ArrowDownCircle, ArrowUpCircle, Receipt, Banknote, Clock, CheckCircle, XCircle, Calendar, Filter, Download, Upload, Eye, Search, Plus, Minus, RefreshCw, ChevronRight, ChevronDown, BarChart3, PieChart, Activity, Users, Building, Briefcase, ShoppingCart, Coffee, Utensils, Bed, Home } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function PaymentModal(props) {
  const { t } = useTranslation();
  const { formatCurrency, handleRecordPayment, paymentModalOpen, selectedFolio, setPaymentModalOpen } = props;
  return (
    <Dialog open={paymentModalOpen} onOpenChange={setPaymentModalOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('cm.components_mobilefinance_dialogs_PaymentModal.tahsilat_kaydi')}</DialogTitle>
        </DialogHeader>
        {selectedFolio && (
          <form onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            handleRecordPayment({
              folio_id: selectedFolio.folio_id,
              amount: parseFloat(formData.get('amount')),
              payment_method: formData.get('payment_method'),
              notes: formData.get('notes')
            });
          }}>
            <div className="space-y-4">
              <div>
                <Label>{t('cm.components_mobilefinance_dialogs_PaymentModal.misafir')}</Label>
                <Input value={selectedFolio.guest_name} disabled />
              </div>
              <div>
                <Label>{t('cm.components_mobilefinance_dialogs_PaymentModal.kalan_bakiye')}</Label>
                <Input value={formatCurrency(selectedFolio.balance)} disabled />
              </div>
              <div>
                <Label>{t('cm.components_mobilefinance_dialogs_PaymentModal.tahsilat_tutari')}</Label>
                <Input 
                  name="amount" 
                  type="number" 
                  step="0.01" 
                  max={selectedFolio.balance}
                  required 
                />
              </div>
              <div>
                <Label>{t('cm.components_mobilefinance_dialogs_PaymentModal.odeme_yontemi')}</Label>
                <select name="payment_method" className="w-full p-2 border rounded" required>
                  <option value="cash">Nakit</option>
                  <option value="card">{t('cm.components_mobilefinance_dialogs_PaymentModal.kredi_karti')}</option>
                  <option value="transfer">Havale</option>
                  <option value="check">{t('cm.components_mobilefinance_dialogs_PaymentModal.cek')}</option>
                </select>
              </div>
              <div>
                <Label>Notlar</Label>
                <Textarea name="notes" rows={3} />
              </div>
              <Button type="submit" className="w-full bg-green-600 hover:bg-green-700">
                {t('cm.components_mobilefinance_dialogs_PaymentModal.tahsilat_kaydet')}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
