import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import tr from '../src/locales/tr.json';
import { Tabs } from '../src/components/ui/tabs';
import BookingsTab from '../src/components/pms/BookingsTab';
import '../src/index.css';

// Local, synthetic presentation fixture. No credentials or property API calls.
i18n.use(initReactI18next).init({ lng: 'tr', resources: { tr: { translation: tr } }, interpolation: { escapeValue: false } });
const bookings = [
  { id: 'far', guest_name: 'Ali Kılıç', check_in: '2042-09-27', check_out: '2042-09-29', room_id: '101', room_number: '101', currency: 'TRY', total_amount: 1200, status: 'confirmed' },
  { id: 'tomorrow', guest_name: 'Deniz Kaya', check_in: '2026-10-27', check_out: '2026-10-29', room_id: '102', room_number: '102', currency: 'EUR', total_amount: 500, status: 'confirmed' },
  { id: 'today', guest_name: 'Selin Demir', check_in: '2026-10-26', check_out: '2026-10-28', currency: 'USD', total_amount: 300, status: 'confirmed' },
];
const stats = { total: 484, confirmed: 43, checkedIn: 31, revenueByCurrency: { EUR: 10996, TRY: 13440337.96, USD: 10606 }, adrByCurrency: { EUR: 422.92, TRY: 31402.66, USD: 353.53 } };
createRoot(document.getElementById('root')).render(<MemoryRouter><main className="mx-auto max-w-[1600px] p-4 sm:p-6"><Tabs defaultValue="bookings"><BookingsTab bookings={bookings} bookingStats={stats} businessDate="2026-10-26" setOpenDialog={() => {}} setReservationDetailId={() => {}} /></Tabs></main></MemoryRouter>);
