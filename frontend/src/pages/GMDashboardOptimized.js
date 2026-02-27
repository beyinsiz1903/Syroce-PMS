import { useQuery, useQueries } from '@tanstack/react-query';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, TrendingDown, DollarSign, Users, Bed, Calendar,
  Target, PieChart, BarChart3, Activity, Home, CheckCircle,
  AlertTriangle, FileText, Mail, Download, Zap, LogIn,
  ArrowUpCircle, MessageSquare, Key, Printer, Phone, Send,
  Building2, Settings, RefreshCw, Plus
} from 'lucide-react';
import FloatingActionButton from '@/components/FloatingActionButton';
import ExpenseSummaryCard from '@/components/ExpenseSummaryCard';
import TrendChart from '@/components/TrendChart';
import SLAConfigCard from '@/components/SLAConfigCard';
import { queryKeys } from '@/lib/queryClient';
import { useTranslation } from 'react-i18next';

// Skeleton component for loading state
const MetricSkeleton = () => (
  <Card>
    <CardHeader className="pb-2">
      <div className="h-4 bg-gray-200 rounded animate-pulse w-1/2"></div>
    </CardHeader>
    <CardContent>
      <div className="h-8 bg-gray-200 rounded animate-pulse w-3/4 mb-2"></div>
      <div className="h-3 bg-gray-200 rounded animate-pulse w-1/3"></div>
    </CardContent>
  </Card>
);

