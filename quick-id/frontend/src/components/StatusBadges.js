import { Badge } from './ui/badge';

const statusMap = {
  pending: { label: 'Bekliyor', className: 'status-pending' },
  checked_in: { label: 'Giriş Yapıldı', className: 'status-checked-in' },
  checked_out: { label: 'Çıkış Yapıldı', className: 'status-checked-out' },
};

const docTypeMap = {
  tc_kimlik: 'TC Kimlik',
  passport: 'Pasaport',
  drivers_license: 'Ehliyet',
  old_nufus_cuzdani: 'Eski Nüfus',
  other: 'Diğer',
};

export function StatusBadge({ status }) {
  const config = statusMap[status] || { label: status || 'Bilinmiyor', className: 'status-pending' };
  return (
    <Badge variant="outline" className={`${config.className} text-xs font-medium px-2.5 py-0.5 rounded-full`} data-testid="guest-status-chip">
      {config.label}
    </Badge>
  );
}

export function DocTypeBadge({ type }) {
  const label = docTypeMap[type] || type || 'Bilinmiyor';
  return (
    <Badge variant="outline" className="text-xs bg-[hsl(var(--secondary))] text-[var(--brand-slate)] border-[hsl(var(--border))] px-2 py-0.5 rounded-full">
      {label}
    </Badge>
  );
}

export function GenderBadge({ gender }) {
  if (!gender) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span className="text-xs text-muted-foreground">
      {gender === 'M' ? 'Erkek' : gender === 'F' ? 'Kadın' : gender}
    </span>
  );
}
