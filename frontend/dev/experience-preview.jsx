// Local-only visual QA. No production API request or real guest data is used.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { ThemeProvider } from 'next-themes';
import axios from 'axios';
import api from '../src/api/axios';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import tr from '../src/locales/tr.json';
import en from '../src/locales/en.json';
import '../src/index.css';
import '../src/App.css';
import { EntitlementProvider } from '../src/context/EntitlementContext';
import Layout from '../src/components/Layout';
import PMSModule from '../src/pages/PMSModule';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
const previewQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
import { SimulationProvider } from '../src/context/SimulationContext';
import RoleStart from '../src/components/experience/RoleStart';
import DashboardWelcome from '../src/components/experience/DashboardWelcome';
import ApplicationCenter from '../src/pages/ApplicationCenter';
import CRMWorkspace from '../src/pages/CRMWorkspace';
import HousekeepingRoomGrid from '../src/components/pms/HousekeepingRoomGrid';
import ShiftHandoverPage from '../src/pages/ShiftHandoverPage';
import BookingDialog from '../src/components/pms/BookingDialog';
import { PRODUCT_MODULES } from '../src/lib/moduleCatalog';
import { Button } from '../src/components/ui/button';

const tenant = { id: 'visual-qa', property_name: 'Örnek Otel · Yerel önizleme', modules: Object.fromEntries(PRODUCT_MODULES.map(item => [item.key, true])) };
const user = { id: 'visual-operator', name: 'Örnek yönetici', role: 'super_admin', tenant_id: tenant.id };
const rooms = [{ id: 'r1', room_number: '101', room_type: 'Standart', status: 'available', housekeeping_status: 'dirty' }, { id: 'r2', room_number: '102', room_type: 'Deluxe', status: 'available', housekeeping_status: 'cleaning' }];
const adapter = async config => {
  const path = config.url || '';
  let data = {};
  if (path.includes('subscription/current')) data = { modules: tenant.modules };
  if (path.includes('business-date')) data = { business_date: '2026-10-09' };
  if (path.includes('staff-tasks')) data = { tasks: [{ id: 't1', title: 'Giriş öncesi oda kontrolü', status: 'pending', priority: 'high', assigned_to: 'Örnek çalışan' }], total: 1 };
  if (path.includes('shift-handover')) data = { items: [{ id: 'h1', business_date: '2026-10-09', shift: 'morning', to_shift: 'night', note: 'Geç giriş yapacak misafirin oda hazırlığını takip edin.', priority: 'normal', acknowledged: false, created_at: '2026-10-09T09:00:00Z' }], total: 1 };
  if (path.includes('operational-alerts')) data = { alerts: [], summary: {} };
  if (path.includes('housekeeping/rooms')) data = { rooms, summary: { dirty: 1, cleaning: 1 } };
  if (path.includes('guests/search')) data = [{ id: 'g1', name: 'Örnek Misafir' }];
  if (path.includes('/crm/guest/')) data = { guest: { name: 'Örnek Misafir', email: 'example@example.test', tags: ['Sessiz oda'] }, stay_history: [{ id: 'stay1', check_in: '2026-10-01', check_out: '2026-10-03', status: 'checked_out', room_number: '101' }] };
  if (path.includes('data-intelligence')) data = { guests_analyzed: 30, high_churn_guests: [{ guest_id: 'g1', name: 'Örnek Misafir', churn_score: 0.55, next_action: 'Son konaklama deneyimini değerlendirin.' }], top_value_guests: [], upsell_opportunities: [] };
  if (path.includes('frontdesk/search-bookings')) data = { bookings: [{ id: 'b1', guest_name: 'Örnek Misafir', booking_number: 'R-100', check_in: '2026-10-09', check_out: '2026-10-11', room_number: '101' }] };
  if (path.startsWith('/pms/rooms?')) data = rooms;
  if (path.startsWith('/pms/bookings?') || path.startsWith('/pms/guests?') || path.startsWith('/companies?')) data = [];
  if (path.startsWith('/frontdesk/')) data = [];
  return { data, status: 200, statusText: 'OK', headers: {}, config };
};

function Preview() {
  const location = useLocation(); const navigate = useNavigate();
  const [bookingOpen, setBookingOpen] = useState(false);
  const [draft, setDraft] = useState({ check_in: '2026-10-09', check_out: '2026-10-11', currency: 'TRY', adults: 2, children: 0, company_id: '', channel: 'direct' });
  const [lines, setLines] = useState([{ id: 'line1', room_id: '', adults: 2, children: 0, base_rate: 1500, total_amount: 3000 }]);
  const update = (index, key, value) => setLines(current => current.map((line, i) => i === index ? { ...line, [key]: value } : line));
  const props = { user, tenant, onLogout: () => {} };
  if (location.pathname === "/app/pms") return <PMSModule {...props} />;
  return <Layout {...props}><div className="border-b bg-blue-50 p-3 text-sm text-blue-950">Yerel tasarım kontrolü · örnek kayıtlar · canlı sisteme bağlı değildir.<div className="mt-2 flex flex-wrap gap-2">{[['/app/dashboard', 'Başlangıç'], ['/app/pms', 'Ön büro önizlemesi'], ['/app/applications', 'Uygulamalar'], ['/crm', 'CRM'], ['/housekeeping-status', 'Kat hizmetleri'], ['/shift-handover', 'Vardiya devri']].map(([path, label]) => <Button key={path} size="sm" variant="outline" onClick={() => navigate(path)}>{label}</Button>)}<Button size="sm" onClick={() => setBookingOpen(true)}>Rezervasyon formu</Button></div></div>
    {location.pathname === '/app/applications' ? <ApplicationCenter {...props} /> : location.pathname === '/crm' ? <CRMWorkspace {...props} /> : location.pathname === '/housekeeping-status' ? <HousekeepingRoomGrid /> : location.pathname === '/shift-handover' ? <ShiftHandoverPage {...props} /> : <div className="p-6"><DashboardWelcome {...props} /><RoleStart {...props} /></div>}
    <BookingDialog open={bookingOpen} onClose={() => setBookingOpen(false)} guests={[]} rooms={rooms} companies={[]} ratePlans={[]} packages={[]} newBooking={draft} setNewBooking={setDraft} multiRoomBooking={lines} updateMultiRoomField={update} addRoomToMultiBooking={() => setLines(current => [...current, { ...current[0], id: String(current.length) }])} removeRoomFromMultiBooking={index => setLines(current => current.filter((_, i) => i !== index))} updateMultiRoomChildrenAges={(index, value) => update(index, 'children', value)} updateMultiRoomChildAge={() => {}} handleChildrenChange={() => {}} handleChildAgeChange={() => {}} handleCompanySelect={() => {}} handleContractedRateSelect={() => {}} handleCreateBooking={event => { event.preventDefault(); setBookingOpen(false); }} setOpenDialog={() => {}} />
  </Layout>;
}

if (import.meta.env.DEV) {
  axios.defaults.adapter = adapter; api.defaults.adapter = adapter;
  await i18n.use(initReactI18next).init({ lng: 'tr', fallbackLng: 'en', resources: { tr: { translation: tr }, en: { translation: en } }, interpolation: { escapeValue: false } });
  createRoot(document.getElementById('root')).render(<ThemeProvider attribute="class"><MemoryRouter initialEntries={['/app/dashboard']}><EntitlementProvider currentTenantId={tenant.id} isSuperAdmin><SimulationProvider><QueryClientProvider client={previewQueryClient}><Preview /></QueryClientProvider></SimulationProvider></EntitlementProvider></MemoryRouter></ThemeProvider>);
}
