import { cn } from '@/lib/utils';

const intentClasses = {
  info: 'bg-sky-100 text-sky-800 border-sky-200',
  success: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  warning: 'bg-amber-100 text-amber-800 border-amber-200',
  danger: 'bg-rose-100 text-rose-800 border-rose-200',
  neutral: 'bg-slate-100 text-slate-700 border-slate-200',
  default: 'bg-slate-100 text-slate-700 border-slate-200',
};

export function StatusBadge({
  intent = 'default',
  icon: Icon,
  children,
  className,
  ...rest
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold whitespace-nowrap',
        intentClasses[intent] || intentClasses.default,
        className,
      )}
      {...rest}
    >
      {Icon && <Icon className="w-3 h-3" />}
      {children}
    </span>
  );
}

export default StatusBadge;
