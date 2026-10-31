import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback || key }) }));
vi.mock('@/lib/currency', () => ({ formatCurrency: value => `${value ?? 0} TRY` }));
import CashierTab from '../CashierTab';
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
beforeEach(() => { get.mockReset(); });

it('converts naive UTC opening, closing and report generation to explicitly labelled Türkiye time', async () => {
  const row = { id: 'closed', status: 'closed', opened_at: '2026-10-31T16:34:54.123456', closed_at: '2026-10-31T16:45:10' };
  get.mockImplementation(async path => ({ data: path === '/cashier/current-shift' ? { shift: null } : path.startsWith('/cashier/shift-history') ? { shifts: [row] } : { ...row, report_type: 'Z', generated_at: '2026-10-31T17:15:00Z', by_method: {}, by_type: {} } }));
  render(<CashierTab />);
  fireEvent.click(await screen.findByRole('button', { name: /Z-Rapor/ }));
  const dialog = await screen.findByRole('dialog');
  expect(dialog).toHaveTextContent('31.10.2026 19:34');
  expect(dialog).toHaveTextContent('31.10.2026 19:45');
  expect(dialog).toHaveTextContent('31.10.2026 20:15');
  expect(dialog).toHaveTextContent('Türkiye saati · Europe/Istanbul');
  expect(dialog.querySelector('#cashier-report')).toHaveTextContent('Türkiye saati · Europe/Istanbul');
  expect(dialog).not.toHaveTextContent('2026-10-31 16:34');
});

it('shows the correct date at midnight in shift history and the active transaction clock', async () => {
  const row = { id: 'open', status: 'open', business_date: '2026-10-26', opened_at: '2026-10-31T22:10:00Z', opening_amount: 0 };
  get.mockImplementation(async path => ({ data: path === '/cashier/current-shift' ? { shift: row, transactions: [{ id: 't', type: 'manual_cash_in', method: 'cash', direction: 'in', amount: 1, created_at: '2026-10-31T22:15:00Z' }] } : path.startsWith('/cashier/shift-history') ? { shifts: [{ ...row, id: 'closed', status: 'closed', closed_at: '2026-11-01T02:05:00+03:00' }] } : [] }));
  render(<CashierTab />);
  expect((await screen.findAllByText(/01\.11\.2026 01:10/)).length).toBeGreaterThan(0);
  expect(screen.getByText(/01\.11\.2026 02:05/)).toBeInTheDocument();
  expect(screen.getByText('01:15')).toBeInTheDocument();
  expect(screen.getByText('Vardiyanın iş günü: 2026-10-26')).toBeInTheDocument();
});

function captureDownload() {
  const createObjectURL = vi.fn(() => 'blob:local-cashier-test');
  const OriginalURL = URL;
  vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = createObjectURL; static revokeObjectURL = vi.fn(); });
  vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  return async () => {
    const reader = new FileReader();
    const loaded = new Promise(resolve => { reader.onload = () => resolve(reader.result); });
    reader.readAsText(createObjectURL.mock.calls[0][0]);
    return loaded;
  };
}

it('exports transaction instants in the same labelled timezone as the screen', async () => {
  const download = captureDownload();
  get.mockImplementation(async path => ({ data: path === '/cashier/current-shift' ? { shift: { id: 's', status: 'open', opening_amount: 0 }, transactions: [{ id: 't', method: 'cash', direction: 'in', amount: 1, created_at: '2026-10-31T16:34:54' }] } : { shifts: [] } }));
  render(<CashierTab />);
  fireEvent.click(await screen.findByRole('button', { name: 'CSV', exact: true }));
  const csv = await download();
  expect(csv).toContain('Türkiye saati · Europe/Istanbul');
  expect(csv).toContain('31.10.2026 19:34:54');
  expect(csv).not.toContain('2026-10-31 16:34');
});

it('exports and prints period generation time without converting the business-day range', async () => {
  const download = captureDownload();
  get.mockImplementation(async path => ({ data: path === '/cashier/current-shift' ? { shift: null } : path.startsWith('/cashier/shift-history') ? { shifts: [] } : { start_date: '2026-10-26', end_date: '2026-10-26', generated_at: '2026-10-31T17:15:00', totals: {}, shifts: [] } }));
  render(<CashierTab />);
  fireEvent.click(screen.getByRole('button', { name: 'cm.components_pms_CashierTab.donem_raporu', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Getir', exact: true }));
  const csvButton = await screen.findByRole('button', { name: 'CSV', exact: true });
  expect(document.getElementById('period-report')).toHaveTextContent('31.10.2026 20:15');
  expect(document.getElementById('period-report')).toHaveTextContent('2026-10-26 → 2026-10-26');
  fireEvent.click(csvButton);
  const csv = await download();
  expect(csv).toContain('Türkiye saati · Europe/Istanbul');
  expect(csv).toContain('31.10.2026 20:15:00');
  expect(csv).toContain('2026-10-26 - 2026-10-26');
});
