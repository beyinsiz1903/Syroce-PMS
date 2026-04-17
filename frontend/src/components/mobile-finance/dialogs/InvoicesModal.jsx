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

export default function InvoicesModal(props) {
  const { allInvoices, formatCurrency, invoicesModalOpen, setInvoicesModalOpen } = props;
  return (
    <Dialog open={invoicesModalOpen} onOpenChange={setInvoicesModalOpen}>
      <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Faturalar ({allInvoices.length})</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          {allInvoices.length === 0 ? (
            <p className="text-center text-gray-500 py-8">Henüz fatura yok</p>
          ) : (
            allInvoices.map((invoice) => (
              <div key={invoice.id} className="p-3 bg-gray-50 rounded-lg border">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="font-bold text-gray-900">Fatura #{invoice.invoice_number}</p>
                    <p className="text-sm text-gray-600">{invoice.guest_name || invoice.company_name}</p>
                  </div>
                  <Badge className={{
                    'paid': 'bg-green-500',
                    'pending': 'bg-yellow-500',
                    'overdue': 'bg-red-500',
                    'cancelled': 'bg-gray-500'
                  }[invoice.status] || 'bg-gray-500'}>
                    {invoice.status}
                  </Badge>
                </div>
                <div className="text-sm text-gray-600">
                  <p>Tutar: {formatCurrency(invoice.total_amount)}</p>
                  <p>Tarih: {invoice.invoice_date ? new Date(invoice.invoice_date).toLocaleDateString('tr-TR') : 'N/A'}</p>
                  {invoice.due_date && (
                    <p>Vade: {new Date(invoice.due_date).toLocaleDateString('tr-TR')}</p>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
