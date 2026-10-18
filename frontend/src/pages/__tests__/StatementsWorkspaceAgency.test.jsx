import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { toastSuccess } = vi.hoisted(() => ({ toastSuccess: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: vi.fn() } }));

import StatementsWorkspace from '@/components/statements/StatementsWorkspace';

const line = { booking_id: 'b1', confirmation_code: 'MKT-1', check_in: '2026-11-21', guest_name: 'Test', status: 'confirmed', payment_terms: 'on_arrival', gross: 8000, commission: 1200, hotel_owes_agency: 1200, agency_owes_hotel: 0 };
const base = '/marketplace/v1/statements';

function renderAgency(api) {
  return render(<StatementsWorkspace side="agency" api={api} base={base} partiesPath={`${base}/hotels`} />);
}

describe('StatementsWorkspace (agency side)', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('lets the agency issue its commission statement for a hotel', async () => {
    const api = {
      get: vi.fn(url => Promise.resolve({ data: url.endsWith('/hotels') ? { hotels: [{ tenant_id: 't1', name: 'Demo Otel', currency: 'TRY' }] } : { items: [] } })),
      post: vi.fn((url, body) => Promise.resolve({ data: url.endsWith('/preview')
        ? { hotel_name: 'Demo Otel', period_start: body.period_start, period_end: body.period_end, currency: 'TRY', lines: [line], totals: { net_balance: -1200 }, outstanding: -1200, signature: 'sig' }
        : { number: 'EKS-2026-0009' } })),
    };
    renderAgency(api);
    await userEvent.selectOptions(await screen.findByLabelText('Otel'), 't1');
    await userEvent.click(screen.getByText('Ekstreyi önizle'));
    expect(await screen.findByText('Otel ödeyecek: 1.200,00 TRY', { exact: false })).toBeTruthy();
    expect(api.post).toHaveBeenCalledWith(`${base}/preview`, expect.objectContaining({ tenant_id: 't1' }));
    await userEvent.click(screen.getByText('Otele gönder'));
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith(base, expect.objectContaining({ tenant_id: 't1', expected_signature: 'sig' })));
    expect(toastSuccess).toHaveBeenCalledWith('EKS-2026-0009 düzenlendi ve otele iletildi.');
  });

  it('marks a supplementary statement in the preview and in the list', async () => {
    const supplement = { id: 's9', number: 'EKS-2026-0009', hotel_name: 'Demo Otel', status: 'issued', issuer: 'agency', revision: 1,
      agreements: { hotel: null, agency: 1 }, period_start: '2026-11-01', period_end: '2026-11-30', currency: 'TRY',
      lines: [line], totals: { net_balance: -1200 }, outstanding: -1200, payments: [], payment_notices: [], supplement_of: ['EKS-2026-0001'] };
    const api = {
      get: vi.fn(url => Promise.resolve({ data: url.endsWith('/hotels') ? { hotels: [{ tenant_id: 't1', name: 'Demo Otel', currency: 'TRY' }] } : url === base ? { items: [supplement] } : supplement })),
      post: vi.fn((url, body) => Promise.resolve({ data: { hotel_name: 'Demo Otel', period_start: body.period_start, period_end: body.period_end, currency: 'TRY',
        lines: [line], totals: { net_balance: -1200 }, outstanding: -1200, signature: 'sig', supplement_of: ['EKS-2026-0001'] } })),
    };
    renderAgency(api);
    expect(await screen.findByTestId('supplement-EKS-2026-0009')).toHaveTextContent('Ek ekstre (EKS-2026-0001)');
    await userEvent.selectOptions(await screen.findByLabelText('Otel'), 't1');
    await userEvent.click(screen.getByText('Ekstreyi önizle'));
    expect(await screen.findByTestId('statement-preview-supplement')).toHaveTextContent('EKS-2026-0001');
  });

  it('asks to recalculate only when the corrections really differ from the preview', async () => {
    const api = {
      get: vi.fn(url => Promise.resolve({ data: url.endsWith('/hotels') ? { hotels: [{ tenant_id: 't1', name: 'Demo Otel', currency: 'TRY' }] } : { items: [] } })),
      post: vi.fn((url, body) => Promise.resolve({ data: { hotel_name: 'Demo Otel', period_start: body.period_start, period_end: body.period_end, currency: 'TRY',
        lines: [line], totals: { net_balance: -1200 }, outstanding: -1200, signature: 'sig' } })),
    };
    renderAgency(api);
    await userEvent.selectOptions(await screen.findByLabelText('Otel'), 't1');
    await userEvent.click(screen.getByText('Ekstreyi önizle'));
    const box = await screen.findByLabelText(`${line.confirmation_code} satırını düzelt`);
    const send = () => screen.getByRole('button', { name: 'Otele gönder' });
    const warning = () => screen.queryByText('Düzeltmeler değişti; göndermeden önce yeniden hesaplayın.');

    await userEvent.click(box);                               // opened, nothing typed
    expect(warning()).toBeNull();
    await userEvent.click(box);                               // and closed again: the reported case
    expect(warning()).toBeNull();
    expect(send()).not.toBeDisabled();

    await userEvent.click(box);
    await userEvent.type(screen.getByLabelText('Düzeltme tutarı'), '-100');
    expect(warning()).not.toBeNull();                         // a real change: recalculate first
    expect(send()).toBeDisabled();
    await userEvent.clear(screen.getByLabelText('Düzeltme tutarı'));
    expect(warning()).toBeNull();                             // undone: same as the preview
  });

  it('verifies the commission payment the hotel reported, and offers "Ödeme alındı" instead of reporting', async () => {
    const statement = { id: 's1', number: 'EKS-2026-0009', hotel_name: 'Demo Otel', period_start: '2026-11-01', period_end: '2026-11-30', currency: 'TRY',
      status: 'agreed', issuer: 'agency', revision: 1, agreements: { hotel: 1, agency: 1 }, outstanding: -1200, lines: [line], payments: [],
      payment_notices: [{ id: 'n1', amount: 1200, paid_at: '2026-12-01', reference: 'EFT-9', direction: 'hotel_to_agency', status: 'pending', has_proof: true }] };
    const api = {
      get: vi.fn(url => Promise.resolve({ data: url.endsWith('/hotels') ? { hotels: [] } : url === base ? { items: [statement] } : statement })),
      post: vi.fn(() => Promise.resolve({ data: { ...statement, status: 'settled', outstanding: 0, payment_notices: [{ ...statement.payment_notices[0], status: 'verified' }] } })),
    };
    renderAgency(api);
    expect(await screen.findByText('1 ödeme bildirimi')).toBeTruthy();
    await userEvent.click(screen.getByText('EKS-2026-0009 · Demo Otel'));
    expect(await screen.findByTestId('record-payment-form')).toBeTruthy(); // the agency is owed: it records, it does not report
    expect(screen.queryByTestId('report-payment-form')).toBeNull();
    await userEvent.click(screen.getByText('Doğrula'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`${base}/s1/payment-notices/n1/verify`, { note: '' }));
  });

  it('asks the agency to agree to a hotel-issued statement with the revision it sees', async () => {
    const statement = { id: 's2', number: 'EKS-2026-0010', hotel_name: 'Demo Otel', period_start: '2026-11-01', period_end: '2026-11-30', currency: 'TRY',
      status: 'issued', issuer: 'hotel', revision: 3, agreements: { hotel: 3, agency: null }, outstanding: 5600, lines: [line], payments: [], payment_notices: [] };
    const api = {
      get: vi.fn(url => Promise.resolve({ data: url.endsWith('/hotels') ? { hotels: [] } : url === base ? { items: [statement] } : statement })),
      post: vi.fn(() => Promise.resolve({ data: { ...statement, status: 'agreed', agreements: { hotel: 3, agency: 3 } } })),
    };
    renderAgency(api);
    expect(await screen.findByText('Onayınız bekleniyor')).toBeTruthy();
    await userEvent.click(screen.getByText('EKS-2026-0010 · Demo Otel'));
    expect(await screen.findByText('İtiraz et')).toBeTruthy();
    await userEvent.click(screen.getByText('Mutabıkız'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`${base}/s2/agree`, { revision: 3 }));
  });
});
