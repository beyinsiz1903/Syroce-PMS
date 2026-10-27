import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import axios from 'axios';
import tr from '../src/locales/tr.json';
import ReservationDetailModal from '../src/pages/ReservationDetailModal';
import Guest360Dialog from '../src/components/pms/Guest360Dialog';
import MessagingDashboard from '../src/pages/MessagingDashboard';
import '../src/index.css';

// Synthetic local-only fixture: all API reads are in-memory, all writes fail.
// Never authenticate or use a real property/guest in presentation acceptance.
i18n.use(initReactI18next).init({ lng: 'tr', resources: { tr: { translation: tr } }, interpolation: { escapeValue: false } });
const guest = { id: 'synthetic-guest', name: 'Deniz Kaya', email: 'deniz@example.com' };
const booking = { id: 'synthetic-booking', guest_id: guest.id, guest_name: guest.name, check_in: '2026-10-21', check_out: '2026-10-26', room_id: 'synthetic-room', room_number: '104', currency: 'USD', total_amount: 560, status: 'checked_in', adults: 2, children: 0, channel: 'direct', hotel_name: 'Örnek Otel', cancellation_policy: { free_until_days_before: 7, penalty_pct: 50, no_show_penalty_pct: 100 } };
const folios = [{ id: 'g', folio_type: 'guest', currency: 'USD', status: 'open', balance: 638.8, folio_number: 'F-2026-00299' }, { id: 'a', payor_type: 'agency', currency: 'USD', status: 'open', balance: 9900, folio_number: 'F-2026-00300' }];
const charges = [
  ...[21, 22, 23, 24, 25].map(day => ({ id: `room-${day}`, folio_id: 'g', description: `Konaklama · ${day} Ekim`, charge_type: 'room', amount: 112, total: 112, currency: 'USD', business_date: `2026-10-${day}`, created_at: '2026-10-27T08:52:00Z' })),
  { id: 'food', folio_id: 'g', description: 'Akşam yemeği', category: 'food', total: 12, currency: 'USD', service_date: '2026-10-24', service_time: '19:30', created_at: '2026-10-26T08:50:00Z' },
  { id: 'drink', folio_id: 'g', description: 'İçecek servisi', category: 'beverage', total: 4.4, currency: 'USD', service_date: '2026-10-24', service_time: '19:35' },
  { id: 'old', folio_id: 'g', description: 'Eski spa kaydı', category: 'spa', total: 22, currency: 'USD', created_at: '2026-10-24T12:00:00Z' },
  { id: 'spa', folio_id: 'g', description: 'Aromaterapi masajı · 60 dk', category: 'spa', total: 30, currency: 'USD', service_date: '2026-10-25', service_time: '14:30', service_timing_source: 'spa_appointment' },
  { id: 'minibar', folio_id: 'g', description: 'Minibar tüketimi', category: 'minibar', total: 10.4, currency: 'USD', service_date: '2026-10-25' },
  { id: 'agency-room', folio_id: 'a', description: 'Gizli acente bedeli', category: 'room', total: 9900, currency: 'USD' },
];
if (new URLSearchParams(window.location.search).has('long')) {
  charges.push(...Array.from({ length: 100 }, (_, index) => ({ id: `long-${index}`, folio_id: 'g', category: 'food', description: `Yapay yemek kalemi ${String(index + 1).padStart(3, '0')}`, total: 1, currency: 'USD', service_date: '2026-10-24', service_time: '19:30' })));
}
const detail = { booking, guest, room: { id: booking.room_id, room_number: '104', room_type: 'Standard' }, guests: [guest], folios, charges, payments: [], extra_charges: [], notes: [], history: [], deposits: [], communication_logs: [], room_moves: [], daily_rates: [], business_date: '2026-10-26', summary: { total_amount: 560, accommodation_total: 560, total_charges: 10538.8, balance: 10538.8, reservation_total_due: 10538.8, additional_charge_total: 9978.8, gross_total: 10538.8, total_payments: 0 } };
axios.get = async url => ({ data: url.includes('/full-detail') ? detail : url.startsWith('/folio-windows/booking/') ? folios.map((f, index) => ({ ...f, folio_id: f.id, window_number: index + 1, charges_count: charges.filter(c => c.folio_id === f.id).length, payments_count: 0 })) : url === '/messaging-center/settings' ? { email: { enabled: false, is_sandbox: false, credentials: {} } } : url.startsWith('/crm/guest/') ? { guest } : url === '/exchange-rates' ? { rates: { USD: 40, EUR: 50, TRY: 1 } } : {} });
axios.post = axios.put = axios.patch = axios.delete = async () => { throw new Error('LOCAL_FIXTURE_WRITES_FORBIDDEN'); };

function Workspace() {
  const [profile, setProfile] = useState(false);
  return <main className="p-4"><h1 className="text-lg font-semibold">Örnek Otel · Yapay misafir kartı kabulü</h1><button className="m-3 rounded border p-2" onClick={() => setProfile(true)}>Misafir profilini aç</button>{profile ? <Guest360Dialog open onClose={() => setProfile(false)} selectedGuest360={guest.id} guest360Data={{ guest, profile: { loyalty_status: 'standard', loyalty_points: 250 }, stats: { currency: 'USD', total_stays: 2, total_nights: 5, lifetime_value_by_currency: { USD: 638.8, EUR: 500 }, average_adr_by_currency: { USD: 112, EUR: 250 } }, stay_history: [booking] }} /> : <ReservationDetailModal bookingId={booking.id} onClose={() => setProfile(true)} allBookings={[booking]} />}</main>;
}
createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={['/app/pms']}><Routes><Route path="/messaging-dashboard" element={<MessagingDashboard />} /><Route path="*" element={<Workspace />} /></Routes></MemoryRouter>);
