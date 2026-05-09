import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useTranslation } from 'react-i18next';

export function OccupancyChart({ dateRange, bookings, rooms, isBookingOnDate, isWeekend, formatDateWithDay }) {
  const { t } = useTranslation();
  if (!dateRange?.length || !rooms?.length) return null;

  // Calculate occupancy for each date
  const occupancyData = dateRange.map((date) => {
    const activeBookings = bookings.filter(b => {
      if (b.status === 'cancelled' || b.status === 'no_show') return false;
      return isBookingOnDate(b, date);
    });
    return {
      date,
      count: activeBookings.length,
      total: rooms.length,
      pct: Math.round((activeBookings.length / rooms.length) * 100),
    };
  });

  const maxPct = Math.max(...occupancyData.map(d => d.pct), 1);
  const chartWidth = dateRange.length * 70;
  const chartHeight = 60;

  // Generate SVG path
  const points = occupancyData.map((d, i) => {
    const x = (i / Math.max(dateRange.length - 1, 1)) * (chartWidth - 20) + 10;
    const y = chartHeight - (d.pct / Math.max(maxPct, 1)) * (chartHeight - 10) + 5;
    return `${x},${y}`;
  });
  const linePath = `M ${points.join(' L ')}`;
  const areaPath = `${linePath} L ${(chartWidth - 10)},${chartHeight} L 10,${chartHeight} Z`;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3" data-testid="occupancy-chart">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-gray-500">Doluluk</span>
      </div>
      <div className="overflow-x-auto">
        <svg width={chartWidth} height={chartHeight + 20} className="block">
          {/* Grid lines */}
          <line x1="10" y1={chartHeight} x2={chartWidth - 10} y2={chartHeight} stroke="#e5e7eb" strokeWidth="0.5" />
          <line x1="10" y1={chartHeight / 2} x2={chartWidth - 10} y2={chartHeight / 2} stroke="#e5e7eb" strokeWidth="0.5" strokeDasharray="3,3" />
          {/* Area fill */}
          <path d={areaPath} fill="url(#occupancy-gradient)" opacity="0.3" />
          {/* Line */}
          <path d={linePath} fill="none" stroke="#f97316" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          {/* Dots and labels */}
          {occupancyData.map((d, i) => {
            const x = (i / Math.max(dateRange.length - 1, 1)) * (chartWidth - 20) + 10;
            const y = chartHeight - (d.pct / Math.max(maxPct, 1)) * (chartHeight - 10) + 5;
            return (
              <g key={i}>
                <circle cx={x} cy={y} r="2.5" fill="#f97316" stroke="white" strokeWidth="1" />
                <text x={x} y={chartHeight + 14} textAnchor="middle" className="text-[8px] fill-gray-400">{d.count}</text>
              </g>
            );
          })}
          <defs>
            <linearGradient id="occupancy-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f97316" stopOpacity="0.6" />
              <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
  );
}

export function CalendarLegend() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-4 text-xs text-gray-500" data-testid="calendar-legend">
      <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-amber-400" /> Expedia</div>
      <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-blue-500" /> Tatilbudur/Online</div>
      <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-blue-600" /> Booking.com</div>
      <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-gray-600" /> Kesin</div>
      <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-emerald-500" /> {t('cm.components_calendar_CalendarWidgets.musait')}</div>
      <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-red-500" /> {t('cm.components_calendar_CalendarWidgets.dolu')}</div>
    </div>
  );
}

export function CalendarStats({ bookings, rooms, dateRange, isBookingOnDate }) {
  const { t } = useTranslation();
  const todayBookings = bookings.filter(b => b.status !== 'cancelled' && b.status !== 'no_show' && isBookingOnDate(b, new Date()));
  const occupancyPct = rooms.length > 0 ? Math.round((todayBookings.length / rooms.length) * 100) : 0;
  const todayRevenue = todayBookings.reduce((sum, b) => {
    const nights = Math.max(1, Math.ceil((new Date(b.check_out) - new Date(b.check_in)) / 86400000));
    return sum + (b.total_amount || 0) / nights;
  }, 0);
  const adr = todayBookings.length > 0 ? Math.round(todayRevenue / todayBookings.length) : 0;

  return (
    <div className="grid grid-cols-4 gap-3 mb-3" data-testid="calendar-stats">
      <Card className="bg-white border shadow-sm">
        <CardContent className="p-3 text-center">
          <div className="text-xs text-gray-500 font-medium">{t('cm.components_calendar_CalendarWidgets.bugun_dolu')}</div>
          <div className="text-lg font-bold text-gray-800">{todayBookings.length} / {rooms.length}</div>
        </CardContent>
      </Card>
      <Card className="bg-white border shadow-sm">
        <CardContent className="p-3 text-center">
          <div className="text-xs text-gray-500 font-medium">Doluluk</div>
          <div className="text-lg font-bold text-amber-600">{occupancyPct}%</div>
        </CardContent>
      </Card>
      <Card className="bg-white border shadow-sm">
        <CardContent className="p-3 text-center">
          <div className="text-xs text-gray-500 font-medium">{t('cm.components_calendar_CalendarWidgets.ort_gunluk_gelir')}</div>
          <div className="text-lg font-bold text-emerald-600">{adr.toLocaleString('tr-TR')} TL</div>
        </CardContent>
      </Card>
      <Card className="bg-white border shadow-sm">
        <CardContent className="p-3 text-center">
          <div className="text-xs text-gray-500 font-medium">{t('cm.components_calendar_CalendarWidgets.toplam_rev')}</div>
          <div className="text-lg font-bold text-blue-600">{Math.round(todayRevenue).toLocaleString('tr-TR')} TL</div>
        </CardContent>
      </Card>
    </div>
  );
}
