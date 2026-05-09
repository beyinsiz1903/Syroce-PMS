import { Card } from '@/components/ui/card';
import { KpiCard } from '@/components/ui/kpi-card';
import { PageHeader } from '@/components/ui/page-header';
import { BarChart3 } from 'lucide-react';

// Sprint A DS palette: sky / emerald / amber / rose / indigo / slate.
// Recharts grafikleri için hex tonları (mavi/yeşil yerine sky/emerald):
export const COLORS = ['#0284C7', '#059669', '#D97706', '#E11D48', '#4F46E5', '#0EA5E9', '#10B981', '#F59E0B', '#F43F5E', '#6366F1'];

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

// Eski color → Sprint A intent eşlemesi (geriye dönük uyumluluk için).
const COLOR_TO_INTENT = {
  blue: 'info', sky: 'info', cyan: 'info', indigo: 'info',
  green: 'success', emerald: 'success', teal: 'success',
  amber: 'warning', yellow: 'warning', orange: 'warning',
  red: 'danger', rose: 'danger',
  purple: 'neutral', violet: 'neutral', gray: 'neutral', slate: 'neutral',
  // DS intent kimliği — doğrudan geçirilirse fallback'e düşmesin
  info: 'info', success: 'success', warning: 'warning', danger: 'danger', neutral: 'neutral', default: 'default',
};

export const KPICard = ({ title, value, prevValue, prevLabel, icon: Icon, color = 'default' }) => {
  const intent = COLOR_TO_INTENT[color] || 'default';
  const isCurrency = /gelir|adr|rev|ciro|ödeme|tutar/i.test(title);
  const displayVal = typeof value === 'number' ? (isCurrency ? formatCurrency(value) : formatNumber(value)) : value;
  let sub = prevLabel;
  if (!sub && prevValue !== undefined && typeof value === 'number') {
    const change = calcChange(value, typeof prevValue === 'number' ? prevValue : 0);
    if (Number(change.pct) > 0) {
      sub = (change.direction === 'up' ? '▲ +' : '▼ -') + change.pct + '% (önceki dönem)';
    }
  }
  return (
    <KpiCard
      icon={Icon}
      label={title}
      value={displayVal}
      sub={sub}
      intent={intent}
      data-testid={`kpi-${(title || '').toString().toLowerCase().replace(/\s+/g, '-')}`}
    />
  );
};

export const CustomTooltip = ({ active, payload, label, formatter }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white/95 backdrop-blur-sm p-3 border border-slate-200 rounded-lg shadow-xl text-xs">
      <p className="font-semibold text-slate-800 mb-1.5 border-b pb-1">{label}</p>
      {payload.map((entry, idx) => (
        <p key={idx} style={{ color: entry.color }} className="flex items-center gap-1.5 py-0.5">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
          <span className="text-slate-600">{entry.name}:</span>
          <span className="font-medium">{formatter ? formatter(entry.value) : entry.value}</span>
        </p>
      ))}
    </div>
  );
};

// SectionHeader: Sprint A `<PageHeader>` üstüne ince bir wrapper.
export const SectionHeader = ({ title, description, actions, icon }) => (
  <PageHeader icon={icon || BarChart3} title={title} subtitle={description} actions={actions} />
);

export const EmptyState = ({ icon: Icon, message, submessage }) => (
  <div className="text-center py-16 text-slate-400">
    <Icon className="w-12 h-12 mx-auto mb-3 opacity-30" />
    <p className="text-sm font-medium">{message}</p>
    {submessage && <p className="text-xs mt-1">{submessage}</p>}
  </div>
);

// StatBox: Sprint A palette (sky / emerald / amber / rose / slate / indigo).
const STATBOX_PALETTE = {
  blue:   { border: 'border-l-sky-500',     icon: 'text-sky-600',     value: 'text-slate-900' },
  sky:    { border: 'border-l-sky-500',     icon: 'text-sky-600',     value: 'text-slate-900' },
  cyan:   { border: 'border-l-sky-500',     icon: 'text-sky-600',     value: 'text-slate-900' },
  green:  { border: 'border-l-emerald-500', icon: 'text-emerald-600', value: 'text-slate-900' },
  emerald:{ border: 'border-l-emerald-500', icon: 'text-emerald-600', value: 'text-slate-900' },
  amber:  { border: 'border-l-amber-500',   icon: 'text-amber-600',   value: 'text-slate-900' },
  red:    { border: 'border-l-rose-500',    icon: 'text-rose-600',    value: 'text-slate-900' },
  rose:   { border: 'border-l-rose-500',    icon: 'text-rose-600',    value: 'text-slate-900' },
  purple: { border: 'border-l-indigo-500',  icon: 'text-indigo-600',  value: 'text-slate-900' },
  violet: { border: 'border-l-indigo-500',  icon: 'text-indigo-600',  value: 'text-slate-900' },
  gray:   { border: 'border-l-slate-400',   icon: 'text-slate-500',   value: 'text-slate-900' },
};

export const StatBox = ({ label, value, color = 'blue', icon: Icon }) => {
  const p = STATBOX_PALETTE[color] || STATBOX_PALETTE.blue;
  return (
    <Card className={`p-3 text-center border-l-4 ${p.border}`}>
      {Icon && <Icon className={`w-5 h-5 mx-auto mb-1 ${p.icon}`} />}
      <p className={`text-2xl font-bold ${p.value}`}>{value}</p>
      <p className="text-xs text-slate-500 mt-0.5">{label}</p>
    </Card>
  );
};

export const ROOM_STATUS_COLORS = { available: '#059669', occupied: '#0284C7', dirty: '#D97706', maintenance: '#E11D48', out_of_order: '#64748B' };
export const ROOM_STATUS_LABELS = { available: 'Müsait', occupied: 'Dolu', dirty: 'Kirli', maintenance: 'Bakım', out_of_order: 'Devre Dışı' };
