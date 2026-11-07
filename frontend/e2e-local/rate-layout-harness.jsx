// Actual page and all sidebars, synthetic GET responses only. No writes allowed.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import tr from '@/locales/tr.json';
import UnifiedRateManager from '@/pages/UnifiedRateManager';
import '@/index.css';

await i18n.use(initReactI18next).init({ lng: 'tr', fallbackLng: 'tr', resources: { tr: { translation: tr } } });
window.__rateLayoutWrites = [];
axios.defaults.adapter = async config => {
  if (config.method !== 'get') {
    window.__rateLayoutWrites.push(config.url);
    throw new Error('Writes forbidden in isolated layout fixture');
  }
  const path = config.url;
  let data;
  if (path.endsWith('/detect-provider')) data = { provider: 'exely' };
  else if (path.includes('/grid?')) data = {
    room_types: [{ code: 'STD', name: 'Standart' }, { code: 'DLX', name: 'Deluxe' }],
    rate_plans: [{ code: 'BASE', name: 'Base rate USD' }, { code: 'NRF', name: 'Non-ref rate USD' }], grid: [], currency: 'USD',
    exely_placement_tariffs_version: 1,
    pricing_settings: { STD: 'per_person', DLX: 'per_person' },
    occupancy_pricing_rules: Object.fromEntries(['STD', 'DLX'].map(code => [code, {
      pricing_type: 'per_person', base_occupancy: 2, currency: 'USD', provider_pricing_verified: true,
      exely_placements_reviewed: true, exely_price_placements: [{ kind: 'adult_main', number_of_guests: 1, price_mode: 'fixed', value: 80 }],
    }])),
  };
  else if (path.endsWith('/push-providers')) data = { providers: [{ name: 'Exely', mode: 'live' }] };
  else if (path.endsWith('/agencies')) data = { agencies: [{ id: 'demo', name: 'Örnek Acente', commission_rate: 10 }] };
  else if (path.endsWith('/circuit-breakers')) data = { breakers: [] };
  else if (path.includes('/stop-sale-summary?')) data = { stops: [] };
  else if (path.endsWith('/stop-sale/status')) data = {};
  else if (path.endsWith('/holidays')) data = { holidays: [] };
  else if (path.endsWith('/stop-sale-schedules')) data = { schedules: [] };
  else throw new Error(`Unmocked layout GET: ${path}`);
  return { data, status: 200, statusText: 'OK', headers: {}, config };
};
createRoot(document.getElementById('root')).render(<MemoryRouter>
  <main className="mx-auto max-w-[1200px] p-3 sm:p-6"><UnifiedRateManager embedded /></main>
</MemoryRouter>);
