import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import ExtranetFinanceDirectory from '../ExtranetFinanceDirectory';

const amounts = (currency, agency, hotel) => ({ currency,
  receivables: { agency_owes_hotel: agency, hotel_owes_agency: hotel, pending_notices: { count: 1 } },
  unbilled: { agency_owes_hotel: 0, hotel_owes_agency: 0 }, forward: { 90: { bookings: 2, gross: 16000 } },
});
const partner = { id: 'a1', name: 'Test Acente E2E', contact_email: 'agent@example.com', approved: true,
  currencies: [amounts('TRY', 6800, 300), amounts('EUR', 0, 150)] };
const statement = { id: 's1', agency_id: 'a1', agency_name: partner.name, number: 'EKS-1',
  period_start: '2026-11-01', period_end: '2026-11-30', currency: 'TRY', status: 'agreed', outstanding: 6800,
  lines: [], payments: [], agreements: { agency: 1, hotel: 1 } };

beforeEach(() => {
  get.mockImplementation(url => {
    if (url === '/agent-arap/extranet-agencies') return Promise.resolve({ data: { agencies: [partner] } });
    if (url.endsWith('/agencies')) return Promise.resolve({ data: { agencies: [{ id: 'a1', name: partner.name }, { id: 'a2', name: 'Other partner' }] } });
    if (url.endsWith('/s1')) return Promise.resolve({ data: statement });
    return Promise.resolve({ data: { items: [statement, { ...statement, id: 's2', agency_id: 'a2', agency_name: 'Other partner', number: 'EKS-OTHER' }] } });
  });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe('Extranet finance directory', () => {
  it('lists the real global agency without a local card and keeps currencies/directions separate', async () => {
    render(<ExtranetFinanceDirectory />);
    const card = await screen.findByTestId('extranet-finance-a1');
    expect(card).toHaveTextContent('Test Acente E2E');
    expect(card).toHaveTextContent('6.800,00 TRY');
    expect(card).toHaveTextContent('300,00 TRY');
    expect(card).toHaveTextContent('150,00 EUR');
    expect(card).not.toHaveTextContent('6.500,00');
    expect(card).toHaveTextContent('Gelecek 90 gün · satış tutarı, bakiye değil');
    expect(card).toHaveTextContent('Doğrulanana kadar bakiyeden düşülmez.');
    expect(post).not.toHaveBeenCalled();
  });

  it('shows a newly approved partner with no sales and does not manufacture a TRY balance', async () => {
    get.mockResolvedValue({ data: { agencies: [{ ...partner, currencies: [] }] } });
    render(<ExtranetFinanceDirectory />);
    const card = await screen.findByTestId('extranet-finance-a1');
    expect(card).toHaveTextContent('Henüz satış veya ekstre kaydı yok.');
    expect(card).not.toHaveTextContent('0,00 TRY');
  });

  it('uses only the selected agency and the canonical statements, never the old payment endpoint', async () => {
    const changed = vi.fn();
    render(<ExtranetFinanceDirectory onChanged={changed} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Mutabakat ve ödeme' }));
    expect(await screen.findByText('EKS-1 · Test Acente E2E')).toBeTruthy();
    expect(screen.queryByText('EKS-OTHER · Other partner')).toBeNull();
    expect(get).toHaveBeenCalledWith('/marketplace/hotel/statements', { params: { agency_id: 'a1' } });
    expect(screen.getByLabelText('Acente')).toHaveValue('a1');
    expect(screen.getByLabelText('Acente')).toBeDisabled();
    // Mixed currencies: do not assume TRY for a newly issued statement.
    expect(screen.getByLabelText('Para birimi')).toHaveValue('');
    await userEvent.click(screen.getByText('EKS-1 · Test Acente E2E'));
    await userEvent.type(await screen.findByLabelText('Alınan tutar'), '6800');
    await userEvent.type(screen.getByLabelText('Alınan ödeme referansı'), 'EFT-TEST-1');
    post.mockResolvedValue({ data: { ...statement, outstanding: 0, status: 'settled' } });
    get.mockImplementation(url => {
      if (url === '/agent-arap/extranet-agencies') return Promise.resolve({ data: { agencies: [{ ...partner, currencies: [amounts('TRY', 0, 300)] }] } });
      if (url.endsWith('/agencies')) return Promise.resolve({ data: { agencies: [{ id: 'a1', name: partner.name }] } });
      return Promise.resolve({ data: { items: [{ ...statement, outstanding: 0, status: 'settled' }] } });
    });
    await userEvent.click(screen.getByRole('button', { name: 'Ödeme kaydet' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/marketplace/hotel/statements/s1/payments', expect.objectContaining({ amount: 6800, direction: 'agency_to_hotel', reference: 'EFT-TEST-1' })));
    await waitFor(() => expect(get.mock.calls.filter(([url]) => url === '/agent-arap/extranet-agencies')).toHaveLength(2));
    // Refresh does not destroy the open statement/dialog on a successful save.
    expect(await screen.findByRole('dialog')).toHaveTextContent('Bakiye yok');
    expect(post.mock.calls.some(([url]) => url === '/agent-arap/payment')).toBe(false);
    expect(changed).toHaveBeenCalledOnce();
  });

  it('filters using the same list search and displays a load failure instead of zero money', async () => {
    const { rerender } = render(<ExtranetFinanceDirectory searchTerm="no match" />);
    expect(await screen.findByText(/Bu tesis ve arama için Extranet acentesi yok/)).toBeTruthy();
    rerender(<ExtranetFinanceDirectory searchTerm="E2E" />);
    expect(screen.getByTestId('extranet-finance-a1')).toBeTruthy();
    get.mockRejectedValue({ response: { data: { detail: 'Yetki yok' } } });
    fireEvent.click(screen.getByRole('button', { name: 'Extranet bakiyelerini yenile' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Yetki yok');
    expect(screen.queryByTestId('extranet-finance-a1')).toBeNull();
  });

  it('does not accept an unrelated malformed response as an empty directory', async () => {
    get.mockResolvedValue({ data: { detail: 'maintenance' } });
    render(<ExtranetFinanceDirectory />);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.queryByText(/Bu tesis ve arama için Extranet acentesi yok/)).toBeNull();
  });

  it('distinguishes closed financial history from a partner that never had a statement', async () => {
    get.mockResolvedValue({ data: { agencies: [{ ...partner, approved: false, has_financial_history: true, currencies: [] }] } });
    render(<ExtranetFinanceDirectory />);
    expect(await screen.findByText(/Finans geçmişi var; açık bakiye veya gelecek rezervasyon bulunmuyor/)).toBeTruthy();
    expect(screen.queryByText(/Henüz satış veya ekstre kaydı yok/)).toBeNull();
  });
});
