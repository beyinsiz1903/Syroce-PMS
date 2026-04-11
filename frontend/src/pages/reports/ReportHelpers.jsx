import { Card, CardContent } from '@/components/ui/card';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export const COLORS = ['#2563EB', '#059669', '#D97706', '#DC2626', '#7C3AED', '#DB2777', '#0891B2', '#65A30D', '#EA580C', '#0D9488'];

export const formatCurrency = (val) => {
  if (val === undefined || val === null || isNaN(val)) return '₺0';
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(val);
};

export const formatNumber = (val) => {
  if (val === undefined || val === null) return '0';
  return new Intl.NumberFormat('tr-TR').format(val);
};

export const formatPercent = (val) => '%' + (val || 0).toFixed(1);

export const calcChange = (current, prev) => {
  if (!prev || prev === 0) return { pct: 0, direction: 'neutral' };
  const pct = ((current - prev) / prev * 100);
  return { pct: Math.abs(pct).toFixed(1), direction: pct >= 0 ? 'up' : 'down' };
};

export const KPICard = ({ title, value, prevValue, prevLabel, icon: Icon, color = 'blue' }) => {
  const change = calcChange(typeof value === 'number' ? value : 0, typeof prevValue === 'number' ? prevValue : 0);
  const colorMap = {
    blue: 'from-blue-500 to-blue-600', green: 'from-emerald-500 to-emerald-600',
    purple: 'from-violet-500 to-violet-600', amber: 'from-amber-500 to-amber-600',
    cyan: 'from-cyan-500 to-cyan-600', red: 'from-rose-500 to-rose-600',
    indigo: 'from-indigo-500 to-indigo-600', teal: 'from-teal-500 to-teal-600',
  };
  const isCurrency = /gelir|adr|rev|ciro|ödeme|tutar/i.test(title);
  const displayVal = typeof value === 'number' ? (isCurrency ? formatCurrency(value) : formatNumber(value)) : value;

  return (
    <Card className="hover:shadow-md transition-all border-0 shadow-sm bg-white" data-testid={`kpi-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <div className={`p-2 rounded-lg bg-gradient-to-br text-white ${colorMap[color] || colorMap.blue}`}>
            <Icon className="w-4 h-4" />
          </div>
          {prevValue !== undefined && Number(change.pct) > 0 && (
            <span className={`text-[11px] font-semibold flex items-center gap-0.5 px-2 py-0.5 rounded-full ${
              change.direction === 'up' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
            }`}>
              {change.direction === 'up' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
              {change.pct}%
            </span>
          )}
        </div>
        <p className="text-[11px] text-gray-500 font-medium uppercase tracking-wider">{title}</p>
        <p className="text-xl font-bold text-gray-900 mt-0.5">{displayVal}</p>
        {prevLabel && <p className="text-[10px] text-gray-400 mt-1">{prevLabel}</p>}
      </CardContent>
    </Card>
  );
};

export const CustomTooltip = ({ active, payload, label, formatter }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white/95 backdrop-blur-sm p-3 border border-gray-200 rounded-lg shadow-xl text-xs">
      <p className="font-semibold text-gray-800 mb-1.5 border-b pb-1">{label}</p>
      {payload.map((entry, idx) => (
        <p key={idx} style={{ color: entry.color }} className="flex items-center gap-1.5 py-0.5">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
          <span className="text-gray-600">{entry.name}:</span>
          <span className="font-medium">{formatter ? formatter(entry.value) : entry.value}</span>
        </p>
      ))}
    </div>
  );
};

export const SectionHeader = ({ title, description, actions }) => (
  <div className="flex items-start justify-between mb-5">
    <div>
      <h2 className="text-lg font-bold text-gray-900">{title}</h2>
      {description && <p className="text-sm text-gray-500 mt-0.5">{description}</p>}
    </div>
    {actions && <div className="flex gap-2">{actions}</div>}
  </div>
);

export const EmptyState = ({ icon: Icon, message, submessage }) => (
  <div className="text-center py-16 text-gray-400">
    <Icon className="w-12 h-12 mx-auto mb-3 opacity-30" />
    <p className="text-sm font-medium">{message}</p>
    {submessage && <p className="text-xs mt-1">{submessage}</p>}
  </div>
);

export const StatBox = ({ label, value, color = 'blue', icon: Icon }) => {
  const bg = { blue: 'bg-blue-50 border-blue-100', green: 'bg-emerald-50 border-emerald-100', amber: 'bg-amber-50 border-amber-100', red: 'bg-rose-50 border-rose-100', gray: 'bg-gray-50 border-gray-200', purple: 'bg-violet-50 border-violet-100', cyan: 'bg-cyan-50 border-cyan-100' };
  const text = { blue: 'text-blue-700', green: 'text-emerald-700', amber: 'text-amber-700', red: 'text-rose-700', gray: 'text-gray-700', purple: 'text-violet-700', cyan: 'text-cyan-700' };
  const iconC = { blue: 'text-blue-500', green: 'text-emerald-500', amber: 'text-amber-500', red: 'text-rose-500', gray: 'text-gray-500', purple: 'text-violet-500', cyan: 'text-cyan-500' };
  return (
    <div className={`p-3 rounded-lg text-center border ${bg[color] || bg.blue}`}>
      {Icon && <Icon className={`w-5 h-5 mx-auto mb-1 ${iconC[color]}`} />}
      <p className={`text-2xl font-bold ${text[color]}`}>{value}</p>
      <p className={`text-xs ${iconC[color]}`}>{label}</p>
    </div>
  );
};

export const ROOM_STATUS_COLORS = { available: '#059669', occupied: '#2563EB', dirty: '#D97706', maintenance: '#DC2626', out_of_order: '#6B7280' };
export const ROOM_STATUS_LABELS = { available: 'Müsait', occupied: 'Dolu', dirty: 'Kirli', maintenance: 'Bakım', out_of_order: 'Devre Dışı' };
