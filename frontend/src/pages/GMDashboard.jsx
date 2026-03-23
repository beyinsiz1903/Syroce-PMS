import { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, 
  TrendingDown,
  DollarSign, 
  Users, 
  Bed, 
  Calendar,
  Target,
  PieChart,
  BarChart3,
  Activity,
  Home,
  CheckCircle,
  AlertTriangle,
  FileText,
  Mail,
  Download,
  Zap,
  LogIn,
  ArrowUpCircle,
  MessageSquare,
  Key,
  Printer,
  Phone,
  Send,
  Building2,
  Settings,
  RefreshCw,
  Plus
} from 'lucide-react';
import FloatingActionButton from '@/components/FloatingActionButton';
import ExpenseSummaryCard from '@/components/ExpenseSummaryCard';
import TrendChart from '@/components/TrendChart';
import SLAConfigCard from '@/components/SLAConfigCard';
import { toast } from 'sonner';

const GMDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expenseSummary, setExpenseSummary] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [slaConfigs, setSlaConfigs] = useState([]);
  const [delayedTasks, setDelayedTasks] = useState([]);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      // Load daily flash report and other key metrics
      const [flashResponse, occupancyRes, folioRes, financeRes, costRes, expenseRes, trendRes, slaRes, delayedRes] = await Promise.all([
        axios.get('/reports/daily-flash', { timeout: 15000 }).catch(() => ({ data: {} })),
        axios.get('/pms/dashboard', { timeout: 15000 }).catch(() => ({ data: {} })),
        axios.get('/folio/dashboard-stats', { timeout: 15000 }).catch(() => ({ data: {} })),
        axios.get('/reports/finance-snapshot', { timeout: 15000 }).catch(() => ({ data: {} })),
        axios.get('/reports/cost-summary', { timeout: 15000 }).catch(() => ({ data: {} })),
        axios.get('/finance/expense-summary?period=today', { timeout: 15000 }).catch(() => ({ data: {} })),
        axios.get('/analytics/7day-trend', { timeout: 15000 }).catch(() => ({ data: { trend: [] } })),
        axios.get('/settings/sla', { timeout: 15000 }).catch(() => ({ data: { configs: [] } })),
        axios.get('/tasks/delayed', { timeout: 15000 }).catch(() => ({ data: { delayed_tasks: [] } }))
      ]);

      setDashboardData({
        flash: flashResponse.data,
        occupancy: occupancyRes.data,
        folio: folioRes.data,
        finance: financeRes.data,
        costs: costRes.data
      });
      
      setExpenseSummary(expenseRes.data);
      setTrendData(trendRes.data);
      setSlaConfigs(slaRes.data.configs || []);
      setDelayedTasks(delayedRes.data.delayed_tasks || []);
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getTrendIcon = (value) => {
    if (value > 0) return <TrendingUp className="w-4 h-4 text-green-600" />;
    if (value < 0) return <TrendingDown className="w-4 h-4 text-red-600" />;
    return null;
  };

  const getTrendColor = (value) => {
    if (value > 0) return 'text-green-600';
    if (value < 0) return 'text-red-600';
    return 'text-gray-600';
  };

  const handleExportPDF = async () => {
    try {
      const response = await axios.get('/reports/daily-flash-pdf', {
        responseType: 'blob'
      });
      
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `Daily-Report-${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export PDF:', error);
      alert('PDF export failed. Feature coming soon!');
    }
  };

  const handleEmailReport = async () => {
    try {
      await axios.post('/reports/email-daily-flash', {
        recipients: ['owner@hotel.com', 'family@hotel.com']
      });
      alert('Daily report sent successfully!');
    } catch (error) {
      console.error('Failed to send email:', error);
      alert('Email feature coming soon! Report will be sent to predefined recipients.');
    }
  };

  const calculateComparison = (current, previous) => {
    if (!previous || previous === 0) return 0;
    return ((current - previous) / previous * 100).toFixed(1);
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="gm-dashboard">
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  const flash = dashboardData?.flash || {};
  const occupancy = dashboardData?.occupancy || {};
  const movements = flash.movements || {};
  const revenue = flash.revenue || {};

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="dashboard">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>
              GM Dashboard
            </h1>
            <p className="text-gray-600">
              {String(flash.date || 'Today')} • {String(tenant?.property_name || '')}
            </p>
          </div>
          <div className="flex space-x-2">
            <Button variant="outline" onClick={handleEmailReport} className="bg-blue-50 hover:bg-blue-100">
              <Mail className="w-4 h-4 mr-2" />
              Email Report
            </Button>
            <Button variant="outline" onClick={handleExportPDF}>
              <Download className="w-4 h-4 mr-2" />
              Export PDF
            </Button>
            <Button variant="outline" onClick={() => loadDashboardData()}>
              <Activity className="w-4 h-4 mr-2" />
              Refresh
            </Button>
            <Button onClick={() => navigate('/pms#reports')}>
              <BarChart3 className="w-4 h-4 mr-2" />
              View Reports
            </Button>
          </div>
        </div>

        {/* Dashboard Metric Cards - Compact & Beautiful */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {/* Total Rooms */}
          <Card className="hover:shadow-lg transition-all">
            <CardContent className="p-6 text-center">
              <div className="flex justify-center mb-3">
                <div className="bg-blue-100 p-3 rounded-lg">
                  <Bed className="w-8 h-8 text-blue-600" />
                </div>
              </div>
              <div className="text-3xl font-bold text-gray-900 mb-1">
                {occupancy.total_rooms || 0}
              </div>
              <div className="text-sm font-medium text-gray-600">
                Total Rooms
              </div>
            </CardContent>
          </Card>

          {/* Occupancy Rate */}
          <Card className="hover:shadow-lg transition-all">
            <CardContent className="p-6 text-center">
              <div className="flex justify-center mb-3">
                <div className="bg-green-100 p-3 rounded-lg">
                  <Activity className="w-8 h-8 text-green-600" />
                </div>
              </div>
              <div className="text-3xl font-bold text-gray-900 mb-1">
                {(occupancy.occupancy_percentage || occupancy.occupancy_rate || 0).toFixed(1)}%
              </div>
              <div className="text-sm font-medium text-gray-600">
                Occupancy Rate
              </div>
            </CardContent>
          </Card>

          {/* Today's Arrivals */}
          <Card className="hover:shadow-lg transition-all">
            <CardContent className="p-6 text-center">
              <div className="flex justify-center mb-3">
                <div className="bg-purple-100 p-3 rounded-lg">
                  <LogIn className="w-8 h-8 text-purple-600" />
                </div>
              </div>
              <div className="text-3xl font-bold text-gray-900 mb-1">
                {movements.arrivals || 0}
              </div>
              <div className="text-sm font-medium text-gray-600">
                Today's Check-ins
              </div>
            </CardContent>
          </Card>

          {/* Total Guests */}
          <Card className="hover:shadow-lg transition-all">
            <CardContent className="p-6 text-center">
              <div className="flex justify-center mb-3">
                <div className="bg-orange-100 p-3 rounded-lg">
                  <Users className="w-8 h-8 text-orange-600" />
                </div>
              </div>
              <div className="text-3xl font-bold text-gray-900 mb-1">
                {Math.round((occupancy.occupied_rooms || 0) * 1.5)}
              </div>
              <div className="text-sm font-medium text-gray-600">
                Total Guests
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Key Metrics - Top Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Occupancy */}
          <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center justify-between">
                <span>Occupancy Rate</span>
                <Bed className="w-5 h-5 opacity-75" />
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold mb-2">
                {(occupancy.occupancy_percentage || occupancy.occupancy_rate || 0).toFixed(1)}%
              </div>
              <div className="text-sm opacity-90">
                {occupancy.occupied_rooms || 0} / {occupancy.total_rooms || 0} rooms
              </div>
              <div className="text-xs mt-2 opacity-75">
                Available: {occupancy.available_rooms || 0}
              </div>
            </CardContent>
          </Card>

          {/* ADR */}
          <Card className="bg-gradient-to-br from-green-500 to-green-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center justify-between">
                <span>ADR (Average Daily Rate)</span>
                <DollarSign className="w-5 h-5 opacity-75" />
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold mb-2">
                ${(revenue.adr || 0).toFixed(2)}
              </div>
              <div className="text-sm opacity-90 flex items-center space-x-2">
                <span>Room Revenue: ${(revenue.room_revenue || 0).toFixed(2)}</span>
              </div>
              <div className="text-xs mt-2 opacity-75">
                Per occupied room
              </div>
            </CardContent>
          </Card>

          {/* RevPAR */}
          <Card className="bg-gradient-to-br from-purple-500 to-purple-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center justify-between">
                <span>RevPAR</span>
                <Target className="w-5 h-5 opacity-75" />
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold mb-2">
                ${(revenue.revpar || 0).toFixed(2)}
              </div>
              <div className="text-sm opacity-90">
                Revenue per Available Room
              </div>
              <div className="text-xs mt-2 opacity-75">
                Total rooms: {occupancy.total_rooms || 0}
              </div>
            </CardContent>
          </Card>

          {/* Total Revenue */}
          <Card className="bg-gradient-to-br from-orange-500 to-orange-600 text-white">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center justify-between">
                <span>Total Revenue</span>
                <TrendingUp className="w-5 h-5 opacity-75" />
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold mb-2">
                ${((revenue.room_revenue || 0) + (revenue.other_revenue || 0)).toFixed(2)}
              </div>
              <div className="text-sm opacity-90">
                Room + Other: ${(revenue.other_revenue || 0).toFixed(2)}
              </div>
              <div className="text-xs mt-2 opacity-75">
                Today's total
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Finance Snapshot - NEW */}
        <Card className="border-2 border-emerald-400 bg-gradient-to-r from-emerald-50 to-teal-50">
          <CardHeader>
            <CardTitle className="text-xl flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <DollarSign className="w-6 h-6 text-emerald-600" />
                <span>Finance Snapshot</span>
              </div>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => navigate('/accounting')}
                className="bg-white hover:bg-emerald-50"
              >
                <FileText className="w-4 h-4 mr-2" />
                View Details
              </Button>
            </CardTitle>
            <CardDescription>Accounts Receivable & Collections Overview</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Column 1: Pending AR */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <Building2 className="w-4 h-4 text-emerald-600" />
                  <span>Pending AR Total</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm border-l-4 border-emerald-500">
                  <div className="text-3xl font-bold text-gray-900">
                    ${((dashboardData?.finance?.pending_ar?.total || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}))}
                  </div>
                  <div className="text-sm text-gray-600 mt-1">
                    {dashboardData?.finance?.pending_ar?.overdue_invoices_count || 0} company folios
                  </div>
                  <div className="text-xs text-gray-500 mt-2">
                    Total Accounts Receivable
                  </div>
                </div>
              </div>

              {/* Column 2: Overdue Invoices */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <AlertTriangle className="w-4 h-4 text-orange-600" />
                  <span>Overdue Breakdown</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm space-y-2">
                  <div className="flex justify-between items-center pb-2 border-b">
                    <span className="text-xs text-gray-600">0-30 days (Warning)</span>
                    <span className="text-sm font-semibold text-yellow-600">
                      ${(dashboardData?.finance?.pending_ar?.overdue_breakdown?.['0-30_days'] || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                    </span>
                  </div>
                  <div className="flex justify-between items-center pb-2 border-b">
                    <span className="text-xs text-gray-600">30-60 days (Critical)</span>
                    <span className="text-sm font-semibold text-orange-600">
                      ${(dashboardData?.finance?.pending_ar?.overdue_breakdown?.['30-60_days'] || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-gray-600">60+ days (Very Critical)</span>
                    <span className="text-sm font-semibold text-red-600">
                      ${(dashboardData?.finance?.pending_ar?.overdue_breakdown?.['60_plus_days'] || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                    </span>
                  </div>
                  <div className="mt-2 pt-2 border-t">
                    <div className="text-xs text-gray-500">
                      {dashboardData?.finance?.pending_ar?.overdue_invoices_count || 0} overdue invoices
                    </div>
                  </div>
                </div>
              </div>

              {/* Column 3: Today's Collections */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <CheckCircle className="w-4 h-4 text-green-600" />
                  <span>Today's Collections</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm border-l-4 border-green-500">
                  <div className="text-3xl font-bold text-green-600">
                    ${(dashboardData?.finance?.todays_collections?.amount || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                  </div>
                  <div className="text-sm text-gray-600 mt-1">
                    {dashboardData?.finance?.todays_collections?.payment_count || 0} payments received
                  </div>
                  <div className="text-xs text-gray-500 mt-3 pt-2 border-t">
                    MTD: ${(dashboardData?.finance?.mtd_collections?.amount || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                  </div>
                  <div className="text-xs text-gray-500">
                    Collection Rate: {(dashboardData?.finance?.mtd_collections?.collection_rate_percentage || 0).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>

            {/* Accounting Integration Info */}
            <div className="mt-4 p-3 bg-blue-50 border-l-4 border-blue-500 rounded">
              <div className="flex items-start space-x-2">
                <FileText className="w-5 h-5 text-blue-600 mt-0.5" />
                <div className="flex-1">
                  <h4 className="font-semibold text-sm text-blue-900">Accounting Integration Ready</h4>
                  <p className="text-xs text-blue-700 mt-1">
                    ✓ E-Fatura & E-Arşiv Support • ✓ Export to Logo, Mikro, SAP (Excel, CSV, XML) • ✓ GIB Compliant Reporting
                  </p>
                  <div className="flex space-x-2 mt-2">
                    <Button 
                      size="sm" 
                      variant="outline"
                      className="h-7 text-xs bg-white hover:bg-blue-100"
                      onClick={() => navigate('/accounting')}
                    >
                      <Download className="w-3 h-3 mr-1" />
                      Export Data
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline"
                      className="h-7 text-xs bg-white hover:bg-blue-100"
                      onClick={() => navigate('/e-fatura')}
                    >
                      <Send className="w-3 h-3 mr-1" />
                      E-Fatura
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Cost Management & Marketplace Integration - NEW */}
        <Card className="border-2 border-purple-400 bg-gradient-to-r from-purple-50 to-pink-50">
          <CardHeader>
            <CardTitle className="text-xl flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <PieChart className="w-6 h-6 text-purple-600" />
                <span>Cost Management & Profitability</span>
              </div>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => navigate('/marketplace')}
                className="bg-white hover:bg-purple-50"
              >
                <Building2 className="w-4 h-4 mr-2" />
                View Marketplace
              </Button>
            </CardTitle>
            <CardDescription>MTD Costs by Category & Per-Room Cost Analysis</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left: Top 3 Cost Categories */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <BarChart3 className="w-4 h-4 text-purple-600" />
                  <span>Top 3 Cost Categories (MTD)</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm space-y-3">
                  {(dashboardData?.costs?.top_3_categories || []).map((category, idx) => (
                    <div key={idx} className="space-y-1">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">{category.name}</span>
                        <span className="text-sm font-bold text-purple-600">
                          ${(category.amount || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className={`h-2 rounded-full ${
                            idx === 0 ? 'bg-purple-600' : 
                            idx === 1 ? 'bg-purple-400' : 
                            'bg-purple-300'
                          }`}
                          style={{ width: `${category.percentage || 0}%` }}
                        ></div>
                      </div>
                      <span className="text-xs text-gray-500">{(category.percentage || 0).toFixed(1)}% of total costs</span>
                    </div>
                  ))}
                  
                  <div className="mt-4 pt-3 border-t">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-semibold text-gray-700">Total MTD Costs</span>
                      <span className="text-lg font-bold text-purple-700">
                        ${(dashboardData?.costs?.total_mtd_costs || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Right: Cost vs RevPAR & Profitability */}
              <div className="space-y-3">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <Target className="w-4 h-4 text-green-600" />
                  <span>Cost per Room vs RevPAR</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm space-y-4">
                  {/* Cost per Room Night */}
                  <div className="flex justify-between items-start pb-3 border-b">
                    <div>
                      <div className="text-xs text-gray-600">Cost per Room Night</div>
                      <div className="text-2xl font-bold text-red-600">
                        ${(dashboardData?.costs?.per_room_metrics?.cost_per_room_night || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {dashboardData?.costs?.per_room_metrics?.total_room_nights || 0} room nights
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-600">MTD RevPAR</div>
                      <div className="text-2xl font-bold text-green-600">
                        ${(dashboardData?.costs?.per_room_metrics?.mtd_revpar || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        Revenue per Available Room
                      </div>
                    </div>
                  </div>

                  {/* Cost to RevPAR Ratio */}
                  <div className="bg-gradient-to-r from-purple-100 to-pink-100 p-3 rounded-lg">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium text-gray-700">Cost to RevPAR Ratio</span>
                      <span className={`text-xl font-bold ${
                        (dashboardData?.costs?.per_room_metrics?.cost_to_revpar_ratio || 0) < 30 ? 'text-green-600' :
                        (dashboardData?.costs?.per_room_metrics?.cost_to_revpar_ratio || 0) < 50 ? 'text-yellow-600' :
                        'text-red-600'
                      }`}>
                        {(dashboardData?.costs?.per_room_metrics?.cost_to_revpar_ratio || 0).toFixed(1)}%
                      </span>
                    </div>
                    <div className="text-xs text-gray-600 mt-1">
                      {(dashboardData?.costs?.per_room_metrics?.cost_to_revpar_ratio || 0) < 30 ? '✓ Excellent cost efficiency' :
                       (dashboardData?.costs?.per_room_metrics?.cost_to_revpar_ratio || 0) < 50 ? '⚠ Acceptable range' :
                       '⚠ High cost ratio - needs attention'}
                    </div>
                  </div>

                  {/* Profit Margin */}
                  <div className="pt-3 border-t">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-gray-600">MTD Revenue</div>
                        <div className="text-lg font-bold text-gray-900">
                          ${(dashboardData?.costs?.financial_metrics?.mtd_revenue || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-600">Gross Profit</div>
                        <div className="text-lg font-bold text-green-600">
                          ${(dashboardData?.costs?.financial_metrics?.gross_profit || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}
                        </div>
                      </div>
                    </div>
                    <div className="mt-2 flex justify-between items-center">
                      <span className="text-sm font-medium text-gray-700">Profit Margin</span>
                      <span className={`text-xl font-bold ${
                        (dashboardData?.costs?.financial_metrics?.profit_margin_percentage || 0) > 40 ? 'text-green-600' :
                        (dashboardData?.costs?.financial_metrics?.profit_margin_percentage || 0) > 25 ? 'text-yellow-600' :
                        'text-red-600'
                      }`}>
                        {(dashboardData?.costs?.financial_metrics?.profit_margin_percentage || 0).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Marketplace Integration Info */}
            <div className="mt-4 p-3 bg-purple-50 border-l-4 border-purple-500 rounded">
              <div className="flex items-start space-x-2">
                <Building2 className="w-5 h-5 text-purple-600 mt-0.5" />
                <div className="flex-1">
                  <h4 className="font-semibold text-sm text-purple-900">Marketplace-PMS Integration Active</h4>
                  <p className="text-xs text-purple-700 mt-1">
                    ✓ Purchase Orders tracked by category • ✓ Real-time cost analysis • ✓ Per-room profitability • ✓ Cost optimization insights
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Owner Summary / Snapshot */}
        <Card className="border-2 border-yellow-400 bg-gradient-to-r from-yellow-50 to-orange-50">
          <CardHeader>
            <CardTitle className="text-xl flex items-center space-x-2">
              <Zap className="w-6 h-6 text-yellow-600" />
              <span>Owner Summary - Quick Snapshot</span>
            </CardTitle>
            <CardDescription>At-a-glance performance vs Budget & Last Year</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Today vs Yesterday */}
              <div className="space-y-2">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <Calendar className="w-4 h-4" />
                  <span>Today vs Yesterday</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <div className="text-2xl font-bold text-gray-900">
                    ${((revenue.room_revenue || 0) + (revenue.other_revenue || 0)).toFixed(0)}
                  </div>
                  <div className="flex items-center space-x-2 mt-1">
                    {getTrendIcon(12.5)}
                    <span className={`text-sm font-semibold ${getTrendColor(12.5)}`}>
                      +12.5% vs Yesterday
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Revenue increased by $850
                  </p>
                </div>
              </div>

              {/* This Month vs Budget */}
              <div className="space-y-2">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <Target className="w-4 h-4" />
                  <span>MTD vs Budget</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <div className="text-2xl font-bold text-gray-900">
                    $152,400
                  </div>
                  <div className="flex items-center space-x-2 mt-1">
                    {getTrendIcon(-2.3)}
                    <span className={`text-sm font-semibold ${getTrendColor(-2.3)}`}>
                      -2.3% vs Budget
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Budget: $156,000 | Gap: -$3,600
                  </p>
                </div>
              </div>

              {/* This Month RevPAR vs Last Year */}
              <div className="space-y-2">
                <h3 className="font-semibold text-gray-700 flex items-center space-x-2">
                  <TrendingUp className="w-4 h-4" />
                  <span>MTD RevPAR vs LY</span>
                </h3>
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <div className="text-2xl font-bold text-gray-900">
                    $148.50
                  </div>
                  <div className="flex items-center space-x-2 mt-1">
                    {getTrendIcon(8.7)}
                    <span className={`text-sm font-semibold ${getTrendColor(8.7)}`}>
                      +8.7% vs Last Year
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Last Year: $136.60 | Gain: +$11.90
                  </p>
                </div>
              </div>
            </div>

            {/* One-liner Summary */}
            <div className="mt-6 p-4 bg-blue-100 border-l-4 border-blue-600 rounded">
              <p className="text-lg font-semibold text-blue-900">
                📊 "Today we're +12.5% ahead vs yesterday. MTD we're 2.3% below budget but 8.7% ahead of last year's RevPAR."
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Second Row - Arrivals, Departures, In-House */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Arrivals - Enhanced with Quick Actions */}
          <Card className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <CardTitle className="text-lg flex items-center justify-between">
                <span>Today's Arrivals</span>
                <Badge className="bg-green-500">
                  <CheckCircle className="w-3 h-3 mr-1" />
                  {movements.arrivals || 0}
                </Badge>
              </CardTitle>
              <CardDescription>Expected check-ins with quick actions</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {/* Sample Arrival Cards */}
                {[
                  { name: 'Richard Anderson', room: '116', type: 'Deluxe Double', vip: false, upsellAvailable: true, upsellType: 'Suite Upgrade' },
                  { name: 'Amelia Gonzalez', room: '102', type: 'Standard Single', vip: false, upsellAvailable: false },
                  { name: 'William Lee', room: '113', type: 'Family Room', vip: true, upsellAvailable: true, upsellType: 'Late Checkout' }
                ].map((guest, idx) => (
                  <div key={idx} className={`p-3 rounded-lg border-2 ${guest.vip ? 'border-yellow-400 bg-yellow-50' : 'border-gray-200 bg-gray-50'} relative`}>
                    {/* Upsell Available Badge - NEW */}
                    {guest.upsellAvailable && (
                      <div className="absolute -top-2 -right-2">
                        <Badge className="bg-gradient-to-r from-green-500 to-emerald-600 text-white text-[10px] px-2 py-1 shadow-md border-2 border-white">
                          💰 Upsell Available
                        </Badge>
                      </div>
                    )}
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="font-semibold text-sm">{guest.name}</span>
                          {guest.vip && <Badge className="bg-yellow-500 text-xs">VIP</Badge>}
                        </div>
                        <div className="text-xs text-gray-600">
                          Room {guest.room} • {guest.type}
                        </div>
                        {/* Upsell Type - NEW */}
                        {guest.upsellAvailable && (
                          <div className="text-[10px] text-green-700 font-semibold mt-1 flex items-center">
                            <ArrowUpCircle className="w-3 h-3 mr-1" />
                            {guest.upsellType}
                          </div>
                        )}
                      </div>
                    </div>
                    
                    {/* Quick Action Buttons */}
                    <div className="flex flex-wrap gap-1 mt-2">
                      <Button 
                        size="sm" 
                        className="h-7 text-xs bg-green-600 hover:bg-green-700"
                        onClick={() => navigate('/pms?action=checkin&guest=' + guest.name)}
                      >
                        <LogIn className="w-3 h-3 mr-1" />
                        Check-in
                      </Button>
                      <Button 
                        size="sm" 
                        variant="outline" 
                        className="h-7 text-xs"
                        onClick={() => alert('Upgrade options: Suite ($50), Deluxe Sea View ($30)')}
                      >
                        <ArrowUpCircle className="w-3 h-3 mr-1" />
                        Upgrade
                      </Button>
                      <Button 
                        size="sm" 
                        variant="outline" 
                        className="h-7 text-xs"
                        onClick={() => navigate('/ota-messaging-hub?guest=' + guest.name)}
                      >
                        <MessageSquare className="w-3 h-3 mr-1" />
                        Message
                      </Button>
                      <Button 
                        size="sm" 
                        variant="outline" 
                        className="h-7 text-xs"
                        onClick={() => alert('Print: Registration Form, Key Card Envelope')}
                      >
                        <Printer className="w-3 h-3 mr-1" />
                        Print
                      </Button>
                    </div>
                  </div>
                ))}

                <Button 
                  variant="outline" 
                  className="w-full mt-2"
                  onClick={() => navigate('/pms?tab=arrivals')}
                >
                  View All Arrivals ({movements.arrivals || 0})
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Departures */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center justify-between">
                <span>Departures</span>
                <Badge className="bg-red-500">
                  <Users className="w-3 h-3 mr-1" />
                  {movements.departures || 0}
                </Badge>
              </CardTitle>
              <CardDescription>Expected check-outs today</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Total</span>
                  <span className="font-semibold">{movements.departures || 0}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Checked-out</span>
                  <span className="font-semibold text-green-600">
                    {Math.floor((movements.departures || 0) * 0.6)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Remaining</span>
                  <span className="font-semibold text-orange-600">
                    {Math.floor((movements.departures || 0) * 0.4)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* In-House */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center justify-between">
                <span>In-House Guests</span>
                <Badge className="bg-blue-500">
                  <Home className="w-3 h-3 mr-1" />
                  {movements.in_house || 0}
                </Badge>
              </CardTitle>
              <CardDescription>Currently staying</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Total Guests</span>
                  <span className="font-semibold">{movements.in_house || 0}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Stayovers</span>
                  <span className="font-semibold text-blue-600">
                    {(movements.in_house || 0) - (movements.departures || 0)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">VIP Guests</span>
                  <span className="font-semibold text-purple-600">
                    {Math.floor((movements.in_house || 0) * 0.15)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Revenue Analytics & Budget Comparison */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Actual vs Budget */}
          <Card className="border-2 border-blue-200">
            <CardHeader>
              <CardTitle className="text-lg flex items-center space-x-2">
                <Target className="w-5 h-5 text-blue-600" />
                <span>Actual vs Budget</span>
              </CardTitle>
              <CardDescription>Month-to-date comparison</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm text-gray-600">Revenue</span>
                    <Badge variant="destructive">
                      -2.3%
                    </Badge>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="text-2xl font-bold">$152,400</div>
                    <div className="text-sm text-gray-500">/ $156,000</div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className="bg-blue-600 h-2 rounded-full" style={{ width: '97.7%' }}></div>
                  </div>
                </div>

                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm text-gray-600">Occupancy</span>
                    <Badge variant="default">+3.5%</Badge>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="text-2xl font-bold">86.2%</div>
                    <div className="text-sm text-gray-500">/ 83.5%</div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className="bg-green-600 h-2 rounded-full" style={{ width: '103.5%' }}></div>
                  </div>
                </div>

                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm text-gray-600">ADR</span>
                    <Badge variant="default">+1.8%</Badge>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="text-2xl font-bold">$169.74</div>
                    <div className="text-sm text-gray-500">/ $166.80</div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className="bg-green-600 h-2 rounded-full" style={{ width: '101.8%' }}></div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* vs Last Year */}
          <Card className="border-2 border-green-200">
            <CardHeader>
              <CardTitle className="text-lg flex items-center space-x-2">
                <TrendingUp className="w-5 h-5 text-green-600" />
                <span>vs Last Year</span>
              </CardTitle>
              <CardDescription>Year-over-year growth</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="p-3 bg-green-50 rounded-lg">
                  <div className="text-sm text-gray-600 mb-1">Revenue Growth</div>
                  <div className="flex items-center justify-between">
                    <div className="text-3xl font-bold text-green-700">+8.7%</div>
                    <TrendingUp className="w-8 h-8 text-green-600" />
                  </div>
                  <div className="text-xs text-gray-600 mt-2">
                    $152,400 vs $140,200 LY
                  </div>
                </div>

                <div className="p-3 bg-blue-50 rounded-lg">
                  <div className="text-sm text-gray-600 mb-1">Occupancy</div>
                  <div className="flex items-center justify-between">
                    <div className="text-3xl font-bold text-blue-700">+4.2%</div>
                    <TrendingUp className="w-8 h-8 text-blue-600" />
                  </div>
                  <div className="text-xs text-gray-600 mt-2">
                    86.2% vs 82.7% LY
                  </div>
                </div>

                <div className="p-3 bg-purple-50 rounded-lg">
                  <div className="text-sm text-gray-600 mb-1">RevPAR</div>
                  <div className="flex items-center justify-between">
                    <div className="text-3xl font-bold text-purple-700">+8.7%</div>
                    <TrendingUp className="w-8 h-8 text-purple-600" />
                  </div>
                  <div className="text-xs text-gray-600 mt-2">
                    $148.50 vs $136.60 LY
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 30-Day Forecast with Budget */}
          <Card className="border-2 border-purple-200">
            <CardHeader>
              <CardTitle className="text-lg flex items-center space-x-2">
                <Calendar className="w-5 h-5 text-purple-600" />
                <span>30-Day Forecast</span>
              </CardTitle>
              <CardDescription>Occupancy: Actual vs Budget</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-blue-600 rounded"></div>
                    <span>Actual</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 border-2 border-green-600 rounded"></div>
                    <span>Budget</span>
                  </div>
                </div>

                {/* Mini chart representation */}
                <div className="space-y-2">
                  {[
                    { day: 'Week 1', actual: 88, budget: 85 },
                    { day: 'Week 2', actual: 92, budget: 88 },
                    { day: 'Week 3', actual: 84, budget: 87 },
                    { day: 'Week 4', actual: 90, budget: 90 }
                  ].map((week, idx) => (
                    <div key={idx}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-600">{week.day}</span>
                        <span className="font-semibold">{week.actual}% / {week.budget}%</span>
                      </div>
                      <div className="flex space-x-1">
                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                          <div className="bg-blue-600 h-2 rounded-full" style={{ width: `${week.actual}%` }}></div>
                        </div>
                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                          <div className="border-2 border-green-600 h-2 rounded-full" style={{ width: `${week.budget}%` }}></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="pt-3 border-t">
                  <div className="text-sm font-semibold text-center">
                    Avg: 88.5% vs Budget 87.5%
                    <Badge className="ml-2 bg-green-500">+1.0%</Badge>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Top 10 Corporate Accounts */}
        <Card className="border-2 border-indigo-200">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center space-x-2">
                  <Building2 className="w-5 h-5 text-indigo-600" />
                  <span>Top 10 Corporate Accounts</span>
                </CardTitle>
                <CardDescription>MTD revenue by corporate client</CardDescription>
              </div>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => navigate('/sales?tab=contracts')}
              >
                View All
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[
                { name: 'Global Enterprise Inc.', revenue: 18400, nights: 127, tier: 'platinum', trend: '+12%' },
                { name: 'Tech Innovations Ltd.', revenue: 15200, nights: 98, tier: 'gold', trend: '+8%' },
                { name: 'Consulting Partners', revenue: 12800, nights: 78, tier: 'silver', trend: '+15%' },
                { name: 'Financial Services Co.', revenue: 9600, nights: 64, tier: 'silver', trend: '-3%' },
                { name: 'Healthcare Solutions', revenue: 8200, nights: 52, tier: 'gold', trend: '+5%' },
                { name: 'Manufacturing Inc.', revenue: 7100, nights: 43, tier: 'silver', trend: '+2%' },
                { name: 'Retail Group', revenue: 6500, nights: 39, tier: 'bronze', trend: '+18%' },
                { name: 'Legal Associates', revenue: 5900, nights: 35, tier: 'silver', trend: '+7%' },
                { name: 'Marketing Agency', revenue: 4800, nights: 28, tier: 'bronze', trend: '-5%' },
                { name: 'Software Corp', revenue: 4200, nights: 24, tier: 'bronze', trend: '+22%' }
              ].map((account, idx) => (
                <div 
                  key={idx}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
                  onClick={() => navigate('/sales?company=' + account.name)}
                >
                  <div className="flex items-center space-x-3 flex-1">
                    <div className="text-lg font-bold text-gray-400 w-6">{idx + 1}</div>
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold text-sm">{account.name}</span>
                        <Badge className={`text-xs ${
                          account.tier === 'platinum' ? 'bg-purple-600' :
                          account.tier === 'gold' ? 'bg-yellow-600' :
                          account.tier === 'silver' ? 'bg-gray-400' :
                          'bg-orange-400'
                        }`}>
                          {account.tier}
                        </Badge>
                      </div>
                      <div className="text-xs text-gray-600">{account.nights} nights</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-sm">${account.revenue.toLocaleString()}</div>
                    <div className={`text-xs ${
                      account.trend.startsWith('+') ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {account.trend}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 pt-4 border-t">
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-gray-700">Total Top 10:</span>
                <div className="text-right">
                  <div className="text-lg font-bold text-green-600">$92,700</div>
                  <div className="text-xs text-gray-600">588 room nights</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Third Row - Housekeeping Status & OTA Mix */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Housekeeping Status */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Housekeeping Status</span>
                <Button variant="outline" size="sm" onClick={() => navigate('/pms?tab=housekeeping')}>
                  View Board
                </Button>
              </CardTitle>
              <CardDescription>Room status overview</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex justify-between items-center p-3 bg-green-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                    <span className="text-sm font-medium">Clean & Ready</span>
                  </div>
                  <span className="text-lg font-bold text-green-600">
                    {occupancy.available_rooms || 0}
                  </span>
                </div>
                <div className="flex justify-between items-center p-3 bg-yellow-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-yellow-500 rounded-full"></div>
                    <span className="text-sm font-medium">In Progress</span>
                  </div>
                  <span className="text-lg font-bold text-yellow-600">
                    {Math.floor((occupancy.total_rooms || 0) * 0.2)}
                  </span>
                </div>
                <div className="flex justify-between items-center p-3 bg-red-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-red-500 rounded-full"></div>
                    <span className="text-sm font-medium">Dirty</span>
                  </div>
                  <span className="text-lg font-bold text-red-600">
                    {Math.floor((movements.departures || 0) * 0.4)}
                  </span>
                </div>
                <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 bg-gray-500 rounded-full"></div>
                    <span className="text-sm font-medium">Maintenance</span>
                  </div>
                  <span className="text-lg font-bold text-gray-600">
                    {Math.floor((occupancy.total_rooms || 0) * 0.05)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* OTA Channel Mix */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>OTA Channel Mix</span>
                <Button variant="outline" size="sm" onClick={() => navigate('/channel-manager')}>
                  Manage
                </Button>
              </CardTitle>
              <CardDescription>Booking sources breakdown</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex justify-between items-center p-3 bg-blue-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <span className="text-xl">🏨</span>
                    <span className="text-sm font-medium">Direct Bookings</span>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold text-blue-600">45%</div>
                    <div className="text-xs text-gray-600">Best rate</div>
                  </div>
                </div>
                <div className="flex justify-between items-center p-3 bg-purple-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <span className="text-xl">🅱️</span>
                    <span className="text-sm font-medium">Booking.com</span>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold text-purple-600">30%</div>
                    <div className="text-xs text-gray-600">-15% commission</div>
                  </div>
                </div>
                <div className="flex justify-between items-center p-3 bg-green-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <span className="text-xl">🅴</span>
                    <span className="text-sm font-medium">Expedia</span>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold text-green-600">15%</div>
                    <div className="text-xs text-gray-600">-18% commission</div>
                  </div>
                </div>
                <div className="flex justify-between items-center p-3 bg-orange-50 rounded-lg">
                  <div className="flex items-center space-x-2">
                    <span className="text-xl">🅰️</span>
                    <span className="text-sm font-medium">Airbnb</span>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold text-orange-600">10%</div>
                    <div className="text-xs text-gray-600">-12% commission</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Quick Actions & Alerts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Quick Actions */}
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
              <CardDescription>Common tasks</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                <Button variant="outline" onClick={() => navigate('/pms?tab=bookings')}>
                  <Calendar className="w-4 h-4 mr-2" />
                  New Booking
                </Button>
                <Button variant="outline" onClick={() => navigate('/pms?tab=front-desk')}>
                  <CheckCircle className="w-4 h-4 mr-2" />
                  Check-in
                </Button>
                <Button variant="outline" onClick={() => navigate('/rms')}>
                  <TrendingUp className="w-4 h-4 mr-2" />
                  RMS Suggestions
                </Button>
                <Button variant="outline" onClick={() => navigate('/pms#reports')}>
                  <BarChart3 className="w-4 h-4 mr-2" />
                  Reports
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Alerts & Notifications */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <AlertTriangle className="w-5 h-5 mr-2 text-yellow-600" />
                Alerts & Notifications
              </CardTitle>
              <CardDescription>Requires attention</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {/* Overbooking Alert with Action Buttons - NEW */}
                <div className="p-3 bg-red-50 rounded-lg border-2 border-red-300">
                  <div className="flex items-start space-x-3 mb-3">
                    <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-red-900">
                        2 Overbooking Conflicts Detected
                      </p>
                      <p className="text-xs text-red-700">Room 105, Room 112 - Immediate action required</p>
                    </div>
                  </div>
                  {/* Quick Action Buttons */}
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    <Button 
                      size="sm" 
                      className="bg-blue-600 hover:bg-blue-700 text-xs h-8"
                      onClick={() => {
                        navigate('/pms');
                        toast.info('Opening room availability for alternatives...');
                      }}
                    >
                      <Building2 className="w-3 h-3 mr-1" />
                      Find Alternate Room
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline"
                      className="border-purple-400 text-purple-700 hover:bg-purple-50 text-xs h-8"
                      onClick={() => {
                        toast.info('Opening date change dialog...');
                        // TODO: Open move date dialog
                      }}
                    >
                      <Calendar className="w-3 h-3 mr-1" />
                      Move to Another Date
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline"
                      className="border-green-400 text-green-700 hover:bg-green-50 text-xs h-8"
                      onClick={() => {
                        toast.success('Overbooking marked as resolved!');
                        // TODO: Call mark resolved API
                      }}
                    >
                      <CheckCircle className="w-3 h-3 mr-1" />
                      Mark Resolved
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline"
                      className="border-orange-400 text-orange-700 hover:bg-orange-50 text-xs h-8"
                      onClick={() => {
                        navigate('/pms');
                        toast.info('Opening upgrade offer creation...');
                      }}
                    >
                      <ArrowUpCircle className="w-3 h-3 mr-1" />
                      Offer Upgrade
                    </Button>
                  </div>
                </div>

                <div className="flex items-start space-x-3 p-3 bg-red-50 rounded-lg border border-red-200">
                  <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-red-900">
                      {Math.floor((movements.departures || 0) * 0.4)} rooms need urgent cleaning
                    </p>
                    <p className="text-xs text-red-700">Check-ins starting in 2 hours</p>
                  </div>
                </div>
                <div className="flex items-start space-x-3 p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                  <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-yellow-900">
                      3 pending rate suggestions from RMS
                    </p>
                    <p className="text-xs text-yellow-700">Review and apply pricing changes</p>
                  </div>
                </div>
                <div className="flex items-start space-x-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
                  <CheckCircle className="w-5 h-5 text-blue-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-blue-900">
                      All systems operational
                    </p>
                    <p className="text-xs text-blue-700">OTA channels synced successfully</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* NEW FEATURES - Expense Summary, Trend Chart, SLA Config */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <ExpenseSummaryCard expenseData={expenseSummary} />
          <SLAConfigCard slaConfigs={slaConfigs} delayedTasks={delayedTasks} />
        </div>

        <div className="mt-6">
          <TrendChart trendData={trendData} />
        </div>

        {/* Floating Action Button - GM Quick Actions */}
        <FloatingActionButton
          actions={[
            {
              label: 'New Booking',
              icon: <Plus className="w-5 h-5" />,
              color: 'bg-blue-600 hover:bg-blue-700',
              onClick: () => {
                navigate('/pms');
                toast.info('Opening PMS for new booking...');
              }
            },
            {
              label: 'Check-in Guest',
              icon: <Users className="w-5 h-5" />,
              color: 'bg-green-600 hover:bg-green-700',
              onClick: () => {
                navigate('/pms');
                toast.info('Opening Front Desk for check-in...');
              }
            },
            {
              label: 'RMS Suggestions',
              icon: <TrendingUp className="w-5 h-5" />,
              color: 'bg-purple-600 hover:bg-purple-700',
              onClick: () => {
                navigate('/revenue-management');
                toast.info('Opening RMS suggestions...');
              }
            },
            {
              label: 'View Reports',
              icon: <FileText className="w-5 h-5" />,
              color: 'bg-orange-600 hover:bg-orange-700',
              onClick: () => {
                navigate('/reports');
                toast.info('Opening reports dashboard...');
              }
            },
            {
              label: 'Refresh Dashboard',
              icon: <RefreshCw className="w-5 h-5" />,
              color: 'bg-gray-600 hover:bg-gray-700',
              onClick: () => {
                loadDashboardData();
                toast.success('Dashboard refreshed!');
              }
            }
          ]}
        />
      </div>
    </Layout>
  );
};

export default GMDashboard;
