import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

export const API = '/channel-manager/v2';

export const SeverityBadge = ({ severity }) => {
  const map = {
    critical: 'bg-red-500/15 text-red-400 border-red-500/30',
    high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    low: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    info: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    warning: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  };
  return <Badge data-testid={`severity-${severity}`} className={`${map[severity] || map.low} border text-xs`}>{severity}</Badge>;
};

export const StatusDot = ({ status }) => {
  const colors = { healthy: 'bg-emerald-400', degraded: 'bg-amber-400', critical: 'bg-red-400', stable: 'bg-emerald-400', unstable: 'bg-red-400' };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] || 'bg-slate-400'}`} />;
};

export const ScoreRing = ({ score, size = 80 }) => {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const fill = c - (score / 100) * c;
  const color = score >= 80 ? '#34d399' : score >= 50 ? '#fbbf24' : '#f87171';
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="currentColor" strokeWidth="4" className="text-slate-700" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="4"
        strokeDasharray={c} strokeDashoffset={fill} strokeLinecap="round" />
      <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
        className="fill-white text-lg font-bold" transform={`rotate(90 ${size/2} ${size/2})`}>{score}</text>
    </svg>
  );
};

export const MetricCard = ({ title, value, sub, icon: Icon, color = 'text-slate-300' }) => (
  <Card data-testid={`metric-${title.toLowerCase().replace(/\s+/g,'-')}`} className="bg-slate-800/50 border-slate-700">
    <CardContent className="p-4 flex items-center gap-3">
      {Icon && <Icon className={`w-5 h-5 ${color}`} />}
      <div>
        <p className="text-xs text-slate-400">{title}</p>
        <p className="text-xl font-semibold text-white">{value}</p>
        {sub && <p className="text-[10px] text-slate-500">{sub}</p>}
      </div>
    </CardContent>
  </Card>
);
