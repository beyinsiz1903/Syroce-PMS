import { cn } from '@/lib/utils';

export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
  iconClassName,
  className,
  ...rest
}) {
  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-5',
        className,
      )}
      {...rest}
    >
      <div className="flex items-start gap-3 min-w-0">
        {Icon && (
          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center mt-0.5">
            <Icon className={cn('w-5 h-5 text-slate-700', iconClassName)} />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-slate-900 leading-tight">{title}</h1>
          {subtitle && (
            <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex flex-wrap gap-2 flex-shrink-0">{actions}</div>
      )}
    </div>
  );
}

export default PageHeader;
