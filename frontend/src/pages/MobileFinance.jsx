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
import PaymentModal from '@/components/mobile-finance/dialogs/PaymentModal';
import ReportsModal from '@/components/mobile-finance/dialogs/ReportsModal';
import InvoicesModal from '@/components/mobile-finance/dialogs/InvoicesModal';
import PlDetailModal from '@/components/mobile-finance/dialogs/PlDetailModal';
import CashierShiftModal from '@/components/mobile-finance/dialogs/CashierShiftModal';
import CashFlowModal from '@/components/mobile-finance/dialogs/CashFlowModal';
import RiskModal from '@/components/mobile-finance/dialogs/RiskModal';
import FolioExtractModal from '@/components/mobile-finance/dialogs/FolioExtractModal';
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

  const ctx = {
    user, navigate,
    loading, dailyCollections, monthlyCollections, pendingReceivables, monthlyCosts,
    notifications, refreshing,
    paymentModalOpen, setPaymentModalOpen, selectedFolio, setSelectedFolio,
    reportsModalOpen, setReportsModalOpen,
    invoicesModalOpen, setInvoicesModalOpen, allInvoices, setAllInvoices,
    plDetailModalOpen, setPlDetailModalOpen, plData, setPlData,
    cashierShiftModalOpen, setCashierShiftModalOpen, shiftReportData, setShiftReportData,
    cashFlowData, setCashFlowData, cashFlowModalOpen, setCashFlowModalOpen,
    riskAlerts, setRiskAlerts, overdueAccounts, setOverdueAccounts,
    creditViolations, setCreditViolations, suspiciousReceivables, setSuspiciousReceivables,
    dailyExpenses, setDailyExpenses, bankBalances, setBankBalances,
    riskModalOpen, setRiskModalOpen,
    folioExtractModalOpen, setFolioExtractModalOpen,
    selectedFolioExtract, setSelectedFolioExtract,
    enhancedInvoices, setEnhancedInvoices, invoiceFilters, setInvoiceFilters,
    loadData, handleRefresh, handleRecordPayment, formatCurrency, formatPercent,
    loadPLDetail, loadCashierShiftReport, loadCashFlowDetail, loadRiskDetails,
    loadFolioExtract, loadEnhancedInvoices,
  };

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
      <PaymentModal {...ctx} />

      {/* Reports Modal */}
      <ReportsModal {...ctx} />

      {/* Invoices Modal */}
      <InvoicesModal {...ctx} />

      {/* P&L Detail Modal */}
      <PlDetailModal {...ctx} />

      {/* Cashier Shift Report Modal */}
      <CashierShiftModal {...ctx} />


      {/* Cash Flow Detail Modal - NEW */}
      <CashFlowModal {...ctx} />

      {/* Risk Management Modal - NEW */}
      <RiskModal {...ctx} />

      {/* Folio Full Extract Modal - NEW */}
      <FolioExtractModal {...ctx} />

    </div>
  );
};

export default MobileFinance;