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

export default function FolioExtractModal(props) {
  const { folioExtractModalOpen, formatCurrency, selectedFolioExtract, setFolioExtractModalOpen, t } = props;
  return (
    <Dialog open={folioExtractModalOpen} onOpenChange={setFolioExtractModalOpen}>
      <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <FileText className="w-5 h-5 text-indigo-600" />
            <span>Folio Ekstresi</span>
          </DialogTitle>
        </DialogHeader>
    
        {selectedFolioExtract ? (
          <div className="space-y-4">
            {/* Folio Info */}
            <Card className="bg-gradient-to-r from-indigo-50 to-indigo-50">
              <CardContent className="p-4">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-gray-600">Folio No:</p>
                    <p className="font-bold">{selectedFolioExtract.folio?.folio_number}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Durum:</p>
                    <Badge>{selectedFolioExtract.folio?.status}</Badge>
                  </div>
                  <div>
                    <p className="text-gray-600">Misafir:</p>
                    <p className="font-bold">{selectedFolioExtract.guest?.name}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Oda:</p>
                    <p className="font-bold">{selectedFolioExtract.booking?.room_number}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Giriş:</p>
                    <p>{selectedFolioExtract.booking?.check_in && new Date(selectedFolioExtract.booking.check_in).toLocaleDateString('tr-TR')}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Çıkış:</p>
                    <p>{selectedFolioExtract.booking?.check_out && new Date(selectedFolioExtract.booking.check_out).toLocaleDateString('tr-TR')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Charges */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Harcamalar ({selectedFolioExtract.charges?.length || 0})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {selectedFolioExtract.charges && selectedFolioExtract.charges.length > 0 ? (
                  selectedFolioExtract.charges.map((charge) => (
                    <div key={charge.id} className="p-2 bg-gray-50 rounded border text-sm">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-semibold">{charge.description}</p>
                          <p className="text-xs text-gray-500">
                            {charge.date && new Date(charge.date).toLocaleDateString('tr-TR')} - {charge.category}
                          </p>
                          <p className="text-xs text-gray-500">
                            {charge.quantity}x {formatCurrency(charge.unit_price)}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="font-bold">{formatCurrency(charge.total)}</p>
                          {charge.tax_amount > 0 && (
                            <p className="text-xs text-gray-500">KDV: {formatCurrency(charge.tax_amount)}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-center text-gray-500 py-4">Harcama yok</p>
                )}
              </CardContent>
            </Card>

            {/* Payments */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Ödemeler ({selectedFolioExtract.payments?.length || 0})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {selectedFolioExtract.payments && selectedFolioExtract.payments.length > 0 ? (
                  selectedFolioExtract.payments.map((payment) => (
                    <div key={payment.id} className="p-2 bg-green-50 rounded border border-green-200 text-sm">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-semibold text-green-700">Ödeme</p>
                          <p className="text-xs text-gray-600">
                            {payment.date && new Date(payment.date).toLocaleDateString('tr-TR')} - {payment.payment_method}
                          </p>
                          {payment.notes && (
                            <p className="text-xs text-gray-500 italic">{payment.notes}</p>
                          )}
                        </div>
                        <p className="font-bold text-green-700">{formatCurrency(payment.amount)}</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-center text-gray-500 py-4">Ödeme yok</p>
                )}
              </CardContent>
            </Card>

            {/* Summary */}
            <Card className="bg-gradient-to-r from-blue-50 to-indigo-50">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{t("common.summary")}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-700">Toplam Harcama:</span>
                    <span className="font-bold">{formatCurrency(selectedFolioExtract.summary?.total_charges || 0)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-700">Toplam Ödeme:</span>
                    <span className="font-bold text-green-700">{formatCurrency(selectedFolioExtract.summary?.total_payments || 0)}</span>
                  </div>
                  <div className="flex justify-between pt-2 border-t-2 border-gray-300">
                    <span className="font-bold text-lg text-gray-900">Kalan Bakiye:</span>
                    <span className={`font-bold text-xl ${
                      (selectedFolioExtract.summary?.current_balance || 0) > 0 ? 'text-red-700' : 'text-green-700'
                    }`}>
                      {formatCurrency(selectedFolioExtract.summary?.current_balance || 0)}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="text-center py-8">
            <FileText className="w-12 h-12 mx-auto text-gray-300 mb-2" />
            <p className="text-gray-500">Ekstre yükleniyor...</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
