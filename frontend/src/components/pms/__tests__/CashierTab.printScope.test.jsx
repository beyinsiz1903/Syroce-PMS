import { cleanup, fireEvent, render, screen, waitFor, within, act } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('axios', () => ({ default: { get } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback || key }) }));
vi.mock('@/lib/currency', () => ({ formatCurrency: value => `${value ?? 0} TRY` }));
import CashierTab from '../CashierTab';

const period = (start = '2026-10-26', end = start) => ({ start_date: start, end_date: end,
  generated_at: '2026-10-31T17:15:00', generated_by: 'Selected cashier', totals: { cash_in_total: 100,
    cash_out_total: 40, closing_total: 60, difference_total: 0, transaction_count: 2, shift_count: 1 },
  by_method: { cash: { in: 100, out: 40, net: 60, count: 2 } }, shifts: [] });

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async path => ({ data: path === '/cashier/current-shift' ? { shift: null }
    : path.startsWith('/cashier/shift-history') ? { shifts: [{ id: 'selected', status: 'closed', cashier_name: 'Other private history', closing_amount: 99999 }] }
      : path.startsWith('/cashier/z-report/') ? { report_type: 'Z', cashier_name: 'Selected cashier', status: 'closed', closing_amount: 60,
        opened_at: '2026-10-31T16:34:00', closed_at: '2026-10-31T16:45:00', generated_at: '2026-10-31T17:15:00',
        closing_notes: 'Selected <script>note</script>', transaction_count: 2, by_method: {}, by_type: {} }
        : path === '/cashier/period-report' ? period() : [] }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('marks only the selected portalled Z document for printing, never the history or app shell', async () => {
  const print = vi.spyOn(window, 'print').mockImplementation(() => {});
  render(<CashierTab />);
  fireEvent.click(await screen.findByRole('button', { name: 'Z-Rapor', exact: true }));
  const report = await screen.findByRole('dialog', { name: 'Z-Raporu (Kapanış)' });
  expect(report).toHaveAttribute('data-cashier-print-document', 'shift');
  expect(report.parentElement).toBe(document.body);
  expect(document.querySelectorAll('[data-cashier-print-document]')).toHaveLength(1);
  expect(report).not.toHaveTextContent('Other private history');
  expect(report).not.toHaveTextContent('99999');
  expect(report).toHaveTextContent('31.10.2026 19:34');
  expect(report).toHaveTextContent('31.10.2026 19:45');
  expect(report).toHaveTextContent('Selected <script>note</script>');
  expect(report.querySelector('script')).toBeNull();
  fireEvent.click(within(report).getByRole('button', { name: 'cm.components_pms_CashierTab.yazdir', exact: true }));
  expect(print).toHaveBeenCalledTimes(1);
  fireEvent.click(within(report).getByRole('button', { name: 'cm.components_pms_CashierTab.kapat', exact: true }));
  await waitFor(() => expect(document.querySelector('[data-cashier-print-document]')).toBeNull());
});

async function openPeriod() {
  render(<CashierTab />);
  fireEvent.click(screen.getByRole('button', { name: 'cm.components_pms_CashierTab.donem_raporu', exact: true }));
  const dialog = await screen.findByRole('dialog');
  const inputs = dialog.querySelectorAll('input[type="date"]');
  fireEvent.change(inputs[0], { target: { value: '2026-10-26' } });
  fireEvent.change(inputs[1], { target: { value: '2026-10-26' } });
  return { dialog, inputs };
}

it('prints only an authoritative period result and removes its print marker on close', async () => {
  const { dialog } = await openPeriod();
  expect(dialog).not.toHaveAttribute('data-cashier-print-document');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Getir', exact: true }));
  await screen.findByRole('button', { name: 'CSV', exact: true });
  expect(dialog).toHaveAttribute('data-cashier-print-document', 'period');
  expect(dialog.parentElement).toBe(document.body);
  expect(dialog).toHaveTextContent('2026-10-26 → 2026-10-26');
  expect(dialog).toHaveTextContent('31.10.2026 20:15');
  expect(dialog).not.toHaveTextContent('Other private history');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Kapat', exact: true }));
  await waitFor(() => expect(document.querySelector('[data-cashier-print-document]')).toBeNull());
});

it('invalidates print and CSV immediately when the selected period changes', async () => {
  const { dialog, inputs } = await openPeriod();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Getir', exact: true }));
  await screen.findByRole('button', { name: 'CSV', exact: true });
  fireEvent.change(inputs[0], { target: { value: '2026-10-25' } });
  expect(screen.queryByRole('button', { name: 'CSV', exact: true })).toBeNull();
  expect(dialog).not.toHaveAttribute('data-cashier-print-document');
  expect(dialog).not.toHaveTextContent('2026-10-26 → 2026-10-26');
});

it('does not retain an old printable/CSV result when a refresh fails', async () => {
  const { dialog } = await openPeriod();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Getir', exact: true }));
  await screen.findByRole('button', { name: 'CSV', exact: true });
  get.mockImplementation(async path => { if (path === '/cashier/period-report') throw new Error('offline'); return { data: [] }; });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Getir', exact: true }));
  expect(screen.queryByRole('button', { name: 'CSV', exact: true })).toBeNull();
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Dönem raporu yüklenemedi');
  expect(dialog).not.toHaveAttribute('data-cashier-print-document');
});

it('ignores a late result from a previous range and accepts only the newer query', async () => {
  const { dialog, inputs } = await openPeriod();
  let resolveOld;
  let resolveNew;
  const oldRequest = new Promise(resolve => { resolveOld = resolve; });
  const newRequest = new Promise(resolve => { resolveNew = resolve; });
  get.mockImplementation(path => path === '/cashier/period-report' ? oldRequest : Promise.resolve({ data: [] }));
  fireEvent.click(within(dialog).getByRole('button', { name: 'Getir', exact: true }));
  fireEvent.change(inputs[0], { target: { value: '2026-10-25' } });
  get.mockImplementation(path => path === '/cashier/period-report' ? newRequest : Promise.resolve({ data: [] }));
  fireEvent.click(within(dialog).getByRole('button', { name: 'Getir', exact: true }));
  await act(async () => { resolveNew({ data: period('2026-10-25', '2026-10-26') }); });
  expect(dialog).toHaveTextContent('2026-10-25 → 2026-10-26');
  await act(async () => { resolveOld({ data: period() }); });
  expect(dialog).toHaveTextContent('2026-10-25 → 2026-10-26');
  expect(dialog).not.toHaveTextContent('2026-10-26 → 2026-10-26');
});

it('does not revive a result after closing and reopening the period dialog', async () => {
  const { dialog } = await openPeriod();
  let resolveRequest;
  get.mockImplementation(() => new Promise(resolve => { resolveRequest = resolve; }));
  fireEvent.click(within(dialog).getByRole('button', { name: 'Getir', exact: true }));
  fireEvent.click(within(dialog).getByRole('button', { name: 'Kapat', exact: true }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await act(async () => { resolveRequest({ data: period() }); });
  fireEvent.click(screen.getByRole('button', { name: 'cm.components_pms_CashierTab.donem_raporu', exact: true }));
  expect(screen.queryByRole('button', { name: 'CSV', exact: true })).toBeNull();
  expect(screen.getByRole('dialog')).not.toHaveAttribute('data-cashier-print-document');
});
