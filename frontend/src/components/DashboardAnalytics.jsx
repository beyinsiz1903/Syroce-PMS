import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const axisTick = { fontSize: 10, fill: 'var(--dash-chart-axis, #666)' };
const gridStroke = 'var(--dash-chart-grid, #ccc)';
const dateLabel = value => new Date(value).getDate();
const fullDateLabel = value => new Date(value).toLocaleDateString();

export default function DashboardAnalytics({
  occupancyData,
  revenueData,
  trendData,
  formatMoney,
  currencySymbol,
}) {
  const { t } = useTranslation();

  return <section className="space-y-4" aria-label={t('dashboard.analyticsInsights')}>
      <h2 className="text-xl md:text-2xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
        {t('dashboard.analyticsInsights')}
      </h2>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t('dashboard.occupancyTrend')}</CardTitle>
            <CardDescription>{t('dashboard.dailyOccupancy')}</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={occupancyData}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
                <XAxis dataKey="date" tick={axisTick} tickFormatter={dateLabel} />
                <YAxis tick={axisTick} />
                <Tooltip labelFormatter={fullDateLabel} formatter={value => `${(Number(value) || 0).toFixed(1)}%`} />
                <Area type="monotone" dataKey="occupancy_rate" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} name={t('dashboard.chartOccupancy')} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t('dashboard.revenueTrend')}</CardTitle>
            <CardDescription>{t('dashboard.dailyRevenue')}</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={revenueData}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
                <XAxis dataKey="date" tick={axisTick} tickFormatter={dateLabel} />
                <YAxis tick={axisTick} />
                <Tooltip labelFormatter={fullDateLabel} formatter={value => formatMoney(value, { decimals: 0 })} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Bar dataKey="room_revenue" fill="#10b981" name={t('dashboard.chartRoom')} />
                <Bar dataKey="fnb_revenue" fill="#f59e0b" name={t('dashboard.chartFnB')} />
                <Bar dataKey="other_revenue" fill="#6366f1" name={t('dashboard.chartOther')} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t('dashboard.stayTrends', 'Konaklama Trendleri')}</CardTitle>
            <CardDescription>{t('dashboard.dailyBookings')}</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
                <XAxis dataKey="date" tick={axisTick} tickFormatter={dateLabel} />
                <YAxis yAxisId="left" tick={axisTick} />
                <YAxis yAxisId="right" orientation="right" tick={axisTick} />
                <Tooltip labelFormatter={fullDateLabel} />
                <Legend wrapperStyle={{ fontSize: '12px' }} />
                <Line yAxisId="left" type="monotone" dataKey="occupied_rooms" stroke="#8b5cf6" strokeWidth={2} name={t('dashboard.occupiedRooms', 'Dolu Odalar')} />
                <Line yAxisId="right" type="monotone" dataKey="adr" stroke="#10b981" strokeWidth={2} name={`ADR (${currencySymbol})`} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t('dashboard.revPARPerformance')}</CardTitle>
            <CardDescription>{t('dashboard.revPARDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
                <XAxis dataKey="date" tick={axisTick} tickFormatter={dateLabel} />
                <YAxis tick={axisTick} />
                <Tooltip labelFormatter={fullDateLabel} formatter={value => formatMoney(value, { decimals: 2 })} />
                <Area type="monotone" dataKey="revpar" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.4} name="RevPAR" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{t('dashboard.heatmap30Day')}</CardTitle>
          <CardDescription>{t('dashboard.heatmapDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-10 gap-1">
            {occupancyData.slice(0, 30).map((day, index) => {
              const rawRate = Number(day?.occupancy_rate) || 0;
              const rate = Math.min(Math.max(rawRate, 0), 100);
              const color = rate >= 90 ? 'bg-red-600' : rate >= 80 ? 'bg-amber-500' : rate >= 70 ? 'bg-yellow-500' : rate >= 60 ? 'bg-green-500' : rate >= 50 ? 'bg-blue-500' : 'bg-gray-300';
              const title = rawRate > 100
                ? `${fullDateLabel(day.date)}: %${rate.toFixed(1)} (ham: %${rawRate.toFixed(1)} — overbooking)`
                : `${fullDateLabel(day.date)}: %${rate.toFixed(1)} doluluk`;
              return <div key={day.id || index} className={`${color} cursor-pointer rounded p-2 text-center text-xs font-semibold text-white transition-transform hover:scale-110`} title={title}>
                  {new Date(day.date).getDate()}
                  <div className="text-[10px]">{rate.toFixed(0)}%</div>
                </div>;
            })}
          </div>
          <div className="mt-4 flex justify-center gap-4 text-xs">
            {[['bg-gray-300', '<50%'], ['bg-blue-500', '50-60%'], ['bg-green-500', '60-70%'], ['bg-yellow-500', '70-80%'], ['bg-amber-500', '80-90%'], ['bg-red-600', '>90%']].map(([color, label]) => <div key={label} className="flex items-center gap-1">
                <div className={`h-3 w-3 rounded ${color}`} />
                <span>{label}</span>
              </div>)}
          </div>
        </CardContent>
      </Card>
    </section>;
}
