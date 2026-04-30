import { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useCurrency } from '@/context/CurrencyContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DollarSign,
  TrendingDown,
  Calendar,
  RefreshCw,
  Download,
  BarChart3,
  PieChart,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart as RePieChart,
  Pie,
  Cell,
} from 'recharts';

const COLORS = [
  '#0088FE', '#00C49F', '#FFBB28', '#FF8042',
  '#8884D8', '#82CA9D', '#FFC658', '#FF6B6B',
];

const CATEGORY_KEYS = [
  'salaries', 'utilities', 'supplies', 'maintenance',
  'marketing', 'rent', 'insurance', 'taxes', 'other',
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function monthStartISO() {
  const d = new Date();
  d.setDate(1);
  return d.toISOString().slice(0, 10);
}

function daysBetween(startISO, endISO) {
  const s = new Date(startISO);
  const e = new Date(endISO);
  const ms = e.getTime() - s.getTime();
  return Math.max(1, Math.round(ms / 86400000) + 1);
}

function csvEscape(value) {
  const s = String(value ?? '');
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export default function CostAnalyticsView() {
  const { t, i18n } = useTranslation();
  const { amount: fmtMoney, code: currencyCode } = useCurrency();

  const [loading, setLoading] = useState(true);
  const [expenses, setExpenses] = useState([]);
  const [startDate, setStartDate] = useState(monthStartISO());
  const [endDate, setEndDate] = useState(todayISO());

  const categoryLabel = useCallback(
    (key) => t(`costAnalytics.categories.${key}`, { defaultValue: key }),
    [t]
  );

  const loadExpenses = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      const res = await axios.get('/accounting/expenses', { params });
      setExpenses(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error('Cost analytics load failed:', err);
      toast.error(t('costAnalytics.loadError'));
      setExpenses([]);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, t]);

  useEffect(() => {
    loadExpenses();
  }, [loadExpenses]);

  const { totalCosts, byCategory, entriesCount } = useMemo(() => {
    const buckets = {};
    let total = 0;
    expenses.forEach((exp) => {
      const cat = exp.category || 'other';
      const amt = Number(exp.total_amount ?? exp.amount ?? 0) || 0;
      if (!buckets[cat]) buckets[cat] = { total: 0, count: 0 };
      buckets[cat].total += amt;
      buckets[cat].count += 1;
      total += amt;
    });
    return { totalCosts: total, byCategory: buckets, entriesCount: expenses.length };
  }, [expenses]);

  const categoryData = useMemo(
    () =>
      Object.entries(byCategory)
        .map(([key, data]) => ({
          key,
          name: categoryLabel(key),
          total: data.total,
          count: data.count,
          avg: data.count > 0 ? data.total / data.count : 0,
        }))
        .sort((a, b) => b.total - a.total),
    [byCategory, categoryLabel]
  );

  const periodDays = daysBetween(startDate, endDate);
  const dailyAvg = totalCosts / periodDays;

  const exportCsv = useCallback(() => {
    const headers = [
      t('costAnalytics.headers.category'),
      t('costAnalytics.headers.count'),
      t('costAnalytics.headers.total'),
      t('costAnalytics.headers.avg'),
      t('costAnalytics.headers.share'),
    ];
    const rows = categoryData.map((c) => {
      const share = totalCosts > 0 ? ((c.total / totalCosts) * 100).toFixed(2) : '0';
      return [c.name, c.count, c.total.toFixed(2), c.avg.toFixed(2), `${share}%`];
    });
    rows.push([
      t('costAnalytics.headers.totalRow'),
      entriesCount,
      totalCosts.toFixed(2),
      entriesCount > 0 ? (totalCosts / entriesCount).toFixed(2) : '0.00',
      '100%',
    ]);
    const csv = [headers, ...rows]
      .map((r) => r.map(csvEscape).join(','))
      .join('\n');
    const blob = new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cost-analytics_${startDate}_${endDate}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast.success(t('costAnalytics.exportSuccess'));
  }, [categoryData, totalCosts, entriesCount, startDate, endDate, t]);

  const numberFmt = useMemo(
    () => new Intl.NumberFormat(i18n.language || 'tr-TR'),
    [i18n.language]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-red-600" />
            {t('costAnalytics.title')}
          </h2>
          <p className="text-sm text-gray-600 mt-1">{t('costAnalytics.subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="cost-start" className="text-xs text-gray-600">
              {t('costAnalytics.startDate')}
            </Label>
            <Input
              id="cost-start"
              type="date"
              value={startDate}
              max={endDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-40"
            />
          </div>
          <div>
            <Label htmlFor="cost-end" className="text-xs text-gray-600">
              {t('costAnalytics.endDate')}
            </Label>
            <Input
              id="cost-end"
              type="date"
              value={endDate}
              min={startDate}
              max={todayISO()}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-40"
            />
          </div>
          <Button variant="outline" onClick={loadExpenses} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            {t('costAnalytics.refresh')}
          </Button>
          <Button variant="outline" onClick={exportCsv} disabled={categoryData.length === 0}>
            <Download className="w-4 h-4 mr-2" />
            {t('costAnalytics.exportCsv')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-red-50 to-red-100 border-red-200">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-red-600 font-medium">
                  {t('costAnalytics.kpi.total')}
                </p>
                <p className="text-2xl font-bold text-red-700 mt-1">{fmtMoney(totalCosts)}</p>
                <p className="text-xs text-red-600 mt-1">
                  {t('costAnalytics.kpi.periodDays', { days: periodDays })}
                </p>
              </div>
              <TrendingDown className="w-10 h-10 text-red-300" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-600 font-medium">
                  {t('costAnalytics.kpi.categories')}
                </p>
                <p className="text-2xl font-bold text-blue-700 mt-1">{categoryData.length}</p>
                <p className="text-xs text-blue-600 mt-1">
                  {t('costAnalytics.kpi.categoriesHint')}
                </p>
              </div>
              <PieChart className="w-10 h-10 text-blue-300" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-green-600 font-medium">
                  {t('costAnalytics.kpi.entries')}
                </p>
                <p className="text-2xl font-bold text-green-700 mt-1">
                  {numberFmt.format(entriesCount)}
                </p>
                <p className="text-xs text-green-600 mt-1">
                  {t('costAnalytics.kpi.entriesHint')}
                </p>
              </div>
              <BarChart3 className="w-10 h-10 text-green-300" />
            </div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-purple-50 to-purple-100 border-purple-200">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-purple-600 font-medium">
                  {t('costAnalytics.kpi.dailyAvg')}
                </p>
                <p className="text-2xl font-bold text-purple-700 mt-1">{fmtMoney(dailyAvg)}</p>
                <p className="text-xs text-purple-600 mt-1">
                  {t('costAnalytics.kpi.dailyAvgHint', { days: periodDays })}
                </p>
              </div>
              <Calendar className="w-10 h-10 text-purple-300" />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center text-base">
              <BarChart3 className="w-4 h-4 mr-2 text-blue-600" />
              {t('costAnalytics.byCategory')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {categoryData.length === 0 ? (
              <div className="text-center text-gray-400 py-12">
                {t('costAnalytics.empty')}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={categoryData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-30} textAnchor="end" height={80} />
                  <YAxis />
                  <Tooltip formatter={(value) => fmtMoney(value)} />
                  <Legend />
                  <Bar
                    dataKey="total"
                    fill="#3B82F6"
                    name={t('costAnalytics.headers.total')}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center text-base">
              <PieChart className="w-4 h-4 mr-2 text-purple-600" />
              {t('costAnalytics.distribution')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {categoryData.length === 0 ? (
              <div className="text-center text-gray-400 py-12">
                {t('costAnalytics.empty')}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <RePieChart>
                  <Pie
                    data={categoryData}
                    dataKey="total"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) =>
                      `${name}: %${(percent * 100).toFixed(0)}`
                    }
                    outerRadius={100}
                  >
                    {categoryData.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => fmtMoney(value)} />
                </RePieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('costAnalytics.detailsTitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          {categoryData.length === 0 ? (
            <div className="text-center text-gray-400 py-8">{t('costAnalytics.empty')}</div>
          ) : (
            <div className="space-y-2">
              {categoryData.map((cat, idx) => {
                const share =
                  totalCosts > 0 ? ((cat.total / totalCosts) * 100).toFixed(1) : '0';
                return (
                  <div
                    key={cat.key}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100 transition"
                  >
                    <div className="flex items-center gap-3 flex-1">
                      <div
                        className="w-3 h-3 rounded"
                        style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                      />
                      <div className="flex-1">
                        <p className="font-medium text-gray-900">{cat.name}</p>
                        <p className="text-xs text-gray-600">
                          {t('costAnalytics.entriesShort', { count: cat.count })}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-gray-900">{fmtMoney(cat.total)}</p>
                      <Badge variant="outline" className="mt-1">
                        %{share}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {categoryData.length > 0 && (
        <div className="rounded-md border border-blue-100 bg-blue-50/60 p-4 text-sm text-gray-700 flex items-start gap-3">
          <DollarSign className="w-4 h-4 mt-0.5 text-blue-600 shrink-0" />
          <div>
            <p className="font-medium text-gray-900 mb-1">
              {t('costAnalytics.summaryTitle')}
            </p>
            <p>
              {t('costAnalytics.summaryBody', {
                top: categoryData[0].name,
                topAmount: fmtMoney(categoryData[0].total),
                daily: fmtMoney(dailyAvg),
                currency: currencyCode,
              })}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export { CATEGORY_KEYS };
