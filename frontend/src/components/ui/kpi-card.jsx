import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

const intentBorder = {
  default: 'border-l-slate-300',
  info: 'border-l-sky-500',
  success: 'border-l-emerald-500',
  warning: 'border-l-amber-500',
  danger: 'border-l-rose-500',
  neutral: 'border-l-slate-400',
};

const intentIcon = {
  default: 'text-slate-500',
  info: 'text-sky-600',
  success: 'text-emerald-600',
  warning: 'text-amber-600',
  danger: 'text-rose-600',
  neutral: 'text-slate-500',
};

export function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  intent = 'default',
  highlight = false,
  active = false,
  onClick,
  className,
  ...rest
}) {
  const interactive = typeof onClick === 'function';
  const handleKeyDown = interactive
    ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(e);
        }
      }
    : undefined;
  return (
    <Card
      onClick={onClick}
      onKeyDown={handleKeyDown}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-pressed={interactive ? !!active : undefined}
      className={cn(
        'border-l-4 p-4 transition-shadow',
        intentBorder[intent] || intentBorder.default,
        highlight && 'bg-amber-50',
        active && 'ring-2 ring-slate-900',
        interactive && 'cursor-pointer hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1',
        className,
      )}
      {...rest}
    >
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
        {Icon && <Icon className={cn('w-3.5 h-3.5', intentIcon[intent] || intentIcon.default)} />}
        <span>{label}</span>
      </div>
      <div className="text-2xl font-bold text-slate-900 leading-tight">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </Card>
  );
}

export default KpiCard;
