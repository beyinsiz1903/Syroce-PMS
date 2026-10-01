import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Clock3, Grid3X3, Heart, Search, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useEntitlements } from '@/context/EntitlementContext';
import { PRODUCT_MODULES } from '@/lib/moduleCatalog';

const STORAGE_KEY = 'syroce.application-center.favorites';
const loadFavorites = () => {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; }
};

export default function ApplicationCenter({ tenant }) {
  const navigate = useNavigate();
  const { hasModule } = useEntitlements();
  const [query, setQuery] = useState('');
  const [view, setView] = useState('all');
  const [favorites, setFavorites] = useState(loadFavorites);

  const modules = useMemo(() => PRODUCT_MODULES.map((item) => ({
    ...item,
    enabled: hasModule(item.key),
    favorite: favorites.includes(item.key),
  })).filter((item) => {
    if (!item.enabled) return false;
    if (view === 'favorites' && !item.favorite) return false;
    const needle = query.trim().toLocaleLowerCase('tr-TR');
    return !needle || `${item.label} ${item.hint || ''} ${item.groupTitle}`.toLocaleLowerCase('tr-TR').includes(needle);
  }), [favorites, hasModule, query, view]);

  const groups = useMemo(() => modules.reduce((result, item) => {
    (result[item.groupTitle] ||= []).push(item);
    return result;
  }, {}), [modules]);

  const toggleFavorite = (key) => {
    setFavorites((current) => {
      const next = current.includes(key) ? current.filter((item) => item !== key) : [...current, key];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  return (
    <main className="mx-auto max-w-7xl space-y-5 p-4 md:p-6" data-testid="application-center">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{tenant?.property_name || tenant?.name || 'Otel çalışma alanı'}</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-950">Uygulamalar</h1>
          <p className="mt-1 text-sm text-slate-600">Yetkiniz olan çalışma alanlarına tek yerden ulaşın.</p>
        </div>
        <Button variant="outline" onClick={() => navigate('/app/module-store')}><Settings2 className="mr-2 h-4 w-4" /> Modül ve paketleri yönet</Button>
      </header>

      <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><Input className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Uygulama veya yapmak istediğiniz işi arayın" /></div>
          <div className="flex gap-1">
            <Button variant={view === 'all' ? 'default' : 'ghost'} onClick={() => setView('all')}><Grid3X3 className="mr-2 h-4 w-4" /> Tümü</Button>
            <Button variant={view === 'favorites' ? 'default' : 'ghost'} onClick={() => setView('favorites')}><Heart className="mr-2 h-4 w-4" /> Favoriler</Button>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2 text-xs text-slate-600">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" /> {modules.filter((item) => item.path).length} uygulama kullanıma hazır</span>
        {modules.some((item) => !item.path) && <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1.5 text-amber-800"><Clock3 className="h-3.5 w-3.5" /> {modules.filter((item) => !item.path).length} modül için kurulum bağlantısı bekleniyor</span>}
      </div>

      {Object.entries(groups).map(([group, items]) => (
        <section key={group} className="space-y-3">
          <div><h2 className="text-base font-semibold text-slate-900">{group}</h2><p className="text-xs text-slate-500">{items.length} uygulama</p></div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <article key={item.key} className="flex min-h-48 flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:shadow-md">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100"><Grid3X3 className="h-5 w-5 text-slate-600" /></div>
                  <button type="button" onClick={() => toggleFavorite(item.key)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-rose-500" aria-label={`${item.label} ${item.favorite ? 'favorilerden çıkar' : 'favorilere ekle'}`}><Heart className={`h-4 w-4 ${item.favorite ? 'fill-rose-500 text-rose-500' : ''}`} /></button>
                </div>
                <h3 className="mt-3 text-sm font-semibold text-slate-950">{item.label}</h3>
                <p className="mt-1 flex-1 text-xs leading-5 text-slate-600">{item.hint || 'Otel operasyonu çalışma alanı'}</p>
                {item.path ? (
                  <Button className="mt-4 w-full" onClick={() => navigate(item.path)} data-testid={`launch-${item.key}`}>Uygulamayı aç</Button>
                ) : (
                  <Button className="mt-4 w-full" variant="outline" onClick={() => navigate('/app/module-store')}>Kurulumu tamamla</Button>
                )}
              </article>
            ))}
          </div>
        </section>
      ))}

      {!modules.length && <div className="rounded-xl border border-dashed border-slate-300 p-12 text-center"><Grid3X3 className="mx-auto h-8 w-8 text-slate-300" /><p className="mt-3 text-sm font-medium text-slate-700">Uygulama bulunamadı</p><p className="mt-1 text-xs text-slate-500">Arama ölçütünü değiştirin veya modül yetkilerinizi kontrol edin.</p></div>}
    </main>
  );
}
