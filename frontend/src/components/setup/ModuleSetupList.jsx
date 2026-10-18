import { AlertCircle, ArrowRight, CheckCircle2, MinusCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PRODUCT_MODULES } from '@/lib/moduleCatalog';

// The hotel's enabled modules by setup state (server: core.module_readiness):
// what is missing, with the screen that adds it, then the modules that are
// set up but not used lately. Modules that are off or need no setup are left
// out: there is nothing to do there.

const MODULES = Object.fromEntries(PRODUCT_MODULES.map((item) => [item.key, item]));

export function splitReadiness(modules = {}) {
  const rows = Object.values(modules).filter((row) => MODULES[row.module]);
  const byLabel = (a, b) => MODULES[a.module].label.localeCompare(MODULES[b.module].label, 'tr');
  return {
    incomplete: rows.filter((row) => row.status === 'incomplete').sort(byLabel),
    idle: rows.filter((row) => row.status === 'idle').sort(byLabel),
    active: rows.filter((row) => row.status === 'active').length,
  };
}

export default function ModuleSetupList({ modules, onOpen }) {
  const { incomplete, idle, active } = splitReadiness(modules);
  return (
    <div className="space-y-4" data-testid="module-setup-list">
      {incomplete.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-emerald-700" data-testid="module-setup-complete">
          <CheckCircle2 size={16} /> Açık modüllerin kurulumu tamam{active ? ` · ${active} modül kullanımda` : ''}.
        </p>
      ) : (
        <ul className="space-y-3">
          {incomplete.map((row) => (
            <li key={row.module} className="rounded-lg border border-amber-200 p-3" data-testid={`setup-module-${row.module}`}>
              <p className="flex items-center gap-2 text-sm font-semibold"><AlertCircle size={15} className="text-amber-600" />{MODULES[row.module].label}</p>
              <ul className="mt-2 space-y-1">
                {row.setup.filter((item) => !item.ok).map((item) => (
                  <li key={item.key} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2 text-slate-700"><MinusCircle size={14} className="text-slate-400" />{item.label}</span>
                    <Button size="sm" variant="outline" onClick={() => onOpen(item.path || MODULES[row.module].path)}>
                      Tamamla <ArrowRight size={14} className="ml-1" />
                    </Button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {idle.length > 0 && (
        <details className="text-sm" data-testid="module-setup-idle">
          <summary className="cursor-pointer text-slate-600">Kurulu ama son dönemde kullanılmayan modüller ({idle.length})</summary>
          <ul className="mt-2 space-y-1">
            {idle.map((row) => (
              <li key={row.module} className="flex flex-wrap items-center justify-between gap-2">
                <span>{MODULES[row.module].label}<span className="ml-2 text-xs text-slate-500">{row.usage.map((u) => u.label).join(' · ')}</span></span>
                {MODULES[row.module].path && <Button size="sm" variant="ghost" onClick={() => onOpen(MODULES[row.module].path)}>Aç <ArrowRight size={14} className="ml-1" /></Button>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
