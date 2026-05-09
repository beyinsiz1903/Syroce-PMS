import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Loader2, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export const API = "";

export const fmtDate = (d) => {
  if (!d) return '-';
  return new Date(d).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', weekday: 'short' });
};
export const fmtDateTime = (d) => {
  if (!d) return '-';
  return new Date(d).toLocaleString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};
export const fmtTs = (d) => (d || '').toString().slice(0, 16).replace('T', ' ');
export const fmtTL = (v) => (v || 0).toLocaleString('tr-TR');

export function statusLabel(s) {
  return s === 'checked_in' ? 'Giriş Yapıldı'
    : s === 'in_house' ? 'Otelde'
    : s === 'confirmed' ? 'Onaylandı'
    : s === 'guaranteed' ? 'Garantili'
    : s === 'checked_out' ? 'Çıkış Yapıldı'
    : s === 'cancelled' ? 'İptal Edildi'
    : s === 'no_show' ? 'No-Show'
    : s === 'pending' ? 'Beklemede'
    : s || 'Beklemede';
}

// Yaygın değer çevirileri (İngilizce/teknik → Türkçe gösterim)
export function translateValue(v) {
  if (!v) return v;
  const s = String(v).toLowerCase().trim();
  const map = {
    'direct': 'Doğrudan',
    'walk-in': 'Walk-in',
    'walkin': 'Walk-in',
    'phone': 'Telefon',
    'email': 'E-posta',
    'website': 'Web Sitesi',
    'web': 'Web',
    'agency': 'Acente',
    'corporate': 'Kurumsal',
    'non-refundable': 'İade Edilemez',
    'non_refundable': 'İade Edilemez',
    'nonrefundable': 'İade Edilemez',
    'refundable': 'İade Edilebilir',
    'flexible': 'Esnek',
    'standard': 'Standart',
    'breakfast included': 'Kahvaltı Dahil',
    'breakfast': 'Kahvaltı',
    'half board': 'Yarım Pansiyon',
    'full board': 'Tam Pansiyon',
    'all inclusive': 'Her Şey Dahil',
    'room only': 'Sadece Oda',
    'bed and breakfast': 'Oda + Kahvaltı',
    'bb': 'Oda + Kahvaltı',
    'hb': 'Yarım Pansiyon',
    'fb': 'Tam Pansiyon',
    'ai': 'Her Şey Dahil',
    'ro': 'Sadece Oda',
  };
  return map[s] || v;
}

// Kısa, okunaklı rezervasyon referansı
export function bookingRef(booking) {
  if (!booking) return '';
  if (booking.ota_confirmation) return booking.ota_confirmation;
  if (booking.confirmation_number) return booking.confirmation_number;
  if (booking.booking_reference) return booking.booking_reference;
  if (booking.reservation_number) return booking.reservation_number;
  // UUID'in son 6 karakterini büyük harfle göster — kısa, kullanıcıya kolay
  const id = booking.id || '';
  const tail = id.replace(/-/g, '').slice(-6).toUpperCase();
  return tail ? `RES-${tail}` : '';
}

export function InfoField({ label, value, className = '' }) {
  const { t } = useTranslation();
  return (
    <div>
      <Label className="text-[11px] font-medium text-slate-500 mb-1 block">{label}</Label>
      <div className={`border border-slate-200 rounded-lg px-3 py-2 text-sm bg-slate-50/60 text-slate-800 ${className}`}>{value}</div>
    </div>
  );
}

// Modern, gradient avatar — ad ilk harfini gösterir
export function Avatar({ name, size = 'md' }) {
  const sizes = {
    sm: 'w-7 h-7 text-[11px]',
    md: 'w-9 h-9 text-sm',
    lg: 'w-11 h-11 text-base',
    xl: 'w-16 h-16 text-2xl',
  };
  const s = sizes[size] || sizes.md;
  const letter = (name || 'M').trim()[0]?.toUpperCase() || 'M';
  // Adın hash'inden tutarlı bir ton seç
  const palettes = [
    'from-amber-500 to-amber-600',
    'from-rose-500 to-rose-600',
    'from-indigo-500 to-indigo-600',
    'from-emerald-500 to-emerald-600',
    'from-sky-500 to-sky-600',
    'from-violet-500 to-violet-600',
  ];
  let hash = 0;
  for (let i = 0; i < (name || '').length; i++) hash = ((hash << 5) - hash + (name || '').charCodeAt(i)) | 0;
  const palette = palettes[Math.abs(hash) % palettes.length];
  return (
    <div className={`${s} bg-gradient-to-br ${palette} text-white rounded-full flex items-center justify-center font-semibold shadow-sm ring-2 ring-white`}>
      {letter}
    </div>
  );
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
          {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />} {t('cm.pages_reservationdetail_helpers.kaydet')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose} className="h-8 text-xs">{t('cm.pages_reservationdetail_helpers.iptal')}</Button>
      </div>
    </div>
  );
}

// Yardımcı: bölüm başlığı (form gruplarında kullanılır)
export function SectionHeader({ icon: Icon, title }) {
  return (
    <div className="flex items-center gap-2 pb-1.5 border-b border-slate-200">
      {Icon && <Icon className="w-3.5 h-3.5 text-slate-500" />}
      <h3 className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">{title}</h3>
    </div>
  );
}
