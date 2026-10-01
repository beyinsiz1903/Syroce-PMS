import React from 'react';
import { Eye, EyeOff, ShieldCheck } from 'lucide-react';

const MODE_STYLES = {
  full: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  masked: 'border-amber-200 bg-amber-50 text-amber-800',
  hidden: 'border-slate-300 bg-slate-100 text-slate-700',
};

export default function GuestDataVisibilityEditor({ catalog, value, onChange, disabled = false }) {
  if (!catalog) return null;
  const policy = { ...(catalog.default_policy || {}), ...(value || {}) };

  return (
    <fieldset disabled={disabled} className="space-y-3 rounded-lg border border-sky-200 bg-sky-50/40 p-4">
      <legend className="flex items-center gap-2 px-1 font-semibold text-slate-900">
        <ShieldCheck className="h-4 w-4 text-sky-700" /> Misafir verisi görünürlüğü
      </legend>
      <p className="text-xs leading-5 text-slate-600">
        Bu ayarlar rolden bağımsız olarak bu kullanıcıya uygulanır. Ekran, arama sonucu,
        rapor, CSV/Excel ve yazdırma çıktısı aynı sunucu tarafı kuralını kullanır.
      </p>
      <div className="space-y-2">
        {catalog.fields.map((field) => {
          const mode = policy[field.key] || field.default;
          return (
            <div key={field.key} className="grid gap-2 rounded-md border bg-white p-3 sm:grid-cols-[1fr_180px] sm:items-center">
              <div>
                <div className="flex items-center gap-1.5 text-sm font-medium text-slate-900">
                  {mode === 'hidden' ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  {field.label}
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{field.description}</p>
              </div>
              <select
                aria-label={`${field.label} görünürlüğü`}
                value={mode}
                onChange={(event) => onChange({ ...policy, [field.key]: event.target.value })}
                className={`h-9 rounded-md border px-2 text-sm font-medium ${MODE_STYLES[mode] || ''}`}
              >
                {catalog.modes.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
