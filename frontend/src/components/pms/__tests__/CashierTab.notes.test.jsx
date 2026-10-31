import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const { get, toast } = vi.hoisted(() => ({ get: vi.fn(), toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback || key }) }));
vi.mock('@/lib/currency', () => ({ formatCurrency: value => `${value ?? 0} TRY` }));
import CashierTab from '@/components/pms/CashierTab';
afterEach(cleanup);

describe('Cashier Z report closing explanation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockImplementation(async path => ({ data: path === '/cashier/current-shift' ? { shift: null } : path.startsWith('/cashier/shift-history') ? { shifts: [{ id: 'closed-qa', status: 'closed' }] } : path.startsWith('/cashier/z-report/') ? { report_type: 'Z', status: 'closed', closing_amount: 50, closing_notes: 'QA <script>explanation</script>', by_method: {}, by_type: {} } : [] }));
  });
  it('renders the saved note as text, without executing HTML, in the printable report', async () => {
    render(<CashierTab />);
    fireEvent.click(await screen.findByRole('button', { name: /Z-Rapor/ }));
    const note = await screen.findByTestId('cashier-closing-notes');
    expect(note).toHaveTextContent('QA <script>explanation</script>');
    expect(note.querySelector('script')).toBeNull();
    expect(note.closest('#cashier-report')).not.toBeNull();
    await waitFor(() => expect(get).toHaveBeenCalledWith('/cashier/z-report/closed-qa'));
  });
  it('explains that the current login password is required, not a separate numeric PIN', async () => {
    render(<CashierTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'cm.components_pms_CashierTab.vardiya_ac_4889c', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: 'cm.components_pms_CashierTab.vardiyayi_ac', exact: true }));
    expect(screen.getByText(/Ayrı bir kasa PIN’i yoktur/)).toBeInTheDocument();
    const password = screen.getByLabelText('Mevcut kullanıcının giriş şifresi');
    expect(password).toHaveAttribute('type', 'password');
    expect(password).toHaveAttribute('inputmode', 'text');
    expect(screen.getByRole('button', { name: 'Doğrula', exact: true })).toBeDisabled();
  });
  it('keeps keyboard focus while counting and does not confuse business day with opening time', async () => {
    get.mockImplementation(async path => ({ data: path === '/cashier/current-shift' ? { shift: { id: 's', status: 'open', business_date: '2026-10-26', opened_at: '2026-10-31T16:00:00', opening_amount: 0, cash_in: 100, cash_out: 40 }, transactions: [] } : path.includes('shift-history') ? { shifts: [] } : [] }));
    render(<CashierTab />);
    expect(await screen.findByText('Vardiyanın iş günü: 2026-10-26')).toBeInTheDocument();
    expect(screen.queryByText(/tarihinden beri açık/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'cm.components_pms_CashierTab.vardiya_kapat', exact: true }));
    const input = screen.getByLabelText('50 TL');
    input.focus(); fireEvent.change(input, { target: { value: '1' } });
    expect(document.activeElement).toBe(input);
    expect(input).toHaveValue(1);
    fireEvent.change(input, { target: { value: '12' } });
    expect(document.activeElement).toBe(input);
    expect(input).toHaveValue(12);
  });
});
