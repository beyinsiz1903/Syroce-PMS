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

export default function RiskModal(props) {
  const { creditViolations, formatCurrency, getRiskColor, getRiskIcon, loadFolioExtract, overdueAccounts, riskAlerts, riskModalOpen, setRiskModalOpen, suspiciousReceivables, t } = props;
  return (
    <Dialog open={riskModalOpen} onOpenChange={setRiskModalOpen}>
      <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            <span>Risk Yönetimi</span>
          </DialogTitle>
        </DialogHeader>
    
        <Tabs defaultValue="overdue" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="overdue">Vadeli</TabsTrigger>
            <TabsTrigger value="limits">Limitler</TabsTrigger>
            <TabsTrigger value="suspicious">Şüpheli</TabsTrigger>
            <TabsTrigger value="alerts">Uyarılar</TabsTrigger>
          </TabsList>
      
          <TabsContent value="overdue" className="space-y-2">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-gray-900">Vadesi Geçmiş Hesaplar (7+ gün)</h3>
              {overdueAccounts && (
                <Badge className="bg-red-500">
                  {overdueAccounts.summary?.total_count || 0}
                </Badge>
              )}
            </div>
        
            {overdueAccounts && overdueAccounts.overdue_accounts?.length > 0 ? (
              <div className="space-y-2">
                {overdueAccounts.overdue_accounts.map((account) => (
                  <div key={account.folio_id} className={`p-3 rounded-lg border-2 ${getRiskColor(account.risk_level)}`}>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="font-bold">{account.guest_name}</p>
                        <p className="text-sm">Folio: {account.folio_number}</p>
                        <p className="text-sm">Oda: {account.room_number}</p>
                        <p className="text-sm">Çıkış: {new Date(account.checkout_date).toLocaleDateString('tr-TR')}</p>
                        <Badge className={`mt-1 ${
                          account.risk_level === 'suspicious' ? 'bg-gray-900 text-white' :
                          account.risk_level === 'critical' ? 'bg-red-600' :
                          account.risk_level === 'warning' ? 'bg-yellow-500' : 'bg-green-500'
                        }`}>
                          {account.days_overdue} gün gecikmiş
                        </Badge>
                      </div>
                      <div className="text-right">
                        <p className="font-bold text-lg text-red-700">{formatCurrency(account.balance)}</p>
                        <Button
                          size="sm"
                          className="mt-2"
                          onClick={() => loadFolioExtract(account.folio_id)}
                        >
                          <Eye className="w-3 h-3 mr-1" />
                          Ekstre
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
            
                <div className="mt-4 p-3 bg-gray-100 rounded-lg">
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <span className="text-gray-600">Toplam:</span>
                      <span className="font-bold ml-2">{overdueAccounts.summary.total_count}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Tutar:</span>
                      <span className="font-bold ml-2 text-red-700">
                        {formatCurrency(overdueAccounts.summary.total_amount)}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-600">Şüpheli:</span>
                      <span className="font-bold ml-2">{overdueAccounts.summary.suspicious_count}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Kritik:</span>
                      <span className="font-bold ml-2">{overdueAccounts.summary.critical_count}</span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-center text-gray-500 py-8">Vadesi geçmiş hesap yok</p>
            )}
          </TabsContent>
      
          <TabsContent value="limits" className="space-y-2">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-gray-900">Kredi Limiti Aşımları</h3>
              {creditViolations && (
                <Badge className="bg-orange-500">
                  {creditViolations.summary?.total_count || 0}
                </Badge>
              )}
            </div>
        
            {creditViolations && creditViolations.violations?.length > 0 ? (
              <div className="space-y-2">
                {creditViolations.violations.map((violation) => (
                  <div key={violation.company_id} className={`p-3 rounded-lg border-2 ${
                    violation.over_limit_amount > 0 ? 'bg-red-50 border-red-300' : 'bg-yellow-50 border-yellow-300'
                  }`}>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="font-bold text-gray-900">{violation.company_name}</p>
                        <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
                          <div>
                            <p className="text-gray-600">Limit:</p>
                            <p className="font-semibold">{formatCurrency(violation.credit_limit)}</p>
                          </div>
                          <div>
                            <p className="text-gray-600">Borç:</p>
                            <p className="font-semibold text-red-600">{formatCurrency(violation.current_debt)}</p>
                          </div>
                          <div>
                            <p className="text-gray-600">Kullanım:</p>
                            <p className="font-semibold">{violation.utilization_percentage.toFixed(1)}%</p>
                          </div>
                          <div>
                            <p className="text-gray-600">Vade:</p>
                            <p className="font-semibold">{violation.payment_terms_days} gün</p>
                          </div>
                        </div>
                        {violation.over_limit_amount > 0 && (
                          <Badge className="mt-2 bg-red-600">
                            Limit aşımı: {formatCurrency(violation.over_limit_amount)}
                          </Badge>
                        )}
                        {violation.warning && (
                          <Badge className="mt-2 bg-yellow-500">
                            {violation.warning}
                          </Badge>
                        )}
                      </div>
                    </div>
                    {violation.contact_person && (
                      <div className="mt-2 pt-2 border-t text-xs text-gray-600">
                        <p>İletişim: {violation.contact_person}</p>
                        {violation.contact_phone && <p>Tel: {violation.contact_phone}</p>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-gray-500 py-8">Limit aşımı yok</p>
            )}
          </TabsContent>
      
          <TabsContent value="suspicious" className="space-y-2">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-gray-900">Şüpheli Alacaklar</h3>
              {suspiciousReceivables && (
                <Badge className="bg-gray-900 text-white">
                  {suspiciousReceivables.summary?.total_count || 0}
                </Badge>
              )}
            </div>
        
            {suspiciousReceivables && suspiciousReceivables.suspicious_receivables?.length > 0 ? (
              <div className="space-y-2">
                {suspiciousReceivables.suspicious_receivables.map((item) => (
                  <div key={item.folio_id} className="p-3 rounded-lg border-2 bg-gray-50 border-gray-900">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="font-bold text-gray-900">{item.guest_name}</p>
                        <p className="text-sm">Folio: {item.folio_number}</p>
                        <p className="text-sm">Çıkış: {new Date(item.checkout_date).toLocaleDateString('tr-TR')}</p>
                        <Badge className="mt-1 bg-gray-900 text-white">
                          {item.days_overdue} gün gecikmiş
                        </Badge>
                        <p className="text-xs text-gray-600 mt-1">{item.reason}</p>
                        <p className="text-xs text-gray-500">Ödeme sayısı: {item.payment_history_count}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-bold text-lg text-gray-900">{formatCurrency(item.balance)}</p>
                        <Button
                          size="sm"
                          className="mt-2 bg-gray-900"
                          onClick={() => loadFolioExtract(item.folio_id)}
                        >
                          <Eye className="w-3 h-3 mr-1" />
                          Ekstre
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
            
                <div className="mt-4 p-3 bg-gray-900 text-white rounded-lg">
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <span>Toplam:</span>
                      <span className="font-bold ml-2">{suspiciousReceivables.summary.total_count}</span>
                    </div>
                    <div>
                      <span>Tutar:</span>
                      <span className="font-bold ml-2">
                        {formatCurrency(suspiciousReceivables.summary.total_amount)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-center text-gray-500 py-8">Şüpheli alacak yok</p>
            )}
          </TabsContent>
      
          <TabsContent value="alerts" className="space-y-2">
            {riskAlerts && riskAlerts.alerts?.length > 0 ? (
              <div className="space-y-2">
                {riskAlerts.alerts.map((alert) => (
                  <div key={alert.id} className={`p-3 rounded-lg border-2 ${
                    alert.severity === 'critical' ? 'bg-red-50 border-red-300' :
                    alert.severity === 'high' ? 'bg-orange-50 border-orange-300' :
                    alert.severity === 'medium' ? 'bg-yellow-50 border-yellow-300' :
                    'bg-blue-50 border-blue-300'
                  }`}>
                    <div className="flex items-start space-x-2">
                      {getRiskIcon(alert.severity)}
                      <div className="flex-1">
                        <p className="font-bold text-gray-900">{alert.title}</p>
                        <p className="text-sm text-gray-700">{alert.message}</p>
                        {alert.amount && (
                          <p className="text-sm font-bold text-red-600 mt-1">
                            Tutar: {formatCurrency(alert.amount)}
                          </p>
                        )}
                        {alert.action_required && (
                          <Badge className="mt-2 bg-red-600">Aksiyon Gerekli</Badge>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-gray-500 py-8">Uyarı yok</p>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
