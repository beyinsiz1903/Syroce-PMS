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
import { Wallet, CreditCard, TrendingUp, AlertTriangle, FileText, DollarSign, ArrowDownCircle, ArrowUpCircle, Receipt, Banknote, Clock, CheckCircle, XCircle, Calendar, Filter, Download, Upload, Eye, Search, Plus, Minus, RefreshCw, ChevronRight, ChevronDown, BarChart3, PieChart, Activity, Users, Building, Building2, Briefcase, ShoppingCart, Coffee, Utensils, Bed, Home } from 'lucide-react';

export default function CashFlowModal(props) {
  const { cashFlowData, cashFlowModalOpen, formatCurrency, setCashFlowModalOpen, t } = props;
  return (
    <Dialog open={cashFlowModalOpen} onOpenChange={setCashFlowModalOpen}>
      <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <Wallet className="w-5 h-5 text-cyan-600" />
            <span>Nakit Akışı Detayı</span>
          </DialogTitle>
        </DialogHeader>
    
        {cashFlowData ? (
          <div className="space-y-4">
            {/* Today's Summary */}
            <Card className="bg-gradient-to-r from-cyan-50 to-blue-50">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Bugün ({cashFlowData.today?.date})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-3 bg-green-50 rounded-lg">
                    <p className="text-xs text-green-600">Nakit Girişi</p>
                    <p className="text-lg font-bold text-green-700">
                      {formatCurrency(cashFlowData.today?.cash_inflow || 0)}
                    </p>
                    <p className="text-xs text-gray-500">{cashFlowData.today?.inflow_count} işlem</p>
                  </div>
                  <div className="p-3 bg-red-50 rounded-lg">
                    <p className="text-xs text-red-600">Nakit Çıkışı</p>
                    <p className="text-lg font-bold text-red-700">
                      {formatCurrency(cashFlowData.today?.cash_outflow || 0)}
                    </p>
                    <p className="text-xs text-gray-500">{cashFlowData.today?.outflow_count} işlem</p>
                  </div>
                </div>
                <div className="p-3 bg-cyan-100 rounded-lg border-2 border-cyan-300">
                  <p className="text-sm text-cyan-700 font-medium">Net Nakit Akışı</p>
                  <p className={`text-2xl font-bold ${
                    (cashFlowData.today?.net_flow || 0) >= 0 ? 'text-green-700' : 'text-red-700'
                  }`}>
                    {formatCurrency(cashFlowData.today?.net_flow || 0)}
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Weekly Plan */}
            {cashFlowData.weekly_plan && cashFlowData.weekly_plan.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center">
                    <Calendar className="w-4 h-4 mr-2" />
                    7 Günlük Tahsilat/Ödeme Planı
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {cashFlowData.weekly_plan.map((day) => (
                    <div key={day.date} className="p-2 border rounded-lg">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-sm font-medium text-gray-700">{day.day_name}</span>
                        <span className="text-xs text-gray-500">
                          {new Date(day.date).toLocaleDateString('tr-TR')}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="text-green-700">
                          <span className="font-medium">Tahsilat: </span>
                          {formatCurrency(day.expected_collections)}
                        </div>
                        <div className="text-orange-700">
                          <span className="font-medium">Ödeme: </span>
                          {formatCurrency(day.expected_payments)}
                        </div>
                      </div>
                      {day.checkout_count > 0 && (
                        <p className="text-xs text-gray-500 mt-1">
                          {day.checkout_count} çıkış bekleniyor
                        </p>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Bank Balances */}
            {cashFlowData.bank_balances && cashFlowData.bank_balances.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center">
                    <Building2 className="w-4 h-4 mr-2" />
                    Banka Bakiyeleri
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {cashFlowData.bank_balances.map((bank, idx) => (
                    <div key={idx} className="flex justify-between p-2 bg-gray-50 rounded-lg">
                      <div>
                        <p className="text-sm font-semibold">{bank.bank_name}</p>
                        <p className="text-xs text-gray-500">****{bank.account_number}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-bold text-indigo-700">{formatCurrency(bank.current_balance)}</p>
                        <p className="text-xs text-gray-500">{bank.currency}</p>
                      </div>
                    </div>
                  ))}
                  <div className="mt-2 pt-2 border-t">
                    <div className="flex justify-between">
                      <span className="font-semibold">Toplam (TRY):</span>
                      <span className="font-bold text-lg text-indigo-700">
                        {formatCurrency(cashFlowData.total_bank_balance_try || 0)}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        ) : (
          <div className="text-center py-8">
            <Wallet className="w-12 h-12 mx-auto text-gray-300 mb-2" />
            <p className="text-gray-500">Nakit akışı verisi yükleniyor...</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
