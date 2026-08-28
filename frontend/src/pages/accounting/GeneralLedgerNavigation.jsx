import React, { useMemo, useState } from 'react';
import {
  BarChart3,
  BookOpenCheck,
  CalendarRange,
  Cable,
  FileText,
  Landmark,
  LayoutDashboard,
  ListTree,
  Search,
  Settings2,
  Star,
  Zap,
} from 'lucide-react';
import { Input } from '@/components/ui/input';

export const GL_NAV_GROUPS = [
  {
    label: 'Günlük İşlemler',
    items: [
      { value: 'overview', label: 'Genel Bakış', description: 'Durum ve hızlı işlemler', icon: LayoutDashboard },
      { value: 'journals', label: 'Hızlı Fiş Girişi', description: 'Taslak, onay ve yevmiye', icon: Zap },
      { value: 'account-ledger', label: 'Muavin Defteri', description: 'Hesap hareketleri', icon: BookOpenCheck },
    ],
  },
  {
    label: 'Defter ve Raporlar',
    items: [
      { value: 'accounts', label: 'Hesap Planı (TDHP)', description: 'Hesap kartları ve bakiyeler', icon: ListTree },
      { value: 'trial-balance', label: 'Mizan', description: 'Borç, alacak ve bakiye', icon: BarChart3 },
      { value: 'statements', label: 'Mali Tablolar', description: 'Gelir ve bilanço', icon: FileText },
    ],
  },
  {
    label: 'Dönem ve Kontrol',
    items: [
      { value: 'periods', label: 'Mali Dönemler', description: 'Kilit ve yıl sonu', icon: CalendarRange },
      { value: 'workspace', label: 'Alt Defterler', description: 'AP, bütçe ve sabit kıymet', icon: Landmark },
      { value: 'integrations', label: 'Muhasebe Entegrasyonları', description: 'Nilvera ve otomatik kayıtlar', icon: Cable },
      { value: 'setup', label: 'Kurulum ve Ayarlar', description: 'Açılış ve firma profili', icon: Settings2 },
    ],
  },
];

const FAVORITES_KEY = 'syroce.general-ledger.favorites.v1';
const DEFAULT_FAVORITES = ['journals', 'account-ledger', 'trial-balance'];

const readFavorites = () => {
  if (typeof window === 'undefined') return DEFAULT_FAVORITES;
  try {
    const saved = JSON.parse(window.localStorage.getItem(FAVORITES_KEY));
    return Array.isArray(saved) ? saved : DEFAULT_FAVORITES;
  } catch {
    return DEFAULT_FAVORITES;
  }
};

export const GeneralLedgerNavigation = ({ activeTab, onSelect }) => {
  const [query, setQuery] = useState('');
  const [favorites, setFavorites] = useState(readFavorites);
  const itemByValue = useMemo(
    () => new Map(GL_NAV_GROUPS.flatMap((group) => group.items).map((item) => [item.value, item])),
    [],
  );
  const normalizedQuery = query.trim().toLocaleLowerCase('tr-TR');

  const toggleFavorite = (value) => {
    setFavorites((current) => {
      const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
      if (typeof window !== 'undefined') window.localStorage.setItem(FAVORITES_KEY, JSON.stringify(next));
      return next;
    });
  };

  const renderItem = (item, showStar = true) => {
    const Icon = item.icon;
    const active = activeTab === item.value;
    return (
      <div key={item.value} className="group flex items-center gap-1">
        <button
          type="button"
          role="tab"
          aria-label={item.label}
          aria-selected={active}
          onClick={() => onSelect(item.value)}
          aria-current={active ? 'page' : undefined}
          className={`flex min-w-0 flex-1 items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
            active ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-700 hover:bg-slate-100'
          }`}
        >
          <Icon className={`h-4 w-4 shrink-0 ${active ? 'text-white' : 'text-slate-500'}`} />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{item.label}</span>
            <span className={`block truncate text-[11px] ${active ? 'text-blue-100' : 'text-slate-500'}`}>{item.description}</span>
          </span>
        </button>
        {showStar && (
          <button
            type="button"
            aria-label={`${item.label} ${favorites.includes(item.value) ? 'favorilerden çıkar' : 'favorilere ekle'}`}
            onClick={() => toggleFavorite(item.value)}
            className="rounded-md p-1.5 text-slate-400 hover:bg-amber-50 hover:text-amber-600"
          >
            <Star className={`h-3.5 w-3.5 ${favorites.includes(item.value) ? 'fill-amber-400 text-amber-500' : ''}`} />
          </button>
        )}
      </div>
    );
  };

  return (
    <aside className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm lg:sticky lg:top-4" data-testid="gl-accounting-nav">
      <div className="mb-3 px-1">
        <p className="text-sm font-bold text-slate-900">Muhasebe İşlemleri</p>
        <p className="text-xs text-slate-500">Tüm işlemler tek menüde</p>
      </div>
      <label className="relative mb-4 block">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="h-9 pl-9"
          placeholder="İşlem ara..."
          aria-label="Muhasebe işlemlerinde ara"
        />
      </label>

      {!normalizedQuery && favorites.length > 0 && (
        <section className="mb-4 border-b border-slate-100 pb-4" aria-label="Favori muhasebe işlemleri">
          <p className="mb-1.5 px-2 text-[11px] font-bold uppercase tracking-wider text-amber-700">Favoriler</p>
          <div className="space-y-1">
            {favorites.map((value) => itemByValue.get(value)).filter(Boolean).map((item) => renderItem(item, false))}
          </div>
        </section>
      )}

      <nav className="space-y-4" aria-label="Genel muhasebe menüsü" role="tablist">
        {GL_NAV_GROUPS.map((group) => {
          const visibleItems = group.items.filter((item) => !normalizedQuery
            || `${item.label} ${item.description}`.toLocaleLowerCase('tr-TR').includes(normalizedQuery));
          if (visibleItems.length === 0) return null;
          return (
            <section key={group.label}>
              <p className="mb-1 px-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">{group.label}</p>
              <div className="space-y-1">{visibleItems.map((item) => renderItem(item))}</div>
            </section>
          );
        })}
      </nav>
      {normalizedQuery && GL_NAV_GROUPS.every((group) => group.items.every((item) => !`${item.label} ${item.description}`.toLocaleLowerCase('tr-TR').includes(normalizedQuery))) && (
        <p className="rounded-lg bg-slate-50 p-3 text-center text-xs text-slate-500">Eşleşen işlem bulunamadı.</p>
      )}
    </aside>
  );
};