const GMDashboardOptimized = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  // Critical data - Load first (stale time: 1 minute)
  const { data: flashData, isLoading: flashLoading } = useQuery({
    queryKey: queryKeys.reports.dailyFlash(new Date().toISOString().split('T')[0]),
    queryFn: () => axios.get('/reports/daily-flash').then(res => res.data),
    staleTime: 60 * 1000, // 1 minute
    retry: 2,
  });

  const { data: occupancyData, isLoading: occupancyLoading } = useQuery({
    queryKey: queryKeys.pms.all,
    queryFn: () => axios.get('/pms/dashboard').then(res => res.data),
    staleTime: 60 * 1000,
    retry: 2,
  });

  // Secondary data - Load in parallel but less critical
  const secondaryQueries = useQueries({
    queries: [
      {
        queryKey: queryKeys.finance.snapshot(),
        queryFn: () => axios.get('/folio/dashboard-stats').then(res => res.data),
        staleTime: 5 * 60 * 1000, // 5 minutes
      },
      {
        queryKey: [...queryKeys.finance.all, 'snapshot-report'],
        queryFn: () => axios.get('/reports/finance-snapshot').then(res => res.data),
        staleTime: 5 * 60 * 1000,
      },
      {
        queryKey: [...queryKeys.reports.all, 'cost-summary'],
        queryFn: () => axios.get('/reports/cost-summary').then(res => res.data),
        staleTime: 5 * 60 * 1000,
      },
      {
        queryKey: queryKeys.finance.expenses('today'),
        queryFn: () => axios.get('/finance/expense-summary?period=today').then(res => res.data),
        staleTime: 2 * 60 * 1000, // 2 minutes
      },
      {
        queryKey: [...queryKeys.reports.all, 'trend-7day'],
        queryFn: () => axios.get('/analytics/7day-trend').then(res => res.data),
        staleTime: 10 * 60 * 1000, // 10 minutes
      },
      {
        queryKey: ['sla', 'configs'],
        queryFn: () => axios.get('/settings/sla').then(res => res.data),
        staleTime: 30 * 60 * 1000, // 30 minutes
      },
      {
        queryKey: ['tasks', 'delayed'],
        queryFn: () => axios.get('/tasks/delayed').then(res => res.data),
        staleTime: 2 * 60 * 1000,
      },
    ],
  });

  const [folioData, financeData, costsData, expenseData, trendData, slaData, delayedTasksData] = secondaryQueries;

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

  const calculateComparison = (current, previous) => {
    if (!previous || previous === 0) return 0;
    return ((current - previous) / previous * 100).toFixed(1);
  };

  // Show loading skeleton for critical data
  if (flashLoading || occupancyLoading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="gm-dashboard">
        <div className="space-y-4 p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(8)].map((_, i) => (
              <MetricSkeleton key={i} />
            ))}
          </div>
        </div>
      </Layout>
    );
  }

  const flash = flashData || {};
  const occupancy = occupancyData || {};
  const folio = folioData?.data || {};
  const finance = financeData?.data || {};
  const costs = costsData?.data || {};
  const expenseSummary = expenseData?.data || {};
  const trends = trendData?.data || { trend: [] };
  const slaConfigs = slaData?.data?.configs || [];
  const delayedTasks = delayedTasksData?.data?.delayed_tasks || [];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="gm-dashboard">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">GM Dashboard</h1>
            <p className="text-gray-600">Real-time hotel performance metrics</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              <Download className="w-4 h-4 mr-2" />
              Export PDF
            </Button>
            <Button variant="outline" size="sm">
              <Mail className="w-4 h-4 mr-2" />
              Email Report
            </Button>
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => {
                // Invalidate all queries to force refresh
                window.location.reload();
              }}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Critical Metrics - Always visible */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Occupancy */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Occupancy Rate</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{flash.occupancy?.rate || 0}%</div>
              <p className="text-xs text-gray-600 mt-1">
                {flash.occupancy?.occupied_rooms || 0} / {flash.occupancy?.total_rooms || 0} rooms
              </p>
            </CardContent>
          </Card>

          {/* Revenue */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Today's Revenue</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                ${(flash.revenue?.today || 0).toLocaleString()}
              </div>
              <div className="flex items-center gap-1 mt-1">
                {getTrendIcon(flash.revenue?.trend || 0)}
                <span className={`text-xs ${getTrendColor(flash.revenue?.trend || 0)}`}>
                  {flash.revenue?.trend > 0 ? '+' : ''}{flash.revenue?.trend || 0}% vs yesterday
                </span>
              </div>
            </CardContent>
          </Card>

          {/* ADR */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">ADR</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                ${(flash.financial?.adr || 0).toFixed(2)}
              </div>
              <p className="text-xs text-gray-600 mt-1">Average Daily Rate</p>
            </CardContent>
          </Card>

          {/* RevPAR */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">RevPAR</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                ${(flash.financial?.revpar || 0).toFixed(2)}
              </div>
              <p className="text-xs text-gray-600 mt-1">Revenue per Available Room</p>
            </CardContent>
          </Card>
        </div>

        {/* Secondary Metrics - Show with loading state */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Today's Arrivals</CardTitle>
            </CardHeader>
            <CardContent>
              {flash.arrivals !== undefined ? (
                <>
                  <div className="text-2xl font-bold">{flash.arrivals}</div>
                  <p className="text-xs text-gray-600 mt-1">Expected check-ins</p>
                </>
              ) : (
                <div className="h-8 bg-gray-200 rounded animate-pulse"></div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">Today's Departures</CardTitle>
            </CardHeader>
            <CardContent>
              {flash.departures !== undefined ? (
                <>
                  <div className="text-2xl font-bold">{flash.departures}</div>
                  <p className="text-xs text-gray-600 mt-1">Expected check-outs</p>
                </>
              ) : (
                <div className="h-8 bg-gray-200 rounded animate-pulse"></div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">In-House Guests</CardTitle>
            </CardHeader>
            <CardContent>
              {flash.inhouse !== undefined ? (
                <>
                  <div className="text-2xl font-bold">{flash.inhouse}</div>
                  <p className="text-xs text-gray-600 mt-1">Currently staying</p>
                </>
              ) : (
                <div className="h-8 bg-gray-200 rounded animate-pulse"></div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-600">New Bookings</CardTitle>
            </CardHeader>
            <CardContent>
              {flash.new_bookings !== undefined ? (
                <>
                  <div className="text-2xl font-bold">{flash.new_bookings}</div>
                  <p className="text-xs text-gray-600 mt-1">Today</p>
                </>
              ) : (
                <div className="h-8 bg-gray-200 rounded animate-pulse"></div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Charts and Additional Info */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Expense Summary */}
          {!expenseData.isLoading && expenseSummary && (
            <ExpenseSummaryCard data={expenseSummary} />
          )}

          {/* Trend Chart */}
          {!trendData.isLoading && trends && (
            <TrendChart data={trends} />
          )}
        </div>

        {/* SLA and Delayed Tasks */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {!slaData.isLoading && slaConfigs.length > 0 && (
            <div className="space-y-4">
              {slaConfigs.map((config, idx) => (
                <SLAConfigCard key={idx} config={config} />
              ))}
            </div>
          )}

          {!delayedTasksData.isLoading && delayedTasks.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-orange-500" />
                  Delayed Tasks ({delayedTasks.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {delayedTasks.slice(0, 5).map((task, idx) => (
                    <div key={idx} className="flex justify-between items-center p-2 bg-orange-50 rounded">
                      <div>
                        <div className="font-medium">{task.title || task.task_type}</div>
                        <div className="text-xs text-gray-600">
                          {task.room_number && `Room ${task.room_number}`}
                        </div>
                      </div>
                      <Badge variant="destructive">
                        {task.delay_hours}h delay
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <FloatingActionButton />
    </Layout>
  );
};

export default GMDashboardOptimized;
