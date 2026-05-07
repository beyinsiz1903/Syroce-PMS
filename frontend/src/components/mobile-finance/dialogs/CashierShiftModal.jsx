import React from 'react';
import { toast } from 'sonner';
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
import { Wallet, CreditCard, TrendingUp, AlertTriangle, FileText, DollarSign, ArrowDownCircle, ArrowUpCircle, Receipt, Banknote, Clock, CheckCircle, XCircle, Calendar, Filter, Download, Upload, Eye, Search, Plus, Minus, RefreshCw, ChevronRight, ChevronDown, BarChart3, PieChart, Activity, Users, Building, User, Briefcase, ShoppingCart, Coffee, Utensils, Bed, Home } from 'lucide-react';

export default function CashierShiftModal(props) {
  const { cashierShiftModalOpen, formatCurrency, setCashierShiftModalOpen, shiftReportData, user } = props;
  return (
    <Dialog open={cashierShiftModalOpen} onOpenChange={setCashierShiftModalOpen}>
      <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <User className="w-5 h-5 text-indigo-600" />
            <span>Kasiyer Vardiya Raporu</span>
          </DialogTitle>
        </DialogHeader>
    
        {shiftReportData ? (
          <div className="space-y-4">
            {/* Shift Info */}
            <Card className="bg-gradient-to-r from-indigo-50 to-indigo-50">
              <CardContent className="p-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-gray-600">Kasiyer</p>
                    <p className="font-bold text-gray-900">{shiftReportData.cashier_name || user?.name || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600">Vardiya</p>
                    <p className="font-bold text-gray-900">{shiftReportData.shift_name || 'Gündüz'}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600">Başlangıç</p>
                    <p className="text-sm font-medium">
                      <Clock className="w-3 h-3 inline mr-1" />
                      {shiftReportData.shift_start ? new Date(shiftReportData.shift_start).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '08:00'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600">Bitiş</p>
                    <p className="text-sm font-medium">
                      <Clock className="w-3 h-3 inline mr-1" />
                      {shiftReportData.shift_end ? new Date(shiftReportData.shift_end).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : 'Devam Ediyor'}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Opening/Closing Balance */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Kasa Durumu</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between p-3 bg-blue-50 rounded">
                  <span className="text-gray-700">Açılış Bakiyesi:</span>
                  <span className="font-bold text-blue-700">
                    {formatCurrency(shiftReportData.opening_balance || 0)}
                  </span>
                </div>
                <div className="flex justify-between p-3 bg-green-50 rounded">
                  <span className="text-gray-700">Toplam Tahsilat:</span>
                  <span className="font-bold text-green-700">
                    {formatCurrency(shiftReportData.total_collected || 0)}
                  </span>
                </div>
                <div className="flex justify-between p-3 bg-red-50 rounded">
                  <span className="text-gray-700">Ödemeler:</span>
                  <span className="font-bold text-red-700">
                    -{formatCurrency(shiftReportData.total_paid_out || 0)}
                  </span>
                </div>
                <div className="flex justify-between p-4 bg-indigo-100 rounded-lg border-2 border-indigo-300">
                  <span className="font-bold text-indigo-900">Beklenen Bakiye:</span>
                  <span className="font-bold text-2xl text-indigo-700">
                    {formatCurrency(shiftReportData.expected_balance || 0)}
                  </span>
                </div>
            
                {shiftReportData.actual_balance !== undefined && (
                  <>
                    <div className="flex justify-between p-3 bg-yellow-50 rounded mt-2">
                      <span className="text-gray-700">Fiili Bakiye:</span>
                      <span className="font-bold">
                        {formatCurrency(shiftReportData.actual_balance)}
                      </span>
                    </div>
                    <div className={`flex justify-between p-3 rounded ${
                      Math.abs(shiftReportData.variance || 0) < 0.01 ? 'bg-green-50' : 'bg-red-50'
                    }`}>
                      <span className="text-gray-700">Fark:</span>
                      <span className={`font-bold ${
                        Math.abs(shiftReportData.variance || 0) < 0.01 ? 'text-green-700' : 'text-red-700'
                      }`}>
                        {shiftReportData.variance >= 0 ? '+' : ''}{formatCurrency(shiftReportData.variance || 0)}
                      </span>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Transaction Summary */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">İşlem Özeti</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  <div className="text-center p-3 bg-green-50 rounded">
                    <p className="text-xs text-green-600">Toplam İşlem</p>
                    <p className="text-2xl font-bold text-green-900">
                      {shiftReportData.transaction_count || 0}
                    </p>
                  </div>
                  <div className="text-center p-3 bg-blue-50 rounded">
                    <p className="text-xs text-blue-600">Check-in</p>
                    <p className="text-2xl font-bold text-blue-900">
                      {shiftReportData.checkin_count || 0}
                    </p>
                  </div>
                  <div className="text-center p-3 bg-indigo-50 rounded">
                    <p className="text-xs text-indigo-600">Check-out</p>
                    <p className="text-2xl font-bold text-indigo-900">
                      {shiftReportData.checkout_count || 0}
                    </p>
                  </div>
                  <div className="text-center p-3 bg-amber-50 rounded">
                    <p className="text-xs text-amber-600">Ort. İşlem</p>
                    <p className="text-2xl font-bold text-amber-900">
                      {formatCurrency(shiftReportData.average_transaction || 0)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Payment Methods Breakdown */}
            {shiftReportData.payment_methods && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Ödeme Yöntemleri</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {Object.entries(shiftReportData.payment_methods).map(([method, data]) => (
                    <div key={method} className="p-3 bg-gray-50 rounded border">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <p className="font-bold text-gray-900 capitalize">
                            {method === 'cash' ? 'Nakit' : 
                             method === 'card' ? 'Kredi Kartı' :
                             method === 'transfer' ? 'Havale' :
                             method === 'check' ? 'Çek' : method}
                          </p>
                          <p className="text-xs text-gray-500">
                            {data.count || 0} işlem
                          </p>
                        </div>
                        <p className="font-bold text-lg text-indigo-700">
                          {formatCurrency(data.amount || 0)}
                        </p>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Shift Notes */}
            {shiftReportData.notes && (
              <Card className="bg-yellow-50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Notlar</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-gray-700">{shiftReportData.notes}</p>
                </CardContent>
              </Card>
            )}

            <Button 
              className="w-full bg-indigo-600 hover:bg-indigo-700"
              onClick={() => toast.success('Vardiya raporu kapatıldı!')}
            >
              <CheckCircle className="w-4 h-4 mr-2" />
              Vardiya Kapat
            </Button>
          </div>
        ) : (
          <div className="text-center py-8">
            <User className="w-12 h-12 mx-auto text-gray-300 mb-2" />
            <p className="text-gray-500">Vardiya raporu yükleniyor...</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
