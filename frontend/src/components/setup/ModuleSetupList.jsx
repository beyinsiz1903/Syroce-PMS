import { AlertCircle, ArrowRight, CheckCircle2, MinusCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PRODUCT_MODULES } from '@/lib/moduleCatalog';

const MODULES = Object.fromEntries(PRODUCT_MODULES.map((item) => [item.key, item]));
const STATUSES = new Set(['off', 'incomplete', 'idle', 'active', 'ready', 'unknown']);
const moduleLabel = (row) => MODULES[row.module]?.label || row.module;

export function isReadinessMap(modules) {
  return !!modules && typeof modules === 'object' && !Array.isArray(modules)
    && Object.entries(modules).every(([key, row]) => row && row.module === key
      && STATUSES.has(row.status) && Array.isArray(row.setup) && Array.isArray(row.usage)
      && [...row.setup, ...row.usage].every((item) => item && typeof item === 'object'
        && [true, false, null].includes(item.ok)));
}

export function splitReadiness(modules) {
  const valid = isReadinessMap(modules);
  const rows = valid ? Object.values(modules).filter((row) => row.status !== 'off') : [];
  const byLabel = (a, b) => moduleLabel(a).localeCompare(moduleLabel(b), 'tr');
  // The server reports `unknown` if *any* check fails, including usage.
  // Keep known missing setup visible, and never confuse missing evidence
  // (null) with missing configuration (false).
  const incomplete = rows.filter((row) => row.setup.some((item) => item.ok === false)).sort(byLabel);
  const unverified = rows.filter((row) => row.setup.some((item) => item.ok === null)
    || (row.status === 'unknown' && ![...row.setup, ...row.usage].some((item) => item.ok === null))
    || (row.status === 'incomplete' && !row.setup.some((item) => item.ok === false))).sort(byLabel);
  const attention = rows.filter((row) => incomplete.includes(row) || unverified.includes(row)).sort(byLabel);
  return {
    valid,
    complete: valid && attention.length === 0,
    incomplete,
    unverified,
    attention,
    usageUnknown: rows.filter((row) => row.usage.some((item) => item.ok === null)).sort(byLabel),
    idle: rows.filter((row) => row.status === 'idle' && !attention.includes(row)).sort(byLabel),
    active: rows.filter((row) => row.status === 'active' && !attention.includes(row)).length,
  };
}

export default function ModuleSetupList({ modules, onOpen }) {
  const { valid, complete, attention, unverified, usageUnknown, idle, active } = splitReadiness(modules);
  return (
    <div className="space-y-4" data-testid="module-setup-list">
      {!valid && <p className="text-sm text-slate-600">Modül bilgileri doğrulanamadı. Lütfen yenileyin.</p>}
      {complete && (
        <p className="flex items-center gap-2 text-sm text-emerald-700" data-testid="module-setup-complete">
          <CheckCircle2 size={16} /> Açık modüllerin kurulumu tamam{active ? ` · ${active} modül kullanımda` : ''}.
        </p>
      )}
      {attention.length > 0 && (
        <ul className="space-y-3">
          {attention.map((row) => (
            <li key={row.module} className="rounded-lg border border-amber-200 p-3" data-testid={`setup-module-${row.module}`}>
              <p className="flex items-center gap-2 text-sm font-semibold"><AlertCircle size={15} className="text-amber-600" />{moduleLabel(row)}</p>
              <ul className="mt-2 space-y-1">
                {row.setup.filter((item) => item.ok === false).map((item) => (
                  <li key={item.key} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2 text-slate-700"><MinusCircle size={14} className="text-slate-400" />{item.label}</span>
                    {(item.path || MODULES[row.module]?.path) && <Button size="sm" variant="outline" onClick={() => onOpen(item.path || MODULES[row.module]?.path)}>
                      Tamamla <ArrowRight size={14} className="ml-1" />
                    </Button>}
                  </li>
                ))}
                {row.setup.filter((item) => item.ok === null).map((item) => (
                  <li key={item.key} className="text-sm text-slate-600">
                    {item.label} — henüz doğrulanamadı; yenileyerek tekrar kontrol edin.
                  </li>
                ))}
              </ul>
              {unverified.includes(row) && (
                <p className="mt-2 text-sm text-slate-600" data-testid={`setup-unverified-${row.module}`}>
                  Kurulum durumu henüz doğrulanamadı. Bu, ayarların eksik olduğu anlamına gelmez.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {usageUnknown.length > 0 && (
        <div className="text-sm text-slate-600" data-testid="module-setup-usage-unknown">
          <p>Kullanım bilgisi alınamadı. Bu durum tek başına kurulum eksiği değildir.</p>
          <ul className="mt-1 space-y-1">
            {usageUnknown.map((row) => <li key={row.module}>{moduleLabel(row)}: {row.usage.filter((item) => item.ok === null).map((item) => item.label).join(' · ')}</li>)}
          </ul>
        </div>
      )}
      {idle.length > 0 && (
        <details className="text-sm" data-testid="module-setup-idle">
          <summary className="cursor-pointer text-slate-600">Kurulu ama son dönemde kullanılmayan modüller ({idle.length})</summary>
          <ul className="mt-2 space-y-1">
            {idle.map((row) => (
              <li key={row.module} className="flex flex-wrap items-center justify-between gap-2">
                <span>{moduleLabel(row)}<span className="ml-2 text-xs text-slate-500">{row.usage.map((u) => u.label).join(' · ')}</span></span>
                {MODULES[row.module]?.path && <Button size="sm" variant="ghost" onClick={() => onOpen(MODULES[row.module].path)}>Aç <ArrowRight size={14} className="ml-1" /></Button>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
