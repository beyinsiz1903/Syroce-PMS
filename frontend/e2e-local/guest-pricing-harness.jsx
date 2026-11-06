// Local component acceptance only: no API, credentials, real hotel or guest data.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Toaster } from 'sonner';
import { OccupancyPricingEditor } from '@/pages/rate-manager/OccupancyPricingEditor';
import '@/index.css';

const syntheticRule = {
  pricing_type: 'per_person', base_occupancy: 2, extra_adult_rate: 20, extra_adult_rate_type: 'fixed',
  currency: 'USD', max_occupancy: 4,
  child_age_bands: [
    { min_age: 0, max_age: 6, pricing_mode: 'free', value: 0 },
    { min_age: 7, max_age: 11, pricing_mode: 'adult_percentage', value: 50 },
    { min_age: 12, max_age: 17, pricing_mode: 'adult_rate', value: 0 },
  ],
  exely_placements_reviewed: false,
  exely_price_placements: [
    { kind: 'adult_main', number_of_guests: 1, price_mode: 'fixed', value: 80 },
    { kind: 'child_extra', min_age: 7, max_age: 11, price_mode: 'percentage', value: 10 },
  ],
};
const App = () => {
  const [rule, setRule] = useState(syntheticRule);
  const [saved, setSaved] = useState(null);
  return <main className="mx-auto max-w-2xl p-3 sm:p-6">
    <h1 className="mb-1 text-xl font-semibold text-slate-900">Fiyat & Müsaitlik Yönetimi</h1>
    <p className="mb-5 text-xs text-slate-500">Yalnız yapay verilerle yerel arayüz kontrolü</p>
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <OccupancyPricingEditor roomType={{ code: 'DEMO', name: 'Örnek Standart' }} rule={rule} open onToggle={() => {}}
        onSave={async next => { setSaved(next); setRule({ ...rule, ...next }); }} currentBaseRate={100}
        currencySymbol="$" currency="USD" channelProvider="exely" />
    </div>
    {saved && <output data-testid="saved-rule" className="mt-4 block rounded-lg bg-slate-100 p-3 text-xs">{JSON.stringify(saved)}</output>}
    <Toaster />
  </main>;
};
createRoot(document.getElementById('root')).render(<App />);
