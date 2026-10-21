// Test-only Vite entry. No credentials, live backend, emails or guest data.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { Toaster } from 'sonner';
import { EntitlementProvider } from '@/context/EntitlementContext';
import MicePage from '@/pages/MicePage';
import PublicMiceBeoPage from '@/pages/PublicMiceBeoPage';
import '@/index.css';

await i18n.use(initReactI18next).init({ lng: 'tr', fallbackLng: 'tr', resources: { tr: { translation: { cm: { pages_MicePage: {
  yeni_etkinlik: 'Yeni Etkinlik', yenile: 'Yenile', yukleniyor: 'Yükleniyor', duzenle: 'Düzenle',
  toplam_etkinlik: 'Toplam Etkinlik', toplam_pipeline: 'Açık Pipeline', musteriler: 'Müşteriler (', menuler_paketler: 'Menüler (',
  toplanti_konferans_gala_ve_dugun_etkinli: 'Toplantı, konferans, gala ve düğün etkinlikleri',
  gunun_ops_sheet_i: 'Günün Operasyon Planı', satis_pipeline: 'Satış Pipeline',
} } } } } });
const event = { id: 'demo-event', name: 'Örnek Konferans', client_name: 'Örnek Şirket', expected_pax: 40, event_type: 'conference', status: 'lead', currency: 'TRY', start_date: '2026-10-21', end_date: '2026-10-21', space_bookings: [], resources: [{ name: 'Örnek öğle yemeği', type: 'fb', quantity: 40, unit: 'pax', unit_price: 300 }], agenda: [], payment_schedule: [], totals: { space_total: 0, resources_total: 12000, grand_total: 12000 } };
let spaces = [{ id: 'demo-hall', name: 'Örnek Balo Salonu', location: 'Zemin kat', area_m2: 200, capacity_theatre: 120, capacity_banquet: 80, capacity_classroom: 60, hourly_rate: 1000, daily_rate: 6000, currency: 'TRY', active: true }];
const tasks = [];
window.__miceCalls = [];
axios.defaults.adapter = async config => {
  window.__miceCalls.push({ method: config.method, url: config.url, data: config.data });
  const body = config.data ? JSON.parse(config.data) : {};
  let data;
  if (config.url === '/subscription/current') data = { modules: { mice: true }, entitlements: { mice: { features: ['banquet_operations', 'proposals_contracts', 'advanced_reporting'], limits: { spaces_limit: 10, concurrent_events: 50 }, usage: { spaces_limit: spaces.length, concurrent_events: 0 } } } };
  else if (config.url === '/mice/events/quote-preview') data = { currency: 'TRY', totals: { space_total: 0, resources_total: 0, grand_total: 0 }, notice: 'Örnek sunucu hesap cevabı' };
  else if (config.url === '/mice/events') data = config.method === 'post' ? { ...body, id: 'new-event' } : { events: [event], summary: { lead: { count: 1, total_value_by_currency: { TRY: 12000 } } }, total_count: 1, counts: { spaces: spaces.length, accounts: 0, menus: 0, resources: 0 } };
  else if (config.url === '/mice/spaces' && config.method === 'post') { spaces.push({ ...body, id: 'new-hall' }); data = spaces.at(-1); }
  else if (config.url === '/mice/spaces') data = { spaces };
  else if (config.url.startsWith('/mice/spaces/')) { spaces = spaces.map(s => s.id === config.url.split('/').at(-1) ? { ...s, ...body } : s); data = { ok: true }; }
  else if (config.url === '/mice/accounts') data = { accounts: [] };
  else if (config.url === '/mice/menus') data = { menus: [] };
  else if (config.url === '/mice/resources') data = { resources: [] };
  else if (config.url === '/mice/diary') data = { events: [event] };
  else if (config.url === '/mice/events/demo-event/beo') data = { event, spaces: [], resources: event.resources, agenda: [], payment_schedule: [] };
  else if (config.url === '/mice/events/demo-event') data = event;
  else if (config.url === '/mice/events/demo-event/documents') data = { documents: [] };
  else if (config.url === '/mice/events/demo-event/tasks') {
    if (config.method === 'post') { tasks.push({ ...body, id: `task-${tasks.length}`, status: 'pending' }); data = tasks.at(-1); }
    else data = { tasks, equipment: [], event_status: 'definite', notice: 'Yalnız örnek görev verisi' };
  }
  else if (config.url.startsWith('/mice/events/demo-event/tasks/') && config.url.endsWith('/transition')) { const task = tasks.find(t => t.id === config.url.split('/').at(-2)); task.status = body.status; data = { ok: true }; }
  else if (config.url === '/mice/events/demo-event/actuals') data = { actuals: null, expected_revision: 'local-revision', currency: 'TRY', report: { quoted_net_revenue: 12000, actual_cost: null, quote_based_contribution: null } };
  else if (config.url === '/mice/public/beo/verify') data = { event: { ...event, status: 'definite' }, spaces: [], resources: event.resources, payment_schedule: [] };
  else if (config.url === '/mice/public/beo/sign') data = { success: true };
  else throw new Error(`Unmocked test endpoint: ${config.method} ${config.url}`);
  return { data, status: 200, statusText: 'OK', headers: {}, config };
};
const isPublic = new URLSearchParams(window.location.search).get('public') === '1';
createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={isPublic ? ['/public/mice/beo?token=synthetic-test-token'] : ['/app/mice']}>
  {isPublic ? <PublicMiceBeoPage /> : <EntitlementProvider currentTenantId="isolated-ui-test"><MicePage user={{ role: 'admin' }} tenant={{ id: 'isolated-ui-test' }} /></EntitlementProvider>}
  <Toaster />
</MemoryRouter>);
