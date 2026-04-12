import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ArrowLeft, 
  DollarSign, 
  TrendingUp, 
  Calendar,
  AlertCircle,
  Receipt,
  CreditCard,
  RefreshCw,
  Plus,
  BarChart3,
  User,
  FileText,
  Clock,
  CheckCircle,
  Download,
  FileDown,
  TrendingDown,
  Building2,
  Banknote,
  Filter,
  Eye,
  AlertTriangle,
  XCircle,
  ArrowUpCircle,
  ArrowDownCircle,
  Wallet,
  Home
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MobileFinance = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [dailyCollections, setDailyCollections] = useState(null);
  const [monthlyCollections, setMonthlyCollections] = useState(null);
  const [pendingReceivables, setPendingReceivables] = useState(null);
  const [monthlyCosts, setMonthlyCosts] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [selectedFolio, setSelectedFolio] = useState(null);
  const [reportsModalOpen, setReportsModalOpen] = useState(false);
  const [invoicesModalOpen, setInvoicesModalOpen] = useState(false);
  const [allInvoices, setAllInvoices] = useState([]);
  const [plDetailModalOpen, setPlDetailModalOpen] = useState(false);
  const [cashierShiftModalOpen, setCashierShiftModalOpen] = useState(false);
  const [plData, setPlData] = useState(null);
  const [shiftReportData, setShiftReportData] = useState(null);
  
  // New state for enhanced features
  const [cashFlowData, setCashFlowData] = useState(null);
  const [riskAlerts, setRiskAlerts] = useState(null);
  const [overdueAccounts, setOverdueAccounts] = useState(null);
  const [creditViolations, setCreditViolations] = useState(null);
  const [suspiciousReceivables, setSuspiciousReceivables] = useState(null);
  const [dailyExpenses, setDailyExpenses] = useState(null);
  const [bankBalances, setBankBalances] = useState(null);
  const [cashFlowModalOpen, setCashFlowModalOpen] = useState(false);
  const [riskModalOpen, setRiskModalOpen] = useState(false);
  const [folioExtractModalOpen, setFolioExtractModalOpen] = useState(false);
  const [selectedFolioExtract, setSelectedFolioExtract] = useState(null);
  const [enhancedInvoices, setEnhancedInvoices] = useState([]);
  const [invoiceFilters, setInvoiceFilters] = useState({
    startDate: '',
    endDate: '',
    unpaidOnly: false,
    department: ''
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      
      const [
        dailyRes, 
        monthlyRes, 
        receivablesRes, 
        costsRes, 
        notifRes, 
        invoicesRes,
        cashFlowRes,
        riskAlertsRes,
        dailyExpensesRes,
        bankBalancesRes
      ] = await Promise.all([
        axios.get('/finance/mobile/daily-collections'),
        axios.get('/finance/mobile/monthly-collections'),
        axios.get('/finance/mobile/pending-receivables'),
        axios.get('/finance/mobile/monthly-costs'),
        axios.get('/notifications/mobile/finance'),
        axios.get('/invoice/list').catch(() => ({ data: { invoices: [] } })),
        axios.get('/finance/mobile/cash-flow-summary').catch(() => ({ data: null })),
        axios.get('/finance/mobile/risk-alerts').catch(() => ({ data: null })),
        axios.get('/finance/mobile/daily-expenses').catch(() => ({ data: null })),
        axios.get('/finance/mobile/bank-balances').catch(() => ({ data: null }))
      ]);

      setDailyCollections(dailyRes.data);
      setMonthlyCollections(monthlyRes.data);
      setPendingReceivables(receivablesRes.data);
      setMonthlyCosts(costsRes.data);
      setNotifications(notifRes.data.notifications || []);
      setAllInvoices(invoicesRes.data.invoices || []);
      setCashFlowData(cashFlowRes.data);
      setRiskAlerts(riskAlertsRes.data);
      setDailyExpenses(dailyExpensesRes.data);
      setBankBalances(bankBalancesRes.data);
    } catch (error) {
      console.error('Failed to load finance data:', error);
      toast.error('✗ Veri yükleme hatası');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleRecordPayment = async (formData) => {
    try {
      await axios.post('/finance/mobile/record-payment', formData);
      toast.success('✓ Ödeme');
      setPaymentModalOpen(false);
      loadData();
    } catch (error) {
      toast.error('✗ Ödeme');
    }
  };

  const formatCurrency = (amount) => {
    return `₺${parseFloat(amount || 0).toFixed(2)}`;
  };

  const formatPercent = (value) => {
    return `${parseFloat(value || 0).toFixed(1)}%`;
  };

  const loadPLDetail = async () => {
    try {
      const currentMonth = new Date().toISOString().slice(0, 7); // YYYY-MM
      const res = await axios.get(`/finance/pl-detail?month=${currentMonth}`);
      setPlData(res.data);
      setPlDetailModalOpen(true);
    } catch (error) {
      toast.error('✗ P&L');
    }
  };

  const loadCashierShiftReport = async () => {
    try {
      const res = await axios.get('/finance/cashier-shift-report');
      setShiftReportData(res.data);
      setCashierShiftModalOpen(true);
    } catch (error) {
      toast.error('✗ Vardiya');
    }
  };


  const loadCashFlowDetail = async () => {
    try {
      const res = await axios.get('/finance/mobile/cash-flow-summary');
      setCashFlowData(res.data);
      setCashFlowModalOpen(true);
    } catch (error) {
      toast.error('✗ Nakit akışı yüklenemedi');
    }
  };

  const loadRiskDetails = async () => {
    try {
      const [alertsRes, overdueRes, violationsRes, suspiciousRes] = await Promise.all([
        axios.get('/finance/mobile/risk-alerts'),
        axios.get('/finance/mobile/overdue-accounts?min_days=7'),
        axios.get('/finance/mobile/credit-limit-violations'),
        axios.get('/finance/mobile/suspicious-receivables')
      ]);
      
      setRiskAlerts(alertsRes.data);
      setOverdueAccounts(overdueRes.data);
      setCreditViolations(violationsRes.data);
      setSuspiciousReceivables(suspiciousRes.data);
      setRiskModalOpen(true);
    } catch (error) {
      toast.error('✗ Risk verileri yüklenemedi');
    }
  };

  const loadFolioExtract = async (folioId) => {
    try {
      const res = await axios.get(`/finance/mobile/folio-full-extract/${folioId}`);
      setSelectedFolioExtract(res.data);
      setFolioExtractModalOpen(true);
    } catch (error) {
      toast.error('✗ Folio ekstresi yüklenemedi');
    }
  };

  const loadEnhancedInvoices = async () => {
    try {
      const params = new URLSearchParams();
      if (invoiceFilters.startDate) params.append('start_date', invoiceFilters.startDate);
      if (invoiceFilters.endDate) params.append('end_date', invoiceFilters.endDate);
      if (invoiceFilters.unpaidOnly) params.append('unpaid_only', 'true');
      if (invoiceFilters.department) params.append('department', invoiceFilters.department);
      
      const res = await axios.get(`/finance/mobile/invoices?${params.toString()}`);
      setEnhancedInvoices(res.data.invoices || []);
      setInvoicesModalOpen(true);
    } catch (error) {
      toast.error('✗ Faturalar yüklenemedi');
    }
  };

  const getRiskColor = (riskLevel) => {
    const colors = {
      'normal': 'bg-green-100 text-green-800 border-green-200',
      'warning': 'bg-yellow-100 text-yellow-800 border-yellow-200',
      'critical': 'bg-red-100 text-red-800 border-red-200',
      'suspicious': 'bg-gray-900 text-white border-gray-900'
    };
    return colors[riskLevel] || colors.normal;
  };

  const getRiskIcon = (severity) => {
    if (severity === 'critical') return <XCircle className="w-5 h-5 text-red-600" />;
    if (severity === 'high') return <AlertTriangle className="w-5 h-5 text-orange-600" />;
    if (severity === 'medium') return <AlertCircle className="w-5 h-5 text-yellow-600" />;
    return <AlertCircle className="w-5 h-5 text-blue-600" />;
  };


  const downloadPLReport = async () => {
    try {
      const currentMonth = new Date().toISOString().slice(0, 7);
      const response = await axios.get(`/finance/pl-detail/pdf?month=${currentMonth}`, {
        responseType: 'blob'
      });
      
      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `P&L_Report_${currentMonth}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      
      toast.success('✓ İndirildi');
    } catch (error) {
      // Fallback: Create a simple HTML print version
      toast.info('⏳ Yazdırılıyor...');
      setTimeout(() => {
        window.print();
      }, 500);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-600 mx-auto mb-2" />
          <p className="text-gray-600">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-600 to-indigo-500 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/mobile')}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Finans Dashboard</h1>
              <p className="text-xs text-indigo-100">Finance & AR/AP</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {notifications.length > 0 && (
              <div className="relative">
                <Badge className="bg-red-500 text-white">{notifications.length}</Badge>
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/')}
              className="text-white hover:bg-white/20 p-2"
              title="Ana Sayfa"
            >
              <Home className="w-5 h-5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={downloadPLReport}
              className="text-white hover:bg-white/20 p-2"
              title="Aylık Özet PDF"
            >
              <FileDown className="w-5 h-5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="text-white hover:bg-white/20 p-2"
            >
              <RefreshCw className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Notifications */}
        {notifications.length > 0 && (
          <Card className="bg-gradient-to-r from-red-50 to-orange-50 border-red-200">
            <CardContent className="p-3">
              <div className="flex items-start space-x-2">
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-gray-900">Bildirimler ({notifications.length})</p>
                  {notifications.slice(0, 3).map((notif, idx) => (
                    <p key={idx} className="text-xs text-gray-700 mt-1">
                      • {notif.title}: {notif.message}
                    </p>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Quick Stats */}
        <div className="grid grid-cols-2 gap-3">
          <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-green-600 font-medium">BUGÜN TAHSİLAT</p>
                  <p className="text-2xl font-bold text-green-700">
                    {formatCurrency(dailyCollections?.total_collected || 0)}
                  </p>
                  <p className="text-xs text-green-600 mt-1">
                    {dailyCollections?.payment_count || 0} işlem
                  </p>
                </div>
                <DollarSign className="w-10 h-10 text-green-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-blue-600 font-medium">AYLIK TAHSİLAT</p>
                  <p className="text-2xl font-bold text-blue-700">
                    {formatCurrency(monthlyCollections?.total_collected || 0)}
                  </p>
                  <p className="text-xs text-blue-600 mt-1">
                    Oran: {formatPercent(monthlyCollections?.collection_rate || 0)}
                  </p>
                </div>
                <TrendingUp className="w-10 h-10 text-blue-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-orange-50 to-orange-100 border-orange-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-orange-600 font-medium">BEKLEYEN ALACAK</p>
                  <p className="text-2xl font-bold text-orange-700">
                    {formatCurrency(pendingReceivables?.total_pending || 0)}
                  </p>
                  <p className="text-xs text-orange-600 mt-1">
                    {pendingReceivables?.receivables_count || 0} fatura
                  </p>
                </div>
                <Receipt className="w-10 h-10 text-orange-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-purple-50 to-purple-100 border-purple-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-purple-600 font-medium">AYIN MALİYETİ</p>
                  <p className="text-2xl font-bold text-purple-700">
                    {formatCurrency(monthlyCosts?.total_costs || 0)}
                  </p>
                </div>
                <Calendar className="w-10 h-10 text-purple-300" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Pending Receivables */}
        {pendingReceivables?.receivables && pendingReceivables.receivables.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <Receipt className="w-5 h-5 mr-2 text-orange-600" />
                Bekleyen Alacaklar ({pendingReceivables.receivables_count})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {pendingReceivables.receivables.slice(0, 10).map((receivable) => (
                <div 
                  key={receivable.folio_id} 
                  className={`flex items-center justify-between p-3 rounded-lg border ${
                    receivable.is_overdue ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'
                  }`}
                >
                  <div className="flex-1">
                    <p className="font-bold text-gray-900">{receivable.guest_name}</p>
                    <p className="text-sm text-gray-600">Folio: {receivable.folio_number}</p>
                    {receivable.is_overdue && (
                      <Badge className="bg-red-500 text-xs mt-1">Vadesi Geçmiş</Badge>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-orange-700">{formatCurrency(receivable.balance)}</p>
                    <Button
                      size="sm"
                      onClick={() => {
                        setSelectedFolio(receivable);
                        setPaymentModalOpen(true);
                      }}
                      className="bg-green-600 hover:bg-green-700 mt-1"
                    >
                      <CreditCard className="w-3 h-3 mr-1" />
                      Tahsilat
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Payment Methods Summary */}
        {dailyCollections?.payment_methods && Object.keys(dailyCollections.payment_methods).length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <CreditCard className="w-5 h-5 mr-2 text-green-600" />
                Bugün Ödeme Yöntemleri
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(dailyCollections.payment_methods).map(([method, amount]) => (
                  <div key={method} className="flex items-center justify-between p-2 bg-green-50 rounded-lg">
                    <span className="text-sm font-medium text-gray-700 capitalize">{method}</span>
                    <span className="text-sm font-bold text-green-700">{formatCurrency(amount)}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}



        {/* Risk Alerts - NEW */}
        {riskAlerts && riskAlerts.alerts && riskAlerts.alerts.length > 0 && (
          <Card className="bg-gradient-to-r from-red-50 to-orange-50 border-red-300">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center justify-between">
                <div className="flex items-center">
                  <AlertTriangle className="w-5 h-5 mr-2 text-red-600" />
                  Risk Uyarıları ({riskAlerts.summary.total_alerts})
                </div>
                <Button size="sm" variant="ghost" onClick={loadRiskDetails}>
                  <Eye className="w-4 h-4" />
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {riskAlerts.alerts.slice(0, 3).map((alert) => (
                <div key={alert.id} className="flex items-start space-x-2 p-2 bg-white rounded-lg border">
                  {getRiskIcon(alert.severity)}
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-gray-900">{alert.title}</p>
                    <p className="text-xs text-gray-600">{alert.message}</p>
                    {alert.amount && (
                      <p className="text-xs font-bold text-red-600 mt-1">{formatCurrency(alert.amount)}</p>
                    )}
                  </div>
                </div>
              ))}
              {riskAlerts.alerts.length > 3 && (
                <Button 
                  size="sm" 
                  variant="outline" 
                  className="w-full"
                  onClick={loadRiskDetails}
                >
                  Tümünü Gör ({riskAlerts.alerts.length})
                </Button>
              )}
            </CardContent>
          </Card>
        )}

        {/* Cash Flow Summary - NEW */}
        {cashFlowData && (
          <Card className="bg-gradient-to-br from-cyan-50 to-blue-50 border-cyan-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center justify-between">
                <div className="flex items-center">
                  <Wallet className="w-5 h-5 mr-2 text-cyan-600" />
                  Bugünkü Nakit Akışı
                </div>
                <Button size="sm" variant="ghost" onClick={loadCashFlowDetail}>
                  <ArrowUpCircle className="w-4 h-4" />
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                <div className="flex items-center space-x-2">
                  <ArrowUpCircle className="w-5 h-5 text-green-600" />
                  <div>
                    <p className="text-xs text-green-600">Giriş (Tahsilat)</p>
                    <p className="text-sm text-gray-600">{cashFlowData.today?.inflow_count || 0} işlem</p>
                  </div>
                </div>
                <p className="font-bold text-green-700 text-lg">
                  {formatCurrency(cashFlowData.today?.cash_inflow || 0)}
                </p>
              </div>
              
              <div className="flex items-center justify-between p-3 bg-red-50 rounded-lg">
                <div className="flex items-center space-x-2">
                  <ArrowDownCircle className="w-5 h-5 text-red-600" />
                  <div>
                    <p className="text-xs text-red-600">Çıkış (Gider)</p>
                    <p className="text-sm text-gray-600">{cashFlowData.today?.outflow_count || 0} işlem</p>
                  </div>
                </div>
                <p className="font-bold text-red-700 text-lg">
                  {formatCurrency(cashFlowData.today?.cash_outflow || 0)}
                </p>
              </div>

              <div className="flex items-center justify-between p-3 bg-cyan-100 rounded-lg border-2 border-cyan-300">
                <div>
                  <p className="text-xs text-cyan-700 font-medium">NET NAKİT AKIŞI</p>
                </div>
                <p className={`font-bold text-xl ${
                  (cashFlowData.today?.net_flow || 0) >= 0 ? 'text-green-700' : 'text-red-700'
                }`}>
                  {formatCurrency(cashFlowData.today?.net_flow || 0)}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Bank Balances - NEW */}
        {bankBalances && bankBalances.bank_accounts && bankBalances.bank_accounts.length > 0 && (
          <Card className="bg-gradient-to-br from-indigo-50 to-purple-50 border-indigo-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <Building2 className="w-5 h-5 mr-2 text-indigo-600" />
                Banka Bakiyeleri
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {bankBalances.bank_accounts.map((bank) => (
                <div key={bank.id} className="flex items-center justify-between p-2 bg-white rounded-lg border">
                  <div>
                    <p className="text-sm font-semibold text-gray-900">{bank.bank_name}</p>
                    <p className="text-xs text-gray-500">****{bank.account_number}</p>
                    {bank.last_sync && (
                      <p className="text-xs text-gray-400">
                        Güncelleme: {new Date(bank.last_sync).toLocaleString('tr-TR')}
                      </p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-indigo-700">{formatCurrency(bank.current_balance)}</p>
                    <p className="text-xs text-gray-500">{bank.currency}</p>
                  </div>
                </div>
              ))}
              <div className="mt-3 pt-3 border-t border-gray-200">
                <div className="flex justify-between">
                  <span className="font-semibold text-gray-700">Toplam (TRY):</span>
                  <span className="font-bold text-lg text-indigo-700">
                    {formatCurrency(bankBalances.total_balance_try || 0)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Daily Expenses - NEW */}
        {dailyExpenses && dailyExpenses.total_expenses > 0 && (
          <Card className="bg-gradient-to-br from-rose-50 to-pink-50 border-rose-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <TrendingDown className="w-5 h-5 mr-2 text-rose-600" />
                Bugünkü Giderler
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between p-2 bg-rose-100 rounded-lg">
                <span className="font-semibold text-rose-800">Toplam Gider:</span>
                <span className="font-bold text-rose-800">{formatCurrency(dailyExpenses.total_expenses)}</span>
              </div>
              <p className="text-xs text-gray-600">{dailyExpenses.expense_count} işlem</p>
              
              {dailyExpenses.expenses_by_department && Object.keys(dailyExpenses.expenses_by_department).length > 0 && (
                <div className="mt-2 space-y-1">
                  <p className="text-xs font-semibold text-gray-700">Departman Bazlı:</p>
                  {Object.entries(dailyExpenses.expenses_by_department).map(([dept, amount]) => (
                    <div key={dept} className="flex justify-between text-xs pl-2">
                      <span className="text-gray-600 capitalize">{dept}:</span>
                      <span className="font-medium">{formatCurrency(amount)}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Quick Actions - Enhanced */}
        <div className="grid grid-cols-2 gap-3">
          <Button
            className="h-20 flex flex-col items-center justify-center bg-cyan-600 hover:bg-cyan-700"
            onClick={loadCashFlowDetail}
          >
            <Wallet className="w-6 h-6 mb-1" />
            <span className="text-xs">Nakit Akışı</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-red-600 hover:bg-red-700"
            onClick={loadRiskDetails}
          >
            <AlertTriangle className="w-6 h-6 mb-1" />
            <span className="text-xs">Risk Yönetimi</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-orange-600 hover:bg-orange-700"
            onClick={loadEnhancedInvoices}
          >
            <Receipt className="w-6 h-6 mb-1" />
            <span className="text-xs">Faturalar</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-green-600 hover:bg-green-700"
            onClick={loadPLDetail}
          >
            <BarChart3 className="w-6 h-6 mb-1" />
            <span className="text-xs">P&L Detayı</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-indigo-600 hover:bg-indigo-700"
            onClick={() => setReportsModalOpen(true)}
          >
            <TrendingUp className="w-6 h-6 mb-1" />
            <span className="text-xs">{t("nav.reports")}</span>
          </Button>
          
          <Button
            className="h-20 flex flex-col items-center justify-center bg-purple-600 hover:bg-purple-700"
            onClick={loadCashierShiftReport}
          >
            <User className="w-6 h-6 mb-1" />
            <span className="text-xs">Vardiya</span>
          </Button>
        </div>
      </div>

      {/* Payment Modal */}
      <Dialog open={paymentModalOpen} onOpenChange={setPaymentModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Tahsilat Kaydı</DialogTitle>
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
                  <Label>Misafir</Label>
                  <Input value={selectedFolio.guest_name} disabled />
                </div>
                <div>
                  <Label>Kalan Bakiye</Label>
                  <Input value={formatCurrency(selectedFolio.balance)} disabled />
                </div>
                <div>
                  <Label>Tahsilat Tutarı *</Label>
                  <Input 
                    name="amount" 
                    type="number" 
                    step="0.01" 
                    max={selectedFolio.balance}
                    required 
                  />
                </div>
                <div>
                  <Label>Ödeme Yöntemi *</Label>
                  <select name="payment_method" className="w-full p-2 border rounded" required>
                    <option value="cash">Nakit</option>
                    <option value="card">Kredi Kartı</option>
                    <option value="transfer">Havale</option>
                    <option value="check">Çek</option>
                  </select>
                </div>
                <div>
                  <Label>Notlar</Label>
                  <Textarea name="notes" rows={3} />
                </div>
                <Button type="submit" className="w-full bg-green-600 hover:bg-green-700">
                  Tahsilat Kaydet
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Reports Modal */}
      <Dialog open={reportsModalOpen} onOpenChange={setReportsModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Finansal Raporlar</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Günlük Özet</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">Bugün Tahsilat:</span>
                  <span className="font-bold text-green-700">{formatCurrency(dailyCollections?.total_collected || 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">İşlem Sayısı:</span>
                  <span className="font-bold">{dailyCollections?.payment_count || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Ortalama İşlem:</span>
                  <span className="font-bold">{formatCurrency(dailyCollections?.average_transaction || 0)}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Aylık Özet</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">Toplam Tahsilat:</span>
                  <span className="font-bold text-green-700">{formatCurrency(monthlyCollections?.total_collected || 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Beklenen Tutar:</span>
                  <span className="font-bold">{formatCurrency(monthlyCollections?.total_expected || 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Tahsilat Oranı:</span>
                  <span className="font-bold text-blue-700">{formatPercent(monthlyCollections?.collection_rate || 0)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Kalan Alacak:</span>
                  <span className="font-bold text-orange-700">{formatCurrency(monthlyCollections?.outstanding || 0)}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Maliyet Özeti</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">Aylık Maliyet:</span>
                  <span className="font-bold text-red-700">{formatCurrency(monthlyCosts?.total_costs || 0)}</span>
                </div>
                {monthlyCosts?.costs_by_category && Object.entries(monthlyCosts.costs_by_category).map(([category, amount]) => (
                  <div key={category} className="flex justify-between pl-4">
                    <span className="text-sm text-gray-500 capitalize">{category}:</span>
                    <span className="text-sm">{formatCurrency(amount)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>

      {/* Invoices Modal */}
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

      {/* P&L Detail Modal */}
      <Dialog open={plDetailModalOpen} onOpenChange={setPlDetailModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <BarChart3 className="w-5 h-5 text-green-600" />
              <span>Kar/Zarar Detayı (P&L)</span>
            </DialogTitle>
          </DialogHeader>
          
          {plData ? (
            <div className="space-y-4">
              {/* Period Info */}
              <Card className="bg-gradient-to-r from-green-50 to-blue-50">
                <CardContent className="p-4">
                  <div className="text-center">
                    <p className="text-sm text-gray-600">Dönem</p>
                    <p className="text-lg font-bold text-gray-900">
                      {plData.period || new Date().toLocaleDateString('tr-TR', { year: 'numeric', month: 'long' })}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Revenue Section */}
              <Card>
                <CardHeader className="pb-3 bg-green-50">
                  <CardTitle className="text-base text-green-800">💰 Gelirler</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 pt-3">
                  <div className="flex justify-between p-2 bg-green-50 rounded">
                    <span className="text-gray-700">Oda Gelirleri:</span>
                    <span className="font-bold">{formatCurrency(plData.room_revenue || 0)}</span>
                  </div>
                  <div className="flex justify-between p-2">
                    <span className="text-gray-700">F&B Gelirleri:</span>
                    <span className="font-bold">{formatCurrency(plData.fnb_revenue || 0)}</span>
                  </div>
                  <div className="flex justify-between p-2 bg-green-50 rounded">
                    <span className="text-gray-700">Diğer Gelirler:</span>
                    <span className="font-bold">{formatCurrency(plData.other_revenue || 0)}</span>
                  </div>
                  <div className="flex justify-between p-3 bg-green-200 rounded-lg border-2 border-green-400 mt-2">
                    <span className="font-bold text-green-900">TOPLAM GELİR:</span>
                    <span className="font-bold text-xl text-green-700">
                      {formatCurrency(plData.total_revenue || 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* Cost of Sales Section */}
              <Card>
                <CardHeader className="pb-3 bg-orange-50">
                  <CardTitle className="text-base text-orange-800">📦 Satış Maliyeti</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 pt-3">
                  <div className="flex justify-between p-2 bg-orange-50 rounded">
                    <span className="text-gray-700">F&B Maliyeti:</span>
                    <span className="font-bold">{formatCurrency(plData.fnb_cost || 0)}</span>
                  </div>
                  <div className="flex justify-between p-2">
                    <span className="text-gray-700">Housekeeping Maliyeti:</span>
                    <span className="font-bold">{formatCurrency(plData.housekeeping_cost || 0)}</span>
                  </div>
                  <div className="flex justify-between p-3 bg-orange-200 rounded-lg border-2 border-orange-400 mt-2">
                    <span className="font-bold text-orange-900">TOPLAM SATIŞ MALİYETİ:</span>
                    <span className="font-bold text-xl text-orange-700">
                      {formatCurrency(plData.total_cost_of_sales || 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* Gross Profit */}
              <Card className="bg-blue-50">
                <CardContent className="p-4">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-sm text-blue-700 font-medium">BRÜT KAR</p>
                      <p className="text-xs text-blue-600 mt-1">
                        Brüt Kar Marjı: {formatPercent(plData.gross_profit_margin || 0)}
                      </p>
                    </div>
                    <p className="text-3xl font-bold text-blue-700">
                      {formatCurrency(plData.gross_profit || 0)}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Operating Expenses */}
              <Card>
                <CardHeader className="pb-3 bg-purple-50">
                  <CardTitle className="text-base text-purple-800">🏢 Faaliyet Giderleri</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 pt-3">
                  <div className="flex justify-between p-2 bg-purple-50 rounded">
                    <span className="text-gray-700">Personel Giderleri:</span>
                    <span className="font-bold">{formatCurrency(plData.personnel_cost || 0)}</span>
                  </div>
                  <div className="flex justify-between p-2">
                    <span className="text-gray-700">Enerji Giderleri:</span>
                    <span className="font-bold">{formatCurrency(plData.utility_cost || 0)}</span>
                  </div>
                  <div className="flex justify-between p-2 bg-purple-50 rounded">
                    <span className="text-gray-700">Bakım Onarım:</span>
                    <span className="font-bold">{formatCurrency(plData.maintenance_cost || 0)}</span>
                  </div>
                  <div className="flex justify-between p-2">
                    <span className="text-gray-700">Pazarlama Giderleri:</span>
                    <span className="font-bold">{formatCurrency(plData.marketing_cost || 0)}</span>
                  </div>
                  <div className="flex justify-between p-2 bg-purple-50 rounded">
                    <span className="text-gray-700">Yönetim Giderleri:</span>
                    <span className="font-bold">{formatCurrency(plData.admin_cost || 0)}</span>
                  </div>
                  <div className="flex justify-between p-3 bg-purple-200 rounded-lg border-2 border-purple-400 mt-2">
                    <span className="font-bold text-purple-900">TOPLAM FAALİYET GİDERİ:</span>
                    <span className="font-bold text-xl text-purple-700">
                      {formatCurrency(plData.total_operating_expenses || 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>

              {/* Net Profit/Loss */}
              <Card className={plData.net_profit >= 0 ? 'bg-green-100' : 'bg-red-100'}>
                <CardContent className="p-5">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className={`text-lg font-bold ${plData.net_profit >= 0 ? 'text-green-900' : 'text-red-900'}`}>
                        {plData.net_profit >= 0 ? '✅ NET KAR' : '❌ NET ZARAR'}
                      </p>
                      <p className={`text-sm mt-1 ${plData.net_profit >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                        Net Kar Marjı: {formatPercent(plData.net_profit_margin || 0)}
                      </p>
                    </div>
                    <p className={`text-4xl font-bold ${plData.net_profit >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                      {formatCurrency(Math.abs(plData.net_profit || 0))}
                    </p>
                  </div>
                </CardContent>
              </Card>

              {/* Key Ratios */}
              {plData.key_metrics && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">📊 Anahtar Metrikler</CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-2 gap-3">
                    <div className="text-center p-3 bg-blue-50 rounded">
                      <p className="text-xs text-blue-600">RevPAR</p>
                      <p className="text-lg font-bold text-blue-900">
                        {formatCurrency(plData.key_metrics.revpar || 0)}
                      </p>
                    </div>
                    <div className="text-center p-3 bg-green-50 rounded">
                      <p className="text-xs text-green-600">ADR</p>
                      <p className="text-lg font-bold text-green-900">
                        {formatCurrency(plData.key_metrics.adr || 0)}
                      </p>
                    </div>
                    <div className="text-center p-3 bg-purple-50 rounded">
                      <p className="text-xs text-purple-600">Occ %</p>
                      <p className="text-lg font-bold text-purple-900">
                        {formatPercent(plData.key_metrics.occupancy || 0)}
                      </p>
                    </div>
                    <div className="text-center p-3 bg-orange-50 rounded">
                      <p className="text-xs text-orange-600">GOP %</p>
                      <p className="text-lg font-bold text-orange-900">
                        {formatPercent(plData.key_metrics.gop_percentage || 0)}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Download Buttons */}
              <div className="grid grid-cols-2 gap-3">
                <Button 
                  className="w-full bg-green-600 hover:bg-green-700"
                  onClick={downloadPLReport}
                >
                  <Download className="w-4 h-4 mr-2" />
                  PDF İndir
                </Button>
                <Button 
                  variant="outline"
                  className="w-full"
                  onClick={() => window.print()}
                >
                  <FileDown className="w-4 h-4 mr-2" />
                  Yazdır
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <FileText className="w-12 h-12 mx-auto text-gray-300 mb-2" />
              <p className="text-gray-500">P&L raporu yükleniyor...</p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Cashier Shift Report Modal */}
      <Dialog open={cashierShiftModalOpen} onOpenChange={setCashierShiftModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <User className="w-5 h-5 text-purple-600" />
              <span>Kasiyer Vardiya Raporu</span>
            </DialogTitle>
          </DialogHeader>
          
          {shiftReportData ? (
            <div className="space-y-4">
              {/* Shift Info */}
              <Card className="bg-gradient-to-r from-purple-50 to-indigo-50">
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
                  <CardTitle className="text-base">💰 Kasa Durumu</CardTitle>
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
                  <div className="flex justify-between p-4 bg-purple-100 rounded-lg border-2 border-purple-300">
                    <span className="font-bold text-purple-900">Beklenen Bakiye:</span>
                    <span className="font-bold text-2xl text-purple-700">
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
                  <CardTitle className="text-base">📊 İşlem Özeti</CardTitle>
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
                    <div className="text-center p-3 bg-purple-50 rounded">
                      <p className="text-xs text-purple-600">Check-out</p>
                      <p className="text-2xl font-bold text-purple-900">
                        {shiftReportData.checkout_count || 0}
                      </p>
                    </div>
                    <div className="text-center p-3 bg-orange-50 rounded">
                      <p className="text-xs text-orange-600">Ort. İşlem</p>
                      <p className="text-2xl font-bold text-orange-900">
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
                    <CardTitle className="text-base">💳 Ödeme Yöntemleri</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {Object.entries(shiftReportData.payment_methods).map(([method, data]) => (
                      <div key={method} className="p-3 bg-gray-50 rounded border">
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <p className="font-bold text-gray-900 capitalize">
                              {method === 'cash' ? '💵 Nakit' : 
                               method === 'card' ? '💳 Kredi Kartı' :
                               method === 'transfer' ? '🏦 Havale' :
                               method === 'check' ? '📄 Çek' : method}
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
                    <CardTitle className="text-base">📝 Notlar</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-gray-700">{shiftReportData.notes}</p>
                  </CardContent>
                </Card>
              )}

              <Button 
                className="w-full bg-purple-600 hover:bg-purple-700"
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


      {/* Cash Flow Detail Modal - NEW */}
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

      {/* Risk Management Modal - NEW */}
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

      {/* Folio Full Extract Modal - NEW */}
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
              <Card className="bg-gradient-to-r from-indigo-50 to-purple-50">
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

    </div>
  );
};

export default MobileFinance;