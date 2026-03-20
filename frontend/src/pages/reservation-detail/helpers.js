import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Loader2, Check } from 'lucide-react';

export const API = process.env.REACT_APP_BACKEND_URL;

export const fmtDate = (d) => {
  if (!d) return '-';
  return new Date(d).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', weekday: 'short' });
};
export const fmtTs = (d) => (d || '').toString().slice(0, 16).replace('T', ' ');
export const fmtTL = (v) => (v || 0).toLocaleString('tr-TR');

export function statusLabel(s) {
  return s === 'checked_in' ? 'Giris Yapildi' : s === 'confirmed' ? 'Onaylandi' : s === 'checked_out' ? 'Cikis Yapildi' : s === 'cancelled' ? 'Iptal' : s === 'no_show' ? 'No-Show' : s || 'Beklemede';
}

export function InfoField({ label, value, className = '' }) {
  return <div><Label className="text-xs text-gray-500 mb-1 block">{label}</Label><div className={`border rounded-lg px-3 py-2 text-sm bg-gray-50 ${className}`}>{value}</div></div>;
}

export function Avatar({ name, size = 'md' }) {
  const s = size === 'lg' ? 'w-10 h-10 text-sm' : 'w-8 h-8 text-xs';
  return <div className={`${s} bg-teal-600 text-white rounded-full flex items-center justify-center font-bold`}>{(name || 'M')[0]?.toUpperCase()}</div>;
}

export function EmptyState({ icon: Icon, text }) {
  return <div className="text-center py-8 text-gray-400"><Icon className="w-8 h-8 mx-auto mb-2 opacity-50" /><p className="text-sm">{text}</p></div>;
}

export function SummaryCard({ label, value, color }) {
  return (
    <div className={`bg-${color}-50 border border-${color}-200 rounded-lg p-3 text-center`}>
      <div className={`text-xs text-${color}-600 font-medium`}>{label}</div>
      <div className={`text-lg font-bold text-${color}-800`}>{fmtTL(value)} TL</div>
    </div>
  );
}

export function FormField({ label, value, onChange, type = 'text', placeholder = '' }) {
  return <div><Label className="text-xs">{label}</Label><Input type={type} value={value} onChange={e => onChange(e.target.value)} className="h-8 text-sm" placeholder={placeholder} /></div>;
}

export function SelectField({ label, value, onChange, options }) {
  return (
    <div><Label className="text-xs">{label}</Label>
      <select value={value} onChange={e => onChange(e.target.value)} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
        {options.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </div>
  );
}

export function FormPanel({ color, title, testid, children, onClose, onSubmit, loading }) {
  return (
    <div className={`border rounded-lg p-4 bg-${color}-50/50 space-y-3`} data-testid={testid}>
      <div className={`text-sm font-semibold text-${color}-800`}>{title}</div>
      {children}
      <div className="flex gap-2">
        <Button size="sm" onClick={onSubmit} disabled={loading} className={`bg-${color}-600 hover:bg-${color}-700 text-white h-8 text-xs`}>
          {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />} Kaydet
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose} className="h-8 text-xs">Iptal</Button>
      </div>
    </div>
  );
}
