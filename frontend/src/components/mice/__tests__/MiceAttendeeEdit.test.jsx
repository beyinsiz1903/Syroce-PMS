import { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import EventFormModal from '../modals/EventFormModal';

vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', formatCurrency: value => `${value} TRY` }));
afterEach(cleanup);

function Editor({ onSave }) {
  const [form, setForm] = useState({ name: 'Konuk Deneyimi', client_name: 'Sentetik Kurum',
    client_account_id: '', organizer_user: '', client_email: '', client_phone: '',
    event_type: 'meeting', status: 'tentative', expected_pax: 14, currency: 'TRY',
    reservation_id: '', start_date: '2026-11-12', end_date: '2026-11-12', notes: '',
    space_bookings: [
      { space_id: 'boardroom', setup_style: 'boardroom', expected_pax: 14, rate_snapshot: { hourly_rate: 1500 } },
      { space_id: 'breakout', setup_style: 'theatre', expected_pax: 6, rate_snapshot: { hourly_rate: 1000 } },
    ], resources: [], agenda: [], payment_schedule: [], pricing: null });
  const [eventTab, setEventTab] = useState('basics');
  return <EventFormModal editing={{ id: 'event' }} form={form} setForm={setForm}
    eventTab={eventTab} setEventTab={setEventTab} accounts={[]} accountById={{}} spaces={[]} menus={[]} resources={[]}
    psTotal={0} submit={event => { event.preventDefault(); onSave(form); }} onClose={() => {}} />;
}

it('sends edited event attendance to inherited halls for server capacity validation', () => {
  const save = vi.fn();
  render(<Editor onSave={save} />);
  fireEvent.change(screen.getByLabelText('Beklenen Pax'), { target: { value: '9999' } });
  fireEvent.click(screen.getByRole('button', { name: 'Güncelle', exact: true }));
  const payload = save.mock.calls[0][0];
  expect(payload.expected_pax).toBe(9999);
  expect(payload.space_bookings[0]).toMatchObject({ space_id: 'boardroom', expected_pax: 9999 });
  expect(payload.space_bookings[1]).toMatchObject({ space_id: 'breakout', expected_pax: 6 });
});

it('keeps inherited attendance linked across edits and preserves explicit breakout counts', () => {
  const save = vi.fn();
  render(<Editor onSave={save} />);
  fireEvent.change(screen.getByLabelText('Beklenen Pax'), { target: { value: '20' } });
  fireEvent.change(screen.getByLabelText('Beklenen Pax'), { target: { value: '14' } });
  fireEvent.click(screen.getByRole('button', { name: 'Güncelle', exact: true }));
  expect(save.mock.calls[0][0].space_bookings).toEqual([
    { space_id: 'boardroom', setup_style: 'boardroom', expected_pax: 14, rate_snapshot: { hourly_rate: 1500 } },
    { space_id: 'breakout', setup_style: 'theatre', expected_pax: 6, rate_snapshot: { hourly_rate: 1000 } },
  ]);
});
