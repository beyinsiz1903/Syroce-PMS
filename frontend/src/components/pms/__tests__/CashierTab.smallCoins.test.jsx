import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback || key }) }));
vi.mock('@/lib/currency', () => ({ formatCurrency: value => `${value ?? 0} TRY` }));
import CashierTab from '../CashierTab';

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  get.mockImplementation(async path => ({ data: path === '/cashier/current-shift'
    ? { shift: { id: 's', status: 'open', opening_amount: 38089.51 }, transactions: [] }
    : path.includes('shift-history') ? { shifts: [] } : [] }));
});

it('counts the observed 38089.51 TRY exactly with whole banknotes and coins', async () => {
  render(<CashierTab />);
  fireEvent.click(await screen.findByRole('button', { name: 'cm.components_pms_CashierTab.vardiya_kapat', exact: true }));
  const dialog = screen.getByRole('dialog');
  for (const [label, value] of [['200 TL', 190], ['50 TL', 1], ['20 TL', 1], ['10 TL', 1], ['5 TL', 1], ['1 TL', 4], ['50 Krş', 1], ['1 Krş', 1]]) {
    fireEvent.change(within(dialog).getByLabelText(label, { exact: true }), { target: { value: String(value) } });
  }
  expect(within(dialog).getAllByText('38089.51 TRY')).toHaveLength(2);
  expect(within(dialog).getByText('0 TRY')).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});

it('includes 10, 5 and 1 kuruş in the same integer-cent calculation', async () => {
  render(<CashierTab />);
  fireEvent.click(await screen.findByRole('button', { name: 'cm.components_pms_CashierTab.vardiya_kapat', exact: true }));
  const dialog = screen.getByRole('dialog');
  for (const label of ['10 Krş', '5 Krş', '1 Krş']) {
    const input = within(dialog).getByLabelText(label);
    expect(input).toHaveAttribute('step', '1');
    fireEvent.change(input, { target: { value: '1' } });
  }
  expect(within(dialog).getByText('0.16 TRY')).toBeInTheDocument();
  const input = within(dialog).getByLabelText('1 Krş');
  fireEvent.change(input, { target: { value: '-1' } });
  expect(input).toHaveValue(0);
  expect(within(dialog).getByText('0.15 TRY')).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});
