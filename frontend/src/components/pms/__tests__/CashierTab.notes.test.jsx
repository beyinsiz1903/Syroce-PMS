import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const { get, toast } = vi.hoisted(() => ({ get: vi.fn(), toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback || key }) }));
vi.mock('@/lib/currency', () => ({ formatCurrency: value => `${value ?? 0} TRY` }));
import CashierTab from '@/components/pms/CashierTab';

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
});
