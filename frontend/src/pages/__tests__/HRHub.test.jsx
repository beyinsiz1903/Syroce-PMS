import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import { toast } from 'sonner';
import HRHub from '@/pages/HRHub';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), isCancel: () => false } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/context/EntitlementContext', () => {
  const hasFeature = () => true;
  return { useEntitlements: () => ({ hasFeature }) };
});
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ promptDialog: vi.fn(async () => 'QA'), confirmDialog: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  axios.post.mockReset();
  axios.get.mockImplementation(async (url) => {
    if (url === '/hr/staff') return { data: { staff: [{ id: 'qa', name: 'QA Test Personeli' }], total: 1, total_pages: 1 } };
    if (url === '/hr/leave-requests') return { data: { items: [], total: 0, counts: { pending: 17, approved: 23, rejected: 11 } } };
    if (url === '/hr/leave-balance/qa') return { data: { annual: { entitlement: 19, carry_over: 0, used: 2, remaining: 17 } } };
    if (url === '/hr/overtime-requests') return { data: { items: [], counts: { pending: 9, approved: 0, rejected: 0 } } };
    return { data: { items: [], records: [], summary: [] } };
  });
});
afterEach(cleanup);

it.each([false, true])('submits overtime and preserves input on API failure: %s', async (fails) => {
  if (fails) axios.post.mockRejectedValue({ response: { data: { detail: 'Yetkiniz yok' } } });
  else axios.post.mockResolvedValue({ data: { success: true } });
  render(<MemoryRouter><HRHub /></MemoryRouter>);
  await userEvent.click(screen.getByRole('tab', { name: /Mesai Onayı/ }));
  await userEvent.selectOptions(screen.getByLabelText('Personel', { exact: true }), 'qa');
  fireEvent.change(screen.getByLabelText('Mesai Tarihi'), { target: { value: '2026-09-11' } });
  await userEvent.type(screen.getByLabelText('Mesai Süresi (saat)'), '1.5');
  await userEvent.type(screen.getByLabelText('Mesai Gerekçesi'), 'QA mesai testi');
  const previousLoads = axios.get.mock.calls.filter(([url]) => url === '/hr/overtime-requests').length;
  await userEvent.click(screen.getByRole('button', { name: 'Mesai Talebi Oluştur' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/hr/overtime-request', {
    staff_id: 'qa', work_date: '2026-09-11', hours: 1.5, reason: 'QA mesai testi',
  }));
  if (fails) {
    expect(toast.error).toHaveBeenCalledWith('Yetkiniz yok');
    expect(screen.getByLabelText('Mesai Gerekçesi')).toHaveValue('QA mesai testi');
  } else {
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Mesai talebi oluşturuldu'));
    expect(screen.getByLabelText('Mesai Gerekçesi')).toHaveValue('');
    expect(axios.get.mock.calls.filter(([url]) => url === '/hr/overtime-requests').length).toBeGreaterThan(previousLoads);
  }
});

it('renders staff balances and server leave counts in the routed HR screen', async () => {
  render(<MemoryRouter><HRHub /></MemoryRouter>);
  await userEvent.click(screen.getByRole('tab', { name: 'İzin', exact: true }));
  const staffRow = await screen.findByRole('row', { name: /QA Test Personeli/ });
  await waitFor(() => expect(within(staffRow).getByText('17 gün')).toBeInTheDocument());
  expect(screen.queryByText('Personel yok')).not.toBeInTheDocument();
  expect(screen.getByText('23')).toBeInTheDocument();
  expect(screen.getByText('11')).toBeInTheDocument();
});

it('loads overtime on entry and again on re-entry', async () => {
  render(<MemoryRouter><HRHub /></MemoryRouter>);
  await userEvent.click(screen.getByRole('tab', { name: 'Mesai Onayı' }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/hr/overtime-requests'));
  expect(within(screen.getByRole('tabpanel', { name: /Mesai Onayı/ })).getByText('9')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('tab', { name: 'İzin', exact: true }));
  await userEvent.click(screen.getByRole('tab', { name: /Mesai Onayı/ }));
  await waitFor(() => expect(axios.get.mock.calls.filter(([url]) => url === '/hr/overtime-requests')).toHaveLength(2));
  await userEvent.click(screen.getByTestId('btn-refresh-hr'));
  await waitFor(() => expect(axios.get.mock.calls.filter(([url]) => url === '/hr/overtime-requests')).toHaveLength(3));
});

it('loads saved payroll runs without requiring a new preview', async () => {
  render(<MemoryRouter><HRHub /></MemoryRouter>);
  await userEvent.click(screen.getByRole('tab', { name: 'Bordro', exact: true }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/hr/payroll/runs', { params: { month: expect.stringMatching(/^\d{4}-\d{2}$/) } }));
});

it.each([['Onayla', 'approve', 'active', 'Açık'], ['Reddet', 'reject', 'rejected', 'Reddedildi']])(
  'refreshes the actual routed job list before reporting %s success', async (button, action, status, label) => {
    let resolveRefresh;
    let decided = false;
    const originalGet = axios.get.getMockImplementation();
    const job = { id: 'job-qa', title: 'QA Pozisyon', status: 'pending_approval' };
    axios.get.mockImplementation((url, ...args) => {
      if (url !== '/hr/job-postings') return originalGet(url, ...args);
      if (!decided) return Promise.resolve({ data: { items: [job] } });
      return new Promise((resolve) => { resolveRefresh = resolve; });
    });
    axios.post.mockImplementation(async () => { decided = true; return { data: {} }; });
    render(<MemoryRouter><HRHub /></MemoryRouter>);
    await userEvent.click(screen.getByRole('tab', { name: 'Personel Talebi' }));
    const row = await screen.findByRole('row', { name: /QA Pozisyon/ });
    await userEvent.click(within(row).getByRole('button', { name: button, exact: true }));
    await waitFor(() => expect(resolveRefresh).toBeTypeOf('function'));
    expect(axios.post).toHaveBeenCalledWith(`/hr/job-posting/job-qa/${action}`, { note: 'QA' });
    expect(toast.success).not.toHaveBeenCalled();
    await act(async () => resolveRefresh({ data: { items: [{ ...job, status }] } }));
    expect(within(row).getByText(label)).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalled();
  }
);
